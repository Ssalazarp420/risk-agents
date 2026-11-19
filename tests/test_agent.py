"""The agent loop, driven by a scripted model over the real database."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from risk_agents.agent import (
    CONCLUDE_SPEC,
    MAX_STEPS,
    PRELOADED_TOOLS,
    SYSTEM_PROMPT,
    build_context,
    run_agent,
)
from risk_agents.cases import load_cases
from risk_agents.llm import LLMReply, ScriptedLLM, ToolCall, reply
from risk_agents.tools import TOOL_SPECS, ToolBox

CASES_PATH = Path(__file__).resolve().parent.parent / "datos" / "casos_del_dia.csv"

CONCLUSION = {
    "hallazgos": [{"descripcion": "Comparte dispositivo", "evidencia": "cuentas_relacionadas"}],
    "nivel_preocupacion": "alto",
    "derivar_a": ["riesgo"],
    "resumen": "Anillo de cuentas.",
    "cuentas_relacionadas": ["J101084"],
    "alertas_calidad_datos": [],
}


def call(name: str, args: dict | str = "{}", id: str | None = None) -> ToolCall:
    text = args if isinstance(args, str) else json.dumps(args)
    return ToolCall(id or f"call_{name}", name, text)


def conclude(**changes) -> LLMReply:
    return reply(tool_calls=[call("concluir", {**CONCLUSION, **changes}, id="call_end")])


@pytest.fixture(scope="module")
def cases():
    return {c.caso_id: c for c in load_cases(CASES_PATH)}


@pytest.fixture
def box_for(repo, cases):
    players = frozenset(c.jugador_id for c in cases.values())
    return lambda caso_id: ToolBox(repo, cases[caso_id], case_players=players)


def run(box, *replies, **kwargs):
    """Loop mechanics are tested without preloading; TestPreload covers the default."""
    kwargs.setdefault("preload", ())
    llm = ScriptedLLM(list(replies))
    return run_agent(llm, box, "contexto del caso", **kwargs), llm


class TestHappyPath:
    def test_tools_then_conclusion(self, box_for):
        result, llm = run(
            box_for("C-20261101-016"),
            reply(tool_calls=[call("cuentas_relacionadas"), call("resumen_apuestas")]),
            conclude(),
        )
        assert result.status == "completo"
        assert result.conclusion == CONCLUSION
        assert result.steps == 2
        assert result.error is None

    def test_the_model_sees_the_prompt_the_context_and_every_tool(self, box_for):
        _, llm = run(box_for("C-20261101-016"), conclude())
        first = llm.calls[0]
        assert first["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}
        assert first["messages"][1] == {"role": "user", "content": "contexto del caso"}
        names = [t["function"]["name"] for t in first["tools"]]
        assert names == [t["function"]["name"] for t in TOOL_SPECS] + ["concluir"]

    def test_each_tool_result_answers_its_call(self, box_for):
        _, llm = run(
            box_for("C-20261101-016"),
            reply(tool_calls=[call("cuentas_relacionadas", id="a"), call("bonos", id="b")]),
            conclude(),
        )
        history = llm.calls[1]["messages"]
        assert history[2]["role"] == "assistant"
        tool_messages = history[3:]
        assert [m["tool_call_id"] for m in tool_messages] == ["a", "b"]
        assert "D-88436f9197" in tool_messages[0]["content"]

    def test_reports_which_accounts_the_tools_returned(self, box_for):
        result, _ = run(
            box_for("C-20261101-016"), reply(tool_calls=[call("cuentas_relacionadas")]), conclude()
        )
        assert result.related_seen == frozenset({"J100146", "J100563", "J101084"})

    def test_the_injection_reaches_the_model_flagged(self, box_for):
        _, llm = run(
            box_for("C-20261101-011"), reply(tool_calls=[call("resumen_transacciones")]), conclude()
        )
        tool_result = json.loads(llm.calls[1]["messages"][-1]["content"])
        assert any(n["parece_instruccion"] for n in tool_result["notas"]["items"])


class TestPreload:
    def test_the_first_call_already_has_the_three_basic_results(self, box_for):
        llm = ScriptedLLM([conclude()])
        result = run_agent(llm, box_for("C-20261101-016"), "contexto del caso")
        messages = llm.calls[0]["messages"]
        assert messages[2]["role"] == "assistant"
        assert [c["function"]["name"] for c in messages[2]["tool_calls"]] == list(PRELOADED_TOOLS)
        tool_messages = messages[3:]
        assert [m["tool_call_id"] for m in tool_messages] == [
            c["id"] for c in messages[2]["tool_calls"]
        ]
        assert "D-88436f9197" in tool_messages[0]["content"]
        assert result.steps == 1  # preloading is not a model call

    def test_preloaded_accounts_count_as_seen(self, box_for):
        llm = ScriptedLLM([conclude()])
        result = run_agent(llm, box_for("C-20261101-016"), "contexto del caso")
        assert result.related_seen == frozenset({"J100146", "J100563", "J101084"})

    def test_the_trace_marks_them_as_preloaded(self, box_for):
        llm = ScriptedLLM([conclude()])
        result = run_agent(llm, box_for("C-20261101-016"), "contexto del caso")
        tools = [e for e in result.trace if e["tipo"] == "herramienta"]
        assert [e["nombre"] for e in tools] == list(PRELOADED_TOOLS)
        assert all(e["precargada"] for e in tools)

    def test_the_prompt_says_they_are_already_there(self):
        for name in PRELOADED_TOOLS:
            assert name in SYSTEM_PROMPT
        assert "ya" in SYSTEM_PROMPT and "precarg" in SYSTEM_PROMPT


class TestRecoverableMistakes:
    def test_an_invalid_conclusion_goes_back_with_the_errors(self, box_for):
        result, llm = run(
            box_for("C-20261101-016"),
            conclude(nivel_preocupacion="critico", resumen="x" * 801),
            conclude(),
        )
        assert result.status == "completo"
        assert result.steps == 2
        error = json.loads(llm.calls[1]["messages"][-1]["content"])["error"]
        assert "nivel_preocupacion" in error and "resumen" in error

    def test_a_conclusion_that_is_not_json_goes_back(self, box_for):
        bad = reply(tool_calls=[call("concluir", "{no es json", id="x")])
        result, llm = run(box_for("C-20261101-016"), bad, conclude())
        assert result.status == "completo"
        assert "JSON" in llm.calls[1]["messages"][-1]["content"]

    def test_a_text_answer_gets_a_reminder_to_conclude(self, box_for):
        result, llm = run(box_for("C-20261101-016"), reply("Creo que es alto."), conclude())
        assert result.status == "completo"
        reminder = llm.calls[1]["messages"][-1]
        assert reminder["role"] == "user" and "concluir" in reminder["content"]

    def test_a_tool_error_goes_back_and_the_run_continues(self, box_for):
        result, llm = run(
            box_for("C-20261101-016"),
            reply(tool_calls=[call("resumen_apuestas", {"jugador_id": "J100146"})]),
            conclude(),
        )
        assert result.status == "completo"
        assert "cuentas_relacionadas" in llm.calls[1]["messages"][-1]["content"]


class TestLimits:
    def test_stops_at_the_step_limit(self, box_for):
        looping = [reply(tool_calls=[call("bonos", id=f"c{i}")]) for i in range(MAX_STEPS)]
        result, llm = run(box_for("C-20261101-016"), *looping)
        assert result.status == "incompleto"
        assert result.conclusion is None
        assert len(llm.calls) == MAX_STEPS
        assert "pasos" in result.error

    def test_a_smaller_limit_can_be_set(self, box_for):
        result, llm = run(box_for("C-20261101-016"), reply(tool_calls=[call("bonos")]), max_steps=1)
        assert result.status == "incompleto"
        assert len(llm.calls) == 1

    def test_a_cut_output_is_incomplete(self, box_for):
        cut = LLMReply(None, (), "m", 10, 4096, 1.0, Decimal("0.01"), "length")
        result, _ = run(box_for("C-20261101-016"), cut)
        assert result.status == "incompleto"
        assert "tokens" in result.error

    def test_a_provider_failure_is_incomplete_not_a_crash(self, box_for):
        result, _ = run(box_for("C-20261101-016"))  # the scripted model has nothing to say
        assert result.status == "incompleto"
        assert "AssertionError" in result.error


class TestUsageAndTrace:
    def test_adds_up_tokens_and_cost(self, box_for):
        a = LLMReply(None, (call("bonos"),), "m", 100, 10, 1.0, Decimal("0.01"), "tool_calls")
        b = LLMReply(None, (call("concluir", CONCLUSION),), "m", 200, 20, 1.0, Decimal("0.02"), "")
        result, _ = run(box_for("C-20261101-016"), a, b)
        assert (result.input_tokens, result.output_tokens) == (300, 30)
        assert result.cost_usd == Decimal("0.03")

    def test_an_unknown_cost_makes_the_total_unknown(self, box_for):
        a = LLMReply(None, (call("bonos"),), "m", 100, 10, 1.0, None, "tool_calls")
        result, _ = run(box_for("C-20261101-016"), a, conclude())
        assert result.cost_usd is None

    def test_the_trace_records_model_and_tool_steps(self, box_for):
        result, _ = run(
            box_for("C-20261101-016"),
            reply(tool_calls=[call("cuentas_relacionadas"), call("nada")]),
            conclude(),
        )
        kinds = [(e["tipo"], e.get("nombre")) for e in result.trace]
        assert kinds == [
            ("llm", None),
            ("herramienta", "cuentas_relacionadas"),
            ("herramienta", "nada"),
            ("llm", None),
            ("conclusion", None),
        ]
        assert result.trace[2]["error"] is True
        assert result.trace[1]["error"] is False
        json.dumps(result.trace)  # the trace can be written as JSON


class TestContext:
    def test_has_the_case_profile_score_history_and_metrics(self, repo, cases):
        case = cases["C-20261101-025"]
        text = build_context(case, repo, alerts=["una alerta"])
        assert "C-20261101-025" in text and "J101220" in text
        assert "2026-08-03" in text  # window start
        assert "actividad_nocturna" in text
        assert "0.812" in text and "0.84" in text  # previous and current score
        assert "49196" in text  # n_apuestas from the code's metrics
        assert "una alerta" in text

    def test_gives_the_model_a_sense_of_scale(self, repo, cases):
        data = json.loads(build_context(cases["C-20261101-025"], repo, []).split("\n\n", 1)[1])
        scale = data["referencias_poblacion"]
        assert scale["n_apuestas"]["valor"] == 49196
        assert scale["n_apuestas"]["percentil"] == 100
        assert scale["n_apuestas"]["maximo"] == 49196
        assert scale["max_apuestas_en_un_dia"]["percentil"] == 100
        assert scale["n_apuestas"]["mediana"] < 100

    def test_an_ordinary_player_is_not_extreme(self, repo, cases):
        data = json.loads(build_context(cases["C-20261101-007"], repo, []).split("\n\n", 1)[1])
        assert data["referencias_poblacion"]["n_apuestas"]["percentil"] < 90

    def test_has_no_personal_data(self, repo, cases):
        case = cases["C-20261101-025"]
        personal = repo.conn.execute(
            "SELECT alias, nombre_completo, documento, email, telefono FROM jugadores"
            " WHERE jugador_id = ?",
            (case.jugador_id,),
        ).fetchone()
        text = build_context(case, repo, alerts=[])
        assert all(value not in text for value in personal if value)


def test_the_conclusion_schema_matches_the_case_file_fields():
    schema = json.loads(
        (Path(__file__).resolve().parent.parent / "esquema_expediente.json").read_text()
    )
    params = CONCLUDE_SPEC["function"]["parameters"]
    assert set(params["required"]) == set(params["properties"])
    for field in params["properties"]:
        assert field in schema["properties"]
    assert params["properties"]["resumen"]["maxLength"] == 800
