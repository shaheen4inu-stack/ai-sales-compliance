"""Demo API. Run: uvicorn sales_compliance.api:app --port 8000, then open /docs.

Set DEMO_API_KEY to require an X-API-Key header on the review endpoints.
"""

from __future__ import annotations

import os

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel

from . import __version__
from .aggregate import summarise
from .config import load_config
from .engine import Engine
from .providers import ProviderConfigError
from .runner import run_batch, run_call
from .schemas import Call

app = FastAPI(
    title="AI Sales Compliance",
    version=__version__,
    description=(
        "Sales call compliance review: misleading claims, solicitation or use of competitor confidential pricing, "
        "confidential disclosure and coordination risk. Findings cite verified rep quotes, competitor figures are "
        "masked, and everything is routed to compliance or legal for a person to decide."
    ),
)

_engines: dict[str, Engine] = {}


def engine_factory(provider: str | None) -> Engine:
    key = provider or "default"
    if key not in _engines:
        _engines[key] = Engine(provider_name=provider)
    return _engines[key]


ENGINE_FACTORY = engine_factory  # tests replace this with a fake


def require_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = os.environ.get("DEMO_API_KEY")
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key header")


ProviderParam = Query(default=None, pattern="^(anthropic|openai)$", description="Override the configured provider")


def get_engine(provider: str | None) -> Engine:
    try:
        return ENGINE_FACTORY(provider)
    except ProviderConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


class BatchIn(BaseModel):
    calls: list[Call]


def _public(result) -> dict:
    return {k: v for k, v in result.to_dict().items() if k != "meta"}


@app.get("/health", tags=["System"])
def health() -> dict:
    config = load_config()
    return {"status": "ok", "version": __version__, "provider": config["provider"], "models": config["models"]}


@app.post("/v1/review-call", tags=["Review"], dependencies=[Depends(require_key)])
def review_one(body: Call, provider: str | None = ProviderParam) -> dict:
    return _public(run_call(get_engine(provider), body))


@app.post("/v1/review-batch", tags=["Review"], dependencies=[Depends(require_key)])
def review_batch(body: BatchIn, provider: str | None = ProviderParam) -> dict:
    engine = get_engine(provider)
    limit = engine.config.get("analysis", {}).get("max_batch", 200)
    if len(body.calls) > limit:
        raise HTTPException(status_code=413, detail=f"{len(body.calls)} calls; the limit is {limit} per request.")
    if len({c.id for c in body.calls}) != len(body.calls):
        raise HTTPException(status_code=400, detail="Call ids must be unique.")
    results = run_batch(engine, body.calls)
    min_size = engine.config.get("analysis", {}).get("min_group_size", 5)
    return {"summary": summarise(results, min_group_size=min_size), "results": [_public(r) for r in results]}
