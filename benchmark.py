"""NPA vs OPA Performance Benchmark Suite

Runs identical benchmarks against NPA (Python) and OPA (Go) to compare:
1. CLI eval performance (cold start + evaluation)
2. SDK/Library evaluation (hot path, no startup)
3. REST API throughput (concurrent requests)
4. Policy complexity scaling
5. Data size scaling
6. Startup time
"""

import json
import os
import signal
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error
from pathlib import Path
from statistics import mean, median, stdev

# Paths
SCRIPT_DIR = Path(__file__).parent
OPA_BIN = SCRIPT_DIR.parent / "opa.exe"
EXAMPLES_DIR = SCRIPT_DIR / "examples"

RESULTS = {}

def timer(func, *args, iterations=10, warmup=2, **kwargs):
    """Run function multiple times and return timing stats."""
    # Warmup
    for _ in range(warmup):
        func(*args, **kwargs)
    
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    
    return {
        "min": min(times),
        "max": max(times),
        "mean": mean(times),
        "median": median(times),
        "stdev": stdev(times) if len(times) > 1 else 0,
        "iterations": iterations,
        "times": times,
        "last_result": result,
    }


def run_cmd(cmd, timeout=30):
    """Run a command and return (stdout, stderr, returncode, elapsed)."""
    start = time.perf_counter()
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, shell=isinstance(cmd, str)
    )
    elapsed = time.perf_counter() - start
    return result.stdout, result.stderr, result.returncode, elapsed


# ═══════════════════════════════════════════════════════════════
# BENCHMARK 1: CLI Cold Start Eval
# ═══════════════════════════════════════════════════════════════

def bench_cli_eval():
    """Benchmark CLI evaluation (includes process startup)."""
    print("\n" + "=" * 60)
    print("BENCHMARK 1: CLI Cold-Start Evaluation")
    print("=" * 60)

    examples = [
        ("rbac", "data.rbac.authz"),
        ("http-api-authz", "data.httpapi.authz"),
        ("network-firewall", "data.network.firewall"),
        ("data-filtering", "data.filtering"),
    ]

    for name, query in examples:
        example_dir = EXAMPLES_DIR / name
        input_file = example_dir / "input.json"

        if not example_dir.exists():
            print(f"  SKIP {name}: directory not found")
            continue

        print(f"\n  [{name}] query: {query}")

        # NPA CLI
        npa_cmd = [
            sys.executable, "-m", "npa", "eval",
            "-d", str(example_dir),
            "-i", str(input_file),
            query
        ]
        npa_times = []
        for _ in range(5):
            _, _, rc, elapsed = run_cmd(npa_cmd)
            if rc == 0:
                npa_times.append(elapsed)
        
        # OPA CLI
        opa_cmd = [
            str(OPA_BIN), "eval",
            "-d", str(example_dir),
            "-i", str(input_file),
            query
        ]
        opa_times = []
        for _ in range(5):
            _, _, rc, elapsed = run_cmd(opa_cmd)
            if rc == 0:
                opa_times.append(elapsed)

        if npa_times and opa_times:
            npa_avg = mean(npa_times)
            opa_avg = mean(opa_times)
            RESULTS[f"cli_{name}"] = {
                "npa_avg_ms": npa_avg * 1000,
                "opa_avg_ms": opa_avg * 1000,
                "ratio": npa_avg / opa_avg if opa_avg > 0 else 0,
            }
            print(f"    NPA: {npa_avg*1000:.1f} ms (avg of {len(npa_times)})")
            print(f"    OPA: {opa_avg*1000:.1f} ms (avg of {len(opa_times)})")
            print(f"    Ratio: NPA is {npa_avg/opa_avg:.1f}x vs OPA")


# ═══════════════════════════════════════════════════════════════
# BENCHMARK 2: SDK/Library Hot-Path Evaluation
# ═══════════════════════════════════════════════════════════════

