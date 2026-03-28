"""Unification engine for Rego evaluation.

Implements variable binding and unification for pattern matching
in the Rego top-down evaluation model.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


class UnificationError(Exception):
    """Raised when two values cannot be unified."""


@dataclass
class Bindings:
    """Variable binding environment with undo support for backtracking.

    Uses a flat dict for O(1) lookups with an undo stack to support
    backtracking during evaluation.
    """
    _values: dict[str, Any] = field(default_factory=dict)
    _undo_stack: list[list[str]] = field(default_factory=list)

    def bind(self, var: str, value: Any) -> None:
        if var in self._values:
            if not _values_equal(self._values[var], value):
                raise UnificationError(
                    f"Cannot rebind ${var}: {self._values[var]!r} != {value!r}"
                )
            return
        self._values[var] = value
        if self._undo_stack:
            self._undo_stack[-1].append(var)

    def lookup(self, var: str) -> Any | None:
        return self._values.get(var)

    def is_bound(self, var: str) -> bool:
        return var in self._values

    def resolve(self, value: Any) -> Any:
        """Recursively resolve all variable references in a value."""
        if isinstance(value, str) and value.startswith("$"):
            var_name = value[1:]
            resolved = self._values.get(var_name)
            if resolved is not None:
                return self.resolve(resolved)
            return value
        if isinstance(value, dict):
            return {self.resolve(k): self.resolve(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.resolve(v) for v in value]
        if isinstance(value, (set, frozenset)):
            return frozenset(self.resolve(v) for v in value)
        return value

    def save(self) -> None:
        """Save a checkpoint for backtracking."""
        self._undo_stack.append([])

    def restore(self) -> None:
        """Undo bindings since last save."""
        if not self._undo_stack:
            return
        for var in self._undo_stack.pop():
            self._values.pop(var, None)

    def commit(self) -> None:
        """Commit current checkpoint (discard undo info but keep bindings)."""
        if self._undo_stack:
            committed = self._undo_stack.pop()
            if self._undo_stack:
                self._undo_stack[-1].extend(committed)

    def copy(self) -> Bindings:
        return Bindings(
            _values=dict(self._values),
            _undo_stack=[list(frame) for frame in self._undo_stack],
        )

    def as_dict(self) -> dict[str, Any]:
        return dict(self._values)

    def __contains__(self, var: str) -> bool:
        return var in self._values

    def __len__(self) -> int:
        return len(self._values)


def unify(a: Any, b: Any, bindings: Bindings) -> bool:
    """Attempt to unify values a and b, updating bindings.

    Returns True if unification succeeds, False otherwise.
    Handles variables (strings starting with $), dicts, lists, and scalars.
    """
    a = _deref(a, bindings)
    b = _deref(b, bindings)

    # Both are variables
    if _is_var(a) and _is_var(b):
        bindings.bind(a[1:], b)
        return True

    # One is a variable
    if _is_var(a):
        bindings.bind(a[1:], b)
        return True
    if _is_var(b):
        bindings.bind(b[1:], a)
        return True

    # Both are dicts
    if isinstance(a, dict) and isinstance(b, dict):
        if len(a) != len(b):
            return False
        for k in a:
            if k not in b:
                return False
            if not unify(a[k], b[k], bindings):
                return False
        return True

    # Both are lists
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        return all(unify(x, y, bindings) for x, y in zip(a, b))

    # Both are sets
    if isinstance(a, (set, frozenset)) and isinstance(b, (set, frozenset)):
        return a == b

    # Scalar comparison
    return _values_equal(a, b)


def match_pattern(pattern: Any, value: Any, bindings: Bindings) -> bool:
    """One-directional pattern matching: pattern may contain variables,
    value is ground. Used for rule head matching."""
    pattern = _deref(pattern, bindings)

    if _is_var(pattern):
        bindings.bind(pattern[1:], value)
        return True

    if isinstance(pattern, dict) and isinstance(value, dict):
        for k, v in pattern.items():
            pk = _deref(k, bindings)
            if _is_var(pk):
                # Key is a variable — try matching against all keys
                matched = False
                for vk in value:
                    bindings.save()
                    if match_pattern(pk, vk, bindings) and match_pattern(v, value[vk], bindings):
                        bindings.commit()
                        matched = True
                        break
                    bindings.restore()
                if not matched:
                    return False
            else:
                if pk not in value:
                    return False
                if not match_pattern(v, value[pk], bindings):
                    return False
        return True

    if isinstance(pattern, list) and isinstance(value, list):
        if len(pattern) != len(value):
            return False
        return all(match_pattern(p, v, bindings) for p, v in zip(pattern, value))

    return _values_equal(pattern, value)


def _is_var(x: Any) -> bool:
    return isinstance(x, str) and x.startswith("$")


def _deref(x: Any, bindings: Bindings) -> Any:
    """Dereference a variable through bindings chain."""
    seen: set[str] = set()
    while _is_var(x):
        var_name = x[1:]
        if var_name in seen:
            break
        seen.add(var_name)
        val = bindings.lookup(var_name)
        if val is None:
            break
        x = val
    return x


def _values_equal(a: Any, b: Any) -> bool:
    """Deep equality supporting numeric coercion (int/float)."""
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    return a == b
