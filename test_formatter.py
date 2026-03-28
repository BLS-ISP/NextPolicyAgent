"""Test the Rego formatter."""

from npa.ast.parser import parse_module
from npa.format.formatter import format_module

# Test 1: Basic formatting round-trip
policy = '''package test

import data.foo
import data.bar

default allow = false

allow {
    input.user == "admin"
}
'''

mod = parse_module(policy, "test.rego")
formatted = format_module(mod)
print("=== Formatted output ===")
print(formatted)
print("========================")

# Verify round-trip: format again should be same
mod2 = parse_module(formatted, "test2.rego")
formatted2 = format_module(mod2)
assert formatted == formatted2, "Round-trip formatting failed!"
print("  OK  Round-trip formatting stable")

# Test 2: Imports sorted
policy2 = '''package test2

import data.zebra
import data.alpha
import data.mid

allow = true
'''

mod3 = parse_module(policy2, "test3.rego")
formatted3 = format_module(mod3)
lines = formatted3.split("\n")
import_lines = [l for l in lines if l.startswith("import")]
assert import_lines[0] == "import data.alpha", f"Sort failed: {import_lines}"
assert import_lines[1] == "import data.mid", f"Sort failed: {import_lines}"
assert import_lines[2] == "import data.zebra", f"Sort failed: {import_lines}"
print("  OK  Imports sorted correctly")

# Test 3: Default rule
policy3 = '''package test3

default x = 5
'''

mod4 = parse_module(policy3, "test4.rego")
formatted4 = format_module(mod4)
assert "default x = 5" in formatted4, f"Default rule missing: {formatted4}"
print("  OK  Default rule formatted")

# Test 4: Else chain
policy4 = '''package test4

role = "admin" {
    input.role == "admin"
} else = "user" {
    input.role == "user"
} else = "guest"
'''

mod5 = parse_module(policy4, "test5.rego")
formatted5 = format_module(mod5)
assert "else" in formatted5, f"Else missing: {formatted5}"
print("  OK  Else chain formatted")

# Test 5: Annotations preserved
policy5 = '''package test5

# METADATA
# title: My Rule
# description: Does stuff

allow {
    true
}
'''

mod6 = parse_module(policy5, "test6.rego")
formatted6 = format_module(mod6)
assert "# METADATA" in formatted6, f"Annotations missing: {formatted6}"
assert "# title: My Rule" in formatted6, f"Title missing: {formatted6}"
print("  OK  Annotations preserved")

print("\nAll formatter tests passed!")