def bench_sdk_eval():
    """Benchmark NPA SDK evaluation (hot path, no startup overhead)."""
    print("\n" + "=" * 60)
    print("BENCHMARK 2: NPA SDK Hot-Path Evaluation")
    print("=" * 60)

    from npa.sdk.sdk import NPA

    examples = [
        ("rbac", "data.rbac.authz.allow", "data.rbac.authz"),
        ("http-api-authz", "data.httpapi.authz.allow", "data.httpapi.authz"),
        ("network-firewall", "data.network.firewall.decision", "data.network.firewall"),
        ("data-filtering", "data.filtering.summary", "data.filtering"),
    ]

    for name, bool_query, full_query in examples:
        example_dir = EXAMPLES_DIR / name
        if not example_dir.exists():
            continue

        input_data = json.loads((example_dir / "input.json").read_text(encoding="utf-8"))

        # Initialize engine and load policies (one-time)
        engine = NPA()
        for f in example_dir.glob("*.rego"):
            engine.load_policy(f.name, f.read_text(encoding="utf-8"))
        data_file = example_dir / "data.json"
        if data_file.exists():
            engine.set_data(json.loads(data_file.read_text(encoding="utf-8")))

        # Warm up
        for _ in range(10):
            engine.decide(full_query, input_data)

        # Benchmark
        iterations = 1000
        start = time.perf_counter()
        for _ in range(iterations):
            engine.decide(full_query, input_data)
        total = time.perf_counter() - start

        avg_us = (total / iterations) * 1_000_000
        ops_per_sec = iterations / total

        RESULTS[f"sdk_{name}"] = {
            "avg_us": avg_us,
            "ops_per_sec": ops_per_sec,
            "iterations": iterations,
        }
        print(f"\n  [{name}]")
        print(f"    Avg: {avg_us:.1f} µs/eval")
        print(f"    Throughput: {ops_per_sec:,.0f} evals/sec")


# ═══════════════════════════════════════════════════════════════
# BENCHMARK 3: Policy Complexity Scaling
# ═══════════════════════════════════════════════════════════════

def bench_complexity_scaling():
    """Benchmark how evaluation time scales with policy complexity."""
    print("\n" + "=" * 60)
    print("BENCHMARK 3: Policy Complexity Scaling")
    print("=" * 60)

    from npa.sdk.sdk import NPA

    complexities = [1, 5, 10, 25, 50, 100]

    for num_rules in complexities:
        # Generate policy with N rules
        rules = ["package bench", "default allow = false"]
        for i in range(num_rules):
            rules.append(f'allow if {{ input.role == "role_{i}" }}')
        policy = "\n".join(rules)

        engine = NPA()
        engine.load_policy("bench.rego", policy)

        # Input that matches the LAST rule (worst case)
        input_data = {"role": f"role_{num_rules - 1}"}

        # Warm up
        for _ in range(10):
            engine.decide("data.bench.allow", input_data)

        # Benchmark
        iterations = 500
        start = time.perf_counter()
        for _ in range(iterations):
            engine.decide("data.bench.allow", input_data)
        total = time.perf_counter() - start

        avg_us = (total / iterations) * 1_000_000
        RESULTS[f"complexity_{num_rules}"] = {"avg_us": avg_us, "num_rules": num_rules}
        print(f"  {num_rules:>3} rules: {avg_us:.1f} µs/eval")


# ═══════════════════════════════════════════════════════════════
# BENCHMARK 4: Data Size Scaling
# ═══════════════════════════════════════════════════════════════

