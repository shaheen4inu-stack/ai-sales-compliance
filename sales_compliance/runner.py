"""Audited entry points: one call, or a batch in parallel."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from .analyze import CallResult, error_result, review_call
from .engine import Engine
from .schemas import Call


def _audit(engine: Engine, result: CallResult) -> None:
    meta = result.meta or {}
    record = {
        "request_id": meta.get("request_id"),
        "call_id": result.id,
        "provider": engine.provider.name,
        "model": engine.provider.model,
        "status": result.status,
        "outcome": result.outcome,
        "input_tokens": meta.get("input_tokens", 0),
        "output_tokens": meta.get("output_tokens", 0),
        "latency_ms": round(meta.get("latency_ms", 0.0), 1),
        "attempts": meta.get("attempts", 0),
        "redactions": result.redactions,
        "finding_types": [f["type"] for f in result.findings],
        "unverified_findings": result.unverified_findings,
    }
    if result.error:
        record["error"] = result.error
    if engine.audit.log_content:
        record["output"] = {k: v for k, v in result.to_dict().items() if k != "meta"}
    engine.audit.write(record)


def run_call(engine: Engine, call: Call) -> CallResult:
    """Review one call. Failures come back as results routed for manual review, never dropped."""
    try:
        result = review_call(engine, call)
    except Exception as exc:  # noqa: BLE001
        result = error_result(call, exc)
    _audit(engine, result)
    return result


def run_batch(engine: Engine, calls: list[Call], max_workers: int | None = None) -> list[CallResult]:
    workers = max_workers or engine.config.get("analysis", {}).get("max_workers", 4)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return list(pool.map(lambda c: run_call(engine, c), calls))
