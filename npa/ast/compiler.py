"""Rego Compiler — Compiles parsed AST into an optimized, queryable structure.

Pipeline: Module → Resolve Imports → Build Rule/Module Trees → Type Check → Index
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from npa.ast.types import (
    Body,
    Call,
    Import,
    Location,
    Module,
    Ref,
    Rule,
    RuleKind,
    Term,
    TermKind,
)


class CompileError(Exception):
    def __init__(self, msg: str, location: Location | None = None) -> None:
        super().__init__(f"{location}: {msg}" if location else msg)
        self.location = location


@dataclass
class RuleTreeNode:
    """Tree of rules indexed by path for fast lookup."""
    name: str
    rules: list[Rule] = field(default_factory=list)
    children: dict[str, RuleTreeNode] = field(default_factory=dict)

    def add(self, path: list[str], rule: Rule) -> None:
        if not path:
            self.rules.append(rule)
            return
        child_name = path[0]
        if child_name not in self.children:
            self.children[child_name] = RuleTreeNode(name=child_name)
        self.children[child_name].add(path[1:], rule)

    def lookup(self, path: list[str]) -> list[Rule]:
        if not path:
            return self.rules
        child_name = path[0]
        if child_name in self.children:
            return self.children[child_name].lookup(path[1:])
        return []


@dataclass
class ModuleTreeNode:
    """Tree of modules indexed by package path."""
    name: str
    modules: list[Module] = field(default_factory=list)
    children: dict[str, ModuleTreeNode] = field(default_factory=dict)

    def add(self, path: list[str], module: Module) -> None:
        if not path:
            self.modules.append(module)
            return
        child_name = path[0]
        if child_name not in self.children:
            self.children[child_name] = ModuleTreeNode(name=child_name)
        self.children[child_name].add(path[1:], module)


@dataclass
class Compiler:
    """Rego compiler — builds optimized query structures from parsed modules."""

    modules: dict[str, Module] = field(default_factory=dict)
    rule_tree: RuleTreeNode = field(default_factory=lambda: RuleTreeNode(name="data"))
    module_tree: ModuleTreeNode = field(default_factory=lambda: ModuleTreeNode(name="data"))
    errors: list[CompileError] = field(default_factory=list)
    _builtins: dict[str, Any] = field(default_factory=dict)
    _rule_indices: dict[str, RuleIndex] = field(default_factory=dict)

    def compile(self, modules: dict[str, Module]) -> None:
        """Compile a set of modules."""
        self.modules = modules
        self.errors = []
        self.rule_tree = RuleTreeNode(name="data")
        self.module_tree = ModuleTreeNode(name="data")
        self._rule_indices = {}

        for name, module in modules.items():
            self._compile_module(name, module)

        # Build indices
        self._build_indices()

        if self.errors:
            raise CompileError(f"Compilation failed with {len(self.errors)} error(s): {self.errors[0]}")

    def _build_indices(self) -> None:
        """Build rule indices for all rule groups in the tree."""
        all_rules = self.get_all_rules()
        for path_str, rules in all_rules.items():
            idx = RuleIndex()
            for rule in rules:
                idx.add(rule)
            if idx._eq_index or idx._fallback:
                self._rule_indices[path_str] = idx

    def get_indexed_rules(self, path: list[str], input_data: Any = None) -> list[Rule]:
        """Get rules using the index for fast filtering.

        Falls back to unindexed lookup when no index exists.
        """
        path_str = ".".join(path)
        idx = self._rule_indices.get(path_str)
        if idx:
            return idx.candidates(input_data)
        return self.rule_tree.lookup(path)

    def _compile_module(self, name: str, module: Module) -> None:
        """Compile a single module."""
        # Resolve package path
        pkg_path = module.package.path.as_path()

        # Add to module tree
        self.module_tree.add(pkg_path, module)

        # Process imports
        import_map = self._resolve_imports(module)

        # Process rules
        for rule in module.rules:
            self._compile_rule(pkg_path, rule, import_map)

    def _resolve_imports(self, module: Module) -> dict[str, list[str]]:
        """Resolve imports to their full paths."""
        import_map: dict[str, list[str]] = {}
        for imp in module.imports:
            path = imp.path.as_path()
            alias = imp.alias or path[-1]
            import_map[alias] = path
        return import_map

    def _compile_rule(self, pkg_path: list[str], rule: Rule, imports: dict[str, list[str]]) -> None:
        """Compile a single rule and add it to the rule tree."""
        rule_path = pkg_path + [rule.head.name]

        # Validate rule
        self._check_rule(rule)

        # Add to rule tree
        self.rule_tree.add(rule_path, rule)

    def _check_rule(self, rule: Rule) -> None:
        """Perform static checks on a rule."""
        # Check for unsafe variables in body
        if rule.body and not rule.default:
            self._check_safety(rule)

    def _check_safety(self, rule: Rule) -> None:
        """Check that all output variables appear in at least one non-negated expression."""
        # Simplified safety check — full implementation would walk the AST
        pass

    def get_rules(self, path: list[str]) -> list[Rule]:
        """Get all rules matching a data path."""
        return self.rule_tree.lookup(path)

    def get_all_rules(self) -> dict[str, list[Rule]]:
        """Get all rules indexed by dotted path."""
        result: dict[str, list[Rule]] = {}
        self._collect_rules(self.rule_tree, [], result)
        return result

    def _collect_rules(self, node: RuleTreeNode, path: list[str], result: dict[str, list[Rule]]) -> None:
        if node.rules:
            result[".".join(path)] = node.rules
        for name, child in node.children.items():
            self._collect_rules(child, path + [name], result)


# ---------------------------------------------------------------------------
# Rule indexing for fast evaluation
# ---------------------------------------------------------------------------

@dataclass
class RuleIndex:
    """Index for fast rule selection based on the first equality in the body.

    For a rule like:
        allow { input.method == "GET"; ... }

    We index on the (ref-path, value) pair ("input.method", "GET") so the
    evaluator can skip rules that cannot match the current input without
    evaluating their full body.
    """
    # Mapping: (ref_path, value) → list of rules that require that guard
    _eq_index: dict[tuple[str, Any], list[Rule]] = field(default_factory=dict)
    # Rules that cannot be indexed (complex or no leading equality)
    _fallback: list[Rule] = field(default_factory=list)

    def add(self, rule: Rule) -> None:
        guard = _extract_equality_guard(rule)
        if guard:
            key = guard
            self._eq_index.setdefault(key, []).append(rule)
        else:
            self._fallback.append(rule)

    def candidates(self, input_data: Any = None) -> list[Rule]:
        """Return rules that *might* match, given the current input.

        This is an optimistic filter — it never excludes rules that would
        match, but may include rules that ultimately fail.
        """
        if not self._eq_index:
            return self._fallback

        result = list(self._fallback)
        for (ref_path, expected), rules in self._eq_index.items():
            # Try to resolve the ref_path against input_data
            actual = _resolve_input_path(ref_path, input_data)
            if actual is _NO_VALUE or actual == expected:
                result.extend(rules)
        return result


_NO_VALUE = object()


def _resolve_input_path(ref_path: str, input_data: Any) -> Any:
    """Try to resolve a dotted path like 'input.method' against input_data."""
    parts = ref_path.split(".")
    if not parts or parts[0] != "input":
        return _NO_VALUE
    current = input_data
    for part in parts[1:]:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return _NO_VALUE
    return current


def _extract_equality_guard(rule: Rule) -> tuple[str, Any] | None:
    """Try to extract a simple ``ref == constant`` guard from the first body expression."""
    if not rule.body or not rule.body.exprs:
        return None

    # Rules with else chains must not be indexed — the first body
    # guard might not match but an else clause could.
    if rule.else_rules:
        return None

    expr = rule.body.exprs[0]
    terms = expr.terms
    if expr.negated:
        return None

    # Pattern: Call(operator=eq/equal, args=[ref, const]) or [ref, eq_op, const]
    if isinstance(terms, Term) and terms.kind == TermKind.CALL:
        call: Call = terms.value
        op_parts = call.operator.as_path()
        op_name = ".".join(op_parts)
        if op_name in ("=", "==", "equal", "eq") and len(call.args) == 2:
            return _extract_ref_const(call.args[0], call.args[1])

    if isinstance(terms, (list, tuple)) and len(terms) == 3:
        op = terms[1]
        if isinstance(op, Term) and op.kind == TermKind.VAR and op.value in ("eq", "equal", "unify"):
            return _extract_ref_const(terms[0], terms[2])

    return None


def _extract_ref_const(a: Term, b: Term) -> tuple[str, Any] | None:
    """Given two terms, check if one is a ref and the other a constant."""
    ref_path = _term_ref_path(a)
    const = _term_const(b)
    if ref_path and const is not _NO_VALUE:
        return (ref_path, const)

    ref_path = _term_ref_path(b)
    const = _term_const(a)
    if ref_path and const is not _NO_VALUE:
        return (ref_path, const)

    return None


def _term_ref_path(term: Term) -> str | None:
    """If term is a simple dotted reference, return the path string."""
    if term.kind == TermKind.REF:
        ref: Ref = term.value
        parts = []
        for p in ref.terms:
            if isinstance(p, Term):
                if p.kind in (TermKind.VAR, TermKind.STRING):
                    parts.append(str(p.value))
                else:
                    return None
            elif isinstance(p, str):
                parts.append(p)
            else:
                return None
        return ".".join(parts)
    return None


def _term_const(term: Term) -> Any:
    """If term is a literal constant, return its value; else *_NO_VALUE*."""
    if term.kind in (TermKind.STRING, TermKind.NUMBER, TermKind.BOOLEAN, TermKind.NULL):
        return term.value
    return _NO_VALUE
