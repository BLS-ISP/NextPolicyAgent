"""NPA CLI — Command-line interface using Typer.

Commands mirror OPA CLI for drop-in compatibility:
    npa run       — Start the NPA server
    npa eval      — Evaluate a Rego query
    npa build     — Build a bundle
    npa test      — Run Rego tests
    npa fmt       — Format Rego files
    npa check     — Check/validate Rego files
    npa parse     — Parse and dump AST
    npa inspect   — Inspect a bundle
    npa sign      — Sign a bundle
    npa version   — Show version info
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="npa",
    help="NPA – Next Policy Agent: OPA-compatible policy engine with HTTPS-first design",
    no_args_is_help=True,
)
console = Console()


@app.command()
def run(
    addr: str = typer.Option("0.0.0.0:8443", "--addr", "-a", help="Listening address"),
    config_file: Optional[Path] = typer.Option(None, "--config-file", "-c", help="Config file path"),
    tls_cert: Optional[Path] = typer.Option(None, "--tls-cert-file", help="TLS certificate file"),
    tls_key: Optional[Path] = typer.Option(None, "--tls-private-key-file", help="TLS private key"),
    no_tls: bool = typer.Option(False, "--no-tls", help="Disable TLS (not recommended)"),
    bundle: Optional[list[Path]] = typer.Option(None, "--bundle", "-b", help="Bundle paths to load"),
    log_level: str = typer.Option("info", "--log-level", help="Log level"),
) -> None:
    """Start the NPA server."""
    from npa.config.config import NpaConfig, TLSConfig, ServerConfig

    config = NpaConfig.from_file(config_file) if config_file else NpaConfig()

    # Apply CLI overrides
    host, _, port_str = addr.rpartition(":")
    if host and port_str:
        config.server.addr = host
        config.server.port = int(port_str)

    if tls_cert:
        config.tls.cert_file = tls_cert
    if tls_key:
        config.tls.key_file = tls_key
    if no_tls:
        config.tls.enabled = False
        if config.server.port == 8443:
            config.server.port = 8181
    config.logging.level = log_level.upper()

    from npa.server.app import run_server
    run_server(config)


@app.command()
def eval(
    query: str = typer.Argument(..., help="Rego query to evaluate"),
    input_file: Optional[Path] = typer.Option(None, "--input", "-i", help="Input JSON file"),
    data: Optional[list[Path]] = typer.Option(None, "--data", "-d", help="Data/policy files or dirs"),
    bundle_path: Optional[list[Path]] = typer.Option(None, "--bundle", "-b", help="Bundle paths"),
    output_format: str = typer.Option("json", "--format", "-f", help="Output format (json, raw, pretty)"),
) -> None:
    """Evaluate a Rego query."""
    from npa.sdk.sdk import NPA, NPAError

    engine = NPA()

    # Load data/policies
    if data:
        for path in data:
            _load_path(engine, path)

    if bundle_path:
        for bp in bundle_path:
            engine.load_bundle_from_dir(bp)

    # Load input
    input_data = None
    if input_file:
        input_data = json.loads(input_file.read_text(encoding="utf-8"))

    try:
        result = engine.decide(query, input_data=input_data)
        _output(result, output_format)
    except NPAError as e:
        console.print(f"[red]Error:[/red] {e}", err=True)
        raise typer.Exit(1)


@app.command()
def check(
    paths: list[Path] = typer.Argument(..., help="Rego files or directories to check"),
    strict: bool = typer.Option(False, "--strict", help="Enable strict mode"),
) -> None:
    """Check Rego files for errors."""
    from npa.ast.parser import parse_module

    errors = 0
    for p in paths:
        for rego_file in _find_rego_files(p):
            try:
                source = rego_file.read_text(encoding="utf-8")
                parse_module(source, str(rego_file))
                console.print(f"  [green]✓[/green] {rego_file}")
            except Exception as e:
                console.print(f"  [red]✗[/red] {rego_file}: {e}")
                errors += 1

    if errors:
        console.print(f"\n[red]{errors} error(s) found[/red]")
        raise typer.Exit(1)
    console.print("\n[green]All files OK[/green]")


@app.command()
def parse(
    file: Path = typer.Argument(..., help="Rego file to parse"),
    output_format: str = typer.Option("json", "--format", "-f", help="Output format"),
) -> None:
    """Parse a Rego file and output the AST."""
    from npa.ast.parser import parse_module

    source = file.read_text(encoding="utf-8")
    module = parse_module(source, str(file))

    import dataclasses
    def to_dict(obj: Any) -> Any:
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return {k: to_dict(v) for k, v in dataclasses.asdict(obj).items()}
        if isinstance(obj, list):
            return [to_dict(v) for v in obj]
        if isinstance(obj, dict):
            return {str(k): to_dict(v) for k, v in obj.items()}
        return obj

    console.print_json(json.dumps(to_dict(module), default=str))


@app.command()
def build(
    paths: list[Path] = typer.Argument(..., help="Rego files/dirs to bundle"),
    output: Path = typer.Option("bundle.tar.gz", "--output", "-o", help="Output file"),
    revision: Optional[str] = typer.Option(None, "--revision", "-r", help="Bundle revision"),
) -> None:
    """Build a policy bundle."""
    from npa.bundle.bundle import BundleManifest, build_bundle

    policies: dict[str, str] = {}
    data_docs: dict[str, Any] = {}

    for p in paths:
        for rego_file in _find_rego_files(p):
            rel = rego_file.relative_to(p) if p.is_dir() else rego_file
            policies[rel.as_posix()] = rego_file.read_text(encoding="utf-8")

        # Look for data.json files
        if p.is_dir():
            for data_file in p.rglob("data.json"):
                data_docs.update(json.loads(data_file.read_text(encoding="utf-8")))

    manifest = BundleManifest(revision=revision or "")
    bundle_bytes = build_bundle(policies, data_docs or None, manifest)
    output.write_bytes(bundle_bytes)
    console.print(f"[green]Bundle written to {output}[/green] ({len(bundle_bytes)} bytes)")


@app.command()
def sign(
    bundle_path: Path = typer.Argument(..., help="Bundle .tar.gz to sign"),
    signing_key: Path = typer.Option(..., "--signing-key", help="Private key file (PEM)"),
    algorithm: str = typer.Option("RS256", "--signing-alg", help="Signing algorithm"),
) -> None:
    """Sign a policy bundle."""
    from npa.bundle.bundle import load_bundle_from_bytes
    from npa.bundle.sign import sign_bundle

    data = bundle_path.read_bytes()
    bundle = load_bundle_from_bytes(data)
    key = signing_key.read_text(encoding="utf-8")

    token = sign_bundle(bundle.content_hash(), key, algorithm=algorithm)
    console.print(f"[green]Signature:[/green] {token[:80]}...")


@app.command()
def inspect(
    path: Path = typer.Argument(..., help="Bundle file or directory to inspect"),
) -> None:
    """Inspect a bundle's contents."""
    from npa.bundle.bundle import load_bundle_from_bytes, load_bundle_from_dir

    if path.is_dir():
        bundle = load_bundle_from_dir(path)
    else:
        bundle = load_bundle_from_bytes(path.read_bytes())

    table = Table(title=f"Bundle: {path}")
    table.add_column("Type", style="cyan")
    table.add_column("Path")
    table.add_column("Size", justify="right")

    for f in bundle.files:
        ftype = "rego" if f.is_rego else "data" if f.is_data else "other"
        table.add_row(ftype, f.path, f"{len(f.content)} B")

    table.add_section()
    table.add_row("manifest", f"revision={bundle.manifest.revision}", "")
    table.add_row("hash", bundle.content_hash()[:16] + "...", "")
    table.add_row("signed", "yes" if bundle.signature else "no", "")

    console.print(table)


