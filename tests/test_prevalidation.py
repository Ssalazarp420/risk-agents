"""Checks run on every case before any LLM call."""

from pathlib import Path

from risk_agents.cases import Case, load_cases
from risk_agents.data.repository import Repository, connect_read_only
from risk_agents.prevalidation import Decision, prevalidate

CASES_PATH = Path(__file__).resolve().parent.parent / "datos" / "casos_del_dia.csv"

MINI = """
INSERT INTO tasas_cambio VALUES ('USD', 1.0);
INSERT INTO jugadores (jugador_id, marca, pais, moneda, segmento, estado_cuenta) VALUES
    ('J1', 'A', 'PA', 'USD', 'regular', 'activa'),
    ('J2', 'A', 'PA', 'USD', 'regular', 'activa'),
    ('J3', 'A', 'PA', 'USD', 'regular', 'activa'),
    ('J4', 'A', 'PA', 'USD', 'regular', 'activa');
INSERT INTO scores_riesgo (jugador_id, fecha_corte, score) VALUES
    ('J1', '2026-10-31', 0.9),
    ('J2', '2026-10-31', 0.8),
    ('J3', '2026-10-31', 0.95),
    ('J4', '2026-10-31', 0.1),
    ('J3', '2026-10-24', 0.99);
INSERT INTO transacciones (jugador_id, fecha_hora, tipo, monto, estado) VALUES
    ('J9', '2026-09-01 10:00:00', 'deposito', 10, 'aprobada');
"""


def triage(make_db, cases):
    return prevalidate(cases, Repository(connect_read_only(make_db(MINI))))


def case(caso_id, jugador_id, score, fecha_corte="2026-10-31"):
    return Case(caso_id, jugador_id, fecha_corte, score)


class TestPerCase:
    def test_a_valid_case_goes_to_the_agent_without_alerts(self, make_db):
        report = triage(make_db, [case("C-1", "J1", 0.9)])
        (t,) = report.triages
        assert t.decision is Decision.INVESTIGATE
        assert t.alerts == []

    def test_a_player_missing_from_the_database_has_no_data(self, make_db):
        report = triage(make_db, [case("C-1", "J404", 0.81)])
        (t,) = report.triages
        assert t.decision is Decision.NO_DATA
        assert any("J404" in a and "jugadores" in a for a in t.alerts)

    def test_rows_of_an_unregistered_player_are_reported(self, make_db):
        report = triage(make_db, [case("C-1", "J9", 0.5)])
        (t,) = report.triages
        assert t.decision is Decision.NO_DATA
        assert any("transacciones" in a for a in t.alerts)

    def test_the_second_appearance_of_a_player_and_cutoff_is_a_duplicate(self, make_db):
        report = triage(make_db, [case("C-1", "J1", 0.9), case("C-2", "J1", 0.9)])
        first, second = report.triages
        assert first.decision is Decision.INVESTIGATE
        assert second.decision is Decision.DUPLICATE
        assert second.duplicate_of == "C-1"
        assert any("C-1" in a and "C-2" in a for a in second.alerts)

    def test_the_same_player_on_another_cutoff_is_not_a_duplicate(self, make_db):
        report = triage(
            make_db, [case("C-1", "J3", 0.95), case("C-2", "J3", 0.99, fecha_corte="2026-10-24")]
        )
        assert [t.decision for t in report.triages] == [Decision.INVESTIGATE] * 2

    def test_a_score_that_differs_from_the_model_is_flagged_but_investigated(self, make_db):
        report = triage(make_db, [case("C-1", "J2", 0.7)])
        (t,) = report.triages
        assert t.decision is Decision.INVESTIGATE
        assert any("0.7" in a and "0.8" in a for a in t.alerts)

    def test_a_score_missing_from_the_model_is_flagged(self, make_db):
        report = triage(make_db, [case("C-1", "J1", 0.9, fecha_corte="2026-10-24")])
        (t,) = report.triages
        assert t.decision is Decision.INVESTIGATE
        assert any("scores_riesgo" in a for a in t.alerts)


class TestBatch:
    def test_finds_players_above_the_threshold_that_are_not_in_the_file(self, make_db):
        # Threshold = lowest score in the file (0.8). J3 (0.95) is above it and missing;
        # J4 (0.1) is below it.
        report = triage(make_db, [case("C-1", "J1", 0.9), case("C-2", "J2", 0.8)])
        assert report.missing_players == {"2026-10-31": [("J3", 0.95)]}
        assert any("J3" in a for a in report.alerts)

    def test_a_missing_player_exactly_at_the_threshold_counts(self, make_db):
        db = make_db(
            MINI
            + "INSERT INTO jugadores (jugador_id, moneda) VALUES ('J5', 'USD');"
            + "INSERT INTO scores_riesgo VALUES ('J5', '2026-10-31', 0.8, NULL, NULL);"
        )
        report = prevalidate(
            [case("C-1", "J1", 0.9), case("C-2", "J2", 0.8)],
            Repository(connect_read_only(db)),
        )
        assert ("J5", 0.8) in report.missing_players["2026-10-31"]

    def test_a_repeated_case_id_is_a_batch_alert(self, make_db):
        report = triage(make_db, [case("C-1", "J1", 0.9), case("C-1", "J2", 0.8)])
        assert any("C-1" in a for a in report.alerts)

    def test_triages_keep_the_file_order(self, make_db):
        cases = [case("C-3", "J2", 0.8), case("C-1", "J404", 0.8), case("C-2", "J1", 0.9)]
        report = triage(make_db, cases)
        assert [t.case.caso_id for t in report.triages] == ["C-3", "C-1", "C-2"]


class TestRealCases:
    def test_the_traps_in_todays_file(self, repo):
        report = prevalidate(load_cases(CASES_PATH), repo)
        by_id = {t.case.caso_id: t for t in report.triages}

        assert by_id["C-20261101-004"].decision is Decision.NO_DATA
        assert by_id["C-20261101-018"].decision is Decision.DUPLICATE
        assert by_id["C-20261101-018"].duplicate_of == "C-20261101-014"
        investigated = [t for t in report.triages if t.decision is Decision.INVESTIGATE]
        assert len(investigated) == 23
        assert all(t.alerts == [] for t in investigated)

        assert report.missing_players == {"2026-10-31": [("J100146", 0.958), ("J100563", 0.91)]}
