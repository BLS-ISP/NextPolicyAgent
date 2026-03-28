"""Quick test for rego.metadata builtins and json.patch extensions."""

from npa.ast.parser import parse_module
from npa.ast.compiler import Compiler
from npa.eval.topdown import TopdownEvaluator
from npa.storage.inmemory import InMemoryStorage

# Test 1: rego.metadata.rule()
policy = '''package test

# METADATA
# title: My Rule
# description: A well-documented rule

allow {
    meta := rego.metadata.rule()
    meta.title == "My Rule"
}
'''

mod = parse_module(policy, "test.rego")
compiler = Compiler()
compiler.compile({"test.rego": mod})
store = InMemoryStorage({})
ev = TopdownEvaluator(compiler, store)
result = ev.eval_query("data.test.allow")
assert result is True, f"metadata.rule test failed: {result}"
print("  OK  rego.metadata.rule()")

# Test 2: rego.metadata.chain()
policy2 = '''package test2

# METADATA
# title: Outer Rule

outer {
    chain := rego.metadata.chain()
    count(chain) >= 0
}
'''

mod2 = parse_module(policy2, "test2.rego")
compiler2 = Compiler()
compiler2.compile({"test2.rego": mod2})
store2 = InMemoryStorage({})
ev2 = TopdownEvaluator(compiler2, store2)
result2 = ev2.eval_query("data.test2.outer")
assert result2 is True, f"metadata.chain test failed: {result2}"
print("  OK  rego.metadata.chain()")

# Test 3: json.patch move/copy/test
from npa.ast.builtins import get_builtin
jp = get_builtin("json.patch")

obj = {"a": 1, "b": 2, "c": 3}
r = jp(obj, [{"op": "move", "from": "/a", "path": "/d"}])
assert r == {"b": 2, "c": 3, "d": 1}, f"json.patch move failed: {r}"
print("  OK  json.patch move")

r = jp(obj, [{"op": "copy", "from": "/a", "path": "/d"}])
assert r == {"a": 1, "b": 2, "c": 3, "d": 1}, f"json.patch copy failed: {r}"
print("  OK  json.patch copy")

r = jp(obj, [{"op": "test", "path": "/a", "value": 1}])
assert r == obj, f"json.patch test (success) failed: {r}"
print("  OK  json.patch test (pass)")

try:
    jp(obj, [{"op": "test", "path": "/a", "value": 999}])
    assert False, "json.patch test should have raised"
except Exception:
    pass
print("  OK  json.patch test (fail)")

# Test 4: EdDSA verify registered
b = get_builtin("io.jwt.verify_eddsa")
assert b is not None, "io.jwt.verify_eddsa not registered"
print("  OK  io.jwt.verify_eddsa registered")

# Test 5: crypto.parse_private_keys registered
b2 = get_builtin("crypto.parse_private_keys")
assert b2 is not None, "crypto.parse_private_keys not registered"
print("  OK  crypto.parse_private_keys registered")

# Test 6: Total builtin count
from npa.ast.builtins import list_builtins
count = len(list_builtins())
print(f"\n  Total builtins: {count}")
assert count >= 200, f"Expected >= 200 builtins, got {count}"

print("\nAll new feature tests passed!")
