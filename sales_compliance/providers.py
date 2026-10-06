"""Model providers behind one interface.

Swap Claude <-> OpenAI in config.yaml; use cases never import a vendor SDK directly.
Both SDKs also honour ANTHROPIC_BASE_URL / OPENAI_BASE_URL, so the same code can point
at an enterprise gateway or proxy instead of the public endpoints.
"""

from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass
from typing import Callable


class ProviderConfigError(RuntimeError):
    """Raised when a provider is missing configuration such as an API key."""


@dataclass
class ImageInput:
    data: bytes
    media_type: str  # e.g. image/png

    @property
    def b64(self) -> str:
        return base64.b64encode(self.data).decode("ascii")


@dataclass
class LLMResult:
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: float


class Provider:
    name = "base"

    def __init__(self, model: str):
        self.model = model

    def complete(
        self,
        system: str,
        user: str,
        images: list[ImageInput] | None = None,
        json_mode: bool = False,
    ) -> LLMResult:
        raise NotImplementedError


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self, model: str, max_tokens: int = 4000, temperature: float | None = 0, client=None):
        super().__init__(model)
        self.max_tokens = max_tokens
        self.temperature = temperature
        if client is None:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise ProviderConfigError("ANTHROPIC_API_KEY is not set. Add it to .env or your environment.")
            import anthropic

            client = anthropic.Anthropic()
        self.client = client

    def build_request(self, system: str, user: str, images: list[ImageInput] | None) -> dict:
        content: list[dict] = [
            {"type": "image", "source": {"type": "base64", "media_type": img.media_type, "data": img.b64}}
            for img in images or []
        ]
        content.append({"type": "text", "text": user})
        request = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": content}],
        }
        if self.temperature is not None:
            request["temperature"] = self.temperature
        return request

    def complete(self, system, user, images=None, json_mode=False) -> LLMResult:
        request = self.build_request(system, user, images)
        start = time.perf_counter()
        response = self.client.messages.create(**request)
        latency_ms = (time.perf_counter() - start) * 1000
        text = "".join(getattr(b, "text", "") for b in response.content if getattr(b, "type", "") == "text")
        return LLMResult(text, response.usage.input_tokens, response.usage.output_tokens, latency_ms)


class OpenAIProvider(Provider):
    name = "openai"

    def __init__(self, model: str, max_tokens: int = 16000, temperature: float | None = None, client=None):
        super().__init__(model)
        self.max_tokens = max_tokens
        self.temperature = temperature
        if client is None:
            if not os.environ.get("OPENAI_API_KEY"):
                raise ProviderConfigError("OPENAI_API_KEY is not set. Add it to .env or your environment.")
            import openai

            client = openai.OpenAI()
        self.client = client

    def build_request(self, system: str, user: str, images: list[ImageInput] | None, json_mode: bool) -> dict:
        content: list[dict] = [{"type": "text", "text": user}]
        content += [
            {"type": "image_url", "image_url": {"url": f"data:{img.media_type};base64,{img.b64}"}}
            for img in images or []
        ]
        request = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
            "max_completion_tokens": self.max_tokens,
        }
        if json_mode:
            request["response_format"] = {"type": "json_object"}
        if self.temperature is not None:
            request["temperature"] = self.temperature
        return request

    def complete(self, system, user, images=None, json_mode=False) -> LLMResult:
        request = self.build_request(system, user, images, json_mode)
        start = time.perf_counter()
        response = self.client.chat.completions.create(**request)
        latency_ms = (time.perf_counter() - start) * 1000
        text = response.choices[0].message.content or ""
        return LLMResult(text, response.usage.prompt_tokens, response.usage.completion_tokens, latency_ms)


class FakeProvider(Provider):
    """Deterministic provider for tests. Never used for eval results."""

    name = "fake"

    def __init__(self, responder: str | list[str] | Callable[[str, str, list], str], model: str = "fake-model"):
        super().__init__(model)
        self.responder = responder
        self.calls: list[dict] = []

    def complete(self, system, user, images=None, json_mode=False) -> LLMResult:
        self.calls.append({"system": system, "user": user, "images": images or []})
        if callable(self.responder):
            text = self.responder(system, user, images or [])
        elif isinstance(self.responder, list):
            text = self.responder[min(len(self.calls), len(self.responder)) - 1]
        else:
            text = self.responder
        return LLMResult(text, input_tokens=100, output_tokens=50, latency_ms=1.0)


def make_provider(name: str, config: dict) -> Provider:
    model = config["models"][name]
    max_tokens = config.get("max_output_tokens", {}).get(name, 4000)
    temperature = config.get("temperature", {}).get(name)
    if name == "anthropic":
        return AnthropicProvider(model, max_tokens=max_tokens, temperature=temperature)
    if name == "openai":
        return OpenAIProvider(model, max_tokens=max_tokens, temperature=temperature)
    raise ProviderConfigError(f"Unknown provider '{name}'. Use 'anthropic' or 'openai'.")
