"""Rego code formatter — pretty-prints a parsed Module back to source.

Follows OPA's formatting conventions:
- Consistent indentation (tab = 4 spaces)
- One blank line between rules
- Sorted imports
- Normalized whitespace
"""

from __future__ import annotations

from npa.ast.types import (
    Body,
    Call,
    Every,
    Expr,
    Module,
    Ref,
    Rule,
    RuleKind,
    Term,
    TermKind,
    With,
)

INDENT = "\t"


def format_module(module: Module) -> str:
    """Format a parsed Rego Module back to canonical source."""
    lines: list[str] = []

    # Package
    pkg_path = ".".join(module.package.path.as_path())
    lines.append(f"package {pkg_path}")
    lines.append("")

    # Imports (sorted)
    if module.imports:
        sorted_imports = sorted(module.imports, key=lambda i: ".".join(i.path.as_path()))
        for imp in sorted_imports:
            path = ".".join(imp.path.as_path())
            if imp.alias:
                lines.append(f"import {path} as {imp.alias}")
            else:
                lines.append(f"import {path}")
        lines.append("")

    # Rules
    for i, rule in enumerate(module.rules):
        if i > 0:
            lines.append("")
        lines.extend(_format_rule(rule))

    # Ensure trailing newline
    text = "\n".join(lines)
    if not text.endswith("\n"):
        text += "\n"
    return text


def _format_rule(rule: Rule) -> list[str]:
    """Format a single rule."""
    lines: list[str] = []

    # Annotations
    if rule.annotations:
        lines.append("# METADATA")
        ann = rule.annotations
        if ann.title:
            lines.append(f"# title: {ann.title}")
        if ann.description:
            lines.append(f"# description: {ann.description}")
        if ann.scope:
            lines.append(f"# scope: {ann.scope}")
        if ann.entrypoint:
            lines.append("# entrypoint: true")

    head = _format_rule_head(rule)

    if rule.default:
        lines.append(f"default {head}")
        return lines

    if rule.body and rule.body.exprs:
        lines.append(f"{head} {{")
        for expr in rule.body.exprs:
            lines.append(f"{INDENT}{_format_expr(expr)}")
        lines.append("}")
    else:
        lines.append(head)

    # Else chains
    for else_rule in rule.else_rules:
        else_head = ""
        if else_rule.head.value is not None:
            else_head = f" := {_format_term(else_rule.head.value)}"
        if else_rule.body and else_rule.body.exprs:
            lines[-1] += f" else{else_head} {{"
            for expr in else_rule.body.exprs:
                lines.append(f"{INDENT}{_format_expr(expr)}")
            lines.append("}")
        else:
            lines[-1] += f" else{else_head}"

    return lines


def _format_rule_head(rule: Rule) -> str:
    """Format the head of a rule (name + key + value)."""
    name = rule.head.name

    # Function args
    if rule.head.args:
        args = ", ".join(_format_term(a) for a in rule.head.args)
        head = f"{name}({args})"
    else:
        head = name

    # Partial set with contains
    if rule.kind == RuleKind.PARTIAL_SET and rule.head.contains:
        if rule.head.key is not None:
            head = f"{name} contains {_format_term(rule.head.key)}"
        elif rule.head.value is not None:
            head = f"{name} contains {_format_term(rule.head.value)}"
        return head

    # Key for partial objects
    if rule.head.key is not None and rule.kind == RuleKind.PARTIAL_OBJECT:
        head = f"{name}[{_format_term(rule.head.key)}]"

    # Value
    if rule.head.value is not None:
        val = _format_term(rule.head.value)
        if rule.default or rule.kind == RuleKind.COMPLETE:
            head = f"{head} = {val}"
        else:
            head = f"{head} = {val}"

    return head


def _format_expr(expr: Expr) -> str:
    """Format an expression."""
    parts: list[str] = []

    if expr.negated:
        parts.append("not ")

    parts.append(_format_term(expr.terms))

    for w in expr.with_modifiers:
        parts.append(f" with {_format_term(w.target)} as {_format_term(w.value)}")

    return "".join(parts)


