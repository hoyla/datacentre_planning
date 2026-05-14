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
