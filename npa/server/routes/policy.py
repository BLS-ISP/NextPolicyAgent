"""Policy API endpoints — OPA-compatible /v1/policies interface.

GET /v1/policies          — List all policies
GET /v1/policies/{id}     — Get a specific policy (includes AST)
PUT /v1/policies/{id}     — Create/update a policy (returns metrics)
DELETE /v1/policies/{id}  — Delete a policy (204)
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from npa.ast.compiler import Compiler
from npa.ast.parser import parse_module
from npa.ast.types import module_to_dict
from npa.eval.topdown import TopdownEvaluator
from npa.storage.base import NotFoundError

router = APIRouter(tags=["policies"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class PolicyResponse(BaseModel):
    id: str
    raw: str
    ast: Any = None


class PolicyListResponse(BaseModel):
    result: list[PolicyResponse]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rebuild_evaluator(request: Request) -> None:
    """Recompile all policies and rebuild the evaluator."""
    storage = request.app.state.storage
    policies = storage.list_policies()

    module_dict: dict[str, Any] = {}
    for pid, raw in policies.items():
        try:
            mod = parse_module(raw, pid)
            module_dict[pid] = mod
        except Exception:
            pass

    compiler = Compiler()
    compiler.compile(module_dict)
    request.app.state.compiler = compiler
    request.app.state.evaluator = TopdownEvaluator(
        compiler=compiler,
        store=storage,
    )


def _policy_response(pid: str, raw: str) -> PolicyResponse:
    """Build a policy response with parsed AST."""
    ast = None
    try:
        mod = parse_module(raw, pid)
        ast = module_to_dict(mod)
    except Exception:
        pass
    return PolicyResponse(id=pid, raw=raw, ast=ast)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/policies")
async def list_policies(
    request: Request,
    pretty: bool = Query(False),
) -> PolicyListResponse:
    """List all loaded policies with AST."""
    storage = request.app.state.storage
    policies = storage.list_policies()
    return PolicyListResponse(
        result=[_policy_response(pid, raw) for pid, raw in policies.items()]
    )


@router.get("/policies/{policy_id:path}")
async def get_policy(
    policy_id: str,
    request: Request,
    pretty: bool = Query(False),
) -> dict:
    """Get a specific policy by ID, including AST."""
    storage = request.app.state.storage
    try:
        raw = storage.get_policy(policy_id)
        return {"result": _policy_response(policy_id, raw).model_dump()}
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Policy not found")


@router.put("/policies/{policy_id:path}")
async def put_policy(
    policy_id: str,
    request: Request,
    pretty: bool = Query(False),
    metrics: bool = Query(False),
) -> dict:
    """Create or update a policy (Content-Type: text/plain)."""
    body = await request.body()
    raw = body.decode("utf-8")

    t0 = time.perf_counter()

    try:
        parse_module(raw, policy_id)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_parameter", "message": f"Parse error: {e}"},
        )

    storage = request.app.state.storage
    storage.upsert_policy(policy_id, raw)
    _rebuild_evaluator(request)

    resp: dict[str, Any] = {"result": _policy_response(policy_id, raw).model_dump()}
    if metrics:
        elapsed_ns = int((time.perf_counter() - t0) * 1_000_000_000)
        resp["metrics"] = {
            "timer_rego_module_parse_ns": elapsed_ns,
            "timer_rego_module_compile_ns": elapsed_ns,
            "timer_server_handler_ns": elapsed_ns,
        }
    return resp


@router.delete("/policies/{policy_id:path}")
async def delete_policy(
    policy_id: str,
    request: Request,
    metrics: bool = Query(False),
) -> Response:
    """Delete a policy."""
    storage = request.app.state.storage
    try:
        t0 = time.perf_counter()
        storage.delete_policy(policy_id)
        _rebuild_evaluator(request)
        if metrics:
            elapsed_ns = int((time.perf_counter() - t0) * 1_000_000_000)
            return JSONResponse(status_code=200, content={"metrics": {
                "timer_server_handler_ns": elapsed_ns,
            }})
        return Response(status_code=204)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Policy not found")
        raise HTTPException(status_code=404, detail="Policy not found")
