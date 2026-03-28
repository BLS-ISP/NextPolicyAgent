"""Health check endpoints — OPA-compatible /health interface.

GET /health           — Main health check with optional ?bundles, ?plugins, ?exclude-plugin
GET /health/live      — Kubernetes liveness probe (always 200)
GET /health/ready     — Kubernetes readiness probe (checks storage)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse

router = APIRouter(tags=["health"])


def _bundles_healthy(request: Request) -> bool:
    """Check whether all configured bundles have been activated."""
    bundle_status = getattr(request.app.state, "bundle_status", None)
    if bundle_status is None:
        return True  # no bundles configured → healthy
    return all(b.get("active") for b in bundle_status.values())


def _plugins_healthy(request: Request, exclude: list[str] | None = None) -> bool:
    """Check whether all plugins report OK status."""
    plugin_mgr = getattr(request.app.state, "plugin_manager", None)
    if plugin_mgr is None:
        return True
    exclude_set = set(exclude or [])
    for name, plugin in getattr(plugin_mgr, "plugins", {}).items():
        if name in exclude_set:
            continue
        status = getattr(plugin, "status", "ok")
        if status != "ok":
            return False
    return True


@router.get("/health")
async def health(
    request: Request,
    bundles: bool = Query(False, description="Require all bundles to be activated"),
    plugins: bool = Query(False, description="Require all plugins to be OK"),
    exclude_plugin: list[str] | None = Query(None, alias="exclude-plugin"),
) -> Response:
    """Health check — OPA-compatible.

    - ``?bundles`` — fail if any configured bundle is not active
    - ``?plugins`` — fail if any plugin is not OK
    - ``?exclude-plugin=name`` — exclude specific plugins from the check
    """
    healthy = True

    if bundles and not _bundles_healthy(request):
        healthy = False
    if plugins and not _plugins_healthy(request, exclude_plugin):
        healthy = False

    if not healthy:
        return Response(status_code=500, content="")

    return Response(status_code=200, content="{}")


@router.get("/health/live")
async def liveness() -> dict:
    """Liveness probe — Kubernetes compatible, always returns 200."""
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness(request: Request) -> Response:
    """Readiness probe — returns 200 only when storage is functional."""
    storage = request.app.state.storage
    try:
        storage.read([])
        return JSONResponse(status_code=200, content={"status": "ok"})
    except Exception:
        return JSONResponse(status_code=503, content={"status": "not_ready"})