def _format_term(term: Term) -> str:
    """Format a term to its string representation."""
    kind = term.kind

    if kind == TermKind.NULL:
        return "null"
    if kind == TermKind.BOOLEAN:
        return "true" if term.value else "false"
    if kind == TermKind.NUMBER:
        v = term.value
        if isinstance(v, float) and v == int(v):
            return str(int(v))
        return str(v)
    if kind == TermKind.STRING:
        return _quote_string(term.value)

    if kind == TermKind.VAR:
        return str(term.value)

    if kind == TermKind.REF:
        ref: Ref = term.value
        parts = []
        for i, t in enumerate(ref.terms):
            if i == 0:
                # Root of ref — always printed bare (input, data, varname)
                if t.kind == TermKind.VAR:
                    parts.append(str(t.value))
                elif t.kind == TermKind.STRING:
                    # Root terms stored as strings should be printed bare
                    parts.append(t.value)
                else:
                    parts.append(_format_term(t))
            elif t.kind == TermKind.STRING and t.value.isidentifier():
                parts.append(f".{t.value}")
            else:
                parts.append(f"[{_format_term(t)}]")
        return "".join(parts)

    if kind == TermKind.ARRAY:
        items = ", ".join(_format_term(e) for e in term.value)
        return f"[{items}]"

    if kind == TermKind.OBJECT:
        pairs = ", ".join(
            f"{_format_term(k)}: {_format_term(v)}" for k, v in term.value
        )
        return f"{{{pairs}}}"

    if kind == TermKind.SET:
        if not term.value:
            return "set()"
        items = ", ".join(_format_term(e) for e in term.value)
        return f"{{{items}}}"

    if kind == TermKind.CALL:
        return _format_call(term.value)

    if kind == TermKind.ARRAY_COMPREHENSION:
        comp = term.value
        body = "; ".join(_format_expr(e) for e in comp.body.exprs)
        return f"[{_format_term(comp.term)} | {body}]"

    if kind == TermKind.SET_COMPREHENSION:
        comp = term.value
        body = "; ".join(_format_expr(e) for e in comp.body.exprs)
        return f"{{{_format_term(comp.term)} | {body}}}"

    if kind == TermKind.OBJECT_COMPREHENSION:
        comp = term.value
        body = "; ".join(_format_expr(e) for e in comp.body.exprs)
        return f"{{{_format_term(comp.key)}: {_format_term(comp.value)} | {body}}}"

    if kind == TermKind.EVERY:
        every: Every = term.value
        key_part = ""
        if every.key and every.key.kind == TermKind.VAR:
            key_part = f"{_format_term(every.key)}, "
        body_lines = "; ".join(_format_expr(e) for e in every.body.exprs)
        return f"every {key_part}{_format_term(every.value)} in {_format_term(every.domain)} {{ {body_lines} }}"

    return f"<{kind}>"


def _format_call(call: Call) -> str:
    """Format a function/operator call."""
    func_parts = call.operator.as_path()
    func_name = ".".join(func_parts)

    # Infix operators
    _INFIX = {"=", ":=", "==", "!=", "<", "<=", ">", ">=", "+", "-", "*", "/", "%"}
    if func_name in _INFIX and len(call.args) == 2:
        lhs = _format_term(call.args[0])
        rhs = _format_term(call.args[1])
        return f"{lhs} {func_name} {rhs}"

    # internal.member_2 → x in coll
    if func_name == "internal.member_2" and len(call.args) == 2:
        return f"{_format_term(call.args[0])} in {_format_term(call.args[1])}"

    # Regular function call
    args = ", ".join(_format_term(a) for a in call.args)
    return f"{func_name}({args})"


def _quote_string(s: str) -> str:
    """Quote a string with proper escaping."""
    escaped = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")
    return f'"{escaped}"'
