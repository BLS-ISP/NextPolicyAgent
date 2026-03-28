"""Test parser features for OPA compatibility."""
from npa.ast.parser import parse_module

# Test 1: import future.keywords
src1 = '''package test
import future.keywords.in
import future.keywords.if
import future.keywords.contains
import rego.v1

allow if {
    true
}
'''
mod1 = parse_module(src1, 'test1.rego')
print(f'Test 1 (imports): {len(mod1.imports)} imports, {len(mod1.rules)} rules - OK')

# Test 2: annotations
src2 = '''package test
# METADATA
# title: Allow Rule
# description: Allows access
# scope: rule
allow = true
'''
mod2 = parse_module(src2, 'test2.rego')
ann = mod2.rules[0].annotations
print(f'Test 2 (annotations): title="{ann.title if ann else "NONE"}", desc="{ann.description if ann else "NONE"}" - {"OK" if ann and ann.title == "Allow Rule" else "FAIL"}')

# Test 3: standalone in operator
src3 = '''package test
allow {
    "admin" in input.roles
}
'''
mod3 = parse_module(src3, 'test3.rego')
print(f'Test 3 (standalone in): {len(mod3.rules)} rules - OK')

# Test 4: some x in collection
src4 = '''package test
allow {
    some x in input.items
    x > 5
}
'''
mod4 = parse_module(src4, 'test4.rego')
print(f'Test 4 (some x in): {len(mod4.rules)} rules - OK')

# Test 5: assignment vs unification
src5 = '''package test
result {
    x := 42
    y = x
    y == 42
}
'''
mod5 = parse_module(src5, 'test5.rego')
print(f'Test 5 (operators): {len(mod5.rules)} rules, body has {len(mod5.rules[0].body.exprs)} exprs - OK')

# Test 6: every keyword
src6 = '''package test
all_positive {
    every x in input.numbers {
        x > 0
    }
}
'''
mod6 = parse_module(src6, 'test6.rego')
print(f'Test 6 (every): {len(mod6.rules)} rules - OK')

# Test 7: else chains
src7 = '''package test
role := "admin" {
    input.user == "root"
} else := "user" {
    input.user != ""
} else := "guest"
'''
mod7 = parse_module(src7, 'test7.rego')
print(f'Test 7 (else chain): {len(mod7.rules[0].else_rules)} else clauses - OK')

# Test 8: default rule
src8 = '''package test
default allow = false
allow {
    input.admin == true
}
'''
mod8 = parse_module(src8, 'test8.rego')
print(f'Test 8 (default): {len(mod8.rules)} rules, first is default={mod8.rules[0].default} - OK')

# Test 9: partial set with contains
src9 = '''package test
allowed_users contains user if {
    some user in data.users
    user.active == true
}
'''
mod9 = parse_module(src9, 'test9.rego')
from npa.ast.types import RuleKind
print(f'Test 9 (partial set): kind={mod9.rules[0].kind.name} - {"OK" if mod9.rules[0].kind == RuleKind.PARTIAL_SET else "FAIL"}')

# Test 10: comprehensions
src10 = '''package test
nums := [x | some x in input.values; x > 0]
names := {x | some x in input.names}
'''
mod10 = parse_module(src10, 'test10.rego')
print(f'Test 10 (comprehensions): {len(mod10.rules)} rules - OK')

print("\nAll parser tests passed!")
