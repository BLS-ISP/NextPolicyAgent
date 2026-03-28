"""End-to-end evaluator tests covering OPA-compatible Rego features."""
import sys, traceback
from npa.ast.parser import parse_module
from npa.ast.compiler import Compiler
from npa.eval.topdown import TopdownEvaluator, UndefinedError
from npa.storage.inmemory import InMemoryStorage

passed = 0
failed = 0
errors = []

def run(name, policy, query, input_data=None, store_data=None, expected=None):
    global passed, failed
    try:
        mod = parse_module(policy, f"{name}.rego")
        comp = Compiler()
        comp.compile({name: mod})
        store = InMemoryStorage(store_data or {})
        ev = TopdownEvaluator(comp, store)
        result = ev.eval_query(query, input_data=input_data)
        if expected is not None and result != expected:
            print(f"  FAIL {name}: expected {expected!r}, got {result!r}")
            errors.append(f"{name}: expected {expected!r}, got {result!r}")
            failed += 1
        else:
            print(f"  OK   {name}: {result!r}")
            passed += 1
    except Exception as e:
        print(f"  FAIL {name}: {type(e).__name__}: {e}")
        errors.append(f"{name}: {type(e).__name__}: {e}")
        failed += 1

def run_undefined(name, policy, query, input_data=None, store_data=None):
    """Expect UndefinedError."""
    global passed, failed
    try:
        mod = parse_module(policy, f"{name}.rego")
        comp = Compiler()
        comp.compile({name: mod})
        store = InMemoryStorage(store_data or {})
        ev = TopdownEvaluator(comp, store)
        result = ev.eval_query(query, input_data=input_data)
        print(f"  FAIL {name}: expected undefined, got {result!r}")
        errors.append(f"{name}: expected undefined, got {result!r}")
        failed += 1
    except UndefinedError:
        print(f"  OK   {name}: correctly undefined")
        passed += 1
    except Exception as e:
        print(f"  FAIL {name}: {type(e).__name__}: {e}")
        errors.append(f"{name}: {type(e).__name__}: {e}")
        failed += 1

# === BASIC RULES ===
print("=== Basic Rules ===")
run("bool_true", '''package test
allow = true''', "data.test.allow", expected=True)

run("bool_false", '''package test
deny = false''', "data.test.deny", expected=False)

run("string_value", '''package test
greeting = "hello"''', "data.test.greeting", expected="hello")

run("number_value", '''package test
count = 42''', "data.test.count", expected=42)

# === INPUT ===
print("\n=== Input Access ===")
run("input_simple", '''package test
user = input.name''', "data.test.user", input_data={"name": "alice"}, expected="alice")

run("input_nested", '''package test
role = input.user.role''', "data.test.role",
    input_data={"user": {"role": "admin"}}, expected="admin")

# === CONDITIONAL RULES ===
print("\n=== Conditional Rules ===")
run("cond_true", '''package test
allow {
    input.role == "admin"
}''', "data.test.allow", input_data={"role": "admin"}, expected=True)

run_undefined("cond_false", '''package test
allow {
    input.role == "admin"
}''', "data.test.allow", input_data={"role": "user"})

# === DEFAULT RULES ===
print("\n=== Default Rules ===")
run("default_fallback", '''package test
default allow = false
allow {
    input.admin == true
}''', "data.test.allow", input_data={"admin": False}, expected=False)

run("default_override", '''package test
default allow = false
allow {
    input.admin == true
}''', "data.test.allow", input_data={"admin": True}, expected=True)

# === ELSE CHAINS ===
print("\n=== Else Chains ===")
run("else_first", '''package test
role := "admin" {
    input.user == "root"
} else := "user" {
    input.user != ""
} else := "guest"
''', "data.test.role", input_data={"user": "root"}, expected="admin")

run("else_second", '''package test
role := "admin" {
    input.user == "root"
} else := "user" {
    input.user != ""
} else := "guest"
''', "data.test.role", input_data={"user": "bob"}, expected="user")

run("else_last", '''package test
role := "admin" {
    input.user == "root"
} else := "user" {
    input.user != ""
} else := "guest"
''', "data.test.role", input_data={"user": ""}, expected="guest")

# === ASSIGNMENT vs UNIFICATION vs COMPARISON ===
print("\n=== Operators ===")
run("assign", '''package test
result {
    x := 42
    x == 42
}''', "data.test.result", expected=True)

run("unify", '''package test
result {
    x = 42
    x == 42
}''', "data.test.result", expected=True)

run_undefined("comparison_fail", '''package test
result {
    1 == 2
}''', "data.test.result")  # should be undefined