@app.command()
def version() -> None:
    """Show NPA version information."""
    from npa import __version__
    console.print(f"NPA – Next Policy Agent v{__version__}")
    console.print(f"Python {sys.version}")


@app.command()
def bench(
    query: str = typer.Argument(..., help="Rego query to benchmark"),
    input_file: Optional[Path] = typer.Option(None, "--input", "-i", help="Input JSON file"),
    data: Optional[list[Path]] = typer.Option(None, "--data", "-d", help="Data/policy files or dirs"),
    bundle_path: Optional[list[Path]] = typer.Option(None, "--bundle", "-b", help="Bundle paths"),
    count: int = typer.Option(100, "--count", "-n", help="Number of iterations"),
) -> None:
    """Benchmark a Rego query evaluation."""
    import time
    from npa.sdk.sdk import NPA, NPAError

    engine = NPA()

    if data:
        for path in data:
            _load_path(engine, path)
    if bundle_path:
        for bp in bundle_path:
            engine.load_bundle_from_dir(bp)

    input_data = None
    if input_file:
        input_data = json.loads(input_file.read_text(encoding="utf-8"))

    # Warm-up
    try:
        engine.decide(query, input_data=input_data)
    except NPAError:
        pass

    # Benchmark
    times: list[float] = []
    for _ in range(count):
        t0 = time.perf_counter()
        try:
            engine.decide(query, input_data=input_data)
        except NPAError:
            pass
        times.append(time.perf_counter() - t0)

    avg_ns = (sum(times) / len(times)) * 1_000_000_000
    min_ns = min(times) * 1_000_000_000
    max_ns = max(times) * 1_000_000_000
    p50 = sorted(times)[len(times) // 2] * 1_000_000_000

    table = Table(title=f"Benchmark: {query} ({count} iterations)")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    table.add_row("avg", f"{avg_ns:,.0f} ns")
    table.add_row("min", f"{min_ns:,.0f} ns")
    table.add_row("max", f"{max_ns:,.0f} ns")
    table.add_row("p50", f"{p50:,.0f} ns")
    console.print(table)


@app.command()
def deps(
    query: str = typer.Argument(..., help="Rego query to analyse dependencies for"),
    data: Optional[list[Path]] = typer.Option(None, "--data", "-d", help="Data/policy files or dirs"),
    bundle_path: Optional[list[Path]] = typer.Option(None, "--bundle", "-b", help="Bundle paths"),
    output_format: str = typer.Option("pretty", "--format", "-f", help="Output format"),
) -> None:
    """Show dependencies of a Rego query."""
    from npa.ast.parser import parse_module
    from npa.ast.compiler import Compiler
    from npa.ast.types import TermKind, Ref

    modules: dict[str, Any] = {}
    if data:
        for p in data:
            for rego_file in _find_rego_files(p):
                src = rego_file.read_text(encoding="utf-8")
                modules[str(rego_file)] = parse_module(src, str(rego_file))

    compiler = Compiler()
    if modules:
        compiler.compile(modules)

    path = query.split(".")
    if path[0] == "data":
        path = path[1:]

    rules = compiler.get_rules(path)
    if not rules:
        console.print(f"[yellow]No rules found for {query}[/yellow]")
        raise typer.Exit(0)

    data_deps: set[str] = set()
    input_deps: set[str] = set()

    def _collect_refs(terms: Any) -> None:
        from npa.ast.types import Term
        if isinstance(terms, Term):
            if terms.kind == TermKind.REF:
                ref = terms.value
                parts = []
                for p in ref.terms:
                    if isinstance(p, Term) and p.kind in (TermKind.VAR, TermKind.STRING):
                        parts.append(str(p.value))
                    elif isinstance(p, str):
                        parts.append(p)
                path_str = ".".join(parts)
                if path_str.startswith("data."):
                    data_deps.add(path_str)
                elif path_str.startswith("input."):
                    input_deps.add(path_str)
            if terms.kind == TermKind.CALL:
                call = terms.value
                for arg in call.args:
                    _collect_refs(arg)
            if terms.kind in (TermKind.ARRAY, TermKind.SET):
                for v in terms.value:
                    _collect_refs(v)
            if terms.kind == TermKind.OBJECT:
                for k, v in terms.value:
                    _collect_refs(k)
                    _collect_refs(v)
        elif isinstance(terms, (list, tuple)):
            for t in terms:
                _collect_refs(t)

    for rule in rules:
        if rule.body:
            for expr in rule.body.exprs:
                _collect_refs(expr.terms)

    if output_format == "json":
        print(json.dumps({"data": sorted(data_deps), "input": sorted(input_deps)}))
    else:
        if data_deps:
            console.print("[cyan]Data dependencies:[/cyan]")
            for dep in sorted(data_deps):
                console.print(f"  {dep}")
        if input_deps:
            console.print("[cyan]Input dependencies:[/cyan]")
            for dep in sorted(input_deps):
                console.print(f"  {dep}")
        if not data_deps and not input_deps:
            console.print("[green]No external dependencies found[/green]")


@app.command()
def capabilities(
    output_format: str = typer.Option("json", "--format", "-f", help="Output format"),
    current: bool = typer.Option(True, "--current", help="Show current capabilities"),
) -> None:
    """Output the capabilities of this NPA build."""
    from npa import __version__
    from npa.ast.builtins import _REGISTRY

    builtins_list = []
    for name, fn in sorted(_REGISTRY.items()):
        builtins_list.append({"name": name})

    capabilities_doc = {
        "npa_version": __version__,
        "builtins": builtins_list,
        "features": [
            "rego_v1",
            "future.keywords.every",
            "future.keywords.in",
            "future.keywords.contains",
            "future.keywords.if",
        ],
        "wasm_abi_versions": [],  # NPA does not support Wasm
    }

    if output_format == "json":
        print(json.dumps(capabilities_doc, indent=2))
    else:
        console.print_json(json.dumps(capabilities_doc, indent=2))


@app.command()
def test(
    paths: list[Path] = typer.Argument(default=None, help="Rego files/dirs containing tests"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show test names"),
    run_filter: Optional[str] = typer.Option(None, "--run", "-r", help="Regex filter for test names"),
) -> None:
    """Run Rego tests (rules prefixed with test_)."""
    import re
    from npa.ast.parser import parse_module
    from npa.ast.compiler import Compiler
    from npa.eval.topdown import TopdownEvaluator, UndefinedError
    from npa.storage.inmemory import InMemoryStorage

    search_paths = paths or [Path(".")]
    rego_files: list[Path] = []
    for p in search_paths:
        rego_files.extend(_find_rego_files(p))

    if not rego_files:
        console.print("[yellow]No .rego files found[/yellow]")
        raise typer.Exit(0)

    # Parse all modules
    modules: dict[str, Any] = {}
    data_docs: dict[str, Any] = {}
    for f in rego_files:
        src = f.read_text(encoding="utf-8")
        try:
            mod = parse_module(src, str(f))
            modules[str(f)] = mod
        except Exception as e:
            console.print(f"[red]Parse error in {f}:[/red] {e}")
            raise typer.Exit(1)

        # Load data.json files next to rego files
        data_file = f.parent / "data.json"
        if data_file.exists() and str(data_file) not in data_docs:
            data_docs[str(data_file)] = json.loads(data_file.read_text(encoding="utf-8"))

    # Compile
    compiler = Compiler()
    compiler.compile(modules)
    store_data: dict[str, Any] = {}
    for d in data_docs.values():
        if isinstance(d, dict):
            store_data.update(d)
    store = InMemoryStorage(store_data)

    # Find test rules (prefixed with test_)
    total = 0
    passed_count = 0
    fail_count = 0
    filter_re = re.compile(run_filter) if run_filter else None

    for _fname, mod in modules.items():
        pkg_path = mod.package.path.as_path()
        for rule in mod.rules:
            rule_name = rule.head.name
            if not rule_name.startswith("test_"):
                continue
            full_name = ".".join(pkg_path + [rule_name])
            if filter_re and not filter_re.search(full_name):
                continue

            total += 1
            query = "data." + full_name
            evaluator = TopdownEvaluator(compiler, store)
            try:
                result = evaluator.eval_query(query)
                if result is True or result is not None:
                    passed_count += 1
                    if verbose:
                        console.print(f"  [green]PASS[/green] {full_name}")
                else:
                    fail_count += 1
                    console.print(f"  [red]FAIL[/red] {full_name}: returned {result!r}")
            except UndefinedError:
                fail_count += 1
                console.print(f"  [red]FAIL[/red] {full_name}: undefined")
            except Exception as e:
                fail_count += 1
                console.print(f"  [red]ERROR[/red] {full_name}: {e}")

    # Summary
    console.print(f"\n{total} tests, {passed_count} passed, {fail_count} failed")
    if fail_count > 0:
        raise typer.Exit(1)


@app.command()
def fmt(
    paths: list[Path] = typer.Argument(..., help="Rego files or directories to format"),
    diff_mode: bool = typer.Option(False, "--diff", "-d", help="Show diff instead of writing"),
    check_mode: bool = typer.Option(False, "--check", help="Check if files are formatted (exit 1 if not)"),
) -> None:
    """Format Rego files."""
    from npa.ast.parser import parse_module
    from npa.format.formatter import format_module

    unformatted = 0
    for p in paths:
        for rego_file in _find_rego_files(p):
            source = rego_file.read_text(encoding="utf-8")
            try:
                mod = parse_module(source, str(rego_file))
                formatted = format_module(mod)

                if source == formatted:
                    continue

                unformatted += 1
                if diff_mode:
                    import difflib
                    diff = difflib.unified_diff(
                        source.splitlines(keepends=True),
                        formatted.splitlines(keepends=True),
                        fromfile=str(rego_file),
                        tofile=str(rego_file) + " (formatted)",
                    )
                    console.print("".join(diff))
                elif check_mode:
                    console.print(f"  [yellow]✗[/yellow] {rego_file}")
                else:
                    rego_file.write_text(formatted, encoding="utf-8")
                    console.print(f"  [green]✓[/green] {rego_file}")
            except Exception as e:
                console.print(f"  [red]Error[/red] {rego_file}: {e}")

    if check_mode and unformatted > 0:
        console.print(f"\n[yellow]{unformatted} file(s) need formatting[/yellow]")
        raise typer.Exit(1)


# ===========================================================================
# Helpers
# ===========================================================================

def _find_rego_files(path: Path) -> list[Path]:
    if path.is_file() and path.suffix == ".rego":
        return [path]
    if path.is_dir():
        return sorted(path.rglob("*.rego"))
    return []


def _load_path(engine: Any, path: Path) -> None:
    """Load Rego files and data from a path into the engine."""
    from npa.sdk.sdk import NPA

    if path.is_file():
        if path.suffix == ".rego":
            engine.load_policy(str(path), path.read_text(encoding="utf-8"))
        elif path.suffix == ".json":
            engine.set_data(json.loads(path.read_text(encoding="utf-8")))
    elif path.is_dir():
        for rego_file in path.rglob("*.rego"):
            engine.load_policy(str(rego_file), rego_file.read_text(encoding="utf-8"))
        for data_file in path.rglob("data.json"):
            data = json.loads(data_file.read_text(encoding="utf-8"))
            rel_parts = list(data_file.parent.relative_to(path).parts)
            engine.load_data(rel_parts, data)


def _output(result: Any, fmt: str) -> None:
    if fmt == "raw":
        print(result)
    elif fmt == "pretty":
        console.print_json(json.dumps(result, default=str, indent=2))
    else:
        print(json.dumps(result, default=str))


if __name__ == "__main__":
    app()
