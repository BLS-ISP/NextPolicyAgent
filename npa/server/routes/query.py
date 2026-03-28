"""Query API endpoints — OPA-compatible /v1/query interface.

GET /v1/query?q=...  — Ad-hoc query (query string)
POST /v1/query       — Ad-hoc query (JSON body)
POST /v1/compile     — Partial evaluation / compile queries
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

router = APIRouter(tags=["query"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ExplainMode(str, Enum):
    off = "off"
    full = "full"
    notes = "notes"
    fails = "fails"
    debug = "debug"


class QueryRequest(BaseModel):
    query: str
    input: Any = None


class CompileRequest(BaseModel):
    query: str
    input: Any = None
    unknowns: list[str] | None = None
    options: dict[str, Any] | None = None  # disableInlining, nondeterministicBuiltins


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _opa_error(code: str, message: str, status: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"code": code, "message": message},
    )


def _record_decision(
    request: Request, query: str, input_data: Any, result: Any,
    duration_ms: float, error: str | None = None,
) -> None:
    decision_log = getattr(request.app.state, "decision_log", None)
    if decision_log:
        decision_log.record(query, input_data, result, duration_ms, error)


def _build_query_response(
    result: Any,
    *,
    metrics: bool = False,
    instrument: bool = False,
    explain: ExplainMode = ExplainMode.off,
    traces: list[str] | None = None,
    t0: float | None = None,
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
    if explain != ExplainMode.off and traces:
        resp["explanation"] = traces
    return resp


# ---------------------------------------------------------------------------
# Query endpoints
# ---------------------------------------------------------------------------

@router.get("/query")
async def adhoc_query_get(
    request: Request,
    q: str = Query(..., description="Rego query string"),
    input: str | None = Query(None, description="JSON-encoded input"),
    pretty: bool = Query(False),
    metrics: bool = Query(False),
    explain: ExplainMode = Query(ExplainMode.off),
    instrument: bool = Query(False),
    strict_builtin_errors: bool = Query(False, alias="strict-builtin-errors"),
) -> dict:
    """Evaluate an ad-hoc Rego query via GET (OPA-compatible)."""
    evaluator = request.app.state.evaluator
    if not evaluator:
        raise _opa_error("internal_error", "No policies loaded", 500)

    input_data = None
    if input is not None:
        import json
        try:
            input_data = json.loads(input)
        except json.JSONDecodeError as e:
            raise _opa_error("invalid_parameter", f"Invalid input JSON: {e}")

    trace_on = explain != ExplainMode.off
    t0 = time.perf_counter()
    try:
        result = evaluator.eval_query(q, input_data=input_data, trace=trace_on)
        duration_ms = (time.perf_counter() - t0) * 1000
        traces = getattr(evaluator, "_last_traces", None) if trace_on else None
        _record_decision(request, q, input_data, result, duration_ms)
        return _build_query_response(
            result, metrics=metrics, instrument=instrument,
            explain=explain, traces=traces, t0=t0,
        )
    except Exception as e:
        duration_ms = (time.perf_counter() - t0) * 1000
        _record_decision(request, q, input_data, None, duration_ms, str(e))
        raise _opa_error("evaluation_error", str(e))


@router.post("/query")
async def adhoc_query(
    body: QueryRequest,
    request: Request,
    pretty: bool = Query(False),
    metrics: bool = Query(False),
    explain: ExplainMode = Query(ExplainMode.off),
    instrument: bool = Query(False),
    strict_builtin_errors: bool = Query(False, alias="strict-builtin-errors"),
) -> dict:
    """Evaluate an ad-hoc Rego query via POST."""
    evaluator = request.app.state.evaluator
    if not evaluator:
        raise _opa_error("internal_error", "No policies loaded", 500)

    trace_on = explain != ExplainMode.off
    t0 = time.perf_counter()
    try:
        result = evaluator.eval_query(body.query, input_data=body.input, trace=trace_on)
        duration_ms = (time.perf_counter() - t0) * 1000
        traces = getattr(evaluator, "_last_traces", None) if trace_on else None
        _record_decision(request, body.query, body.input, result, duration_ms)
        return _build_query_response(
            result, metrics=metrics, instrument=instrument,
            explain=explain, traces=traces, t0=t0,
        )
    except Exception as e:
        duration_ms = (time.perf_counter() - t0) * 1000
        _record_decision(request, body.query, body.input, None, duration_ms, str(e))
        raise _opa_error("evaluation_error", str(e))


# ---------------------------------------------------------------------------
# Compile endpoint
# ---------------------------------------------------------------------------

@router.post("/compile")
async def compile_query(
    body: CompileRequest,
    request: Request,
    pretty: bool = Query(False),
    metrics: bool = Query(False),
    instrument: bool = Query(False),
    explain: ExplainMode = Query(ExplainMode.off),
) -> dict:
    """Partially evaluate a query (OPA-compatible).

    When *unknowns* are provided, returns residual queries that can be
    evaluated later once the unknown values become available.  Without
    unknowns the endpoint behaves like a normal ``eval_query``.

    Supported **options** (in body):
      - ``disableInlining`` (list of paths to disable inlining)
      - ``nondeterministicBuiltins`` (bool)
    """
    evaluator = request.app.state.evaluator
    if not evaluator:
        raise _opa_error("internal_error", "No policies loaded", 500)

    t0 = time.perf_counter()
    try:
        if body.unknowns:
            from npa.eval.partial import PartialEvaluator
            pe = PartialEvaluator(
                compiler=evaluator.compiler,
                store=evaluator.store,
                unknowns=body.unknowns,
            )
            pe_result = pe.partial_eval(body.query, input_data=body.input)
            elapsed_ns = int((time.perf_counter() - t0) * 1_000_000_000)
            resp: dict[str, Any] = {
                "result": {
                    "queries": pe_result.queries,
                    "support": pe_result.support,
                },
            }
            if metrics or instrument:
                resp["metrics"] = {
                    "timer_rego_partial_eval_ns": elapsed_ns,
                    "timer_server_handler_ns": elapsed_ns,
                }
            return resp

        # No unknowns — full evaluation
        result = evaluator.eval_query(body.query, input_data=body.input)
        elapsed_ns = int((time.perf_counter() - t0) * 1_000_000_000)
        resp = {
            "result": {
                "queries": [[result]],
            },
        }
        if metrics or instrument:
            resp["metrics"] = {
                "timer_rego_query_compile_ns": elapsed_ns,
                "timer_server_handler_ns": elapsed_ns,
            }
        return resp
    except Exception as e:
        raise _opa_error("evaluation_error", str(e))