# === ARITHMETIC ===
print("\n=== Arithmetic ===")
run("addition", '''package test
result = 2 + 3''', "data.test.result", expected=5)

run("subtraction", '''package test
result = 10 - 3''', "data.test.result", expected=7)

run("multiply", '''package test
result = 4 * 5''', "data.test.result", expected=20)

run("division", '''package test
result = 10 / 2''', "data.test.result", expected=5.0)

run("modulo", '''package test
result = 10 % 3''', "data.test.result", expected=1)

# === BUILTINS ===
print("\n=== Builtins ===")
run("count_array", '''package test
result = count([1, 2, 3])''', "data.test.result", expected=3)

run("count_string", '''package test
result = count("hello")''', "data.test.result", expected=5)

run("lower", '''package test
result = lower("HELLO")''', "data.test.result", expected="hello")

run("upper", '''package test
result = upper("hello")''', "data.test.result", expected="HELLO")

run("concat_builtin", '''package test
result = concat(", ", ["a", "b", "c"])''', "data.test.result", expected="a, b, c")

run("sprintf_test", '''package test
result = sprintf("hello %s, you are %d", ["world", 42])''', "data.test.result", expected="hello world, you are 42")

run("trim_space", '''package test
result = trim_space("  hello  ")''', "data.test.result", expected="hello")

run("contains_str", '''package test
result {
    contains("foobar", "bar")
}''', "data.test.result", expected=True)

run("startswith_test", '''package test
result {
    startswith("hello world", "hello")
}''', "data.test.result", expected=True)

run("replace_test", '''package test
result = replace("hello world", "world", "rego")''', "data.test.result", expected="hello rego")

run("split_test", '''package test
result = split("a.b.c", ".")''', "data.test.result", expected=["a", "b", "c"])

run("sort_test", '''package test
result = sort([3, 1, 2])''', "data.test.result", expected=[1, 2, 3])

run("max_test", '''package test
result = max([3, 1, 5, 2])''', "data.test.result", expected=5)

run("min_test", '''package test
result = min([3, 1, 5, 2])''', "data.test.result", expected=1)

run("sum_test", '''package test
result = sum([1, 2, 3, 4])''', "data.test.result", expected=10)

run("product_test", '''package test
result = product([2, 3, 4])''', "data.test.result", expected=24)

run("abs_test", '''package test
result = abs(-5)''', "data.test.result", expected=5)

run("round_test", '''package test
result = round(3.7)''', "data.test.result", expected=4)

run("to_number_test", '''package test
result = to_number("42")''', "data.test.result", expected=42)

run("array_concat", '''package test
result = array.concat([1, 2], [3, 4])''', "data.test.result", expected=[1, 2, 3, 4])

run("object_get", '''package test
result = object.get({"a": 1}, "a", "default")''', "data.test.result", expected=1)

run("object_get_default", '''package test
result = object.get({"a": 1}, "b", "default")''', "data.test.result", expected="default")

run("is_string", '''package test
result {
    is_string("hello")
}''', "data.test.result", expected=True)

run("is_number", '''package test
result {
    is_number(42)
}''', "data.test.result", expected=True)

run("type_name_test", '''package test
result = type_name("hello")''', "data.test.result", expected="string")

run("json_marshal", '''package test
result = json.marshal({"a": 1})''', "data.test.result", expected='{"a":1}')

run("base64_encode", '''package test
result = base64.encode("hello")''', "data.test.result", expected="aGVsbG8=")

run("base64_decode", '''package test
result = base64.decode("aGVsbG8=")''', "data.test.result", expected="hello")

run("regex_match", '''package test
result {
    regex.match("[a-z]+", "hello")
}''', "data.test.result", expected=True)

run("numbers_range", '''package test
result = numbers.range(1, 5)''', "data.test.result", expected=[1, 2, 3, 4, 5])

# === DATA STORE ===
print("\n=== Data Store ===")
run("data_access", '''package test
result = data.users[0].name''', "data.test.result",
    store_data={"users": [{"name": "alice"}, {"name": "bob"}]},
    expected="alice")

# === COMPREHENSIONS ===
print("\n=== Comprehensions ===")
run("array_comp", '''package test
result = [x | some x in [1, 2, 3]; x > 1]''', "data.test.result",
    expected=[2, 3])

run("set_comp", '''package test
import future.keywords.in
names := {name | some name in input.users}
''', "data.test.names",
    input_data={"users": ["alice", "bob", "alice"]},
    expected={"alice", "bob"})

# === NEGATION ===
print("\n=== Negation ===")
run("not_cond", '''package test
allow {
    not input.blocked
}''', "data.test.allow", input_data={"blocked": False}, expected=True)

run_undefined("not_cond_fail", '''package test
allow {
    not input.blocked
}''', "data.test.allow", input_data={"blocked": True})

