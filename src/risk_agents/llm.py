"""The language model behind the agent: Groq through its OpenAI-compatible API, and a scripted
fake for tests.

The agent loop only sees LLMReply and ToolCall, never the SDK's objects, so swapping the
provider or using the fake does not touch the loop. Every reply carries its tokens, latency and
cost, so runs and evaluations can report them without asking the provider again.
"""

import os
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

import httpx2
from openai import OpenAI

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "openai/gpt-oss-120b"

# gpt-oss is a reasoning model: its hidden reasoning counts as output tokens, so the cap is
# higher than an answer alone would need. The cap bounds the cost of a runaway output.
MAX_OUTPUT_TOKENS = 4096

# Groq retries are handled by the SDK: it retries 408, 409, 429 and 5xx with exponential
# backoff and honours Groq's retry-after header (up to two minutes).
MAX_RETRIES = 4

MILLION = Decimal(1_000_000)

Message = dict[str, Any]


@dataclass(frozen=True)
class Price:
    input_per_mtok: Decimal
    output_per_mtok: Decimal


# USD per million tokens, copied by hand from https://console.groq.com/docs/models
# (production models), checked 2026-11-10.
PRICES: dict[str, Price] = {
    "openai/gpt-oss-120b": Price(Decimal("0.15"), Decimal("0.60")),
    "openai/gpt-oss-20b": Price(Decimal("0.075"), Decimal("0.30")),
}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> Decimal | None:
    """None when the model has no known price: a missing price must not look free."""
    price = PRICES.get(model)
    if price is None:
        return None
    return (input_tokens * price.input_per_mtok + output_tokens * price.output_per_mtok) / MILLION


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # JSON text, exactly as the model wrote it


@dataclass(frozen=True)
class LLMReply:
    content: str | None
    tool_calls: tuple[ToolCall, ...]
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cost_usd: Decimal | None
    finish_reason: str | None  # "length" means the output hit MAX_OUTPUT_TOKENS
    retries: int = 0  # retries the SDK made (429, 5xx...); latency includes their waits

    def as_message(self) -> Message:
        """The reply as an assistant message, to append to the conversation history."""
        message: Message = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            message["tool_calls"] = [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.name, "arguments": c.arguments},
                }
                for c in self.tool_calls
            ]
        return message


class ChatModel(Protocol):
    """What the agent needs from a model. GroqClient and ScriptedLLM both fit."""

    model: str

    def complete(self, messages: list[Message], tools: list[dict] | None = None) -> LLMReply: ...


class MissingApiKeyError(RuntimeError):
    """GROQ_API_KEY is not set."""


class GroqClient:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        *,
        reasoning_effort: str = "medium",
        max_output_tokens: int = MAX_OUTPUT_TOKENS,
        timeout: float = 60,
        http_client: httpx2.Client | None = None,
    ) -> None:
        self.model = model
        self._reasoning_effort = reasoning_effort
        self._max_output_tokens = max_output_tokens
        # http_client is only for tests: a MockTransport replaces the network.
        self._client = OpenAI(
            api_key=api_key,
            base_url=GROQ_BASE_URL,
            timeout=timeout,
            max_retries=MAX_RETRIES,
            http_client=http_client,
        )

    @classmethod
    def from_env(cls, model: str = DEFAULT_MODEL, **kwargs: Any) -> "GroqClient":
        """Read the key from the environment; the code never opens .env itself."""
        key = os.environ.get("GROQ_API_KEY", "").strip()
        if not key:
            raise MissingApiKeyError(
                "GROQ_API_KEY no está definida. Ponla en .env (ver .env.example) y corre con"
                " `uv run --env-file .env ...`, o usa el LLM simulado."
            )
        return cls(key, model, **kwargs)

    def complete(self, messages: list[Message], tools: list[dict] | None = None) -> LLMReply:
        extra = {"tools": tools} if tools else {}
        start = time.perf_counter()
        # with_raw_response exposes how many retries the SDK made before succeeding.
        raw = self._client.chat.completions.with_raw_response.create(
            model=self.model,
            messages=messages,
            max_completion_tokens=self._max_output_tokens,
            reasoning_effort=self._reasoning_effort,
            **extra,
        )
        response = raw.parse()
        latency_ms = (time.perf_counter() - start) * 1000
        choice = response.choices[0]
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        return LLMReply(
            content=choice.message.content,
            tool_calls=tuple(
                ToolCall(c.id, c.function.name, c.function.arguments)
                for c in choice.message.tool_calls or []
            ),
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cost_usd=cost_usd(self.model, input_tokens, output_tokens) if usage else None,
            finish_reason=choice.finish_reason,
            retries=raw.retries_taken,
        )


def reply(content: str | None = None, tool_calls: Iterable[ToolCall] = ()) -> LLMReply:
    """A reply that no provider produced: for the scripted fake and for tests."""
    calls = tuple(tool_calls)
    return LLMReply(
        content=content,
        tool_calls=calls,
        model="scripted",
        input_tokens=0,
        output_tokens=0,
        latency_ms=0.0,
        cost_usd=Decimal(0),  # truly free: no model was called
        finish_reason="tool_calls" if calls else "stop",
    )


@dataclass
class ScriptedLLM:
    """Plays back fixed replies in order and records every request it receives."""

    replies: list[LLMReply]
    model: str = "scripted"
    calls: list[dict] = field(default_factory=list)

    def complete(self, messages: list[Message], tools: list[dict] | None = None) -> LLMReply:
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools})
        assert self.replies, "no scripted reply left: the agent asked the model more than expected"
        return self.replies.pop(0)
