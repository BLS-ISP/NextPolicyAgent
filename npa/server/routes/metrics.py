"""Prometheus metrics endpoint — OPA-compatible /metrics."""

from __future__ import annotations

import time

from fastapi import APIRouter, Request, Response

router = APIRouter(tags=["metrics"])

# In-memory counters — lightweight, no external dependency required at startup.
# When prometheus_client is available, we also expose its default registry.
_COUNTERS: dict[str, float] = {
    "npa_policy_evaluations_total": 0,
    "npa_policy_evaluation_errors_total": 0,
    "npa_bundle_loads_total": 0,
    "npa_http_requests_total": 0,
}

_LAST_EVAL_NS: float = 0.0


def inc(name: str, delta: float = 1.0) -> None:
    """Increment a counter by *delta*."""
    _COUNTERS[name] = _COUNTERS.get(name, 0) + delta


def observe_eval_ns(duration_ns: float) -> None:
    """Record latest evaluation duration."""
    global _LAST_EVAL_NS
    _LAST_EVAL_NS = duration_ns


@router.get("/metrics")
async def prometheus_metrics(request: Request) -> Response:
    """Expose Prometheus-format metrics (text/plain)."""
    lines: list[str] = []

    # Try to use prometheus_client if available
    try:
        from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
        prom_output = generate_latest().decode("utf-8")
        lines.append(prom_output)
    except ImportError:
        pass

    # Always emit our internal counters
    uptime = time.time() - request.app.state.start_time
    lines.append(f"# HELP npa_uptime_seconds NPA server uptime in seconds")
    lines.append(f"# TYPE npa_uptime_seconds gauge")
    lines.append(f"npa_uptime_seconds {uptime:.3f}")

    for name, value in sorted(_COUNTERS.items()):
        lines.append(f"# HELP {name} NPA internal counter")
        lines.append(f"# TYPE {name} counter")
        lines.append(f"{name} {value}")

    lines.append(f"# HELP npa_last_evaluation_ns Duration of last evaluation in nanoseconds")
    lines.append(f"# TYPE npa_last_evaluation_ns gauge")
    lines.append(f"npa_last_evaluation_ns {_LAST_EVAL_NS}")

    body = "\n".join(lines) + "\n"
    return Response(content=body, media_type="text/plain; version=0.0.4; charset=utf-8")
