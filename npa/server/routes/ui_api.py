"""UI-specific API endpoints for the NPA web interface.

Provides aggregated status, decision logging, data tree,
and session-based authentication for the web dashboard.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import deque
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

router = APIRouter(prefix="/v1/ui", tags=["ui"])

# ---------- Session management ----------
# Maps session tokens to expiry timestamps. In-memory — sessions are lost on restart.
_sessions: dict[str, float] = {}
_SESSION_TTL = 8 * 3600  # 8 hours


def _create_session() -> str:
    token = secrets.token_urlsafe(32)
    _sessions[token] = time.time() + _SESSION_TTL
    return token


def _validate_session(token: str | None) -> bool:
    if not token:
        return False
    expiry = _sessions.get(token)
    if expiry is None or expiry < time.time():
        _sessions.pop(token, None)
        return False
    return True


def _invalidate_session(token: str | None) -> None:
    if token:
        _sessions.pop(token, None)


def check_ui_session(request: Request) -> bool:
    """Return True if the request carries a valid UI session cookie."""
    token = request.cookies.get("npa_session")
    return _validate_session(token)


# ---------- Auth endpoints ----------

class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
async def ui_login(body: LoginRequest, request: Request, response: Response) -> dict:
    """Authenticate with username/password and receive a session cookie."""
    config = request.app.state.config
    expected_user = config.auth.ui_username
    expected_pass = config.auth.ui_password

    # Constant-time comparison to avoid timing attacks
    user_ok = hmac.compare_digest(body.username, expected_user)
    pass_ok = hmac.compare_digest(body.password, expected_pass)

    if not (user_ok and pass_ok):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = _create_session()
    response.set_cookie(
        key="npa_session",
        value=token,
        httponly=True,
        samesite="strict",
        max_age=_SESSION_TTL,
        secure=request.url.scheme == "https",
    )
    return {"status": "ok", "message": "Logged in"}


@router.post("/logout")
async def ui_logout(request: Request, response: Response) -> dict:
    """Invalidate the current session."""
    token = request.cookies.get("npa_session")
    _invalidate_session(token)
    response.delete_cookie("npa_session")
    return {"status": "ok"}


@router.get("/session")
async def ui_session(request: Request) -> dict:
    """Check whether the current session is valid."""
    valid = check_ui_session(request)
    return {"authenticated": valid}


class DecisionLog:
    """Thread-safe in-memory ring buffer for decision log entries."""

    def __init__(self, max_size: int = 1000) -> None:
        self._entries: deque[dict] = deque(maxlen=max_size)
        self._counter = 0

    def record(
        self,
        query: str,
        input_data: Any,
        result: Any,
        duration_ms: float,
        error: str | None = None,
    ) -> None:
        self._counter += 1
        self._entries.appendleft({
            "id": self._counter,
            "timestamp": time.time(),
            "query": query,
            "input": input_data,
            "result": result,
            "duration_ms": round(duration_ms, 2),
            "error": error,
        })

    def get_entries(self, limit: int = 100, offset: int = 0) -> list[dict]:
        entries = list(self._entries)
        return entries[offset:offset + limit]

    def count(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()


@router.get("/status")
async def ui_status(request: Request) -> dict:
    """Aggregated server status for the dashboard."""
    storage = request.app.state.storage
    config = request.app.state.config
    policies = storage.list_policies()

    try:
        root_data = storage.read([])
    except Exception:
        root_data = {}

    evaluator = request.app.state.evaluator
    start_time = getattr(request.app.state, "start_time", time.time())
    decision_log: DecisionLog | None = getattr(request.app.state, "decision_log", None)

    return {
        "server": {
            "version": "0.1.0",
            "uptime_seconds": round(time.time() - start_time, 1),
            "healthy": True,
            "tls_enabled": config.tls.enabled,
            "addr": config.server.addr,
            "port": config.server.port,
        },
        "policies": {
            "count": len(policies),
            "ids": list(policies.keys()),
        },
        "data": {
            "root_keys": list(root_data.keys()) if isinstance(root_data, dict) else [],
            "document_count": _count_documents(root_data),
        },
        "evaluator": {
            "ready": evaluator is not None,
        },
        "decisions": {
            "total": decision_log.count() if decision_log else 0,
        },
    }


def _count_documents(data: Any, max_depth: int = 5) -> int:
    """Count leaf documents in the data tree."""
    if not isinstance(data, dict) or max_depth <= 0:
        return 1
    count = 0
    for v in data.values():
        count += _count_documents(v, max_depth - 1)
    return count


@router.get("/decisions")
async def get_decisions(
    request: Request, limit: int = 100, offset: int = 0,
) -> dict:
    """Get decision log entries with pagination."""
    decision_log: DecisionLog | None = getattr(request.app.state, "decision_log", None)
    if not decision_log:
        return {"entries": [], "total": 0}

    entries = decision_log.get_entries(limit=min(limit, 500), offset=max(offset, 0))
    return {
        "entries": entries,
        "total": decision_log.count(),
    }


@router.delete("/decisions")
async def clear_decisions(request: Request) -> dict:
    """Clear all decision log entries."""
    decision_log: DecisionLog | None = getattr(request.app.state, "decision_log", None)
    if decision_log:
        decision_log.clear()
    return {"status": "ok"}


@router.get("/data-tree")
async def get_data_tree(request: Request) -> dict:
    """Get data as a tree structure for the data browser."""
    storage = request.app.state.storage
    try:
        root_data = storage.read([])
    except Exception:
        root_data = {}

    return {"tree": _build_tree_node("root", root_data)}


def _build_tree_node(key: str, value: Any, max_depth: int = 10) -> dict:
    """Recursively build a JSON-serializable tree for the data browser."""
    node: dict[str, Any] = {"key": key}

    if isinstance(value, dict) and max_depth > 0:
        node["type"] = "object"
        node["children"] = [
            _build_tree_node(k, v, max_depth - 1)
            for k, v in sorted(value.items())
        ]
        node["count"] = len(value)
    elif isinstance(value, list) and max_depth > 0:
        node["type"] = "array"
        node["children"] = [
            _build_tree_node(str(i), v, max_depth - 1)
            for i, v in enumerate(value)
        ]
        node["count"] = len(value)
    else:
        node["type"] = type(value).__name__
        node["value"] = value

    return node


# ---------- Rego tool endpoints (fmt, check, parse, test) ----------


class RegoSource(BaseModel):
    source: str
    filename: str = "input.rego"


@router.post("/fmt")
async def ui_format(body: RegoSource) -> dict:
    """Format a Rego source string and return the formatted code."""
    from npa.ast.parser import parse_module
    from npa.format.formatter import format_module

    try:
        mod = parse_module(body.source, body.filename)
        formatted = format_module(mod)
        return {"result": formatted, "changed": formatted != body.source}
    except Exception as e:
        raise HTTPException(status_code=400, detail={"code": "parse_error", "message": str(e)})


@router.post("/check")
async def ui_check(body: RegoSource) -> dict:
    """Validate/check a Rego source string for errors."""
    from npa.ast.parser import parse_module

    try:
        mod = parse_module(body.source, body.filename)
        rule_count = len(mod.rules) if mod.rules else 0
        import_count = len(mod.imports) if mod.imports else 0
        pkg = ".".join(mod.package.path.as_path()) if mod.package else ""
        return {
            "valid": True,
            "package": pkg,
            "rules": rule_count,
            "imports": import_count,
            "errors": [],
        }
    except Exception as e:
        return {
            "valid": False,
            "errors": [{"message": str(e)}],
        }


@router.post("/parse")
async def ui_parse(body: RegoSource) -> dict:
    """Parse Rego source and return the AST as JSON."""
    from npa.ast.parser import parse_module
    from npa.ast.types import module_to_dict

    try:
        mod = parse_module(body.source, body.filename)
        return {"result": module_to_dict(mod)}
    except Exception as e:
        raise HTTPException(status_code=400, detail={"code": "parse_error", "message": str(e)})


@router.post("/test")
async def ui_test(request: Request) -> dict:
    """Run test_ rules from all loaded policies."""
    from npa.ast.compiler import Compiler
    from npa.ast.parser import parse_module
    from npa.eval.topdown import TopdownEvaluator, UndefinedError

    storage = request.app.state.storage
    policies = storage.list_policies()

    if not policies:
        return {"total": 0, "passed": 0, "failed": 0, "results": []}

    modules = {}
    for pid, raw in policies.items():
        try:
            modules[pid] = parse_module(raw, pid)
        except Exception:
            pass

    compiler = Compiler()
    compiler.compile(modules)
    store = storage
    evaluator = TopdownEvaluator(compiler, store)

    results = []
    passed = 0
    failed = 0

    for _fname, mod in modules.items():
        pkg_path = mod.package.path.as_path()
        for rule in mod.rules:
            name = rule.head.name
            if not name.startswith("test_"):
                continue
            full = ".".join(pkg_path + [name])
            query = "data." + full
            try:
                result = evaluator.eval_query(query)
                if result is True or result is not None:
                    passed += 1
                    results.append({"name": full, "status": "PASS"})
                else:
                    failed += 1
                    results.append({"name": full, "status": "FAIL", "message": f"returned {result!r}"})
            except UndefinedError:
                failed += 1
                results.append({"name": full, "status": "FAIL", "message": "undefined"})
            except Exception as e:
                failed += 1
                results.append({"name": full, "status": "ERROR", "message": str(e)})

    return {"total": passed + failed, "passed": passed, "failed": failed, "results": results}


@router.get("/capabilities")
async def ui_capabilities() -> dict:
    """Return NPA capabilities (builtins, features, version)."""
    from npa import __version__
    from npa.ast.builtins import _registry

    builtins_list = _registry.names()
    return {
        "npa_version": __version__,
        "builtins": builtins_list,
        "builtin_count": len(builtins_list),
        "features": [
            "rego_v1",
            "future.keywords.every",
            "future.keywords.in",
            "future.keywords.contains",
            "future.keywords.if",
        ],
    }


@router.get("/metrics")
async def ui_metrics(request: Request) -> dict:
    """Return server metrics for the dashboard."""
    import psutil
    import os

    start_time = getattr(request.app.state, "start_time", time.time())
    decision_log: DecisionLog | None = getattr(request.app.state, "decision_log", None)

    # Compute decision stats
    total_decisions = 0
    avg_duration = 0.0
    error_count = 0
    if decision_log:
        entries = decision_log.get_entries(limit=1000)
        total_decisions = decision_log.count()
        if entries:
            durations = [e["duration_ms"] for e in entries]
            avg_duration = sum(durations) / len(durations)
            error_count = sum(1 for e in entries if e.get("error"))

    process = psutil.Process(os.getpid())
    mem = process.memory_info()

    return {
        "uptime_seconds": round(time.time() - start_time, 1),
        "decisions": {
            "total": total_decisions,
            "error_count": error_count,
            "avg_duration_ms": round(avg_duration, 2),
        },
        "memory": {
            "rss_mb": round(mem.rss / 1024 / 1024, 1),
            "vms_mb": round(mem.vms / 1024 / 1024, 1),
        },
        "cpu_percent": process.cpu_percent(interval=0.1),
    }