def bench_data_scaling():
    """Benchmark how evaluation time scales with data size."""
    print("\n" + "=" * 60)
    print("BENCHMARK 4: Data Size Scaling")
    print("=" * 60)

    from npa.sdk.sdk import NPA

    sizes = [10, 100, 1000, 5000, 10000]

    policy = """package bench
import future.keywords.in
default allow = false
allow if {
    some grant in data.grants
    grant.user == input.user
    grant.action == input.action
}
"""

    for size in sizes:
        grants = [{"user": f"user_{i}", "action": "read"} for i in range(size)]
        # Last user match (worst case linear scan)
        grants[-1]["action"] = "write"
        
        engine = NPA()
        engine.load_policy("bench.rego", policy)
        engine.set_data({"grants": grants})

        input_data = {"user": f"user_{size - 1}", "action": "write"}

        # Warm up
        for _ in range(5):
            engine.decide("data.bench.allow", input_data)

        # Benchmark
        iterations = 200
        start = time.perf_counter()
        for _ in range(iterations):
            engine.decide("data.bench.allow", input_data)
        total = time.perf_counter() - start

        avg_us = (total / iterations) * 1_000_000
        RESULTS[f"datasize_{size}"] = {"avg_us": avg_us, "data_records": size}
        print(f"  {size:>6} records: {avg_us:.1f} µs/eval")


# ═══════════════════════════════════════════════════════════════
# BENCHMARK 5: REST API Throughput (Sequential)
# ═══════════════════════════════════════════════════════════════

def _wait_for_port(port, host="localhost", timeout=15):
    """Wait for a TCP port to become available."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except (ConnectionRefusedError, socket.timeout, OSError):
            time.sleep(0.3)
    return False


def _https_request(url, data=None, method="GET"):
    """Make HTTPS request ignoring SSL cert validation."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    if body:
        req.add_header("Content-Type", "application/json")
    
    with urllib.request.urlopen(req, context=ctx) as resp:
        return json.loads(resp.read().decode())


def _http_request(url, data=None, method="GET"):
    """Make HTTP request."""
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    if body:
        req.add_header("Content-Type", "application/json")
    
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def bench_api_throughput():
    """Benchmark REST API throughput for both NPA and OPA."""
    print("\n" + "=" * 60)
    print("BENCHMARK 5: REST API Throughput")
    print("=" * 60)

    policy_text = 'package authz\ndefault allow = false\nallow if { input.role == "admin" }'
    input_allow = {"input": {"role": "admin"}}

    NPA_PORT = 18080
    OPA_PORT = 18081

    # --- Start NPA (no TLS for fair comparison) ---
    print(f"\n  Starting NPA server (HTTP, port {NPA_PORT})...", flush=True)
    npa_proc = subprocess.Popen(
        [sys.executable, "-m", "npa", "run",
         "--addr", f"127.0.0.1:{NPA_PORT}", "--no-tls", "--log-level", "error"],
        cwd=str(SCRIPT_DIR),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    
    if not _wait_for_port(NPA_PORT, host="127.0.0.1"):
        print("  ERROR: NPA failed to start within timeout", flush=True)
        npa_proc.kill()
        npa_proc.wait()
        return

    time.sleep(1)  # Give the ASGI app time to fully initialize
    npa_base = f"http://127.0.0.1:{NPA_PORT}"

    # Upload policy to NPA
    try:
        req = urllib.request.Request(
            f"{npa_base}/v1/policies/authz",
            data=policy_text.encode(),
            method="PUT"
        )
        req.add_header("Content-Type", "text/plain")
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f"  ERROR uploading NPA policy: {e}")
        npa_proc.kill()
        npa_proc.wait()
        return

    # Warm up NPA
    for _ in range(20):
        _http_request(f"{npa_base}/v1/data/authz/allow", input_allow, "POST")

    # Benchmark NPA
    npa_iterations = 200
    start = time.perf_counter()
    for _ in range(npa_iterations):
        _http_request(f"{npa_base}/v1/data/authz/allow", input_allow, "POST")
    npa_total = time.perf_counter() - start
    npa_rps = npa_iterations / npa_total
    npa_avg_ms = (npa_total / npa_iterations) * 1000

    print(f"  NPA: {npa_avg_ms:.2f} ms/req, {npa_rps:.0f} req/s ({npa_iterations} reqs)")

    # Stop NPA
    npa_proc.kill()
    npa_proc.wait()
    time.sleep(1)

    # --- Start OPA ---
    print(f"  Starting OPA server (HTTP, port {OPA_PORT})...")
    opa_proc = subprocess.Popen(
        [str(OPA_BIN), "run", "--server",
         "--addr", f"127.0.0.1:{OPA_PORT}", "--log-level", "error"],
        cwd=str(SCRIPT_DIR),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    
    if not _wait_for_port(OPA_PORT, host="127.0.0.1"):
        print("  ERROR: OPA failed to start within timeout", flush=True)
        opa_proc.kill()
        opa_proc.wait()
        return

    time.sleep(0.5)
    opa_base = f"http://127.0.0.1:{OPA_PORT}"

    # Upload policy to OPA
    try:
        req = urllib.request.Request(
            f"{opa_base}/v1/policies/authz",
            data=policy_text.encode(),
            method="PUT"
        )
        req.add_header("Content-Type", "text/plain")
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f"  ERROR uploading OPA policy: {e}")
        opa_proc.kill()
        opa_proc.wait()
        return

    # Warm up OPA
    for _ in range(20):
        _http_request(f"{opa_base}/v1/data/authz/allow", input_allow, "POST")

    # Benchmark OPA
    opa_iterations = 200
    start = time.perf_counter()
    for _ in range(opa_iterations):
        _http_request(f"{opa_base}/v1/data/authz/allow", input_allow, "POST")
    opa_total = time.perf_counter() - start
    opa_rps = opa_iterations / opa_total
    opa_avg_ms = (opa_total / opa_iterations) * 1000

    print(f"  OPA: {opa_avg_ms:.2f} ms/req, {opa_rps:.0f} req/s ({opa_iterations} reqs)")

    # Stop OPA
    opa_proc.kill()
    opa_proc.wait()

    ratio = npa_avg_ms / opa_avg_ms if opa_avg_ms > 0 else 0
    print(f"\n  Ratio: NPA {ratio:.2f}x vs OPA (per request latency)")

    RESULTS["api_throughput"] = {
        "npa_avg_ms": npa_avg_ms,
        "npa_rps": npa_rps,
        "opa_avg_ms": opa_avg_ms,
        "opa_rps": opa_rps,
        "ratio": ratio,
    }


