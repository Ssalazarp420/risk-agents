"""The whole batch: prevalidation, agent, assembly, validation, output files and resume."""

import json
from pathlib import Path

import pytest

from risk_agents.baseline import RuleBasedLLM
from risk_agents.case_file import validate
from risk_agents.cases import load_cases
from risk_agents.llm import LLMReply, ScriptedLLM, ToolCall
from risk_agents.orchestrator import code_alerts, run_batch
from risk_agents.prevalidation import prevalidate

CASES_PATH = Path(__file__).resolve().parent.parent / "datos" / "casos_del_dia.csv"


def lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def paths(tmp_path):
    return {"out": tmp_path / "expedientes.jsonl", "traces": tmp_path / "trazas.jsonl"}


def batch(repo, llm, paths, **kwargs):
    return run_batch(CASES_PATH, repo, llm, paths["out"], paths["traces"], **kwargs)


class TestFullRun:
    @pytest.fixture
    def files(self, repo, paths):
        summary = batch(repo, RuleBasedLLM(), paths)
        return summary, {f["caso_id"]: f for f in lines(paths["out"])}, lines(paths["out"])

    def test_one_valid_line_per_case_in_file_order(self, files):
        _, _, ordered = files
        expected = [c.caso_id for c in load_cases(CASES_PATH)]
        assert [f["caso_id"] for f in ordered] == expected
        assert all(validate(f) == [] for f in ordered)

    def test_states(self, files):
        _, by_id, _ = files
        assert by_id["C-20261101-004"]["estado_investigacion"] == "sin_datos"
        assert by_id["C-20261101-018"]["estado_investigacion"] == "omitido"
        completed = [f for f in by_id.values() if f["estado_investigacion"] == "completo"]
        assert len(completed) == 23

    def test_metrics_come_from_the_code(self, files):
        _, by_id, _ = files
        reference = json.loads((CASES_PATH.parent / "casos_referencia.json").read_text())
        for ref in reference:
            assert by_id[ref["caso_id"]]["metricas_90d_usd"] == ref["metricas_90d_usd"]

    def test_code_alerts_reach_the_case_file(self, files):
        _, by_id, _ = files
        ring = by_id["C-20261101-016"]["alertas_calidad_datos"]
        assert any("J100146" in a and "flujo diario" in a for a in ring)
        injection = by_id["C-20261101-011"]["alertas_calidad_datos"]
        assert any("intenta dar instrucciones" in a and "2026-09-11" in a for a in injection)

    def test_one_trace_per_case(self, files, paths):
        traces = lines(paths["traces"])
        assert len(traces) == 25
        ring = next(t for t in traces if t["caso_id"] == "C-20261101-016")
        assert ring["estado"] == "completo"
        assert ring["modelo"] == "reglas"
        assert ring["pasos"] == 2
        assert [e["tipo"] for e in ring["eventos"]][-1] == "conclusion"

    def test_summary(self, files):
        summary, _, _ = files
        assert summary.by_state == {"completo": 23, "sin_datos": 1, "omitido": 1}
        assert summary.investigated == 23
        assert summary.cost_usd == 0
        assert any("J100146" in a for a in summary.batch_alerts)


class TestFailuresAndResume:
    def test_a_failing_model_leaves_valid_incomplete_files(self, repo, paths):
        summary = batch(repo, ScriptedLLM([]), paths)
        files = lines(paths["out"])
        incomplete = [f for f in files if f["estado_investigacion"] == "incompleto"]
        assert len(incomplete) == 23
        assert all(validate(f) == [] for f in files)
        assert all(f["metricas_90d_usd"] is not None for f in incomplete)
        assert summary.by_state["incompleto"] == 23

    def test_resume_only_redoes_what_is_missing_or_incomplete(self, repo, paths):
        batch(repo, ScriptedLLM([]), paths)  # everything investigated ends incomplete
        batch(repo, RuleBasedLLM(), paths, only={"C-20261101-016"})
        assert sum(f["estado_investigacion"] == "completo" for f in lines(paths["out"])) == 1

        silent = ScriptedLLM([])
        summary = batch(repo, RuleBasedLLM(), paths)
        assert summary.investigated == 22  # 016 was kept
        assert all(validate(f) == [] for f in lines(paths["out"]))
        assert len(lines(paths["out"])) == 25
        batch(repo, silent, paths)  # nothing left to do: the model is never called
        assert silent.calls == []

    def test_a_case_file_that_breaks_the_schema_is_not_written_as_complete(
        self, repo, paths, monkeypatch
    ):
        import risk_agents.orchestrator as orchestrator

        real = orchestrator.investigated_file
        monkeypatch.setattr(
            orchestrator, "investigated_file", lambda *a: {**real(*a), "campo_extra": 1}
        )
        batch(repo, RuleBasedLLM(), paths, only={"C-20261101-016"})
        (file,) = lines(paths["out"])
        assert file["estado_investigacion"] == "incompleto"
        assert validate(file) == []
        (trace,) = lines(paths["traces"])
        assert "esquema" in trace["error"]

    def test_an_unknown_cost_makes_the_run_cost_unknown(self, repo, paths):
        conclusion = {
            "hallazgos": [{"descripcion": "d", "evidencia": "e"}],
            "nivel_preocupacion": "bajo",
            "derivar_a": [],
            "resumen": "r",
            "cuentas_relacionadas": [],
            "alertas_calidad_datos": [],
        }
        end = ToolCall("c", "concluir", json.dumps(conclusion))
        unpriced = LLMReply(None, (end,), "sin-precio", 10, 5, 1.0, None, "tool_calls")
        summary = batch(repo, ScriptedLLM([unpriced]), paths, only={"C-20261101-007"})
        assert summary.cost_usd is None

    def test_fresh_ignores_previous_results(self, repo, paths):
        batch(repo, RuleBasedLLM(), paths)
        summary = batch(repo, RuleBasedLLM(), paths, resume=False)
        assert summary.investigated == 23
        assert len(lines(paths["traces"])) == 25

    def test_only_writes_the_requested_cases_on_a_fresh_file(self, repo, paths):
        batch(repo, RuleBasedLLM(), paths, only={"C-20261101-011", "C-20261101-004"})
        assert [f["caso_id"] for f in lines(paths["out"])] == ["C-20261101-004", "C-20261101-011"]


@pytest.fixture(scope="module")
def by_id(repo):
    cases = load_cases(CASES_PATH)
    report = prevalidate(cases, repo)
    return {c.caso_id: code_alerts(c, repo, report.missing_players) for c in cases}


class TestCodeAlerts:
    def test_a_note_that_gives_orders_is_reported(self, by_id):
        assert any("intenta dar instrucciones" in a for a in by_id["C-20261101-011"])

    def test_ring_members_missing_from_the_file_are_reported(self, by_id):
        for caso_id in ("C-20261101-016", "C-20261101-020"):
            alerts = " ".join(by_id[caso_id])
            assert "J100146" in alerts and "J100563" in alerts

    def test_normal_cases_get_no_alerts(self, by_id):
        assert by_id["C-20261101-009"] == []
        assert by_id["C-20261101-007"] == []


def test_the_baseline_only_asks_for_what_was_not_preloaded(repo, paths):
    batch(repo, RuleBasedLLM(), paths, only={"C-20261101-016"})
    (trace,) = lines(paths["traces"])
    asked = [e["nombre"] for e in trace["eventos"] if e["tipo"] == "herramienta"]
    assert asked == ["cuentas_relacionadas", "resumen_transacciones", "resumen_apuestas", "bonos"]
    assert trace["pasos"] == 2
