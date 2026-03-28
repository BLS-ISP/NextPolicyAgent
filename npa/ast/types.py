"""Rego AST node types.

Defines all Abstract Syntax Tree nodes for the Rego policy language.
Immutable dataclass-based design for thread safety and hashability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


# ---------------------------------------------------------------------------
# Source Location
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Location:
    """Source location for error reporting and debugging."""
    file: str = ""
    row: int = 0
    col: int = 0
    offset: int = 0
    end_row: int = 0
    end_col: int = 0

    def __str__(self) -> str:
        if self.file:
            return f"{self.file}:{self.row}:{self.col}"
        return f"{self.row}:{self.col}"


# ---------------------------------------------------------------------------
# Comments & Annotations
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Comment:
    text: str
    location: Location = field(default_factory=Location)


@dataclass(frozen=True, slots=True)
class Annotations:
    """Metadata annotations for rules (title, description, scope, schemas)."""
    title: str = ""
    description: str = ""
    scope: str = ""
    schemas: tuple[SchemaAnnotation, ...] = ()
    custom: dict[str, Any] = field(default_factory=dict)
    entrypoint: bool = False
    location: Location = field(default_factory=Location)


@dataclass(frozen=True, slots=True)
class SchemaAnnotation:
    path: tuple[str, ...]
    schema: Any  # JSON Schema dict or $ref string
    definition: str = ""


# ---------------------------------------------------------------------------
# Term Types — Rego Values
# ---------------------------------------------------------------------------

class TermKind(Enum):
    NULL = auto()
    BOOLEAN = auto()
    NUMBER = auto()
    STRING = auto()
    VAR = auto()
    REF = auto()
    ARRAY = auto()
    OBJECT = auto()
    SET = auto()
    ARRAY_COMPREHENSION = auto()
    SET_COMPREHENSION = auto()
    OBJECT_COMPREHENSION = auto()
    CALL = auto()
    EVERY = auto()


@dataclass(frozen=True, slots=True)
class Term:
    """Base wrapper around all Rego value types."""
    kind: TermKind
    value: Any
    location: Location = field(default_factory=Location)

    def is_ground(self) -> bool:
        """Returns True if the term contains no variables."""
        match self.kind:
            case TermKind.NULL | TermKind.BOOLEAN | TermKind.NUMBER | TermKind.STRING:
                return True
            case TermKind.VAR:
                return False
            case TermKind.REF:
                ref: Ref = self.value
                return all(t.is_ground() for t in ref.terms)
            case TermKind.ARRAY:
                return all(t.is_ground() for t in self.value)
            case TermKind.OBJECT:
                obj: tuple[tuple[Term, Term], ...] = self.value
                return all(k.is_ground() and v.is_ground() for k, v in obj)
            case TermKind.SET:
                return all(t.is_ground() for t in self.value)
            case TermKind.CALL:
                call: Call = self.value
                return all(t.is_ground() for t in call.args)
            case _:
                return False


# ---------------------------------------------------------------------------
# Specific Term Value Types
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Ref:
    """A reference like data.foo.bar[x]."""
    terms: tuple[Term, ...]

    @property
    def head(self) -> Term:
        return self.terms[0]

    def as_path(self) -> list[str]:
        """Convert ground ref to string path segments."""
        parts: list[str] = []
        for t in self.terms:
            if t.kind == TermKind.STRING:
                parts.append(t.value)
            elif t.kind == TermKind.VAR:
                parts.append(str(t.value))
        return parts


@dataclass(frozen=True, slots=True)
class Call:
    """A function call: f(x, y, ...)."""
    operator: Ref
    args: tuple[Term, ...]


@dataclass(frozen=True, slots=True)
class ArrayComprehension:
    term: Term
    body: Body


@dataclass(frozen=True, slots=True)
class SetComprehension:
    term: Term
    body: Body


@dataclass(frozen=True, slots=True)
class ObjectComprehension:
    key: Term
    value: Term
    body: Body


@dataclass(frozen=True, slots=True)
class Every:
    key: Term
    value: Term
    domain: Term
    body: Body


# ---------------------------------------------------------------------------
# Term Constructors (convenience)
# ---------------------------------------------------------------------------

def null_term(loc: Location | None = None) -> Term:
    return Term(TermKind.NULL, None, loc or Location())

def bool_term(v: bool, loc: Location | None = None) -> Term:
    return Term(TermKind.BOOLEAN, v, loc or Location())

def num_term(v: int | float | str, loc: Location | None = None) -> Term:
    return Term(TermKind.NUMBER, v, loc or Location())

def str_term(v: str, loc: Location | None = None) -> Term:
    return Term(TermKind.STRING, v, loc or Location())

def var_term(name: str, loc: Location | None = None) -> Term:
    return Term(TermKind.VAR, name, loc or Location())

def ref_term(terms: list[Term], loc: Location | None = None) -> Term:
    return Term(TermKind.REF, Ref(tuple(terms)), loc or Location())

def array_term(items: list[Term], loc: Location | None = None) -> Term:
    return Term(TermKind.ARRAY, tuple(items), loc or Location())

def object_term(pairs: list[tuple[Term, Term]], loc: Location | None = None) -> Term:
    return Term(TermKind.OBJECT, tuple(pairs), loc or Location())

def set_term(items: list[Term], loc: Location | None = None) -> Term:
    return Term(TermKind.SET, frozenset(items), loc or Location())

def call_term(operator: Ref, args: list[Term], loc: Location | None = None) -> Term:
    return Term(TermKind.CALL, Call(operator, tuple(args)), loc or Location())


# ---------------------------------------------------------------------------
# Expressions & Bodies
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Expr:
    """A single expression in a rule body."""
    terms: Term | list[Term]
    negated: bool = False
    index: int = 0
    with_modifiers: tuple[With, ...] = ()
    location: Location = field(default_factory=Location)

    @property
    def is_call(self) -> bool:
        return isinstance(self.terms, Term) and self.terms.kind == TermKind.CALL


@dataclass(frozen=True, slots=True)
class With:
    """A with modifier: `with input.user as "admin"`."""
    target: Term
    value: Term
    location: Location = field(default_factory=Location)


@dataclass(slots=True)
class Body:
    """A list of expressions that form a query."""
    exprs: list[Expr] = field(default_factory=list)
    location: Location = field(default_factory=Location)

    def __bool__(self) -> bool:
        return len(self.exprs) > 0


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

class RuleKind(Enum):
    COMPLETE = auto()      # rule = value { body }
    PARTIAL_SET = auto()   # rule contains value { body }
    PARTIAL_OBJECT = auto()  # rule[key] = value { body }
    FUNCTION = auto()      # f(x) = y { body }
    DEFAULT = auto()       # default rule = value


@dataclass(slots=True)
class RuleHead:
    """Head of a rule (name, key, value, args)."""
    name: str
    ref: Ref | None = None
    key: Term | None = None
    value: Term | None = None
    args: tuple[Term, ...] = ()
    assign: bool = False  # := vs =
    contains: bool = False  # partial set via 'contains'
    location: Location = field(default_factory=Location)


@dataclass(slots=True)
class Rule:
    """A complete Rego rule."""
    kind: RuleKind
    head: RuleHead
    body: Body = field(default_factory=Body)
    else_rules: list[Rule] = field(default_factory=list)
    default: bool = False
    annotations: Annotations | None = None
    location: Location = field(default_factory=Location)


# ---------------------------------------------------------------------------
# Imports & Package
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Import:
    """An import statement: `import data.foo.bar as baz`."""
    path: Ref
    alias: str = ""
    location: Location = field(default_factory=Location)


@dataclass(frozen=True, slots=True)
class Package:
    """A package declaration: `package example.authz`."""
    path: Ref
    location: Location = field(default_factory=Location)


# ---------------------------------------------------------------------------
# Module — Top-Level AST Node
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Module:
    """A complete Rego module (one .rego file)."""
    package: Package
    imports: list[Import] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)
    comments: list[Comment] = field(default_factory=list)
    annotations: list[Annotations] = field(default_factory=list)
    rego_version: int = 1  # 0 = legacy, 1 = current
    location: Location = field(default_factory=Location)

    @property
    def package_path(self) -> str:
        return ".".join(self.package.path.as_path())


# ---------------------------------------------------------------------------
# AST Serialization — OPA-compatible JSON representation
# ---------------------------------------------------------------------------

def _loc_dict(loc: Location) -> dict:
    return {"file": loc.file, "row": loc.row, "col": loc.col}


def _term_to_dict(term: Term) -> dict:
    match term.kind:
        case TermKind.NULL:
            return {"type": "null", "value": None}
        case TermKind.BOOLEAN:
            return {"type": "boolean", "value": term.value}
        case TermKind.NUMBER:
            return {"type": "number", "value": term.value}
        case TermKind.STRING:
            return {"type": "string", "value": term.value}
        case TermKind.VAR:
            return {"type": "var", "value": term.value}
        case TermKind.REF:
            ref: Ref = term.value
            return {"type": "ref", "value": [_term_to_dict(t) for t in ref.terms]}
        case TermKind.ARRAY:
            return {"type": "array", "value": [_term_to_dict(t) for t in term.value]}
        case TermKind.OBJECT:
            pairs = term.value
            return {"type": "object", "value": [[_term_to_dict(k), _term_to_dict(v)] for k, v in pairs]}
        case TermKind.SET:
            return {"type": "set", "value": [_term_to_dict(t) for t in term.value]}
        case TermKind.CALL:
            call: Call = term.value
            op_terms = [_term_to_dict(t) for t in call.operator.terms]
            return {"type": "call", "value": op_terms + [_term_to_dict(a) for a in call.args]}
        case _:
            return {"type": str(term.kind.name).lower(), "value": str(term.value)}


def _expr_to_dict(expr: Expr) -> dict:
    if isinstance(expr.terms, Term):
        terms = _term_to_dict(expr.terms)
    else:
        terms = [_term_to_dict(t) for t in expr.terms]
    d: dict = {"index": expr.index, "terms": terms}
    if expr.negated:
        d["negated"] = True
    if expr.with_modifiers:
        d["with"] = [
            {"target": _term_to_dict(w.target), "value": _term_to_dict(w.value)}
            for w in expr.with_modifiers
        ]
    return d


def _body_to_list(body: Body) -> list[dict]:
    return [_expr_to_dict(e) for e in body.exprs]


def _rule_to_dict(rule: Rule) -> dict:
    head: dict = {"name": rule.head.name}
    if rule.head.value is not None:
        head["value"] = {"type": "term", "value": _term_to_dict(rule.head.value)}
    if rule.head.key is not None:
        head["key"] = {"type": "term", "value": _term_to_dict(rule.head.key)}
    if rule.head.args:
        head["args"] = [_term_to_dict(a) for a in rule.head.args]
    if rule.head.ref is not None:
        head["ref"] = [_term_to_dict(t) for t in rule.head.ref.terms]
    d: dict = {
        "head": head,
        "body": _body_to_list(rule.body),
        "default": rule.default,
        "location": _loc_dict(rule.location),
    }
    if rule.else_rules:
        d["else"] = [_rule_to_dict(r) for r in rule.else_rules]
    if rule.annotations:
        d["annotations"] = _annotations_to_dict(rule.annotations)
    return d


def _annotations_to_dict(ann: Annotations) -> dict:
    d: dict = {}
    if ann.title:
        d["title"] = ann.title
    if ann.description:
        d["description"] = ann.description
    if ann.scope:
        d["scope"] = ann.scope
    if ann.entrypoint:
        d["entrypoint"] = True
    if ann.custom:
        d["custom"] = ann.custom
    return d


def module_to_dict(mod: Module) -> dict:
    """Serialize a Module AST to an OPA-compatible dict representation."""
    pkg_ref = [_term_to_dict(t) for t in mod.package.path.terms]
    imports = []
    for imp in mod.imports:
        entry: dict = {"path": {"type": "ref", "value": [_term_to_dict(t) for t in imp.path.terms]}}
        if imp.alias:
            entry["alias"] = imp.alias
        imports.append(entry)
    rules = [_rule_to_dict(r) for r in mod.rules]
    return {
        "package": {"path": pkg_ref},
        "imports": imports,
        "rules": rules,
        "rego_version": mod.rego_version,
    }
