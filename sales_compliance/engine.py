"""Engine: provider + guardrails + validated structured output (retry once on invalid JSON)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from .audit import AuditLog
from .config import load_config, resolve
from .guardrails import check_input_size, redact
from .jsonutil import extract_json
from .providers import ImageInput, Provider, make_provider

T = TypeVar("T", bound=BaseModel)


@dataclass
class CallMeta:
    request_id: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    attempts: int = 0


class UseCaseError(RuntimeError):
    """The model could not produce a valid result. Carries call metadata for the audit log."""

    def __init__(self, message: str, meta: CallMeta | None = None):
        super().__init__(message)
        self.meta = meta




class Engine:
    def __init__(
        self,
        config: dict | None = None,
        provider: Provider | None = None,
        audit: AuditLog | None = None,
        provider_name: str | None = None,
    ):
        self.config = config or load_config()
        self.provider = provider or make_provider(provider_name or self.config["provider"], self.config)
        audit_cfg = self.config.get("audit", {})
        self.audit = audit or AuditLog(
            resolve(audit_cfg.get("path", "logs/audit.jsonl")), log_content=audit_cfg.get("log_content", False)
        )
        guard_cfg = self.config.get("guardrails", {})
        self.redact_pii = guard_cfg.get("redact_pii", True)
        self.max_input_chars = guard_cfg.get("max_input_chars", 40000)

    # -- guardrails -------------------------------------------------------
    def guard(self, text: str) -> tuple[str, dict[str, int]]:
        """Size-check and redact a piece of user-supplied text before it goes to a model."""
        check_input_size(text, self.max_input_chars)
        if not self.redact_pii:
            return text, {}
        result = redact(text)
        return result.text, result.counts


    # -- model calls ------------------------------------------------------
    def new_meta(self) -> CallMeta:
        return CallMeta(request_id=uuid.uuid4().hex[:12], provider=self.provider.name, model=self.provider.model)

    def call_json(
        self, system: str, user: str, schema: type[T], images: list[ImageInput] | None = None
    ) -> tuple[T, CallMeta]:
        """Call the model and validate its JSON against a schema. Retries once with the error."""
        meta = self.new_meta()
        prompt = user
        last_error: Exception | None = None
        for attempt in (1, 2):
            meta.attempts = attempt
            result = self.provider.complete(system=system, user=prompt, images=images, json_mode=True)
            meta.input_tokens += result.input_tokens
            meta.output_tokens += result.output_tokens
            meta.latency_ms += result.latency_ms
            try:
                parsed = schema.model_validate(extract_json(result.text))
                return parsed, meta
            except (ValueError, ValidationError) as exc:
                last_error = exc
                first_line = str(exc).splitlines()[0][:300]
                prompt = (
                    f"{user}\n\nYour previous reply could not be used: {first_line}. "
                    "Reply with the JSON object only, using exactly the keys requested."
                )
        raise UseCaseError(f"Model output failed validation twice: {last_error}", meta)
