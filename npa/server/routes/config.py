"""Config & Status endpoints — OPA-compatible /v1/config, /v1/status."""

from __future__ import annotations

import time

from fastapi import APIRouter, Request

router = APIRouter(tags=["config"])


@router.get("/config")
async def get_config(request: Request) -> dict:
    """Return the active NPA configuration (safe subset)."""
    cfg = request.app.state.config
    return {
        "result": {
            "labels": {"id": "npa", "version": "0.1.0"},
            "default_decision": cfg.default_decision if hasattr(cfg, "default_decision") else "/system/main",
            "default_authorization_decision": "/system/authz/allow",
            "storage": {"backend": cfg.storage.backend},
            "server": {
                "addr": cfg.server.addr,
                "port": cfg.server.port,
            },
        }
    }


@router.get("/status")
async def get_status(request: Request) -> dict:
    """Return the server status (uptime, plugin states)."""
    uptime_ns = int((time.time() - request.app.state.start_time) * 1_000_000_000)
    return {
        "result": {
            "uptime_ns": uptime_ns,
            "plugins": {
                "decision_logs": "ok",
                "status": "ok",
                "bundle": "ok" if request.app.state.compiler else "not_ready",
            },
        }
    }
