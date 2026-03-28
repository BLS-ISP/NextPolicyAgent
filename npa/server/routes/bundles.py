"""Bundle API endpoints — OPA-compatible /v1/bundles interface.

GET /v1/bundles                — List all bundles
GET /v1/bundles/{name}         — Get bundle info by name
PUT /v1/bundles/{name}         — Upload a bundle (.tar.gz)
DELETE /v1/bundles/{name}      — Deactivate / remove a bundle
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from npa.bundle.bundle import Bundle, load_bundle_from_bytes

router = APIRouter(tags=["bundles"])


def _activate_bundle(request: Request, name: str, bundle: Bundle) -> None:
    """Load bundle policies & data into the running engine."""
    from npa.ast.compiler import Compiler
    from npa.ast.parser import parse_module
    from npa.eval.topdown import TopdownEvaluator

    storage = request.app.state.storage

    # Merge bundle data into storage
    data = bundle.get_data()
    if data:
        storage.patch_data([], data)

    # Upsert bundle policies
    for path, source in bundle.get_policies().items():
        storage.upsert_policy(f"bundle/{name}/{path}", source)

    # Rebuild evaluator
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
    request.app.state.evaluator = TopdownEvaluator(compiler=compiler, store=storage)

    # Track bundle status
    bundle_status = getattr(request.app.state, "bundle_status", {})
    bundle_status[name] = {
        "active": True,
        "revision": bundle.manifest.revision,
        "roots": bundle.manifest.roots,
        "policies": list(bundle.get_policies().keys()),
        "activated_at": time.time(),
    }
    request.app.state.bundle_status = bundle_status


def _deactivate_bundle(request: Request, name: str) -> None:
    """Remove a bundle's policies from the engine."""
    storage = request.app.state.storage
    bundle_status = getattr(request.app.state, "bundle_status", {})
    info = bundle_status.get(name)
    if info:
        for path in info.get("policies", []):
            try:
                storage.delete_policy(f"bundle/{name}/{path}")
            except Exception:
                pass

    bundle_status.pop(name, None)
    request.app.state.bundle_status = bundle_status

    # Rebuild evaluator
    from npa.ast.compiler import Compiler
    from npa.ast.parser import parse_module
    from npa.eval.topdown import TopdownEvaluator

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
    request.app.state.evaluator = TopdownEvaluator(compiler=compiler, store=storage)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/bundles")
async def list_bundles(request: Request) -> dict:
    """List all active bundles."""
    bundle_status = getattr(request.app.state, "bundle_status", {})
    return {"result": bundle_status}


@router.get("/bundles/{name:path}")
async def get_bundle(name: str, request: Request) -> dict:
    """Get bundle info by name."""
    bundle_status = getattr(request.app.state, "bundle_status", {})
    if name not in bundle_status:
        raise HTTPException(status_code=404, detail="Bundle not found")
    return {"result": bundle_status[name]}


@router.put("/bundles/{name:path}")
async def upload_bundle(name: str, request: Request) -> Response:
    """Upload a bundle (.tar.gz archive)."""
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty bundle")

    try:
        bundle = load_bundle_from_bytes(body)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_parameter", "message": f"Invalid bundle: {e}"},
        )

    _activate_bundle(request, name, bundle)
    return Response(status_code=200, content="")


@router.delete("/bundles/{name:path}")
async def delete_bundle(name: str, request: Request) -> Response:
    """Deactivate and remove a bundle."""
    bundle_status = getattr(request.app.state, "bundle_status", {})
    if name not in bundle_status:
        raise HTTPException(status_code=404, detail="Bundle not found")

    _deactivate_bundle(request, name)
    return Response(status_code=204)
