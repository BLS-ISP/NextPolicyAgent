"""Tests for newly implemented features (Phase 8):
- with data.* overrides
- Partial Evaluation
- Rule Indexing
- Delta Bundles
- Plugin lifecycle
- CLI capabilities
"""

import sys
import json
import traceback

passed = 0
failed = 0
errors = []


def ok(name, msg=""):
    global passed
    passed += 1
    print(f"  OK   {name}{': ' + msg if msg else ''}")


def fail(name, msg):
    global failed
    failed += 1
    errors.append(f"{name}: {msg}")
    print(f"  FAIL {name}: {msg}")


# =============================================================================
# 1. with data.* overrides
# =============================================================================
print("\n=== with data.* overrides ===")

from npa.ast.parser import parse_module
from npa.ast.compiler import Compiler
from npa.eval.topdown import TopdownEvaluator, UndefinedError
from npa.storage.inmemory import InMemoryStorage


def test_with_data():
    policy = '''package test
import future.keywords.if

default allow = false
allow if {
    data.test.config.enabled == true
}

override_allow if {
    allow with data.test.config as {"enabled": true}
}
'''
    mod = parse_module(policy, "test_with_data.rego")
    comp = Compiler()
    comp.compile({"test_with_data": mod})
    store = InMemoryStorage()
    ev = TopdownEvaluator(comp, store)

    # allow should be false because config.enabled doesn't exist
    try:
        result = ev.eval_query("data.test.allow")
        if result is False:
            ok("with_data_allow_default", f"allow=False (default)")
        else:
            fail("with_data_allow_default", f"expected False, got {result}")
    except UndefinedError:
        fail("with_data_allow_default", "should have default value, got undefined")

    # override_allow should be true (data override sets enabled=true)
    try:
        result = ev.eval_query("data.test.override_allow")
        ok("with_data_allow_override", f"override_allow={result}")
    except Exception as e:
        fail("with_data_allow_override", str(e))


def test_with_data_simple():
    """Simple test: with data.x as y overrides a data reference."""
    policy = '''package test
import future.keywords.if

config := {"debug": false}

is_debug if {
    data.test.config.debug == true
}

force_debug if {
    is_debug with data.test.config as {"debug": true}
}
'''
    mod = parse_module(policy, "test_with_data_simple.rego")
    comp = Compiler()
    comp.compile({"test_with_data_simple": mod})
    store = InMemoryStorage()
    ev = TopdownEvaluator(comp, store)

    # is_debug should be false (config.debug == false)
    try:
        ev.eval_query("data.test.is_debug")
        fail("with_data_simple_false", "should be undefined")
    except UndefinedError:
        ok("with_data_simple_false", "is_debug is correctly undefined")

    # force_debug should be true (data override makes debug=true)
    try:
        result = ev.eval_query("data.test.force_debug")
        if result is True:
            ok("with_data_simple_override", "force_debug=True via with data override")
        else:
            fail("with_data_simple_override", f"expected True, got {result}")
    except Exception as e:
        fail("with_data_simple_override", str(e))


test_with_data()
test_with_data_simple()


# =============================================================================
# 2. Partial Evaluation
# =============================================================================
print("\n=== Partial Evaluation ===")

from npa.eval.partial import PartialEvaluator, PartialResult


def test_partial_eval_constant():
    """When no unknowns apply, PE should return the full result."""
    policy = '''package test
allow = true
'''
    mod = parse_module(policy, "pe_const.rego")
    comp = Compiler()
    comp.compile({"pe_const": mod})
    store = InMemoryStorage()

    pe = PartialEvaluator(comp, store, unknowns=["input"])
    result = pe.partial_eval("data.test.allow")
    if result.queries == [[True]]:
        ok("pe_constant", "returns [[True]]")
    else:
        fail("pe_constant", f"expected [[True]], got {result.queries}")


def test_partial_eval_with_unknowns():
    """When the query depends on unknowns, PE should return residual queries."""
    policy = '''package test
import future.keywords.if

allow if {
    input.user == "admin"
}
'''
    mod = parse_module(policy, "pe_unknown.rego")
    comp = Compiler()
    comp.compile({"pe_unknown": mod})
    store = InMemoryStorage()

    pe = PartialEvaluator(comp, store, unknowns=["input"])
    result = pe.partial_eval("data.test.allow")
    # Should have at least one residual query
    if len(result.queries) > 0:
        ok("pe_unknowns", f"got {len(result.queries)} residual query(ies)")
    else:
        fail("pe_unknowns", "expected residual queries")