# === SOME IN ===
print("\n=== Some In ===")
run("some_in_array", '''package test
allow {
    some x in input.roles
    x == "admin"
}''', "data.test.allow", input_data={"roles": ["user", "admin"]}, expected=True)

run_undefined("some_in_missing", '''package test
allow {
    some x in input.roles
    x == "superadmin"
}''', "data.test.allow", input_data={"roles": ["user", "admin"]})

# === STANDALONE IN ===
print("\n=== Standalone In ===")
run("standalone_in", '''package test
allow {
    "admin" in input.roles
}''', "data.test.allow", input_data={"roles": ["user", "admin"]}, expected=True)

run_undefined("standalone_in_miss", '''package test
allow {
    "superadmin" in input.roles
}''', "data.test.allow", input_data={"roles": ["user", "admin"]})

# === EVERY ===
print("\n=== Every ===")
run("every_all_match", '''package test
all_positive {
    every x in input.nums {
        x > 0
    }
}''', "data.test.all_positive", input_data={"nums": [1, 2, 3]}, expected=True)

run_undefined("every_some_fail", '''package test
all_positive {
    every x in input.nums {
        x > 0
    }
}''', "data.test.all_positive", input_data={"nums": [1, -2, 3]})

# === PARTIAL RULES (multiple definitions) ===
print("\n=== Partial Rules ===")
run("multiple_bodies", '''package test
allow {
    input.role == "admin"
}
allow {
    input.role == "superadmin"
}''', "data.test.allow", input_data={"role": "superadmin"}, expected=True)

# === FUNCTIONS ===
print("\n=== User Functions ===")
run("user_func", '''package test
greet(name) = msg {
    msg = concat("", ["Hello, ", name, "!"])
}
result = greet("World")''', "data.test.result", expected="Hello, World!")

# === OBJECT/ARRAY BUILTINS ===
print("\n=== Object/Array Builtins ===")
run("object_keys", '''package test
result = object.keys({"a": 1, "b": 2})''', "data.test.result", expected={"a", "b"})

run("object_remove", '''package test
result = object.remove({"a": 1, "b": 2, "c": 3}, {"b"})''', "data.test.result",
    expected={"a": 1, "c": 3})

run("object_union", '''package test
result = object.union({"a": 1}, {"b": 2, "a": 3})''', "data.test.result",
    expected={"a": 3, "b": 2})

run("array_reverse", '''package test
result = array.reverse([1, 2, 3])''', "data.test.result", expected=[3, 2, 1])

run("array_slice", '''package test
result = array.slice([0, 1, 2, 3, 4], 1, 3)''', "data.test.result", expected=[1, 2])

# === CRYPTO ===
print("\n=== Crypto ===")
run("crypto_md5", '''package test
result = crypto.md5("hello")''', "data.test.result", expected="5d41402abc4b2a76b9719d911017c592")

run("crypto_sha256", '''package test
result = crypto.sha256("hello")''', "data.test.result",
    expected="2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824")

# === SET OPERATIONS ===
print("\n=== Set Operations ===")
run("intersection", '''package test
result = intersection({{"a", "b", "c"}, {"b", "c", "d"}})''', "data.test.result",
    expected={"b", "c"})

run("union_test", '''package test
result = union({{"a", "b"}, {"b", "c"}})''', "data.test.result",
    expected={"a", "b", "c"})

# === REGEX ===
print("\n=== Regex ===")
run("regex_find", '''package test
result = regex.find_all_string_submatch_n("[0-9]+", "abc123def456", -1)''',
    "data.test.result", expected=[["123"], ["456"]])

# === STRING BUILTINS ===
print("\n=== String Builtins ===")
run("indexof_test", '''package test
result = indexof("hello world", "world")''', "data.test.result", expected=6)

run("substring_test", '''package test
result = substring("hello world", 6, 5)''', "data.test.result", expected="world")

run("trim_test", '''package test
result = trim("  hello  ", " ")''', "data.test.result", expected="hello")

run("trim_left", '''package test
result = trim_left("  hello", " ")''', "data.test.result", expected="hello")

run("trim_right", '''package test
result = trim_right("hello  ", " ")''', "data.test.result", expected="hello")

run("trim_prefix", '''package test
result = trim_prefix("hello world", "hello ")''', "data.test.result", expected="world")

run("trim_suffix", '''package test
result = trim_suffix("hello world", " world")''', "data.test.result", expected="hello")

# === REPORT ===
print(f"\n{'='*50}")
print(f"PASSED: {passed}")
print(f"FAILED: {failed}")
if errors:
    print(f"\nFailed tests:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("\nAll evaluator tests passed!")
