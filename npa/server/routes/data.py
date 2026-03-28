"""Data API endpoints — OPA-compatible /v1/data interface.

GET /v1/data/{path}  — Query data + policy evaluation
POST /v1/data/{path} — Evaluate policy with input
PUT /v1/data/{path}  — Create/overwrite document (204 / 304 / If-None-Match)
PATCH /v1/data/{path} — Patch document (JSON Patch)
DELETE /v1/data/{path} — Delete document (204)
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from enum import Enum
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from npa.storage.base import NotFoundError

router = APIRouter(tags=["data"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class ExplainMode(str, Enum):
    off = "off"
    full = "full"
    notes = "notes"
    fails = "fails"
    debug = "debug"


def _opa_error(code: str, message: str, status: int = 500) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"code": code, "message": message},
    )


def _etag_for(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return f'W/"{hashlib.sha256(raw).hexdigest()[:16]}"'


def _parse_body(raw: bytes, content_type: str) -> Any:
    """Parse request body as YAML or JSON based on Content-Type."""
    if "yaml" in content_type.lower():
        try:
            import yaml
            return yaml.safe_load(raw)
        except Exception as e:
            raise _opa_error("invalid_parameter", f"YAML parse error: {e}", 400)
    return json.loads(raw)


def _build_response(
    result: Any,
    *,
    metrics: bool = False,
    provenance: bool = False,
    instrument: bool = False,
    explain: ExplainMode = ExplainMode.off,
    traces: list[str] | None = None,
    t0: float | None = None,
    warning: str | None = None,
) -> dict:
    resp: dict[str, Any] = {
        "decision_id": str(uuid.uuid4()),
        "result": result,
    }
    if (metrics or instrument) and t0 is not None:
        elapsed_ns = int((time.perf_counter() - t0) * 1_000_000_000)
        m: dict[str, Any] = {
            "timer_rego_query_eval_ns": elapsed_ns,
            "timer_server_handler_ns": elapsed_ns,
        }
        if instrument:
            m["timer_rego_query_parse_ns"] = 0
            m["timer_rego_query_compile_ns"] = 0
        resp["metrics"] = m
    if provenance:
        from npa import __version__
        resp["provenance"] = {"version": __version__, "engine": "npa"}
    if explain != ExplainMode.off and traces:
        resp["explanation"] = traces
    if warning:
        resp["warning"] = {"code": "api_usage_warning", "message": warning}
    return resp


# ---------------------------------------------------------------------------
# v1 Data API
# ---------------------------------------------------------------------------

@router.get("/data/{path:path}")
async def get_data(
    path: str,
    request: Request,
    pretty: bool = Query(False),
    metrics: bool = Query(False),
    provenance: bool = Query(True),
    explain: ExplainMode = Query(ExplainMode.off),
    instrument: bool = Query(False),
    strict_builtin_errors: bool = Query(False, alias="strict-builtin-errors"),
    input: str | None = Query(None, description="JSON-encoded input"),
) -> dict:
    """Query data or evaluate policy at the given path."""
    storage = request.app.state.storage
    parts = [p for p in path.split("/") if p]
    t0 = time.perf_counter()

    input_data = None
    if input is not None:
        try:
            input_data = json.loads(input)
        except json.JSONDecodeError as e:
            raise _opa_error("invalid_parameter", f"Invalid input JSON: {e}", 400)

    trace_on = explain != ExplainMode.off
    evaluator = request.app.state.evaluator
    if evaluator:
        try:
            query = "data." + ".".join(parts) if parts else "data"
            result = evaluator.eval_query(query, input_data=input_data, trace=trace_on)
            traces = getattr(evaluator, "_last_traces", None) if trace_on else None
            return _build_response(
                result, metrics=metrics, provenance=provenance,
                instrument=instrument, explain=explain, traces=traces, t0=t0,
            )
        except Exception:
            pass

    try:
        result = storage.read(parts)
        return _build_response(
            result, metrics=metrics, provenance=provenance,
            instrument=instrument, explain=explain, t0=t0,
        )
    except NotFoundError:
        raise _opa_error("resource_not_found", "Document not found", 404)


@router.post("/data/{path:path}")
async def post_data_with_input(
    path: str,
    request: Request,
    pretty: bool = Query(False),
    metrics: bool = Query(False),
    provenance: bool = Query(True),
    explain: ExplainMode = Query(ExplainMode.off),
    instrument: bool = Query(False),
    strict_builtin_errors: bool = Query(False, alias="strict-builtin-errors"),
) -> dict:
    """Evaluate policy at path with input document."""
    evaluator = request.app.state.evaluator
    if not evaluator:
        raise _opa_error("internal_error", "No policies loaded", 500)

    # Parse body — support JSON and YAML
    raw_body = await request.body()
    ct = request.headers.get("content-type", "application/json")
    try:
        body = _parse_body(raw_body, ct)
    except Exception as e:
        raise _opa_error("invalid_parameter", f"Body parse error: {e}", 400)

    # OPA compat: warn if "input" key is missing
    warning: str | None = None
    if isinstance(body, dict) and "input" not in body:
        warning = "Missing 'input' key in request body; treating entire body as input"
        input_data = body
    elif isinstance(body, dict):
        input_data = body.get("input")
    else:
        input_data = body

    parts = [p for p in path.split("/") if p]
    query = "data." + ".".join(parts) if parts else "data"
    t0 = time.perf_counter()
    trace_on = explain != ExplainMode.off

    try:
        result = evaluator.eval_query(query, input_data=input_data, trace=trace_on)
        traces = getattr(evaluator, "_last_traces", None) if trace_on else None
        return _build_response(
            result, metrics=metrics, provenance=provenance,
            instrument=instrument, explain=explain, traces=traces, t0=t0,
            warning=warning,
        )
    except Exception as e:
        raise _opa_error("internal_error", str(e), 500)


@router.put("/data/{path:path}")
async def put_data(
    path: str,
    request: Request,
    metrics: bool = Query(False),
    if_none_match: str | None = Header(None, alias="If-None-Match"),
) -> Response:
    """Create or overwrite a document at the given path."""
    storage = request.app.state.storage
    parts = [p for p in path.split("/") if p]

    # Conditional: If-None-Match: * -> 304 if document exists
    if if_none_match == "*":
        try:
            storage.read(parts)
            return Response(status_code=304)
        except NotFoundError:
            pass

    body = await request.json()
    storage.patch_data(parts, body)

    if metrics:
        return JSONResponse(status_code=200, content={"metrics": {}})
    return Response(status_code=204)


@router.patch("/data/{path:path}")
async def patch_data(
    path: str,
    request: Request,
    metrics: bool = Query(False),
) -> Response:
    """Apply JSON Patch operations to the document at the given path."""
    storage = request.app.state.storage
    patches = await request.json()
    parts = [p for p in path.split("/") if p]

    try:
        current = storage.read(parts)
    except NotFoundError:
        current = {}

    from npa.ast.builtins import builtin_json_patch
    updated = builtin_json_patch(current, patches)
    storage.patch_data(parts, updated)

    if metrics:
        return JSONResponse(status_code=200, content={"metrics": {}})
    return Response(status_code=204)


@router.delete("/data/{path:path}")
async def delete_data(
    path: str,
    request: Request,
    metrics: bool = Query(False),
) -> Response:
    """Delete the document at the given path."""
    storage = request.app.state.storage
    parts = [p for p in path.split("/") if p]
    try:
        storage.remove_data(parts)
        if metrics:
            return JSONResponse(status_code=200, content={"metrics": {}})
        return Response(status_code=204)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Document not found")


# ---------------------------------------------------------------------------
# v0 API — raw result format (no wrapper)
# ---------------------------------------------------------------------------

v0_router = APIRouter(tags=["data-v0"])


@v0_router.get("/data/{path:path}")
async def get_data_v0(
    path: str,
    request: Request,
) -> Any:
    """v0 Data API — returns the raw result without the v1 wrapper."""
    storage = request.app.state.storage
    parts = [p for p in path.split("/") if p]

    evaluator = request.app.state.evaluator
    if evaluator:
        try:
            query = "data." + ".".join(parts) if parts else "data"
            return evaluator.eval_query(query)
        except Exception:
            pass

    try:
        return storage.read(parts)
    except NotFoundError:
        raise _opa_error("resource_not_found", "Document not found", 404)


@v0_router.post("/data/{path:path}")
async def post_data_v0(
    path: str,
    request: Request,
) -> Any:
    """v0 Data API with input — returns the raw result."""
    evaluator = request.app.state.evaluator
    if not evaluator:
        raise _opa_error("internal_error", "No policies loaded", 500)

    raw_body = await request.body()
    ct = request.headers.get("content-type", "application/json")
    try:
        body = _parse_body(raw_body, ct)
    except Exception as e:
        raise _opa_error("invalid_parameter", f"Body parse error: {e}", 400)

    if isinstance(body, dict):
        input_data = body.get("input", body)
    else:
        input_data = body

    parts = [p for p in path.split("/") if p]
    query = "data." + ".".join(parts) if parts else "data"

    try:
        return evaluator.eval_query(query, input_data=input_data)
    except Exception as e:
        raise _opa_error("internal_error", str(e), 500)