def test_partial_eval_known_input():
    """With fully known input, PE should resolve to a constant."""
    policy = '''package test
import future.keywords.if

allow if {
    input.role == "admin"
}
'''
    mod = parse_module(policy, "pe_known.rego")
    comp = Compiler()
    comp.compile({"pe_known": mod})
    store = InMemoryStorage()

    pe = PartialEvaluator(comp, store, unknowns=["input"])
    result = pe.partial_eval("data.test.allow", input_data={"role": "admin"})
    if result.queries == [[True]]:
        ok("pe_known_input", "fully resolved with known input")
    else:
        fail("pe_known_input", f"expected [[True]], got {result.queries}")


test_partial_eval_constant()
test_partial_eval_with_unknowns()
test_partial_eval_known_input()


# =============================================================================
# 3. Rule Indexing
# =============================================================================
print("\n=== Rule Indexing ===")

from npa.ast.compiler import RuleIndex, _extract_equality_guard, _NO_VALUE


def test_rule_indexing():
    """Compiler builds indices for rules with equality guards."""
    policy = '''package authz
import future.keywords.if

allow if {
    input.method == "GET"
    input.path == "/public"
}

allow if {
    input.role == "admin"
}

default deny = false
'''
    mod = parse_module(policy, "idx_test.rego")
    comp = Compiler()
    comp.compile({"idx_test": mod})

    # Check that indices were built
    all_rules = comp.get_all_rules()
    if "authz.allow" in all_rules:
        idx = comp._rule_indices.get("authz.allow")
        if idx:
            ok("rule_index_built", f"index for authz.allow exists")
        else:
            fail("rule_index_built", "no index built")
    else:
        fail("rule_index_built", "authz.allow not in rules")

    # Test indexed lookup
    candidates_get = comp.get_indexed_rules(
        ["authz", "allow"], input_data={"method": "GET", "path": "/public"}
    )
    if len(candidates_get) >= 1:
        ok("rule_index_candidates", f"got {len(candidates_get)} candidates for GET")
    else:
        fail("rule_index_candidates", "expected at least 1 candidate")


def test_rule_index_guard_extraction():
    """Test extraction of equality guards from rule bodies."""
    policy = '''package test
import future.keywords.if

r1 if {
    input.x == "a"
}

r2 if {
    true
}
'''
    mod = parse_module(policy, "guard_test.rego")
    comp = Compiler()
    comp.compile({"guard_test": mod})

    rules = comp.get_rules(["test", "r1"])
    if rules:
        guard = _extract_equality_guard(rules[0])
        if guard and guard[1] == "a":
            ok("guard_extraction", f"extracted guard {guard}")
        else:
            fail("guard_extraction", f"expected ('input.x', 'a'), got {guard}")
    else:
        fail("guard_extraction", "no rules for test.r1")


test_rule_indexing()
test_rule_index_guard_extraction()


# =============================================================================
# 4. Delta Bundles
# =============================================================================
print("\n=== Delta Bundles ===")

from npa.bundle.bundle import (
    Bundle, BundleFile, BundleManifest, DeltaPatch, apply_delta_bundle,
)


def test_delta_bundle_apply():
    """Delta bundle add/remove operations."""
    store = InMemoryStorage({"existing": {"key": "value"}})
    policies = {"authz.rego": "package authz\nallow = true"}

    # Create a delta bundle
    delta_ops = [
        {"op": "add", "path": "/data/new_data", "value": {"hello": "world"}},
        {"op": "remove", "path": "/policy/authz.rego"},
    ]
    delta_json = json.dumps(delta_ops).encode()
    delta_bundle = Bundle(
        files=[BundleFile(path="delta.json", content=delta_json)],
        manifest=BundleManifest(delta=True),
    )

    updated_policies = apply_delta_bundle(delta_bundle, store, policies)

    # Check that new data was added
    try:
        val = store.read(["new_data"])
        if val == {"hello": "world"}:
            ok("delta_add_data", "new data added")
        else:
            fail("delta_add_data", f"expected {{'hello': 'world'}}, got {val}")
    except Exception as e:
        fail("delta_add_data", str(e))

    # Check that policy was removed
    if "authz.rego" not in updated_policies:
        ok("delta_remove_policy", "policy removed")
    else:
        fail("delta_remove_policy", "policy not removed")


