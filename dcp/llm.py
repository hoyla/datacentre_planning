"""Pluggable LLM backend. Ollama for production; FakeBackend keeps tests dependency-free."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol


@dataclass
class LLMResponse:
    text: str
    model: str
    raw: dict | None = None


class LLMBackend(Protocol):
    def complete(self, prompt: str, *, system: str | None = None) -> LLMResponse: ...


class OllamaBackend:
    def __init__(
        self,
        host: str | None = None,
        model: str | None = None,
        request_timeout: float | None = None,
    ):
        self.host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.model = model or os.environ.get("OLLAMA_MODEL", "llama3.2")
        # 90s default. Caller can pass a higher value for slow models / larger ctx,
        # or read from OLLAMA_REQUEST_TIMEOUT env var.
        if request_timeout is None:
            env_to = os.environ.get("OLLAMA_REQUEST_TIMEOUT")
            request_timeout = float(env_to) if env_to else 90.0
        self.request_timeout = request_timeout

    def complete(self, prompt: str, *, system: str | None = None) -> LLMResponse:
        import httpx

        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        resp = httpx.post(
            f"{self.host}/api/chat",
            json={"model": self.model, "messages": messages, "stream": False},
            timeout=self.request_timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return LLMResponse(text=data["message"]["content"], model=self.model, raw=data)


class ClaudeBackend:
    """Anthropic Claude via the Messages API (anthropic SDK).

    Used for the Sonnet-5-vs-granite triage trial (2026-08) and available to
    any stage that takes a model string: `make_backend` routes any name
    starting 'claude' here. Runs on Luke's personal Anthropic account — the
    same personal-account caveat as the v1 Read-tool extraction applies.

    Defaults are deliberate: adaptive thinking stays on (the model decides,
    and classification benefits), and max_tokens leaves room for thinking +
    the JSON verdict.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-5",
        request_timeout: float | None = None,
        max_tokens: int = 4000,
    ):
        import anthropic

        self.model = model
        self.max_tokens = max_tokens
        self.client = anthropic.Anthropic(timeout=request_timeout or 120.0)

    def complete(self, prompt: str, *, system: str | None = None) -> LLMResponse:
        kwargs: dict = {}
        if system:
            kwargs["system"] = system
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )
        text = "".join(b.text for b in msg.content if b.type == "text")
        return LLMResponse(text=text, model=self.model, raw=msg.to_dict())


def make_backend(
    model: str, request_timeout: float | None = None
) -> LLMBackend:
    """Model-string dispatch: 'claude-*' → ClaudeBackend, anything else →
    OllamaBackend. Keeps CLI surfaces (`dcp triage --model X`,
    `scripts/eval_triage.py --model X`) backend-agnostic."""
    if model.startswith("claude"):
        return ClaudeBackend(model=model, request_timeout=request_timeout)
    return OllamaBackend(model=model, request_timeout=request_timeout)


class FakeBackend:
    """Deterministic fake: returns canned responses keyed by prompt prefix."""

    def __init__(self, responses: dict[str, str] | None = None):
        self.responses = responses or {}
        self.calls: list[tuple[str, str | None]] = []

    def complete(self, prompt: str, *, system: str | None = None) -> LLMResponse:
        self.calls.append((prompt, system))
        for prefix, text in self.responses.items():
            if prompt.startswith(prefix):
                return LLMResponse(text=text, model="fake")
        return LLMResponse(text="", model="fake")


def default_backend() -> LLMBackend:
    return OllamaBackend()