# ═══════════════════════════════════════════════════════════════
# BENCHMARK 6: Startup Time
# ═══════════════════════════════════════════════════════════════

def bench_startup():
    """Benchmark cold start time for both engines."""
    print("\n" + "=" * 60)
    print("BENCHMARK 6: Startup Time (CLI version command)")
    print("=" * 60)

    # NPA version
    npa_times = []
    for _ in range(5):
        _, _, rc, elapsed = run_cmd([sys.executable, "-m", "npa", "version"])
        if rc == 0:
            npa_times.append(elapsed)

    # OPA version
    opa_times = []
    for _ in range(5):
        _, _, rc, elapsed = run_cmd([str(OPA_BIN), "version"])
        if rc == 0:
            opa_times.append(elapsed)

    if npa_times and opa_times:
        npa_avg = mean(npa_times)
        opa_avg = mean(opa_times)
        RESULTS["startup"] = {
            "npa_avg_ms": npa_avg * 1000,
            "opa_avg_ms": opa_avg * 1000,
            "ratio": npa_avg / opa_avg,
        }
        print(f"  NPA: {npa_avg*1000:.0f} ms")
        print(f"  OPA: {opa_avg*1000:.0f} ms")
        print(f"  Ratio: NPA {npa_avg/opa_avg:.1f}x vs OPA")


# ═══════════════════════════════════════════════════════════════
# BENCHMARK 7: Memory footprint (approximate)
# ═══════════════════════════════════════════════════════════════

