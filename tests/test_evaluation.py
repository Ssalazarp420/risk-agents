"""Scoring case files against the analyst's references and our hypotheses."""

import json
from pathlib import Path

import pytest

from risk_agents.baseline import RuleBasedLLM
from risk_agents.evaluation import (
    Expectation,
    load_expectations,
    main,
    render_report,
    score_case,
    score_run,
)
from risk_agents.orchestrator import run_batch

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "datos" / "casos_del_dia.csv"
REFERENCES = json.loads((ROOT / "datos" / "casos_referencia.json").read_text())
REF_020 = next(r for r in REFERENCES if r["caso_id"] == "C-20261101-020")


@pytest.fixture(scope="module")
def expectations():
    return load_expectations()


class TestExpectations:
    def test_covers_every_case_of_the_day(self, expectations):
        assert len(expectations) == 25

    def test_references_come_from_the_official_file(self, expectations):
        e = expectations["C-20261101-020"]
        assert e.source == "analista"
        assert e.levels == {"alto"}
        assert e.teams_exact == {"riesgo"}
        assert e.accounts == {"J100146", "J100563", "J101070"}
        assert e.metrics == REF_020["metricas_90d_usd"]

    def test_hypotheses_are_marked_as_such(self, expectations):
        e = expectations["C-20261101-025"]
        assert e.source == "hipotesis"
        assert e.levels == {"medio", "alto"}
        assert e.teams_include == {"juego_responsable"}
        assert e.metrics is None


class TestScoreCase:
    def test_the_reference_itself_scores_perfectly(self, expectations):
        s = score_case(REF_020, expectations["C-20261101-020"])
        assert s.valid and s.state and s.level and s.teams and s.accounts and s.metrics
        assert s.facts == (2, 2)

    def test_a_wrong_level_and_team(self, expectations):
        file = {**REF_020, "nivel_preocupacion": "medio", "derivar_a": ["juego_responsable"]}
        s = score_case(file, expectations["C-20261101-020"])
        assert s.level is False and s.teams is False

    def test_team_order_does_not_matter(self, expectations):
        e = Expectation(
            "X",
            "analista",
            "completo",
            levels={"alto"},
            teams_exact={"riesgo", "juego_responsable"},
        )
        file = {**REF_020, "derivar_a": ["juego_responsable", "riesgo"]}
        assert score_case(file, e).teams is True

    def test_include_and_exclude_for_hypotheses(self):
        e = Expectation(
            "X",
            "hipotesis",
            "completo",
            levels={"medio", "alto"},
            teams_include={"juego_responsable"},
            teams_exclude={"riesgo"},
        )
        ok = {**REF_020, "nivel_preocupacion": "medio", "derivar_a": ["juego_responsable"]}
        assert score_case(ok, e).teams is True
        both = {**ok, "derivar_a": ["juego_responsable", "riesgo"]}
        assert score_case(both, e).teams is False

    def test_missing_and_extra_accounts_are_counted(self, expectations):
        file = {**REF_020, "cuentas_relacionadas": ["J100146", "J999999"]}
        s = score_case(file, expectations["C-20261101-020"])
        assert s.accounts is False
        assert (s.accounts_missing, s.accounts_extra) == (2, 1)

    def test_facts_ignore_case_and_accents(self):
        e = Expectation("X", "hipotesis", "completo", facts=[["contracargo"], ["vip"]])
        file = {
            **REF_020,
            "hallazgos": [{"descripcion": "CONTRACARGÓ", "evidencia": "x"}],
            "resumen": "cliente Vip",
        }
        assert score_case(file, e).facts == (2, 2)

    def test_alerts(self):
        e = Expectation("X", "hipotesis", "completo", alerts=[["actividad_nocturna"]])
        assert score_case({**REF_020, "alertas_calidad_datos": []}, e).alerts is False
        hit = {**REF_020, "alertas_calidad_datos": ["El factor actividad_nocturna no cuadra"]}
        assert score_case(hit, e).alerts is True

    def test_an_incomplete_file_fails_the_judgement_checks(self, expectations):
        file = {**REF_020, "estado_investigacion": "incompleto", "nivel_preocupacion": None}
        s = score_case(file, expectations["C-20261101-020"])
        assert s.state is False and s.level is False

    def test_a_missing_file_scores_nothing(self, expectations):
        s = score_case(None, expectations["C-20261101-020"])
        assert not s.valid and s.state is False

    def test_checks_that_do_not_apply_are_none(self, expectations):
        s = score_case(
            {**REF_020, "caso_id": "C-20261101-004", "estado_investigacion": "sin_datos"},
            expectations["C-20261101-004"],
        )
        assert s.level is None and s.teams is None and s.accounts is None


@pytest.fixture(scope="module")
def baseline_run(repo, tmp_path_factory):
    folder = tmp_path_factory.mktemp("reglas")
    summary = run_batch(
        CASES, repo, RuleBasedLLM(), folder / "expedientes.jsonl", folder / "trazas.jsonl"
    )
    (folder / "resumen_corrida.json").write_text(
        json.dumps({"modelo": "reglas", **summary.as_dict()})
    )
    return folder


class TestRuns:
    def test_the_baseline_matches_the_five_references(self, baseline_run, expectations):
        run = score_run(baseline_run, expectations)
        assert run.valid == 25
        refs = [s for s in run.cases.values() if s.source == "analista"]
        assert len(refs) == 5
        assert all(s.level and s.teams and s.metrics for s in refs)
        assert run.model == "reglas"
        assert run.cost_usd == 0

    def test_report_and_command(self, baseline_run, tmp_path):
        out = tmp_path / "reporte.md"
        assert main(["--system", f"reglas={baseline_run}", "--out", str(out)]) == 0
        text = out.read_text()
        assert "reglas" in text and "C-20261101-025" in text
        assert json.loads((tmp_path / "reporte.json").read_text())["sistemas"]["reglas"]

    def test_runs_of_one_system_report_ranges_and_consistency(self, baseline_run):
        text = render_report({"reglas": [score_run(baseline_run), score_run(baseline_run)]})
        assert "2 corridas" in text
        assert "100 %" in text  # two identical runs are fully consistent
