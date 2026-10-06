"""Provider request/response shapes, checked against stub clients (no network)."""

from types import SimpleNamespace

import pytest

from sales_compliance.providers import AnthropicProvider, ImageInput, OpenAIProvider, ProviderConfigError, make_provider


class StubAnthropic:
    def __init__(self):
        self.request = None
        self.messages = self

    def create(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text='{"ok": true}')],
            usage=SimpleNamespace(input_tokens=11, output_tokens=7),
        )


class StubOpenAI:
    def __init__(self):
        self.request = None
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))],
            usage=SimpleNamespace(prompt_tokens=13, completion_tokens=5),
        )


def test_anthropic_request_and_parsing():
    stub = StubAnthropic()
    provider = AnthropicProvider("claude-test", max_tokens=100, temperature=0, client=stub)
    result = provider.complete("sys", "hello", images=[ImageInput(b"img", "image/png")])
    content = stub.request["messages"][0]["content"]
    assert content[0]["type"] == "image" and content[0]["source"]["media_type"] == "image/png"
    assert content[-1] == {"type": "text", "text": "hello"}
    assert stub.request["system"] == "sys" and stub.request["temperature"] == 0
    assert (result.text, result.input_tokens, result.output_tokens) == ('{"ok": true}', 11, 7)


def test_openai_request_and_parsing():
    stub = StubOpenAI()
    provider = OpenAIProvider("gpt-test", max_tokens=100, temperature=None, client=stub)
    result = provider.complete("sys", "hello", images=[ImageInput(b"img", "image/jpeg")], json_mode=True)
    content = stub.request["messages"][1]["content"]
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert stub.request["response_format"] == {"type": "json_object"}
    assert "temperature" not in stub.request
    assert stub.request["max_completion_tokens"] == 100
    assert (result.input_tokens, result.output_tokens) == (13, 5)


def test_missing_key_gives_clear_error(monkeypatch, config):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    for name in ("anthropic", "openai"):
        with pytest.raises(ProviderConfigError, match="API_KEY"):
            make_provider(name, config)