def bench_memory():
    """Benchmark approximate memory usage."""
    print("\n" + "=" * 60)
    print("BENCHMARK 7: Memory Usage (SDK with loaded policies)")
    print("=" * 60)

    import tracemalloc
    from npa.sdk.sdk import NPA

    tracemalloc.start()

    engine = NPA()
    
    # Load all example policies
    for example_dir in EXAMPLES_DIR.iterdir():
        if not example_dir.is_dir():
            continue
        for f in example_dir.glob("*.rego"):
            engine.load_policy(f"{example_dir.name}/{f.name}", f.read_text(encoding="utf-8"))
        data_file = example_dir / "data.json"
        if data_file.exists():
            engine.set_data(json.loads(data_file.read_text(encoding="utf-8")))

    # Run some evals
    for _ in range(100):
        engine.decide("data.rbac.authz.allow", {"user": "alice", "action": "write", "resource": "reports"})

    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    RESULTS["memory"] = {
        "current_mb": current / 1024 / 1024,
        "peak_mb": peak / 1024 / 1024,
    }
    print(f"  Current: {current / 1024 / 1024:.1f} MB")
    print(f"  Peak:    {peak / 1024 / 1024:.1f} MB")


# ═══════════════════════════════════════════════════════════════
# BENCHMARK 8: Builtin function performance
# ═══════════════════════════════════════════════════════════════

def bench_builtins():
    """Benchmark common builtin functions."""
    print("\n" + "=" * 60)
    print("BENCHMARK 8: Builtin Function Performance")
    print("=" * 60)

    from npa.sdk.sdk import NPA

    benchmarks = [
        ("string_ops", """package bench
result := concat(", ", sort([upper(input.name), lower(input.name), trim_space(input.name)]))
""", {"name": "  Hello World  "}),
        ("json_ops", """package bench
result := json.marshal(object.union({"a": 1}, input.extra))
""", {"extra": {"b": 2, "c": 3, "d": [1, 2, 3]}}),
        ("regex_ops", """package bench
result := regex.find_all_string_submatch_n("(\\\\w+)@(\\\\w+\\\\.\\\\w+)", input.text, -1)
""", {"text": "contact alice@example.com and bob@test.org for info"}),
        ("crypto_hash", """package bench
result := crypto.sha256(input.data)
""", {"data": "benchmark test data for hashing performance evaluation"}),
        ("array_comprehension", """package bench
import future.keywords.in
result := [x * 2 | some x in input.numbers; x > 5]
""", {"numbers": list(range(100))}),
        ("set_operations", """package bench
import future.keywords.in
a := {x | some x in input.set_a}
b := {x | some x in input.set_b}
result := count(a & b)
""", {"set_a": list(range(0, 100, 2)), "set_b": list(range(0, 100, 3))}),
    ]

    for name, policy, input_data in benchmarks:
        engine = NPA()
        engine.load_policy("bench.rego", policy)

        # Warm up
        for _ in range(10):
            try:
                engine.decide("data.bench.result", input_data)
            except Exception:
                break

        iterations = 500
        start = time.perf_counter()
        ok = True
        for _ in range(iterations):
            try:
                engine.decide("data.bench.result", input_data)
            except Exception:
                ok = False
                break
        total = time.perf_counter() - start
        
        if ok:
            avg_us = (total / iterations) * 1_000_000
            RESULTS[f"builtin_{name}"] = {"avg_us": avg_us}
            print(f"  {name:<25} {avg_us:.1f} µs/eval")
        else:
            print(f"  {name:<25} SKIPPED (eval error)")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════════╗")
    print("║         NPA vs OPA — Performance Benchmark Suite        ║")
    print("╠══════════════════════════════════════════════════════════╣")
    print(f"║  NPA Version: 1.0.0 (Python/FastAPI)                    ║")
    print(f"║  OPA Version: 1.3.0 (Go)                                ║")
    print(f"║  Platform:    {sys.platform} / Python {sys.version.split()[0]:<22}║")
    print("╚══════════════════════════════════════════════════════════╝")

    bench_startup()
    bench_cli_eval()
    bench_sdk_eval()
    bench_complexity_scaling()
    bench_data_scaling()
    bench_builtins()
    bench_memory()
    bench_api_throughput()

    # Save results
    results_file = SCRIPT_DIR / "benchmark_results.json"
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(RESULTS, f, indent=2, default=str)
    
    print(f"\n\nResults saved to: {results_file}")
    print("\n" + "=" * 60)
    print("BENCHMARK COMPLETE")
    print("=" * 60)