test_delta_bundle_apply()


# =============================================================================
# 5. Plugin System
# =============================================================================
print("\n=== Plugin System ===")

import asyncio
from npa.plugins.manager import (
    PluginManager, PluginState, BundlePlugin, DecisionLogPlugin,
    StatusPlugin, DiscoveryPlugin,
)


def test_plugin_lifecycle():
    """Test plugin registration, start, stop cycle."""
    async def _run():
        pm = PluginManager()
        pm.register(StatusPlugin())
        pm.register(DecisionLogPlugin())
        pm.register(DiscoveryPlugin())

        # All should be NOT_READY before start
        statuses = pm.statuses()
        all_not_ready = all(s.state == PluginState.NOT_READY for s in statuses.values())
        if all_not_ready:
            ok("plugin_initial_state", "all NOT_READY")
        else:
            fail("plugin_initial_state", "not all NOT_READY")

        await pm.start_all()

        statuses = pm.statuses()
        all_ok = all(s.state == PluginState.OK for s in statuses.values())
        if all_ok:
            ok("plugin_started", "all OK after start")
        else:
            fail("plugin_started", f"states: {[(n, s.state.name) for n, s in statuses.items()]}")

        await pm.stop_all()

        statuses = pm.statuses()
        all_stopped = all(s.state == PluginState.NOT_READY for s in statuses.values())
        if all_stopped:
            ok("plugin_stopped", "all NOT_READY after stop")
        else:
            fail("plugin_stopped", "not all NOT_READY after stop")

    asyncio.run(_run())


def test_decision_log_record():
    """Test decision log plugin recording."""
    async def _run():
        plugin = DecisionLogPlugin({"console": False})
        pm = PluginManager()
        await plugin.start(pm)

        plugin.record({
            "decision_id": "test-123",
            "query": "data.test.allow",
            "input": {"user": "admin"},
            "result": True,
        })

        if len(plugin._buffer) == 1:
            ok("decision_log_record", "entry recorded")
        else:
            fail("decision_log_record", f"expected 1 entry, got {len(plugin._buffer)}")

        await plugin.stop()

    asyncio.run(_run())


def test_status_plugin_bundle_tracking():
    """Test status plugin tracks bundle updates."""
    plugin = StatusPlugin()
    plugin.record_bundle("authz", "rev-abc123")

    if "authz" in plugin._bundle_statuses:
        info = plugin._bundle_statuses["authz"]
        if info["active_revision"] == "rev-abc123":
            ok("status_bundle_tracking", "bundle revision tracked")
        else:
            fail("status_bundle_tracking", f"wrong revision: {info}")
    else:
        fail("status_bundle_tracking", "bundle not tracked")


test_plugin_lifecycle()
test_decision_log_record()
test_status_plugin_bundle_tracking()


# =============================================================================
# 6. Overlay Store (with data.* internals)
# =============================================================================
print("\n=== Overlay Store ===")

from npa.eval.topdown import _OverlayStore


def test_overlay_store():
    """Overlay store correctly intercepts reads for overridden paths."""
    base_store = InMemoryStorage({"servers": {"web": {"port": 80}}})

    overrides = {
        "servers.web.port": (["servers", "web", "port"], 443),
    }
    overlay = _OverlayStore(base_store, overrides)

    # Direct hit
    val = overlay.read(["servers", "web", "port"])
    if val == 443:
        ok("overlay_direct", f"port={val}")
    else:
        fail("overlay_direct", f"expected 443, got {val}")

    # Parent path should merge
    val = overlay.read(["servers", "web"])
    if isinstance(val, dict) and val.get("port") == 443:
        ok("overlay_parent_merge", f"got {val}")
    else:
        fail("overlay_parent_merge", f"expected merged dict with port=443, got {val}")

    # Unrelated path should pass through
    base_store2 = InMemoryStorage({"other": "data", "servers": {"web": {"port": 80}}})
    overlay2 = _OverlayStore(base_store2, overrides)
    val = overlay2.read(["other"])
    if val == "data":
        ok("overlay_passthrough", "unrelated path passes through")
    else:
        fail("overlay_passthrough", f"expected 'data', got {val}")


test_overlay_store()


# =============================================================================
# Summary
# =============================================================================
print(f"\n{'=' * 50}")
print(f"PASSED: {passed}")
print(f"FAILED: {failed}")
if errors:
    print("\nErrors:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("\nAll Phase 8 tests passed!")
