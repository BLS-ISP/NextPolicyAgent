"""Top-down Rego evaluation engine.

Implements a top-down evaluation strategy with:
- Complete Rego expression evaluation
- Multi-layer caching (intra-query + inter-query)
- Backtracking with undo support
- With-modifier support
- Partial evaluation (partial queries & partial objects)
- Comprehension indexing
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from npa.ast import builtins as bi
from npa.ast.compiler import Compiler, RuleTreeNode
from npa.ast.types import (
    Body,
    Call,
    Expr,
    Every,
    Module,
    Ref,
    Rule,
    RuleKind,
    Term,
    TermKind,
    With,
)
from npa.eval.cache import CacheKey, CacheMiss, InterQueryCache, IntraQueryCache
from npa.storage.base import NotFoundError
from npa.eval.unify import Bindings, match_pattern, unify


class EvalError(Exception):
    """Raised on unrecoverable evaluation errors."""


class UndefinedError(EvalError):
    """Result is undefined (not an error, just no matching rules)."""


@dataclass
class EvalContext:
    """Holds all state for one evaluation run."""
    compiler: Compiler
    store: Any  # Storage interface
    input_data: Any = None
    intra_cache: IntraQueryCache = field(default_factory=IntraQueryCache)
    inter_cache: InterQueryCache | None = None
    depth: int = 0
    max_depth: int = 1000
    with_stack: list[dict[str, Any]] = field(default_factory=list)
    trace_enabled: bool = False
    traces: list[str] = field(default_factory=list)
    cancel: bool = False
    current_package: list[str] = field(default_factory=list)
    current_rule: Any = None  # Rule being evaluated (for rego.metadata.rule)
    metadata_chain: list[dict] = field(default_factory=list)  # for rego.metadata.chain

    def child(self) -> EvalContext:
        """Create a child context with incremented depth."""
        if self.depth >= self.max_depth:
            raise EvalError(f"Maximum evaluation depth exceeded ({self.max_depth})")
        return EvalContext(
            compiler=self.compiler,
            store=self.store,
            input_data=self.input_data,
            intra_cache=self.intra_cache,
            inter_cache=self.inter_cache,
            depth=self.depth + 1,
            max_depth=self.max_depth,
            with_stack=list(self.with_stack),
            trace_enabled=self.trace_enabled,
            traces=self.traces,
            cancel=self.cancel,
            current_package=list(self.current_package),
            current_rule=self.current_rule,
            metadata_chain=list(self.metadata_chain),
        )


class TopdownEvaluator:
    """Main evaluation engine implementing Rego's top-down evaluation.

    Usage:
        compiler = Compiler()
        compiler.compile([module1, module2])
        evaluator = TopdownEvaluator(compiler, store)
        result = evaluator.eval_query("data.example.allow", input_data={"user": "admin"})
    """

    def __init__(
        self,
        compiler: Compiler,
        store: Any,
        inter_cache: InterQueryCache | None = None,
    ) -> None:
        self.compiler = compiler
        self.store = store
        self.inter_cache = inter_cache or InterQueryCache()

    def eval_query(
        self,
        query: str,
        input_data: Any = None,
        *,
        trace: bool = False,
    ) -> Any:
        """Evaluate a query string against compiled policies and data.

        Args:
            query: Dot-separated reference path (e.g., "data.example.allow")
            input_data: The input document
            trace: Enable evaluation tracing

        Returns:
            The result value, or raises UndefinedError if undefined.
        """
        ctx = EvalContext(
            compiler=self.compiler,
            store=self.store,
            input_data=input_data,
            inter_cache=self.inter_cache,
            trace_enabled=trace,
        )
        path = query.split(".")
        if path[0] == "data":
            return self._eval_ref(ctx, path[1:], Bindings())
        if path[0] == "input":
            return _lookup_path(input_data, path[1:])
        raise EvalError(f"Unknown root: {path[0]}")

    def eval_rule(
        self,
        rule: Rule,
        ctx: EvalContext,
        bindings: Bindings,
    ) -> Any:
        """Evaluate a single rule, returning its value if the body is satisfied."""
        if ctx.cancel:
            raise EvalError("Evaluation cancelled")

        child_ctx = ctx.child()

        # Inject metadata context for rego.metadata.rule/chain builtins
        child_ctx.current_rule = rule
        if rule.annotations:
            ann = rule.annotations
            meta = {}
            if ann.title:
                meta["title"] = ann.title
            if ann.description:
                meta["description"] = ann.description
            if ann.scope:
                meta["scope"] = ann.scope
            if ann.entrypoint:
                meta["entrypoint"] = True
            if ann.custom:
                meta["custom"] = ann.custom
            child_ctx.metadata_chain = ctx.metadata_chain + [meta]
        else:
            child_ctx.metadata_chain = list(ctx.metadata_chain)

        # Evaluate body
        if rule.body:
            if not self._eval_body(child_ctx, rule.body, bindings):
                raise UndefinedError()

        # Evaluate rule head value
        if rule.head.value is not None:
            return self._eval_term(child_ctx, rule.head.value, bindings)

        # Boolean rules (no value specified) return True
        if rule.kind in (RuleKind.COMPLETE, RuleKind.DEFAULT, RuleKind.FUNCTION):
            return True

        raise UndefinedError()

    def _eval_ref(self, ctx: EvalContext, path: list[str], bindings: Bindings) -> Any:
        """Evaluate a data reference by walking the rule tree and store."""
        if not path:
            effective_store = ctx.store if ctx.store is not None else self.store
            return effective_store.read([])

        # Check cache first
        cache_key = CacheKey.build("/".join(path), "", ctx.input_data)
        try:
            return ctx.intra_cache.get(cache_key)
        except CacheMiss:
            pass

        if ctx.inter_cache:
            try:
                result = ctx.inter_cache.get(cache_key)
                ctx.intra_cache.put(cache_key, result)
                return result
            except CacheMiss:
                pass

        # Try rules first
        result = self._eval_rules_for_ref(ctx, path, bindings)
        if result is not _UNDEFINED:
            ctx.intra_cache.put(cache_key, result)
            if ctx.inter_cache:
                ctx.inter_cache.put(cache_key, result)
            return result

        # Fall through to store (use ctx.store which may be an overlay)
        effective_store = ctx.store if ctx.store is not None else self.store
        try:
            value = effective_store.read(path)
            ctx.intra_cache.put(cache_key, value)
            return value
        except (KeyError, IndexError, NotFoundError):
            raise UndefinedError(f"Undefined: data.{'.'.join(path)}")

    def _eval_rules_for_ref(
        self, ctx: EvalContext, path: list[str], bindings: Bindings
    ) -> Any:
        """Find and evaluate rules matching the given reference path."""
        # Use indexed lookup when available for fast filtering
        if hasattr(self.compiler, 'get_indexed_rules'):
            rules = self.compiler.get_indexed_rules(path, ctx.input_data)
        else:
            rules = self.compiler.get_rules(path)
        if not rules:
            return _UNDEFINED

        # Set current package context (all but last segment is the package)
        if len(path) > 1:
            ctx.current_package = path[:-1]

        # Group by rule kind
        complete_rules: list[Rule] = []
        default_rules: list[Rule] = []
        partial_obj_rules: list[Rule] = []
        partial_set_rules: list[Rule] = []

        for rule in rules:
            if rule.kind == RuleKind.DEFAULT:
                default_rules.append(rule)
            elif rule.kind == RuleKind.COMPLETE:
                complete_rules.append(rule)
            elif rule.kind == RuleKind.PARTIAL_SET:
                partial_set_rules.append(rule)
            elif rule.kind == RuleKind.PARTIAL_OBJECT:
                partial_obj_rules.append(rule)
            elif rule.kind == RuleKind.FUNCTION:
                complete_rules.append(rule)

        # Complete rules: first matching rule wins (with else chain)
        if complete_rules:
            for rule in complete_rules:
                try:
                    return self.eval_rule(rule, ctx, bindings.copy())
                except UndefinedError:
                    # Try else chain
                    for else_rule in rule.else_rules:
                        try:
                            return self.eval_rule(else_rule, ctx, bindings.copy())
                        except UndefinedError:
                            continue
                    continue

        # Partial set rules: collect all values into a set
        if partial_set_rules:
            result_set: set[Any] = set()
            for rule in partial_set_rules:
                try:
                    val = self.eval_rule(rule, ctx, bindings.copy())
                    if isinstance(val, (int, float, str, bool)) or val is None:
                        result_set.add(val)
                    else:
                        result_set.add(_make_hashable(val))
                except UndefinedError:
                    continue
            if result_set:
                return result_set

        # Partial object rules: collect all key-value pairs
        if partial_obj_rules:
            result_obj: dict[str, Any] = {}
            for rule in partial_obj_rules:
                try:
                    child_bindings = bindings.copy()
                    val = self.eval_rule(rule, ctx, child_bindings)
                    if rule.head.key is not None:
                        key = self._eval_term(ctx, rule.head.key, child_bindings)
                        result_obj[key] = val
                except UndefinedError:
                    continue
            if result_obj:
                return result_obj

        # Default rules: only used as fallback after all other rules fail
        if default_rules:
            for rule in default_rules:
                try:
                    return self.eval_rule(rule, ctx, bindings.copy())
                except UndefinedError:
                    continue

        return _UNDEFINED

    def _eval_body(self, ctx: EvalContext, body: Body, bindings: Bindings) -> bool:
        """Evaluate a rule body — all expressions must be satisfied.

        Uses _iter_body for proper backtracking over 'some x in coll' bindings.
        """
        for solution in self._iter_body(ctx, body, bindings):
            # Any successful solution makes the body true
            # Copy final bindings back
            for var, val in solution._values.items():
                if not bindings.is_bound(var):
                    bindings.bind(var, val)
            return True
        return False

    def _eval_expr(self, ctx: EvalContext, expr: Expr, bindings: Bindings) -> bool:
        """Evaluate a single expression."""
        # Apply with modifiers
        if expr.with_modifiers:
            return self._eval_with_modifiers(ctx, expr, bindings)

        result = self._eval_terms(ctx, expr.terms, bindings)

        if expr.negated:
            return not _is_truthy(result)
        return _is_truthy(result)

    def _eval_with_modifiers(
        self, ctx: EvalContext, expr: Expr, bindings: Bindings
    ) -> bool:
        """Evaluate an expression with 'with' modifiers applied.

        Supports both ``with input.x as v`` and ``with data.x as v``.
        For data overrides the store is temporarily wrapped so that
        reads on the overridden paths return the mock values.
        """
        saved_input = ctx.input_data
        saved_store = ctx.store
        data_overrides: dict[str, Any] = {}

        try:
            for with_mod in expr.with_modifiers:
                # Extract target path directly from the Ref — do NOT
                # evaluate it as a data lookup (that would fail if the
                # path doesn't exist yet, which is exactly the case we
                # want to override).
                target_path = self._with_target_path(with_mod.target)
                value = self._eval_term(ctx, with_mod.value, bindings)

                if target_path.startswith("input"):
                    parts = target_path.split(".")[1:]
                    ctx.input_data = _set_path(
                        copy.deepcopy(ctx.input_data) if ctx.input_data else {},
                        parts,
                        value,
                    )
                elif target_path.startswith("data"):
                    parts = target_path.split(".")[1:]
                    data_overrides[".".join(parts)] = (parts, value)

            # If we have data overrides, wrap the store
            if data_overrides:
                ctx.store = _OverlayStore(saved_store, data_overrides)

            # Also invalidate intra-cache for affected paths so the
            # evaluator doesn't return stale cached rule results.
            saved_cache = ctx.intra_cache
            if data_overrides:
                ctx.intra_cache = IntraQueryCache()

            try:
                # Evaluate without with modifiers
                expr_copy = Expr(
                    terms=expr.terms,
                    negated=expr.negated,
                    with_modifiers=(),
                    location=expr.location,
                )
                return self._eval_expr(ctx, expr_copy, bindings)
            finally:
                if data_overrides:
                    ctx.intra_cache = saved_cache
        finally:
            ctx.input_data = saved_input
            ctx.store = saved_store

    @staticmethod
    def _with_target_path(target: Term) -> str:
        """Extract a dotted path string from a ``with`` target ref.

        The target is always a simple ref like ``input.x.y`` or
        ``data.a.b`` — we just need the path string, NOT the value.
        """
        if target.kind == TermKind.REF:
            ref: Ref = target.value
            parts = []
            for p in ref.terms:
                if isinstance(p, Term):
                    parts.append(str(p.value))
                else:
                    parts.append(str(p))
            return ".".join(parts)
        if target.kind == TermKind.VAR:
            return str(target.value)
        return str(target.value)

    def _eval_terms(self, ctx: EvalContext, terms: Any, bindings: Bindings) -> Any:
        """Evaluate terms in an expression."""
        if isinstance(terms, Term):
            return self._eval_term(ctx, terms, bindings)

        if isinstance(terms, list):
            if not terms:
                return True
            # Binary/unary operations or function calls
            if len(terms) == 1:
                return self._eval_term(ctx, terms[0], bindings)

            # Check if this is an assignment/unification: x := expr or x = expr
            if len(terms) == 3:
                op = terms[1]
                if isinstance(op, Term) and op.kind == TermKind.VAR:
                    op_name = op.value
                    if op_name in ("assign", "eq", "unify"):
                        lhs = self._eval_term(ctx, terms[0], bindings)
                        rhs = self._eval_term(ctx, terms[2], bindings)
                        return unify(lhs, rhs, bindings)

            # Function call: [func_ref, arg1, arg2, ..., output]
            first = terms[0]
            if isinstance(first, Term) and first.kind == TermKind.REF:
                func_name = ".".join(str(p) for p in first.value)
                builtin = bi.get_builtin(func_name)
                if builtin:
                    args = [self._eval_term(ctx, t, bindings) for t in terms[1:]]
                    return builtin(*args)

            # Evaluate all terms and return last
            results = [self._eval_term(ctx, t, bindings) for t in terms]
            return results[-1]

        return terms

    def _eval_term(self, ctx: EvalContext, term: Term, bindings: Bindings) -> Any:
        """Evaluate a single AST term to a Python value."""
        kind = term.kind

        if kind == TermKind.NULL:
            return None
        if kind == TermKind.BOOLEAN:
            return term.value
        if kind == TermKind.NUMBER:
            return term.value
        if kind == TermKind.STRING:
            return term.value

        if kind == TermKind.VAR:
            var_name = term.value
            # Check bindings first
            if bindings.is_bound(var_name):
                return bindings.lookup(var_name)
            # Special variables
            if var_name == "input":
                return ctx.input_data
            if var_name == "data":
                return self.store.read([])
            # Unbound variable — return as variable reference
            return f"${var_name}"

        if kind == TermKind.REF:
            return self._eval_ref_term(ctx, term, bindings)

        if kind == TermKind.ARRAY:
            return [self._eval_term(ctx, elem, bindings) for elem in term.value]

        if kind == TermKind.OBJECT:
            return {
                self._eval_term(ctx, k, bindings): self._eval_term(ctx, v, bindings)
                for k, v in term.value
            }

        if kind == TermKind.SET:
            return frozenset(
                _make_hashable(self._eval_term(ctx, elem, bindings))
                for elem in term.value
            )

        if kind == TermKind.CALL:
            return self._eval_call(ctx, term, bindings)

        if kind in (
            TermKind.ARRAY_COMPREHENSION,
            TermKind.SET_COMPREHENSION,
            TermKind.OBJECT_COMPREHENSION,
        ):
            return self._eval_comprehension(ctx, term, bindings)

        if kind == TermKind.EVERY:
            return self._eval_every(ctx, term, bindings)

        raise EvalError(f"Unsupported term kind: {kind}")

    def _eval_ref_term(self, ctx: EvalContext, term: Term, bindings: Bindings) -> Any:
        """Evaluate a reference term like data.foo.bar or input.x."""
        ref: Ref = term.value
        parts = ref.terms
        if not parts:
            raise EvalError("Empty reference")

        # Resolve first part
        head = parts[0]
        if isinstance(head, Term):
            head_val = self._eval_term(ctx, head, bindings)
        else:
            head_val = head

        # Resolve root
        if head_val == "data" or head_val == "$data":
            path = []
            for p in parts[1:]:
                if isinstance(p, Term):
                    path.append(str(self._eval_term(ctx, p, bindings)))
                else:
                    path.append(str(p))
            return self._eval_ref(ctx, path, bindings)

        if head_val == "input" or head_val == "$input":
            current = ctx.input_data
            for p in parts[1:]:
                if isinstance(p, Term):
                    key = self._eval_term(ctx, p, bindings)
                else:
                    key = p
                current = _index_into(current, key)
            return current

        # Variable reference with path
        current = head_val
        if isinstance(current, str) and current.startswith("$"):
            var_name = current[1:]
            if bindings.is_bound(var_name):
                current = bindings.lookup(var_name)
            else:
                raise UndefinedError(f"Unbound variable: {var_name}")

        for p in parts[1:]:
            if isinstance(p, Term):
                key = self._eval_term(ctx, p, bindings)
            else:
                key = p
            current = _index_into(current, key)

        return current

    def _eval_call(self, ctx: EvalContext, term: Term, bindings: Bindings) -> Any:
        """Evaluate a function call (builtin or user-defined)."""
        call = term.value
        # Build function name from operator ref
        func_parts = call.operator.as_path()
        func_name = ".".join(func_parts)

        # --- Context-sensitive builtins ---
        if func_name == "rego.metadata.rule":
            if ctx.current_rule and hasattr(ctx.current_rule, 'annotations') and ctx.current_rule.annotations:
                ann = ctx.current_rule.annotations
                meta: dict[str, Any] = {}
                if ann.title:
                    meta["title"] = ann.title
                if ann.description:
                    meta["description"] = ann.description
                if ann.scope:
                    meta["scope"] = ann.scope
                if ann.entrypoint:
                    meta["entrypoint"] = True
                if ann.custom:
                    meta["custom"] = ann.custom
                return meta
            return {}

        if func_name == "rego.metadata.chain":
            return list(ctx.metadata_chain)

        # --- Unification (=) — can bind variables ---
        if func_name == "=":
            lhs = self._eval_term(ctx, call.args[0], bindings)
            rhs = self._eval_term(ctx, call.args[1], bindings)
            return unify(lhs, rhs, bindings)

        # --- Assignment (:=) — bind lhs to rhs value ---
        if func_name == ":=":
            rhs = self._eval_term(ctx, call.args[1], bindings)
            lhs_term = call.args[0]
            if lhs_term.kind == TermKind.VAR:
                bindings.bind(lhs_term.value, rhs)
                return True
            lhs = self._eval_term(ctx, lhs_term, bindings)
            return lhs == rhs

        args = [self._eval_term(ctx, arg, bindings) for arg in call.args]

        # Infix operators mapped to builtins
        _INFIX_MAP = {
            "==": "equal", "!=": "neq",
            "<": "lt", "<=": "lte", ">": "gt", ">=": "gte",
            "+": "plus", "-": "minus", "*": "mul", "/": "div", "%": "rem",
            "&": "and", "|": "or",
        }
        resolved_name = _INFIX_MAP.get(func_name, func_name)

        # Try built-in
        builtin = bi.get_builtin(resolved_name)
        if builtin:
            return builtin(*args)

        # Try user-defined function — look up in rule tree
        # For e.g. func_name = "data.pkg.my_func" or just "my_func"
        if func_parts and func_parts[0] == "data":
            rule_path = func_parts[1:]
        else:
            # Lookup using package-relative path
            rule_path = func_parts

        func_rules = self.compiler.get_rules(rule_path)
        # If not found directly, try with current package prefix
        if not func_rules and ctx.current_package:
            func_rules = self.compiler.get_rules(ctx.current_package + func_parts)
        for rule in func_rules:
            if rule.kind == RuleKind.FUNCTION and len(rule.head.args) == len(args):
                child_bindings = bindings.copy()
                # Bind function arguments
                for param_term, arg_val in zip(rule.head.args, args):
                    if param_term.kind == TermKind.VAR:
                        child_bindings.bind(param_term.value, arg_val)
                try:
                    return self.eval_rule(rule, ctx.child(), child_bindings)
                except UndefinedError:
                    continue

        raise EvalError(f"Unknown function: {func_name}")

    def _eval_comprehension(
        self, ctx: EvalContext, term: Term, bindings: Bindings
    ) -> Any:
        """Evaluate array/set/object comprehensions."""
        comp = term.value
        child_ctx = ctx.child()

        if term.kind == TermKind.ARRAY_COMPREHENSION:
            results: list[Any] = []
            for solution in self._iter_body(child_ctx, comp.body, bindings.copy()):
                val = self._eval_term(child_ctx, comp.term, solution)
                results.append(val)
            return results

        if term.kind == TermKind.SET_COMPREHENSION:
            result_set: set[Any] = set()
            for solution in self._iter_body(child_ctx, comp.body, bindings.copy()):
                val = self._eval_term(child_ctx, comp.term, solution)
                result_set.add(_make_hashable(val))
            return frozenset(result_set)

        if term.kind == TermKind.OBJECT_COMPREHENSION:
            result_obj: dict[Any, Any] = {}
            for solution in self._iter_body(child_ctx, comp.body, bindings.copy()):
                key = self._eval_term(child_ctx, comp.key, solution)
                val = self._eval_term(child_ctx, comp.value, solution)
                result_obj[key] = val
            return result_obj

        raise EvalError(f"Unknown comprehension type: {term.kind}")

    def _eval_every(self, ctx: EvalContext, term: Term, bindings: Bindings) -> bool:
        """Evaluate 'every x in domain { body }' — true iff body holds for all elements."""
        every: Every = term.value
        domain = self._eval_term(ctx, every.domain, bindings)

        items: list[tuple[Any, Any]]
        if isinstance(domain, dict):
            items = list(domain.items())
        elif isinstance(domain, (list, tuple)):
            items = list(enumerate(domain))
        elif isinstance(domain, (set, frozenset)):
            items = [(v, v) for v in domain]
        else:
            return True  # vacuously true for non-iterable

        for key, val in items:
            child = bindings.copy()
            if every.key and every.key.kind == TermKind.VAR:
                child.bind(every.key.value, key)
            if every.value and every.value.kind == TermKind.VAR:
                child.bind(every.value.value, val)
            if not self._eval_body(ctx.child(), every.body, child):
                return False
        return True

    def _iter_body(
        self, ctx: EvalContext, body: Body, bindings: Bindings
    ):
        """Iterate over all satisfying bindings for a body.

        Yields Bindings for each solution. Implements backtracking:
        for each expression in the body, try all possible assignments.
        """
        if not body.exprs:
            yield bindings
            return

        first_expr = body.exprs[0]
        rest = Body(exprs=body.exprs[1:])

        # Detect internal.member_2 / internal.member_3 calls (from "some x in coll")
        member_call = self._detect_member_call(first_expr)
        if member_call is not None:
            kind, var_terms, coll_term = member_call
            collection = self._eval_term(ctx, coll_term, bindings)
            if kind == 2:
                # some x in coll -> iterate values
                items = self._iter_collection_values(collection)
                var = var_terms[0]
                for val in items:
                    child = bindings.copy()
                    if var.kind == TermKind.VAR and not bindings.is_bound(var.value):
                        child.bind(var.value, val)
                    elif self._eval_term(ctx, var, bindings) != val:
                        continue
                    yield from self._iter_body(ctx, rest, child)
            elif kind == 3:
                # some k, v in coll -> iterate key-value pairs
                items = self._iter_collection_kv(collection)
                key_var, val_var = var_terms
                for k, v in items:
                    child = bindings.copy()
                    if key_var.kind == TermKind.VAR and not bindings.is_bound(key_var.value):
                        child.bind(key_var.value, k)
                    elif self._eval_term(ctx, key_var, bindings) != k:
                        continue
                    if val_var.kind == TermKind.VAR and not bindings.is_bound(val_var.value):
                        child.bind(val_var.value, v)
                    elif self._eval_term(ctx, val_var, bindings) != v:
                        continue
                    yield from self._iter_body(ctx, rest, child)
            return

        # Standard expression evaluation
        bindings.save()
        try:
            if self._eval_expr(ctx, first_expr, bindings):
                bindings.commit()
                yield from self._iter_body(ctx, rest, bindings)
            else:
                bindings.restore()
        except (UndefinedError, EvalError):
            bindings.restore()

    def _detect_member_call(self, expr: Expr) -> tuple[int, list[Term], Term] | None:
        """Detect if expr is an internal.member_2/3 call. Returns (arity, var_terms, coll_term) or None."""
        terms = expr.terms
        if not isinstance(terms, Term) or terms.kind != TermKind.CALL:
            return None
        call = terms.value
        func_parts = call.operator.as_path()
        func_name = ".".join(func_parts)
        if func_name == "internal.member_2" and len(call.args) == 2:
            return (2, [call.args[0]], call.args[1])
        if func_name == "internal.member_3" and len(call.args) == 3:
            return (3, [call.args[0], call.args[1]], call.args[2])
        return None

    @staticmethod
    def _iter_collection_values(collection: Any):
        """Yield all values from a collection."""
        if isinstance(collection, dict):
            yield from collection.values()
        elif isinstance(collection, (list, tuple)):
            yield from collection
        elif isinstance(collection, (set, frozenset)):
            yield from collection
        else:
            yield collection

    @staticmethod
    def _iter_collection_kv(collection: Any):
        """Yield (key, value) pairs from a collection."""
        if isinstance(collection, dict):
            yield from collection.items()
        elif isinstance(collection, (list, tuple)):
            for i, v in enumerate(collection):
                yield i, v
        elif isinstance(collection, (set, frozenset)):
            for v in collection:
                yield v, v


# ===========================================================================
# Overlay store for ``with data.x as v``
# ===========================================================================


class _OverlayStore:
    """Thin wrapper around a real store that intercepts reads on overridden paths.

    Used by ``_eval_with_modifiers`` to provide temporary data overrides
    without mutating the underlying store.
    """

    def __init__(self, base: Any, overrides: dict[str, tuple[list[str], Any]]) -> None:
        self._base = base
        # overrides: { "pkg.rule": ([pkg, rule], value), ... }
        self._overrides = overrides

    def read(self, path: list[str]) -> Any:
        # Check if any override matches the requested path (or is a prefix)
        req = ".".join(path)
        for key, (opath, oval) in self._overrides.items():
            if path == opath:
                return oval
            # If the requested path is a sub-path of an override
            if len(path) > len(opath) and path[: len(opath)] == opath:
                remainder = path[len(opath):]
                current = oval
                for seg in remainder:
                    current = _index_into(current, seg)
                return current
            # If the requested path is a parent of an override, merge
            if len(path) < len(opath) and opath[: len(path)] == path:
                try:
                    base_val = copy.deepcopy(self._base.read(path))
                except Exception:
                    base_val = {}
                if not isinstance(base_val, dict):
                    base_val = {}
                remainder = opath[len(path):]
                base_val = _set_path(base_val, remainder, oval)
                return base_val
        return self._base.read(path)

    # Delegate everything else to the base store
    def __getattr__(self, name: str) -> Any:
        return getattr(self._base, name)


# ===========================================================================
# Helpers
# ===========================================================================

_UNDEFINED = object()  # Sentinel for undefined values


def _is_truthy(value: Any) -> bool:
    """Rego truthiness: false and undefined are falsy, everything else is truthy."""
    if value is None or value is _UNDEFINED:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (set, frozenset, list, dict)):
        return len(value) > 0
    return True


def _index_into(obj: Any, key: Any) -> Any:
    """Index into a compound value (dict, list, string)."""
    if obj is None:
        raise UndefinedError(f"Cannot index into null with key {key!r}")
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        # Try string key
        str_key = str(key)
        if str_key in obj:
            return obj[str_key]
        raise UndefinedError(f"Key {key!r} not found")
    if isinstance(obj, list):
        idx = int(key)
        if 0 <= idx < len(obj):
            return obj[idx]
        raise UndefinedError(f"Index {idx} out of range")
    if isinstance(obj, str):
        idx = int(key)
        return obj[idx]
    raise UndefinedError(f"Cannot index into {type(obj).__name__}")


def _lookup_path(obj: Any, path: list[str]) -> Any:
    """Walk a dot-separated path through nested dicts/lists."""
    current = obj
    for p in path:
        current = _index_into(current, p)
    return current


def _set_path(obj: dict, path: list[str], value: Any) -> dict:
    """Set a value at a nested path, creating intermediary dicts as needed."""
    if not path:
        return value
    if not isinstance(obj, dict):
        obj = {}
    key = path[0]
    if len(path) == 1:
        obj[key] = value
    else:
        obj[key] = _set_path(obj.get(key, {}), path[1:], value)
    return obj


def _make_hashable(val: Any) -> Any:
    """Convert a value to a hashable form for use in sets."""
    if isinstance(val, dict):
        return tuple(sorted((_make_hashable(k), _make_hashable(v)) for k, v in val.items()))
    if isinstance(val, list):
        return tuple(_make_hashable(v) for v in val)
    if isinstance(val, set):
        return frozenset(_make_hashable(v) for v in val)
    return val
