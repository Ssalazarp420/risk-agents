"""The LLM client: Groq through the OpenAI-compatible API, cost per call, and the scripted fake.

No test reaches the network: the real client gets an httpx MockTransport.
"""

import json
from decimal import Decimal

import httpx2 as httpx
import openai
import pytest

from risk_agents.llm import (
    DEFAULT_MODEL,
    MAX_OUTPUT_TOKENS,
    PRICES,
    GroqClient,
    LLMReply,
    MissingApiKeyError,
    Price,
    ScriptedLLM,
    ToolCall,
    cost_usd,
    reply,
)

USER = [{"role": "user", "content": "hola"}]


def completion(message: dict, prompt_tokens=1000, completion_tokens=500, finish="stop") -> dict:
    """A response body shaped like the OpenAI chat completions API."""
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "openai/gpt-oss-120b",
        "choices": [
            {"index": 0, "message": {"role": "assistant", **message}, "finish_reason": finish}
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def client_with(*responses: httpx.Response, **kwargs):
    """A GroqClient whose HTTP layer replays `responses` and records the requests."""
    requests = []
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return queue.pop(0)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    return GroqClient("fake-key", http_client=http, **kwargs), requests


class TestCost:
    def test_uses_the_price_per_million_tokens(self, monkeypatch):
        monkeypatch.setitem(PRICES, "test/model", Price(Decimal("0.15"), Decimal("0.60")))
        assert cost_usd("test/model", 1_000_000, 500_000) == Decimal("0.45")

    def test_an_unknown_model_has_unknown_cost_not_zero(self):
        assert cost_usd("test/not-priced", 1000, 500) is None

    def test_the_default_model_has_a_price(self):
        assert DEFAULT_MODEL in PRICES


class TestGroqClient:
    def test_returns_text_tokens_cost_and_latency(self):
        client, _ = client_with(httpx.Response(200, json=completion({"content": "listo"})))
        r = client.complete(USER)
        assert r.content == "listo"
        assert r.tool_calls == ()
        assert (r.input_tokens, r.output_tokens) == (1000, 500)
        assert r.cost_usd == cost_usd(DEFAULT_MODEL, 1000, 500)
        assert r.latency_ms >= 0
        assert r.finish_reason == "stop"
        assert r.model == DEFAULT_MODEL

    def test_sends_the_model_limits_and_tools(self):
        client, requests = client_with(httpx.Response(200, json=completion({"content": "ok"})))
        tools = [{"type": "function", "function": {"name": "bonos", "parameters": {}}}]
        client.complete(USER, tools=tools)
        (sent,) = requests
        assert sent["model"] == DEFAULT_MODEL
        assert sent["max_completion_tokens"] == MAX_OUTPUT_TOKENS
        assert sent["reasoning_effort"] == "medium"
        assert sent["tools"] == tools
        assert sent["messages"] == USER

    def test_sends_no_tools_key_without_tools(self):
        client, requests = client_with(httpx.Response(200, json=completion({"content": "ok"})))
        client.complete(USER)
        assert "tools" not in requests[0]

    def test_parses_tool_calls(self):
        message = {
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "bonos", "arguments": '{"jugador_id": "J1"}'},
                }
            ],
        }
        client, _ = client_with(httpx.Response(200, json=completion(message, finish="tool_calls")))
        r = client.complete(USER)
        assert r.tool_calls == (ToolCall("call_1", "bonos", '{"jugador_id": "J1"}'),)
        assert r.finish_reason == "tool_calls"

    def test_retries_a_rate_limit_and_then_succeeds(self):
        client, requests = client_with(
            httpx.Response(429, headers={"retry-after-ms": "1"}, json={"error": "rate"}),
            httpx.Response(200, json=completion({"content": "ok"})),
        )
        assert client.complete(USER).content == "ok"
        assert len(requests) == 2

    def test_does_not_retry_a_bad_key(self):
        client, requests = client_with(httpx.Response(401, json={"error": "bad key"}))
        with pytest.raises(openai.AuthenticationError):
            client.complete(USER)
        assert len(requests) == 1

    def test_missing_usage_means_unknown_cost(self):
        body = completion({"content": "ok"})
        del body["usage"]
        client, _ = client_with(httpx.Response(200, json=body))
        r = client.complete(USER)
        assert (r.input_tokens, r.output_tokens, r.cost_usd) == (0, 0, None)


class TestFromEnv:
    def test_without_a_key_explains_how_to_set_it(self, monkeypatch):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        with pytest.raises(MissingApiKeyError, match="GROQ_API_KEY.*--env-file"):
            GroqClient.from_env()

    def test_an_empty_key_counts_as_missing(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "  ")
        with pytest.raises(MissingApiKeyError):
            GroqClient.from_env()

    def test_reads_the_key_and_model(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "fake-key")
        assert GroqClient.from_env(model="openai/gpt-oss-20b").model == "openai/gpt-oss-20b"


class TestReplyAsMessage:
    def test_text_reply(self):
        assert reply("hola").as_message() == {"role": "assistant", "content": "hola"}

    def test_tool_call_reply_can_go_back_into_the_history(self):
        r = reply(tool_calls=[ToolCall("c1", "bonos", "{}")])
        assert r.as_message() == {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "bonos", "arguments": "{}"}}
            ],
        }


class TestScriptedLLM:
    def test_replays_replies_in_order_and_records_what_it_saw(self):
        llm = ScriptedLLM([reply(tool_calls=[ToolCall("c1", "bonos", "{}")]), reply("fin")])
        assert llm.complete(USER).tool_calls[0].name == "bonos"
        assert llm.complete(USER + [{"role": "tool", "content": "{}"}]).content == "fin"
        assert len(llm.calls) == 2
        assert llm.calls[1]["messages"][-1]["role"] == "tool"

    def test_records_a_copy_of_the_messages(self):
        llm = ScriptedLLM([reply("a")])
        messages = list(USER)
        llm.complete(messages)
        messages.append({"role": "user", "content": "después"})
        assert len(llm.calls[0]["messages"]) == 1

    def test_running_out_of_replies_is_an_error(self):
        llm = ScriptedLLM([])
        with pytest.raises(AssertionError, match="no scripted reply"):
            llm.complete(USER)

    def test_costs_nothing_and_says_so(self):
        r = reply("x")
        assert isinstance(r, LLMReply)
        assert r.cost_usd == Decimal(0)
        assert r.model == "scripted"


def test_the_test_run_cannot_reach_the_network():
    import socket

    with pytest.raises(RuntimeError, match="network"):
        socket.create_connection(("api.groq.com", 443), timeout=1)
