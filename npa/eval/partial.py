"""Partial Evaluation Engine for NPA.

Implements OPA-compatible partial evaluation (PE):
- Given a query, input, data, and a set of *unknowns*, PE reduces the query
  to a set of residual queries and support rules that, when evaluated later
  with the missing data, yield the same result as full evaluation.

OPA's ``POST /v1/compile`` endpoint is backed by this engine.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from npa.ast.compiler import Compiler
from npa.ast.types import (
    Body,
    Call,
    Expr,
    Module,
    Ref,
    Rule,
    RuleKind,
    Term,
    TermKind,
)
from npa.eval.topdown import (
    EvalContext,
    EvalError,
    TopdownEvaluator,
    UndefinedError,
    _is_truthy,
    _lookup_path,
    _UNDEFINED,
    _set_path,
    _make_hashable,
)
from npa.eval.unify import Bindings
from npa.eval.cache import IntraQueryCache


@dataclass
class PartialResult:
    """Result of partial evaluation."""
    queries: list[list[Any]]  # residual queries (list of conjunctions)
    support: list[dict[str, Any]]  # support rules


class PartialEvaluator:
    """Performs partial evaluation by walking the rule tree and stopping at unknowns.

    When the evaluator encounters a reference that overlaps with one of the
    declared ``unknowns`` paths, it keeps the reference symbolic instead of
    resolving it.  Everything else is evaluated normally and simplified away.
    """

    def __init__(
        self,
        compiler: Compiler,
        store: Any,
        unknowns: list[str] | None = None,
    ) -> None:
        self.compiler = compiler
        self.store = store
        self.unknowns = unknowns or ["input"]
        # Also use a full evaluator for sub-expressions that are fully known
        self._full_eval = TopdownEvaluator(compiler, store)

    def partial_eval(
        self,
        query: str,
        input_data: Any = None,
    ) -> PartialResult:
        """Partially evaluate *query*.

        Returns a ``PartialResult`` with residual queries and (optional)
        support rules that the caller must keep around.
        """
        ctx = EvalContext(
            compiler=self.compiler,
            store=self.store,
            input_data=input_data,
            intra_cache=IntraQueryCache(),
        )

        path = query.split(".")

        if path[0] == "data":
            data_path = path[1:]
        else:
            # Bare query — try to evaluate as-is, but keep unknowns symbolic
            data_path = path

        residuals: list[list[Any]] = []
        support: list[dict[str, Any]] = []

        # Try to fully evaluate first — if all data is known the result
        # is a single constant query.
        try:
            result = self._full_eval.eval_query(query, input_data=input_data)
            # Fully resolved — return constant result
            residuals.append([result])
            return PartialResult(queries=residuals, support=support)
        except (UndefinedError, EvalError):
            pass

        # Not fully resolvable — walk rules and keep unknown refs symbolic
        rules = self.compiler.get_rules(data_path)
        if not rules:
            # No rules — the path might be pure data or undefined
            if self._is_unknown_path(path):
                residuals.append([query])
                return PartialResult(queries=residuals, support=support)
            raise EvalError(f"Partial eval: undefined path {query}")

        for rule in rules:
            residual = self._partial_eval_rule(ctx, rule, data_path)
            if residual is not None:
                residuals.append(residual)

        if not residuals:
            # All rules were unsatisfied
            raise UndefinedError(f"Partial eval: undefined for {query}")

        return PartialResult(queries=residuals, support=support)

    def _is_unknown_path(self, path_parts: list[str]) -> bool:
        """Check if *path_parts* is (a sub‑path of) a declared unknown."""
        path_str = ".".join(path_parts)
        for unk in self.unknowns:
            if path_str == unk or path_str.startswith(unk + "."):
                return True
            if unk.startswith(path_str + "."):
                return True
        return False

    def _partial_eval_rule(
        self,
        ctx: EvalContext,
        rule: Rule,
        path: list[str],
    ) -> list[Any] | None:
        """Partially evaluate a single rule.

        Returns a list of residual terms (a conjunction) or None if the
        rule is definitely unsatisfied.
        """
        bindings = Bindings()
        residual_terms: list[Any] = []

        if rule.body:
            for expr in rule.body.exprs:
                # Try full evaluation
                try:
                    child_ctx = ctx.child()
                    result = self._try_full_eval_expr(child_ctx, expr, bindings)
                    if result is False:
                        return None  # Rule body fails — skip rule
                    # Expression resolved to true — no residual needed
                    continue
                except (UndefinedError, EvalError):
                    pass

                # Expression couldn't be fully evaluated — keep as residual
                residual_terms.append(self._expr_to_json(expr, bindings))

        # Rule head value
        if rule.head.value is not None:
            try:
                child_ctx = ctx.child()
                val = self._full_eval.eval_rule(rule, child_ctx, bindings.copy())
                if not residual_terms:
                    return [val]
                residual_terms.insert(0, val)
                return residual_terms
            except (UndefinedError, EvalError):
                if not residual_terms:
                    return None

        if not residual_terms:
            return [True]

        return residual_terms

    def _try_full_eval_expr(
        self, ctx: EvalContext, expr: Expr, bindings: Bindings,
    ) -> bool:
        """Try to fully evaluate an expression. Raises on unknowns."""
        # Quick check: does this expression reference any unknowns?
        if self._expr_has_unknowns(expr):
            raise UndefinedError("Expression contains unknowns")

        evaluator = TopdownEvaluator(self.compiler, self.store)
        # Use _eval_expr from the evaluator
        return evaluator._eval_expr(ctx, expr, bindings)

    def _expr_has_unknowns(self, expr: Expr) -> bool:
        """Check if an expression references unknown paths."""
        return self._terms_have_unknowns(expr.terms)

    def _terms_have_unknowns(self, terms: Any) -> bool:
        if isinstance(terms, Term):
            return self._term_has_unknowns(terms)
        if isinstance(terms, (list, tuple)):
            return any(self._terms_have_unknowns(t) for t in terms)
        return False

    def _term_has_unknowns(self, term: Term) -> bool:
        if term.kind == TermKind.REF:
            ref = term.value
            if isinstance(ref, Ref):
                path_parts = []
                for p in ref.terms:
                    if isinstance(p, Term) and p.kind in (TermKind.VAR, TermKind.STRING):
                        path_parts.append(str(p.value))
                    elif isinstance(p, str):
                        path_parts.append(p)
                path_str = ".".join(path_parts)
                for unk in self.unknowns:
                    if path_str == unk or path_str.startswith(unk + "."):
                        return True
        if term.kind == TermKind.CALL:
            call = term.value
            return any(self._term_has_unknowns(a) for a in call.args)
        if term.kind in (TermKind.ARRAY, TermKind.SET):
            return any(self._term_has_unknowns(v) for v in term.value)
        if term.kind == TermKind.OBJECT:
            return any(
                self._term_has_unknowns(k) or self._term_has_unknowns(v)
                for k, v in term.value
            )
        return False

    def _expr_to_json(self, expr: Expr, bindings: Bindings) -> dict[str, Any]:
        """Convert expression to a JSON-serialisable representation."""
        terms_json = self._terms_to_json(expr.terms, bindings)
        result: dict[str, Any] = {"terms": terms_json}
        if expr.negated:
            result["negated"] = True
        return result

    def _terms_to_json(self, terms: Any, bindings: Bindings) -> Any:
        if isinstance(terms, Term):
            return self._term_to_json(terms, bindings)
        if isinstance(terms, (list, tuple)):
            return [self._terms_to_json(t, bindings) for t in terms]
        return terms

    def _term_to_json(self, term: Term, bindings: Bindings) -> Any:
        if term.kind in (TermKind.NULL, TermKind.BOOLEAN, TermKind.NUMBER, TermKind.STRING):
            return {"type": term.kind.name.lower(), "value": term.value}
        if term.kind == TermKind.VAR:
            if bindings.is_bound(term.value):
                return {"type": "value", "value": bindings.lookup(term.value)}
            return {"type": "var", "value": term.value}
        if term.kind == TermKind.REF:
            ref = term.value
            parts = []
            for p in ref.terms:
                if isinstance(p, Term):
                    parts.append(self._term_to_json(p, bindings))
                else:
                    parts.append({"type": "string", "value": str(p)})
            return {"type": "ref", "value": parts}
        if term.kind == TermKind.CALL:
            call = term.value
            op_parts = call.operator.as_path()
            return {
                "type": "call",
                "operator": ".".join(op_parts),
                "args": [self._term_to_json(a, bindings) for a in call.args],
            }
        return {"type": "unknown", "value": str(term)}
