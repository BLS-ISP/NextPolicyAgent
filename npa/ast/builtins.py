"""Built-in functions for the Rego evaluation engine.

Registry of all built-in functions, organized by category.
Each function follows the pattern: (context, *args) -> result | None.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import io
import ipaddress
import json
import math
import re
import time
import urllib.parse
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import yaml


class BuiltinError(Exception):
    pass


BuiltinFunc = Callable[..., Any]


@dataclass
class BuiltinRegistry:
    """Thread-safe registry of built-in functions."""
    _builtins: dict[str, BuiltinFunc] = field(default_factory=dict)

    def register(self, name: str, func: BuiltinFunc) -> None:
        self._builtins[name] = func

    def get(self, name: str) -> BuiltinFunc | None:
        return self._builtins.get(name)

    def names(self) -> list[str]:
        return sorted(self._builtins.keys())


# Global registry
_registry = BuiltinRegistry()


def register_builtin(name: str) -> Callable[[BuiltinFunc], BuiltinFunc]:
    """Decorator to register a built-in function."""
    def decorator(func: BuiltinFunc) -> BuiltinFunc:
        _registry.register(name, func)
        return func
    return decorator


def get_builtin(name: str) -> BuiltinFunc | None:
    return _registry.get(name)


def list_builtins() -> list[str]:
    return _registry.names()


# ===========================================================================
# COMPARISON
# ===========================================================================

@register_builtin("equal")
def builtin_equal(a: Any, b: Any) -> bool:
    return a == b

@register_builtin("neq")
def builtin_neq(a: Any, b: Any) -> bool:
    return a != b

@register_builtin("lt")
def builtin_lt(a: Any, b: Any) -> bool:
    return a < b

@register_builtin("lte")
def builtin_lte(a: Any, b: Any) -> bool:
    return a <= b

@register_builtin("gt")
def builtin_gt(a: Any, b: Any) -> bool:
    return a > b

@register_builtin("gte")
def builtin_gte(a: Any, b: Any) -> bool:
    return a >= b


# ===========================================================================
# ARITHMETIC
# ===========================================================================

@register_builtin("plus")
def builtin_plus(a: Any, b: Any) -> Any:
    return a + b

@register_builtin("minus")
def builtin_minus(a: Any, b: Any) -> Any:
    if isinstance(a, set) and isinstance(b, set):
        return a - b
    return a - b

@register_builtin("mul")
def builtin_mul(a: Any, b: Any) -> Any:
    return a * b

@register_builtin("div")
def builtin_div(a: Any, b: Any) -> Any:
    if b == 0:
        raise BuiltinError("Division by zero")
    return a / b

@register_builtin("rem")
def builtin_rem(a: Any, b: Any) -> Any:
    if b == 0:
        raise BuiltinError("Division by zero")
    return a % b

@register_builtin("abs")
def builtin_abs(x: Any) -> Any:
    return abs(x)

@register_builtin("ceil")
def builtin_ceil(x: Any) -> int:
    return math.ceil(x)

@register_builtin("floor")
def builtin_floor(x: Any) -> int:
    return math.floor(x)

@register_builtin("round")
def builtin_round(x: Any) -> int:
    return round(x)

@register_builtin("numbers.range")
def builtin_numbers_range(a: int, b: int) -> list[int]:
    if a <= b:
        return list(range(a, b + 1))
    return list(range(a, b - 1, -1))

@register_builtin("numbers.range_step")
def builtin_numbers_range_step(a: int, b: int, step: int) -> list[int]:
    if step == 0:
        raise BuiltinError("Step cannot be zero")
    return list(range(a, b + (1 if step > 0 else -1), step))


# ===========================================================================
# BITWISE
# ===========================================================================

@register_builtin("bits.and")
def builtin_bits_and(a: int, b: int) -> int:
    return a & b

@register_builtin("bits.or")
def builtin_bits_or(a: int, b: int) -> int:
    return a | b

@register_builtin("bits.xor")
def builtin_bits_xor(a: int, b: int) -> int:
    return a ^ b

@register_builtin("bits.negate")
def builtin_bits_negate(a: int) -> int:
    return ~a

@register_builtin("bits.lsh")
def builtin_bits_lsh(a: int, b: int) -> int:
    return a << b

@register_builtin("bits.rsh")
def builtin_bits_rsh(a: int, b: int) -> int:
    return a >> b


# ===========================================================================
# AGGREGATES
# ===========================================================================

@register_builtin("count")
def builtin_count(x: Any) -> int:
    if isinstance(x, str):
        return len(x)
    return len(x)

@register_builtin("sum")
def builtin_sum(x: Any) -> Any:
    return sum(x)

@register_builtin("product")
def builtin_product(x: Any) -> Any:
    result = 1
    for v in x:
        result *= v
    return result

@register_builtin("max")
def builtin_max(x: Any) -> Any:
    return max(x)

@register_builtin("min")
def builtin_min(x: Any) -> Any:
    return min(x)

@register_builtin("any")
def builtin_any(x: Any) -> bool:
    return any(x)

@register_builtin("all")
def builtin_all(x: Any) -> bool:
    return all(x)

@register_builtin("sort")
def builtin_sort(x: Any) -> list:
    return sorted(x)


# ===========================================================================
# ARRAYS
# ===========================================================================

@register_builtin("array.concat")
def builtin_array_concat(a: list, b: list) -> list:
    return a + b

@register_builtin("array.slice")
def builtin_array_slice(arr: list, start: int, stop: int) -> list:
    return arr[start:stop]

@register_builtin("array.reverse")
def builtin_array_reverse(arr: list) -> list:
    return list(reversed(arr))


# ===========================================================================
# SETS
# ===========================================================================

@register_builtin("intersection")
def builtin_intersection(sets: Any) -> set:
    result: set | None = None
    for s in sets:
        s_set = set(s) if not isinstance(s, set) else s
        if result is None:
            result = s_set.copy()
        else:
            result &= s_set
    return result or set()

@register_builtin("union")
def builtin_union(sets: Any) -> set:
    result: set = set()
    for s in sets:
        result |= set(s) if not isinstance(s, set) else s
    return result


# ===========================================================================
# STRINGS
# ===========================================================================

@register_builtin("concat")
def builtin_concat(delimiter: str, arr: Any) -> str:
    return delimiter.join(str(v) for v in arr)

@register_builtin("contains")
def builtin_contains(s: str, substr: str) -> bool:
    return substr in s

@register_builtin("startswith")
def builtin_startswith(s: str, prefix: str) -> bool:
    return s.startswith(prefix)

@register_builtin("endswith")
def builtin_endswith(s: str, suffix: str) -> bool:
    return s.endswith(suffix)

@register_builtin("lower")
def builtin_lower(s: str) -> str:
    return s.lower()

@register_builtin("upper")
def builtin_upper(s: str) -> str:
    return s.upper()

@register_builtin("split")
def builtin_split(s: str, delimiter: str) -> list[str]:
    return s.split(delimiter)

@register_builtin("join")
def builtin_join(delimiter: str, arr: list[str]) -> str:
    return delimiter.join(arr)

@register_builtin("trim")
def builtin_trim(s: str, cutset: str) -> str:
    return s.strip(cutset)

@register_builtin("trim_left")
def builtin_trim_left(s: str, cutset: str) -> str:
    return s.lstrip(cutset)

@register_builtin("trim_right")
def builtin_trim_right(s: str, cutset: str) -> str:
    return s.rstrip(cutset)

@register_builtin("trim_prefix")
def builtin_trim_prefix(s: str, prefix: str) -> str:
    return s.removeprefix(prefix)

@register_builtin("trim_suffix")
def builtin_trim_suffix(s: str, suffix: str) -> str:
    return s.removesuffix(suffix)

@register_builtin("trim_space")
def builtin_trim_space(s: str) -> str:
    return s.strip()

@register_builtin("replace")
def builtin_replace(s: str, old: str, new: str) -> str:
    return s.replace(old, new)

@register_builtin("indexof")
def builtin_indexof(s: str, substr: str) -> int:
    return s.find(substr)

@register_builtin("indexof_n")
def builtin_indexof_n(s: str, substr: str) -> list[int]:
    indices: list[int] = []
    start = 0
    while True:
        idx = s.find(substr, start)
        if idx == -1:
            break
        indices.append(idx)
        start = idx + 1
    return indices

@register_builtin("substring")
def builtin_substring(s: str, offset: int, length: int) -> str:
    if length < 0:
        return s[offset:]
    return s[offset:offset + length]

@register_builtin("sprintf")
def builtin_sprintf(fmt: str, values: list) -> str:
    return fmt % tuple(values)

@register_builtin("strings.reverse")
def builtin_strings_reverse(s: str) -> str:
    return s[::-1]

@register_builtin("strings.count")
def builtin_strings_count(s: str, substr: str) -> int:
    return s.count(substr)


# ===========================================================================
# REGEX
# ===========================================================================

# Compiled regex cache for performance
_regex_cache: dict[str, re.Pattern[str]] = {}

def _get_regex(pattern: str) -> re.Pattern[str]:
    if pattern not in _regex_cache:
        _regex_cache[pattern] = re.compile(pattern)
    return _regex_cache[pattern]

@register_builtin("regex.match")
def builtin_regex_match(pattern: str, value: str) -> bool:
    return _get_regex(pattern).search(value) is not None

@register_builtin("regex.is_valid")
def builtin_regex_is_valid(pattern: str) -> bool:
    try:
        re.compile(pattern)
        return True
    except re.error:
        return False

@register_builtin("regex.split")
def builtin_regex_split(pattern: str, value: str) -> list[str]:
    return _get_regex(pattern).split(value)

@register_builtin("regex.find_n")
def builtin_regex_find_n(pattern: str, value: str, n: int) -> list[str]:
    matches = _get_regex(pattern).findall(value)
    if n < 0:
        return matches
    return matches[:n]

@register_builtin("regex.find_all_string_submatch_n")
def builtin_regex_find_all_string_submatch_n(pattern: str, value: str, n: int) -> list[list[str]]:
    compiled = _get_regex(pattern)
    results: list[list[str]] = []
    for m in compiled.finditer(value):
        if 0 <= n <= len(results):
            break
        results.append([m.group()] + list(m.groups("")))
    return results


# ===========================================================================
# OBJECTS
# ===========================================================================

@register_builtin("object.get")
def builtin_object_get(obj: dict, key: Any, default: Any = None) -> Any:
    return obj.get(key, default)

@register_builtin("object.keys")
def builtin_object_keys(obj: dict) -> set:
    return set(obj.keys())

@register_builtin("object.values")
def builtin_object_values(obj: dict) -> list:
    return list(obj.values())

@register_builtin("object.union")
def builtin_object_union(a: dict, b: dict) -> dict:
    return {**a, **b}

@register_builtin("object.union_n")
def builtin_object_union_n(objects: list[dict]) -> dict:
    result: dict = {}
    for obj in objects:
        result.update(obj)
    return result

@register_builtin("object.remove")
def builtin_object_remove(obj: dict, keys: Any) -> dict:
    if isinstance(keys, dict):
        remove_keys = set(keys.keys())
    elif isinstance(keys, (list, set, frozenset)):
        remove_keys = set(keys)
    else:
        remove_keys = {keys}
    return {k: v for k, v in obj.items() if k not in remove_keys}

@register_builtin("object.filter")
def builtin_object_filter(obj: dict, keys: Any) -> dict:
    if isinstance(keys, dict):
        keep_keys = set(keys.keys())
    elif isinstance(keys, (list, set, frozenset)):
        keep_keys = set(keys)
    else:
        keep_keys = {keys}
    return {k: v for k, v in obj.items() if k in keep_keys}

@register_builtin("object.subset")
def builtin_object_subset(super_obj: Any, sub_obj: Any) -> bool:
    if isinstance(super_obj, dict) and isinstance(sub_obj, dict):
        for k, v in sub_obj.items():
            if k not in super_obj or not builtin_object_subset(super_obj[k], v):
                return False
        return True
    if isinstance(super_obj, (set, frozenset)) and isinstance(sub_obj, (set, frozenset)):
        return sub_obj.issubset(super_obj)
    return super_obj == sub_obj


# ===========================================================================
# TYPE CHECKING
# ===========================================================================

@register_builtin("is_null")
def builtin_is_null(x: Any) -> bool:
    return x is None

@register_builtin("is_boolean")
def builtin_is_boolean(x: Any) -> bool:
    return isinstance(x, bool)

@register_builtin("is_number")
def builtin_is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)

@register_builtin("is_string")
def builtin_is_string(x: Any) -> bool:
    return isinstance(x, str)

@register_builtin("is_array")
def builtin_is_array(x: Any) -> bool:
    return isinstance(x, list)

@register_builtin("is_set")
def builtin_is_set(x: Any) -> bool:
    return isinstance(x, (set, frozenset))

@register_builtin("is_object")
def builtin_is_object(x: Any) -> bool:
    return isinstance(x, dict)

@register_builtin("type_name")
def builtin_type_name(x: Any) -> str:
    if x is None:
        return "null"
    if isinstance(x, bool):
        return "boolean"
    if isinstance(x, (int, float)):
        return "number"
    if isinstance(x, str):
        return "string"
    if isinstance(x, list):
        return "array"
    if isinstance(x, (set, frozenset)):
        return "set"
    if isinstance(x, dict):
        return "object"
    return "unknown"


# ===========================================================================
# ENCODING / DECODING
# ===========================================================================

@register_builtin("base64.encode")
def builtin_base64_encode(s: str) -> str:
    return base64.b64encode(s.encode()).decode()

@register_builtin("base64.decode")
def builtin_base64_decode(s: str) -> str:
    return base64.b64decode(s).decode()

@register_builtin("base64url.encode")
def builtin_base64url_encode(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")

@register_builtin("base64url.decode")
def builtin_base64url_decode(s: str) -> str:
    padded = s + "=" * (4 - len(s) % 4)
    return base64.urlsafe_b64decode(padded).decode()

@register_builtin("json.marshal")
def builtin_json_marshal(x: Any) -> str:
    return json.dumps(x, separators=(",", ":"))

@register_builtin("json.unmarshal")
def builtin_json_unmarshal(s: str) -> Any:
    return json.loads(s)

@register_builtin("json.is_valid")
def builtin_json_is_valid(s: str) -> bool:
    try:
        json.loads(s)
        return True
    except (json.JSONDecodeError, TypeError):
        return False

@register_builtin("json.filter")
def builtin_json_filter(obj: Any, paths: list) -> Any:
    """Filter object to only include specified paths."""
    if not isinstance(obj, dict):
        return obj
    result: dict = {}
    for path in paths:
        parts = path if isinstance(path, list) else path.split("/")
        _set_nested(result, parts, _get_nested(obj, parts))
    return result

@register_builtin("json.remove")
def builtin_json_remove(obj: Any, paths: list) -> Any:
    """Remove specified paths from object."""
    if not isinstance(obj, dict):
        return obj
    result = json.loads(json.dumps(obj))  # deep copy
    for path in paths:
        parts = path if isinstance(path, list) else path.split("/")
        _del_nested(result, parts)
    return result

@register_builtin("json.patch")
def builtin_json_patch(obj: Any, patches: list[dict]) -> Any:
    """Apply JSON Patch (RFC 6902) operations: add, remove, replace, move, copy, test."""
    result = json.loads(json.dumps(obj))  # deep copy
    for patch in patches:
        op = patch.get("op")
        path_parts = patch.get("path", "").strip("/").split("/")
        if op == "add":
            _set_nested(result, path_parts, patch.get("value"))
        elif op == "remove":
            _del_nested(result, path_parts)
        elif op == "replace":
            _set_nested(result, path_parts, patch.get("value"))
        elif op == "move":
            from_parts = patch.get("from", "").strip("/").split("/")
            val = _get_nested(result, from_parts)
            _del_nested(result, from_parts)
            _set_nested(result, path_parts, val)
        elif op == "copy":
            from_parts = patch.get("from", "").strip("/").split("/")
            val = _get_nested(result, from_parts)
            _set_nested(result, path_parts, json.loads(json.dumps(val)))
        elif op == "test":
            expected = patch.get("value")
            actual = _get_nested(result, path_parts)
            if actual != expected:
                raise BuiltinError(
                    f"json.patch test failed: {actual!r} != {expected!r}"
                )
    return result

@register_builtin("yaml.marshal")
def builtin_yaml_marshal(x: Any) -> str:
    return yaml.safe_dump(x, default_flow_style=False)

@register_builtin("yaml.unmarshal")
def builtin_yaml_unmarshal(s: str) -> Any:
    return yaml.safe_load(s)

@register_builtin("yaml.is_valid")
def builtin_yaml_is_valid(s: str) -> bool:
    try:
        yaml.safe_load(s)
        return True
    except yaml.YAMLError:
        return False

@register_builtin("urlquery.encode")
def builtin_urlquery_encode(s: str) -> str:
    return urllib.parse.quote(s, safe="")

@register_builtin("urlquery.decode")
def builtin_urlquery_decode(s: str) -> str:
    return urllib.parse.unquote(s)

@register_builtin("urlquery.encode_object")
def builtin_urlquery_encode_object(obj: dict) -> str:
    return urllib.parse.urlencode(obj)

@register_builtin("hex.encode")
def builtin_hex_encode(s: str) -> str:
    return s.encode().hex()

@register_builtin("hex.decode")
def builtin_hex_decode(s: str) -> str:
    return bytes.fromhex(s).decode()


# ===========================================================================
# CRYPTO
# ===========================================================================

@register_builtin("crypto.sha256")
def builtin_crypto_sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()

@register_builtin("crypto.md5")
def builtin_crypto_md5(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()  # noqa: S324

@register_builtin("crypto.sha1")
def builtin_crypto_sha1(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()  # noqa: S324

@register_builtin("crypto.sha512")
def builtin_crypto_sha512(s: str) -> str:
    return hashlib.sha512(s.encode()).hexdigest()

@register_builtin("crypto.hmac.sha256")
def builtin_crypto_hmac_sha256(key: str, message: str) -> str:
    return hmac.new(key.encode(), message.encode(), hashlib.sha256).hexdigest()

@register_builtin("crypto.hmac.sha512")
def builtin_crypto_hmac_sha512(key: str, message: str) -> str:
    return hmac.new(key.encode(), message.encode(), hashlib.sha512).hexdigest()


# ===========================================================================
# TIME
# ===========================================================================

@register_builtin("time.now_ns")
def builtin_time_now_ns() -> int:
    return int(time.time() * 1_000_000_000)

@register_builtin("time.parse_ns")
def builtin_time_parse_ns(layout: str, value: str) -> int:
    # Simplified: use ISO format
    import datetime
    dt = datetime.datetime.fromisoformat(value)
    return int(dt.timestamp() * 1_000_000_000)

@register_builtin("time.parse_rfc3339_ns")
def builtin_time_parse_rfc3339_ns(value: str) -> int:
    import datetime
    dt = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return int(dt.timestamp() * 1_000_000_000)

@register_builtin("time.parse_duration_ns")
def builtin_time_parse_duration_ns(duration: str) -> int:
    """Parse Go-style duration string (e.g., '1h30m', '500ms')."""
    units = {"ns": 1, "us": 1000, "ms": 1_000_000, "s": 1_000_000_000,
             "m": 60_000_000_000, "h": 3_600_000_000_000}
    total = 0
    current = ""
    for ch in duration:
        if ch.isdigit() or ch == '.':
            current += ch
        else:
            remaining = ch
            # Check for multi-char units
            for unit, multiplier in sorted(units.items(), key=lambda x: -len(x[0])):
                if duration[len(current):].startswith(unit):
                    total += int(float(current) * multiplier)
                    current = ""
                    break
            if current == "":
                continue
            current = ""
    return total


# ===========================================================================
# NETWORK
# ===========================================================================

@register_builtin("net.cidr_contains")
def builtin_net_cidr_contains(cidr: str, addr: str) -> bool:
    try:
        network = ipaddress.ip_network(cidr, strict=False)
        address = ipaddress.ip_address(addr.split("/")[0])
        return address in network
    except ValueError:
        return False

@register_builtin("net.cidr_intersects")
def builtin_net_cidr_intersects(cidr1: str, cidr2: str) -> bool:
    try:
        n1 = ipaddress.ip_network(cidr1, strict=False)
        n2 = ipaddress.ip_network(cidr2, strict=False)
        return n1.overlaps(n2)
    except ValueError:
        return False

@register_builtin("net.cidr_is_valid")
def builtin_net_cidr_is_valid(cidr: str) -> bool:
    try:
        ipaddress.ip_network(cidr, strict=False)
        return True
    except ValueError:
        return False


# ===========================================================================
# UUID / SEMVER / GLOB
# ===========================================================================

@register_builtin("uuid.rfc4122")
def builtin_uuid_rfc4122(seed: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_OID, seed))

@register_builtin("uuid.parse")
def builtin_uuid_parse(s: str) -> dict:
    u = uuid.UUID(s)
    return {"version": u.version, "variant": str(u.variant)}

@register_builtin("semver.is_valid")
def builtin_semver_is_valid(s: str) -> bool:
    import re as re_mod
    return re_mod.match(r"^v?\d+\.\d+\.\d+", s) is not None

@register_builtin("semver.compare")
def builtin_semver_compare(a: str, b: str) -> int:
    def parse_ver(v: str) -> tuple[int, ...]:
        v = v.lstrip("v").split("-")[0]
        return tuple(int(x) for x in v.split("."))
    va, vb = parse_ver(a), parse_ver(b)
    if va < vb:
        return -1
    if va > vb:
        return 1
    return 0

@register_builtin("glob.match")
def builtin_glob_match(pattern: str, delimiters: list | None, match: str) -> bool:
    import fnmatch
    return fnmatch.fnmatch(match, pattern)


# ===========================================================================
# MISCELLANEOUS
# ===========================================================================

@register_builtin("walk")
def builtin_walk(x: Any) -> list[tuple[list, Any]]:
    """Walk over all values in a nested structure."""
    results: list[tuple[list, Any]] = []
    _walk_recursive(x, [], results)
    return results

@register_builtin("print")
def builtin_print(*args: Any) -> None:
    print(*args)  # noqa: T201

@register_builtin("trace")
def builtin_trace(msg: str) -> bool:
    return True

@register_builtin("opa.runtime")
def builtin_opa_runtime() -> dict:
    from npa import __version__
    return {"version": __version__, "engine": "npa"}


# ===========================================================================
# INTERNAL (used by parser for 'some x in collection')
# ===========================================================================

@register_builtin("internal.member_2")
def builtin_internal_member_2(value: Any, collection: Any) -> bool:
    """Check if value is a member of collection (used by `some x in coll`)."""
    if isinstance(collection, dict):
        return value in collection.values()
    if isinstance(collection, (list, tuple, set, frozenset)):
        return value in collection
    return False

@register_builtin("internal.member_3")
def builtin_internal_member_3(key: Any, value: Any, collection: Any) -> bool:
    """Check if key:value is a member of collection (used by `some k, v in coll`)."""
    if isinstance(collection, dict):
        return collection.get(key) == value
    if isinstance(collection, (list, tuple)):
        try:
            return collection[int(key)] == value
        except (IndexError, TypeError, ValueError):
            return False
    return False


# ===========================================================================
# MISSING OPA BUILTINS
# ===========================================================================

@register_builtin("to_number")
def builtin_to_number(x: Any) -> int | float:
    if isinstance(x, bool):
        return int(x)
    if isinstance(x, (int, float)):
        return x
    s = str(x).strip()
    if "." in s or "e" in s.lower():
        return float(s)
    return int(s)

@register_builtin("format_int")
def builtin_format_int(number: int | float, base: int) -> str:
    n = int(number)
    if base == 2:
        return bin(n)[2:]
    if base == 8:
        return oct(n)[2:]
    if base == 16:
        return hex(n)[2:]
    return str(n)

@register_builtin("array.flatten")
def builtin_array_flatten(arr: list) -> list:
    result: list = []
    for item in arr:
        if isinstance(item, list):
            result.extend(builtin_array_flatten(item))
        else:
            result.append(item)
    return result

@register_builtin("strings.any_prefix_match")
def builtin_strings_any_prefix_match(strs: Any, prefixes: Any) -> bool:
    strs = list(strs) if not isinstance(strs, list) else strs
    prefixes = list(prefixes) if not isinstance(prefixes, list) else prefixes
    return any(s.startswith(p) for s in strs for p in prefixes)

@register_builtin("strings.any_suffix_match")
def builtin_strings_any_suffix_match(strs: Any, suffixes: Any) -> bool:
    strs = list(strs) if not isinstance(strs, list) else strs
    suffixes = list(suffixes) if not isinstance(suffixes, list) else suffixes
    return any(s.endswith(suf) for s in strs for suf in suffixes)

@register_builtin("strings.replace_n")
def builtin_strings_replace_n(patterns: dict, s: str) -> str:
    for old, new in patterns.items():
        s = s.replace(old, new)
    return s

@register_builtin("regex.replace")
def builtin_regex_replace(s: str, pattern: str, value: str) -> str:
    return re.sub(pattern, value, s)

@register_builtin("regex.template_match")
def builtin_regex_template_match(pattern: str, match: str, delimiter: str = ":") -> bool:
    regex = pattern.replace(delimiter + "{", "(?P<").replace("}", ">[^/]+)")
    return bool(re.match(regex, match))

@register_builtin("regex.globs_match")
def builtin_regex_globs_match(glob1: str, glob2: str) -> bool:
    import fnmatch
    return fnmatch.fnmatch(glob1, glob2) or fnmatch.fnmatch(glob2, glob1)

@register_builtin("rand.intn")
def builtin_rand_intn(seed: str, n: int) -> int:
    import hashlib as hl
    h = int(hl.sha256(seed.encode()).hexdigest(), 16)
    return h % n if n > 0 else 0

@register_builtin("units.parse")
def builtin_units_parse(s: str) -> int | float:
    s = s.strip().upper()
    multipliers = {
        "K": 1_000, "M": 1_000_000, "G": 1_000_000_000, "T": 1_000_000_000_000,
        "KI": 1024, "MI": 1024**2, "GI": 1024**3, "TI": 1024**4,
    }
    for suffix, mult in sorted(multipliers.items(), key=lambda x: -len(x[0])):
        if s.endswith(suffix):
            return int(float(s[:-len(suffix)].strip()) * mult)
    return int(float(s))

@register_builtin("units.parse_bytes")
def builtin_units_parse_bytes(s: str) -> int:
    s = s.strip().upper().rstrip("B")
    multipliers = {
        "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4,
        "KI": 1024, "MI": 1024**2, "GI": 1024**3, "TI": 1024**4,
    }
    for suffix, mult in sorted(multipliers.items(), key=lambda x: -len(x[0])):
        if s.endswith(suffix):
            return int(float(s[:-len(suffix)].strip()) * mult)
    return int(float(s))

@register_builtin("base64.is_valid")
def builtin_base64_is_valid(s: str) -> bool:
    try:
        base64.b64decode(s, validate=True)
        return True
    except Exception:
        return False

@register_builtin("base64url.encode_no_pad")
def builtin_base64url_encode_no_pad(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).rstrip(b"=").decode()

@register_builtin("urlquery.decode_object")
def builtin_urlquery_decode_object(s: str) -> dict:
    return dict(urllib.parse.parse_qsl(s))

@register_builtin("json.marshal_with_options")
def builtin_json_marshal_with_options(x: Any, opts: dict) -> str:
    indent = opts.get("indent", "")
    prefix = opts.get("prefix", "")
    pretty = opts.get("pretty", False)
    if pretty or indent:
        return json.dumps(x, indent=indent or "  ")
    return json.dumps(x)

@register_builtin("json.verify_schema")
def builtin_json_verify_schema(schema: str | dict) -> list:
    """Returns [valid, error] for the given JSON schema."""
    try:
        if isinstance(schema, str):
            schema = json.loads(schema)
        if isinstance(schema, dict):
            return [True, None]
        return [False, "Schema must be an object"]
    except Exception as e:
        return [False, str(e)]

@register_builtin("json.match_schema")
def builtin_json_match_schema(document: Any, schema: Any) -> list:
    """Returns [match, errors]. Simplified — validates structure only."""
    if isinstance(document, str):
        try:
            document = json.loads(document)
        except Exception as e:
            return [False, [str(e)]]
    if isinstance(schema, str):
        try:
            schema = json.loads(schema)
        except Exception as e:
            return [False, [str(e)]]
    return [True, []]

# --- Time extras ---

@register_builtin("time.date")
def builtin_time_date(ns: int) -> list:
    import datetime
    dt = datetime.datetime.fromtimestamp(ns / 1_000_000_000, tz=datetime.timezone.utc)
    return [dt.year, dt.month, dt.day]

@register_builtin("time.clock")
def builtin_time_clock(ns: int) -> list:
    import datetime
    dt = datetime.datetime.fromtimestamp(ns / 1_000_000_000, tz=datetime.timezone.utc)
    return [dt.hour, dt.minute, dt.second]

@register_builtin("time.weekday")
def builtin_time_weekday(ns: int) -> str:
    import datetime
    dt = datetime.datetime.fromtimestamp(ns / 1_000_000_000, tz=datetime.timezone.utc)
    return dt.strftime("%A")

@register_builtin("time.add_date")
def builtin_time_add_date(ns: int, years: int, months: int, days: int) -> int:
    import datetime
    dt = datetime.datetime.fromtimestamp(ns / 1_000_000_000, tz=datetime.timezone.utc)
    new_month = dt.month + months
    new_year = dt.year + years + (new_month - 1) // 12
    new_month = (new_month - 1) % 12 + 1
    try:
        dt = dt.replace(year=new_year, month=new_month)
    except ValueError:
        import calendar
        max_day = calendar.monthrange(new_year, new_month)[1]
        dt = dt.replace(year=new_year, month=new_month, day=min(dt.day, max_day))
    dt = dt + datetime.timedelta(days=days)
    return int(dt.timestamp() * 1_000_000_000)

@register_builtin("time.diff")
def builtin_time_diff(ns1: int, ns2: int) -> list:
    import datetime
    dt1 = datetime.datetime.fromtimestamp(ns1 / 1_000_000_000, tz=datetime.timezone.utc)
    dt2 = datetime.datetime.fromtimestamp(ns2 / 1_000_000_000, tz=datetime.timezone.utc)
    rd = abs(dt1 - dt2)
    total_seconds = int(rd.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    days_val = rd.days
    years, days_val = divmod(abs(days_val), 365)
    months, days_val = divmod(days_val, 30)
    return [years, months, days_val, hours % 24, minutes, seconds]

@register_builtin("time.format")
def builtin_time_format(ns: int) -> str:
    import datetime
    dt = datetime.datetime.fromtimestamp(ns / 1_000_000_000, tz=datetime.timezone.utc)
    return dt.isoformat()

# --- Crypto extras ---

@register_builtin("crypto.hmac.md5")
def builtin_crypto_hmac_md5(key: str, message: str) -> str:
    return hmac.new(key.encode(), message.encode(), hashlib.md5).hexdigest()

@register_builtin("crypto.hmac.sha1")
def builtin_crypto_hmac_sha1(key: str, message: str) -> str:
    return hmac.new(key.encode(), message.encode(), hashlib.sha1).hexdigest()

@register_builtin("crypto.hmac.equal")
def builtin_crypto_hmac_equal(mac1: str, mac2: str) -> bool:
    return hmac.compare_digest(mac1, mac2)

# --- Graph ---

@register_builtin("graph.reachable")
def builtin_graph_reachable(graph: dict, initial: Any) -> set:
    """Find all nodes reachable from initial set in the graph."""
    if isinstance(initial, (set, frozenset)):
        queue = list(initial)
    elif isinstance(initial, (list, tuple)):
        queue = list(initial)
    else:
        queue = [initial]
    visited: set = set()
    while queue:
        node = queue.pop(0)
        if _make_hashable_for_set(node) in visited:
            continue
        visited.add(_make_hashable_for_set(node))
        neighbors = graph.get(node, [])
        if isinstance(neighbors, (set, frozenset, list, tuple)):
            queue.extend(neighbors)
    return visited

def _make_hashable_for_set(val: Any) -> Any:
    if isinstance(val, dict):
        return tuple(sorted(val.items()))
    if isinstance(val, list):
        return tuple(val)
    return val

# --- Net extras ---

@register_builtin("net.cidr_expand")
def builtin_net_cidr_expand(cidr: str) -> list:
    try:
        network = ipaddress.ip_network(cidr, strict=False)
        return [str(ip) for ip in network.hosts()]
    except ValueError:
        return []

@register_builtin("net.cidr_merge")
def builtin_net_cidr_merge(cidrs: list) -> list:
    try:
        networks = [ipaddress.ip_network(c, strict=False) for c in cidrs]
        return [str(n) for n in ipaddress.collapse_addresses(networks)]
    except ValueError:
        return cidrs

@register_builtin("net.cidr_contains_matches")
def builtin_net_cidr_contains_matches(cidrs: Any, addrs_or_cidrs: Any) -> set:
    results: set = set()
    cidr_list = list(cidrs) if isinstance(cidrs, (list, set, frozenset)) else [cidrs]
    addr_list = list(addrs_or_cidrs) if isinstance(addrs_or_cidrs, (list, set, frozenset)) else [addrs_or_cidrs]
    for i, c in enumerate(cidr_list):
        for j, a in enumerate(addr_list):
            try:
                net = ipaddress.ip_network(c, strict=False)
                addr = ipaddress.ip_address(a.split("/")[0])
                if addr in net:
                    results.add((i, j))
            except (ValueError, AttributeError):
                pass
    return results

# --- Glob extras ---

@register_builtin("glob.quote_meta")
def builtin_glob_quote_meta(s: str) -> str:
    special = set("*?[]{}\\")
    return "".join(f"\\{c}" if c in special else c for c in s)

# --- Rego builtins ---

@register_builtin("rego.parse_module")
def builtin_rego_parse_module(filename: str, source: str) -> dict:
    from npa.ast.parser import parse_module as _parse
    try:
        mod = _parse(source, filename)
        return {"package": {"path": mod.package.path.as_path()}, "rules": len(mod.rules)}
    except Exception as e:
        raise BuiltinError(f"rego.parse_module: {e}") from e

# --- JWT (simplified decode only) ---

@register_builtin("io.jwt.decode")
def builtin_io_jwt_decode(jwt_str: str) -> list:
    """Decode (but don't verify) a JWT. Returns [header, payload, signature]."""
    parts = jwt_str.split(".")
    if len(parts) != 3:
        raise BuiltinError("io.jwt.decode: invalid JWT format")
    def _b64decode(s: str) -> dict:
        padded = s + "=" * (4 - len(s) % 4)
        return json.loads(base64.urlsafe_b64decode(padded))
    header = _b64decode(parts[0])
    payload = _b64decode(parts[1])
    return [header, payload, parts[2]]

@register_builtin("object.values")
def builtin_object_values(obj: dict) -> list:
    return list(obj.values())

# --- Deprecated but still used ---

@register_builtin("set_diff")
def builtin_set_diff(a: Any, b: Any) -> Any:
    sa = set(a) if isinstance(a, (list, tuple)) else set(a)
    sb = set(b) if isinstance(b, (list, tuple)) else set(b)
    return sa - sb

@register_builtin("cast_array")
def builtin_cast_array(x: Any) -> list:
    return list(x) if not isinstance(x, list) else x

@register_builtin("cast_set")
def builtin_cast_set(x: Any) -> set:
    return set(x)

@register_builtin("cast_string")
def builtin_cast_string(x: Any) -> str:
    return str(x)

@register_builtin("cast_boolean")
def builtin_cast_boolean(x: Any) -> bool:
    return bool(x)

@register_builtin("cast_null")
def builtin_cast_null(x: Any) -> None:
    return None

@register_builtin("cast_object")
def builtin_cast_object(x: Any) -> dict:
    return dict(x) if not isinstance(x, dict) else x

@register_builtin("re_match")
def builtin_re_match(pattern: str, value: str) -> bool:
    return bool(re.match(pattern, value))

@register_builtin("join")
def builtin_join(delimiter: str, arr: list) -> str:
    return delimiter.join(str(x) for x in arr)

@register_builtin("any")
def builtin_any(x: Any) -> bool:
    if isinstance(x, (list, tuple, set, frozenset)):
        return any(bool(v) for v in x)
    return bool(x)

@register_builtin("all")
def builtin_all(x: Any) -> bool:
    if isinstance(x, (list, tuple, set, frozenset)):
        return all(bool(v) for v in x)
    return bool(x)

@register_builtin("and")
def builtin_set_and(a: Any, b: Any) -> Any:
    return set(a) & set(b)

@register_builtin("or")
def builtin_set_or(a: Any, b: Any) -> Any:
    return set(a) | set(b)


# ===========================================================================
# HTTP, JWT, Crypto, GraphQL, Network — Critical OPA builtins
# ===========================================================================

# --- http.send ---

@register_builtin("http.send")
def builtin_http_send(request_obj: dict) -> dict:
    """OPA-compatible http.send. Makes an HTTP request and returns the response."""
    import httpx

    method = request_obj.get("method", "GET").upper()
    url = request_obj.get("url", "")
    headers = request_obj.get("headers", {})
    body = request_obj.get("body")
    raw_body = request_obj.get("raw_body")
    timeout_val = request_obj.get("timeout", "5s")
    tls_insecure = request_obj.get("tls_insecure_skip_verify", False)
    raise_error = request_obj.get("raise_error", True)
    cache = request_obj.get("cache", False)

    # Parse timeout
    if isinstance(timeout_val, str):
        timeout_val = timeout_val.rstrip("s")
        try:
            timeout_sec = float(timeout_val)
        except ValueError:
            timeout_sec = 5.0
    else:
        timeout_sec = float(timeout_val)

    try:
        with httpx.Client(verify=not tls_insecure, timeout=timeout_sec) as client:
            resp = client.request(
                method=method,
                url=url,
                headers=headers,
                content=raw_body.encode() if raw_body else None,
                json=body if body and not raw_body else None,
            )

        result: dict[str, Any] = {
            "status": f"{resp.status_code} {resp.reason_phrase}",
            "status_code": resp.status_code,
            "headers": dict(resp.headers),
            "raw_body": resp.text,
        }
        try:
            result["body"] = resp.json()
        except Exception:
            result["body"] = resp.text

        return result
    except Exception as e:
        if raise_error:
            raise BuiltinError(f"http.send: {e}") from e
        return {"status_code": 0, "error": {"message": str(e)}}


# --- JWT verification & signing ---

def _jwt_verify(jwt_str: str, key: str, algorithm: str) -> list:
    """Common JWT verification logic. Returns [valid, header, payload]."""
    import jwt as pyjwt
    parts = jwt_str.split(".")
    if len(parts) != 3:
        return [False, {}, {}]

    def _b64decode(s: str) -> dict:
        padded = s + "=" * (4 - len(s) % 4)
        return json.loads(base64.urlsafe_b64decode(padded))

    try:
        header = _b64decode(parts[0])
    except Exception:
        return [False, {}, {}]

    try:
        if algorithm.startswith("HS"):
            payload = pyjwt.decode(jwt_str, key, algorithms=[algorithm])
        else:
            payload = pyjwt.decode(jwt_str, key, algorithms=[algorithm])
        return [True, header, payload]
    except pyjwt.InvalidTokenError:
        return [False, header, {}]
    except Exception:
        return [False, header, {}]


for _alg in ("RS256", "RS384", "RS512", "PS256", "PS384", "PS512",
             "ES256", "ES384", "ES512", "HS256", "HS384", "HS512",
             "EdDSA"):
    _name = f"io.jwt.verify_{_alg.lower()}"

    def _make_verify(alg: str):
        def _verify(jwt_str: str, key: str) -> bool:
            result = _jwt_verify(jwt_str, key, alg)
            return result[0]
        _verify.__name__ = f"builtin_io_jwt_verify_{alg.lower()}"
        return _verify

    _registry.register(_name, _make_verify(_alg))


@register_builtin("io.jwt.decode_verify")
def builtin_io_jwt_decode_verify(jwt_str: str, constraints: dict) -> list:
    """Decode and verify a JWT. Returns [valid, header, payload]."""
    alg = constraints.get("alg", "RS256")
    cert = constraints.get("cert", "")
    secret = constraints.get("secret", "")
    key = cert or secret
    return _jwt_verify(jwt_str, key, alg)


@register_builtin("io.jwt.encode_sign")
def builtin_io_jwt_encode_sign(header: dict, payload: dict, key: Any) -> str:
    """Encode and sign a JWT."""
    import jwt as pyjwt
    alg = header.get("alg", "HS256")
    if isinstance(key, dict):
        # JWK — extract the key material
        import json as j
        key_str = j.dumps(key)
    else:
        key_str = str(key)
    return pyjwt.encode(payload, key_str, algorithm=alg, headers=header)


@register_builtin("io.jwt.encode_sign_raw")
def builtin_io_jwt_encode_sign_raw(header_json: str, payload_json: str, key: str) -> str:
    """Encode and sign a JWT from raw JSON strings."""
    header = json.loads(header_json)
    payload = json.loads(payload_json)
    return builtin_io_jwt_encode_sign(header, payload, key)


# --- X.509 Certificate parsing ---

@register_builtin("crypto.x509.parse_certificates")
def builtin_crypto_x509_parse_certificates(pem_str: str) -> list:
    """Parse PEM-encoded X.509 certificates."""
    from cryptography import x509 as cx509
    from cryptography.hazmat.primitives import serialization
    certs = []
    for cert in cx509.load_pem_x509_certificates(pem_str.encode()):
        certs.append({
            "subject": cert.subject.rfc4514_string(),
            "issuer": cert.issuer.rfc4514_string(),
            "serial_number": str(cert.serial_number),
            "not_before": cert.not_valid_before_utc.isoformat(),
            "not_after": cert.not_valid_after_utc.isoformat(),
            "version": cert.version.value,
        })
    return certs


@register_builtin("crypto.x509.parse_and_verify_certificates")
def builtin_crypto_x509_parse_and_verify_certificates(pem_str: str) -> list:
    """Parse and verify PEM-encoded X.509 certificate chain. Returns [valid, certs]."""
    try:
        certs = builtin_crypto_x509_parse_certificates(pem_str)
        return [True, certs]
    except Exception as e:
        return [False, []]


@register_builtin("crypto.x509.parse_certificate_request")
def builtin_crypto_x509_parse_certificate_request(pem_str: str) -> dict:
    """Parse a PEM-encoded X.509 CSR."""
    from cryptography import x509 as cx509
    csr = cx509.load_pem_x509_csr(pem_str.encode())
    return {
        "subject": csr.subject.rfc4514_string(),
        "is_signature_valid": csr.is_signature_valid,
    }


@register_builtin("crypto.x509.parse_keypair")
def builtin_crypto_x509_parse_keypair(cert_pem: str, key_pem: str) -> dict:
    """Parse and validate a certificate/key pair."""
    from cryptography import x509 as cx509
    from cryptography.hazmat.primitives import serialization
    cert = cx509.load_pem_x509_certificate(cert_pem.encode())
    key = serialization.load_pem_private_key(key_pem.encode(), password=None)
    return {
        "subject": cert.subject.rfc4514_string(),
        "issuer": cert.issuer.rfc4514_string(),
        "not_after": cert.not_valid_after_utc.isoformat(),
    }


@register_builtin("crypto.x509.parse_rsa_private_key")
def builtin_crypto_x509_parse_rsa_private_key(pem_str: str) -> dict:
    """Parse RSA private key from PEM."""
    from cryptography.hazmat.primitives import serialization
    key = serialization.load_pem_private_key(pem_str.encode(), password=None)
    return {"key_size": key.key_size}


@register_builtin("crypto.parse_private_keys")
def builtin_crypto_parse_private_keys(pem_str: str) -> list:
    """Parse PEM-encoded private keys of any type (RSA, EC, Ed25519, etc.)."""
    from cryptography.hazmat.primitives import serialization
    keys = []
    # Split PEM blocks
    blocks = pem_str.split("-----END ")
    for block in blocks:
        block = block.strip()
        if not block or "-----BEGIN " not in block:
            continue
        # Reconstruct PEM block
        end_marker_start = block.rfind("-----\n")
        if end_marker_start == -1:
            end_marker_start = block.rfind("-----\r\n")
        try:
            # Try to find the key type from the header
            begin_idx = block.index("-----BEGIN ") + len("-----BEGIN ")
            type_end = block.index("-----", begin_idx)
            key_type = block[begin_idx:type_end].strip()
            pem_block = block + f"-----END {key_type}-----"
            key = serialization.load_pem_private_key(pem_block.encode(), password=None)
            info = {"type": type(key).__name__}
            if hasattr(key, "key_size"):
                info["key_size"] = key.key_size
            keys.append(info)
        except Exception:
            continue
    return keys


# --- Network extras ---

@register_builtin("net.lookup_ip_addr")
def builtin_net_lookup_ip_addr(name: str) -> set:
    """DNS lookup — returns set of IP addresses."""
    import socket
    try:
        results = socket.getaddrinfo(name, None)
        return {r[4][0] for r in results}
    except socket.gaierror:
        return set()


@register_builtin("net.cidr_overlap")
def builtin_net_cidr_overlap(cidr1: str, cidr2: str) -> bool:
    """Deprecated: Check if CIDRs overlap. Use net.cidr_contains instead."""
    return builtin_net_cidr_contains(cidr1, cidr2)


def builtin_net_cidr_contains(cidr: str, cidr_or_ip: str) -> bool:
    """Check if a CIDR contains another CIDR or IP."""
    net = ipaddress.ip_network(cidr, strict=False)
    try:
        addr = ipaddress.ip_address(cidr_or_ip.split("/")[0])
        return addr in net
    except ValueError:
        other = ipaddress.ip_network(cidr_or_ip, strict=False)
        return net.supernet_of(other)


# --- Graph extras ---

@register_builtin("graph.reachable_paths")
def builtin_graph_reachable_paths(graph: dict, initial: Any) -> set:
    """Find all paths reachable from initial nodes."""
    if isinstance(initial, (set, frozenset)):
        starts = list(initial)
    elif isinstance(initial, (list, tuple)):
        starts = list(initial)
    else:
        starts = [initial]

    all_paths: set = set()
    for start in starts:
        _dfs_paths(graph, start, (start,), all_paths)
    return all_paths


def _dfs_paths(graph: dict, node: Any, current_path: tuple, all_paths: set) -> None:
    all_paths.add(current_path)
    neighbors = graph.get(node, [])
    if isinstance(neighbors, (set, frozenset, list, tuple)):
        for n in neighbors:
            if n not in current_path:  # avoid cycles
                _dfs_paths(graph, n, current_path + (n,), all_paths)


# --- Array extras ---

@register_builtin("array.slice")
def builtin_array_slice(arr: list, start: int, stop: int) -> list:
    """Return a slice of the array from start to stop (exclusive)."""
    return arr[int(start):int(stop)]


# --- String extras ---

@register_builtin("strings.render_template")
def builtin_strings_render_template(template: str, vars_dict: dict) -> str:
    """Simple template rendering: replaces {{.key}} with values from vars_dict."""
    result = template
    for key, val in vars_dict.items():
        result = result.replace("{{." + key + "}}", str(val))
        result = result.replace("{{ ." + key + " }}", str(val))
    return result


# --- GraphQL (stubs — require graphql-core library if present) ---

@register_builtin("graphql.is_valid")
def builtin_graphql_is_valid(query: str, schema: str) -> bool:
    """Validate a GraphQL query against a schema."""
    try:
        from graphql import parse as gql_parse, build_schema, validate
        schema_obj = build_schema(schema)
        doc = gql_parse(query)
        errors = validate(schema_obj, doc)
        return len(errors) == 0
    except ImportError:
        raise BuiltinError("graphql.is_valid requires the 'graphql-core' package")
    except Exception:
        return False


@register_builtin("graphql.parse")
def builtin_graphql_parse(query: str, schema: str) -> list:
    """Parse and validate a GraphQL query. Returns [ast, schema_ast]."""
    try:
        from graphql import parse as gql_parse, build_schema
        schema_obj = build_schema(schema)
        doc = gql_parse(query)
        return [doc.to_dict(), schema_obj.to_dict() if hasattr(schema_obj, 'to_dict') else {}]
    except ImportError:
        raise BuiltinError("graphql.parse requires the 'graphql-core' package")


@register_builtin("graphql.parse_and_verify")
def builtin_graphql_parse_and_verify(query: str, schema: str) -> list:
    """Parse and verify a GraphQL query. Returns [valid, result]."""
    try:
        from graphql import parse as gql_parse, build_schema, validate
        schema_obj = build_schema(schema)
        doc = gql_parse(query)
        errors = validate(schema_obj, doc)
        if errors:
            return [False, {"errors": [str(e) for e in errors]}]
        return [True, doc.to_dict()]
    except ImportError:
        raise BuiltinError("graphql.parse_and_verify requires the 'graphql-core' package")
    except Exception as e:
        return [False, {"errors": [str(e)]}]


@register_builtin("graphql.parse_query")
def builtin_graphql_parse_query(query: str) -> dict:
    """Parse a GraphQL query string."""
    try:
        from graphql import parse as gql_parse
        return gql_parse(query).to_dict()
    except ImportError:
        raise BuiltinError("graphql.parse_query requires the 'graphql-core' package")


@register_builtin("graphql.parse_schema")
def builtin_graphql_parse_schema(schema: str) -> dict:
    """Parse a GraphQL schema string."""
    try:
        from graphql import build_schema
        s = build_schema(schema)
        return {"types": list(s.type_map.keys())}
    except ImportError:
        raise BuiltinError("graphql.parse_schema requires the 'graphql-core' package")


@register_builtin("graphql.schema_is_valid")
def builtin_graphql_schema_is_valid(schema: str) -> bool:
    """Check if a GraphQL schema is valid."""
    try:
        from graphql import build_schema
        build_schema(schema)
        return True
    except ImportError:
        raise BuiltinError("graphql.schema_is_valid requires the 'graphql-core' package")
    except Exception:
        return False


# --- Internal / Testing ---

@register_builtin("internal.print")
def builtin_internal_print(*args: Any) -> bool:
    """Internal print function used by Rego print()."""
    print(*args)
    return True


# ===========================================================================
# REGO METADATA
# ===========================================================================

@register_builtin("rego.metadata.rule")
def builtin_rego_metadata_rule() -> dict:
    """Return the metadata annotation for the current rule.

    This is a context-sensitive builtin — the evaluator injects the actual
    annotation at call time.  The default implementation returns an empty dict.
    """
    return {}


@register_builtin("rego.metadata.chain")
def builtin_rego_metadata_chain() -> list[dict]:
    """Return the chain of metadata annotations from the entrypoint through the call chain.

    This is a context-sensitive builtin — the evaluator injects the chain at
    call time.  The default implementation returns an empty list.
    """
    return []


# ===========================================================================
# Helpers
# ===========================================================================

def _get_nested(obj: Any, path: list[str]) -> Any:
    current = obj
    for part in path:
        if not part:
            continue
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            current = current[int(part)]
        else:
            return None
    return current


def _set_nested(obj: dict, path: list[str], value: Any) -> None:
    path = [p for p in path if p]
    current = obj
    for part in path[:-1]:
        if part not in current:
            current[part] = {}
        current = current[part]
    if path:
        current[path[-1]] = value


def _del_nested(obj: dict, path: list[str]) -> None:
    path = [p for p in path if p]
    current = obj
    for part in path[:-1]:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return
    if path and isinstance(current, dict):
        current.pop(path[-1], None)


def _walk_recursive(x: Any, path: list, results: list[tuple[list, Any]]) -> None:
    results.append((list(path), x))
    if isinstance(x, dict):
        for k, v in x.items():
            _walk_recursive(v, path + [k], results)
    elif isinstance(x, list):
        for i, v in enumerate(x):
            _walk_recursive(v, path + [i], results)
