"""SQLite access: read-only connection, player profile and the 90-day metrics."""

import dataclasses
import json
import sqlite3
from pathlib import Path

import pytest

from risk_agents.data.repository import (
    Player,
    Repository,
    UnknownCurrencyError,
    connect_read_only,
)
from risk_agents.data.rules import window_for

REFERENCE_CASES = json.loads(
    (Path(__file__).resolve().parent.parent / "datos" / "casos_referencia.json").read_text()
)
PERSONAL_DATA = {"alias", "nombre_completo", "documento", "email", "telefono"}

# One player in MXN with an easy rate, and rows on both sides of every rule.
MINI = """
INSERT INTO tasas_cambio VALUES ('USD', 1.0), ('MXN', 0.5);
INSERT INTO jugadores VALUES ('J1', 'B', 'PB', 'MXN', '2026-01-01 10:00:00', 'alias1',
    'Nombre Uno', '123', 'uno@example.com', '+52 1', 'regular', 'activa');
INSERT INTO jugadores VALUES ('J2', 'A', 'PA', 'EUR', '2026-01-01 10:00:00', 'alias2',
    'Nombre Dos', '456', 'dos@example.com', '+52 2', 'regular', 'activa');

-- Window for cutoff 2026-10-31: 2026-08-03 00:00:00 to 2026-10-31 23:59:59
INSERT INTO transacciones (jugador_id, fecha_hora, tipo, medio_pago, monto, moneda, estado)
VALUES
    ('J1', '2026-08-03 00:00:00', 'deposito', 'tarjeta', 100, 'MXN', 'aprobada'),
    ('J1', '2026-10-31 23:59:59', 'deposito', 'tarjeta', 20, 'MXN', 'aprobada'),
    ('J1', '2026-09-01 12:00:00', 'deposito', 'tarjeta', 50, 'MXN', 'rechazada'),
    ('J1', '2026-09-01 12:00:00', 'deposito', 'tarjeta', 30, 'MXN', 'revertida'),
    ('J1', '2026-09-01 12:00:00', 'deposito', 'tarjeta', 70, 'MXN', 'pendiente'),
    ('J1', '2026-09-01 12:00:00', 'ajuste', 'tarjeta', 999, 'MXN', 'aprobada'),
    ('J1', '2026-09-02 12:00:00', 'retiro', 'transferencia', 40, 'MXN', 'aprobada'),
    ('J1', '2026-09-02 12:00:00', 'retiro', 'transferencia', 10, 'MXN', 'pendiente'),
    ('J1', '2026-08-02 23:59:59', 'deposito', 'tarjeta', 1000, 'MXN', 'aprobada'),
    ('J1', '2026-11-01 00:00:00', 'deposito', 'tarjeta', 2000, 'MXN', 'aprobada');

INSERT INTO apuestas (jugador_id, fecha_hora, producto, detalle, monto, ganancia, cuota,
    con_bono, moneda)
VALUES
    ('J1', '2026-08-03 00:00:00', 'deportes', 'fútbol', 10, 0, 1.5, 0, 'MXN'),
    ('J1', '2026-10-31 23:59:59', 'casino', 'slots', 30, 50, NULL, 1, 'MXN'),
    ('J1', '2026-11-05 10:00:00', 'casino', 'slots', 500, 0, NULL, 0, 'MXN');

INSERT INTO bonos (jugador_id, tipo, monto, moneda, fecha_otorgado, estado) VALUES
    ('J1', 'bienvenida', 8, 'MXN', '2026-08-10 09:00:00', 'expirado'),
    ('J1', 'recarga', 4, 'MXN', '2026-09-10 09:00:00', 'redimido'),
    ('J1', 'recarga', 100, 'MXN', '2026-11-02 09:00:00', 'otorgado');
"""


class TestReadOnlyConnection:
    def test_rejects_writes(self, make_db):
        conn = connect_read_only(make_db(MINI))
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("DELETE FROM jugadores")

    def test_a_missing_file_is_an_error_not_a_new_empty_database(self, tmp_path):
        missing = tmp_path / "missing.db"
        with pytest.raises(FileNotFoundError, match="missing.db"):
            connect_read_only(missing)
        assert not missing.exists()


class TestPlayer:
    def test_returns_the_profile_without_personal_data(self, make_db):
        repo = Repository(connect_read_only(make_db(MINI)))
        assert repo.get_player("J1") == Player(
            jugador_id="J1",
            marca="B",
            pais="PB",
            moneda="MXN",
            fecha_registro="2026-01-01 10:00:00",
            segmento="regular",
            estado_cuenta="activa",
        )

    def test_the_profile_type_has_no_personal_data_fields(self):
        fields = {f.name for f in dataclasses.fields(Player)}
        assert not fields & PERSONAL_DATA

    def test_unknown_player_is_none(self, make_db):
        repo = Repository(connect_read_only(make_db(MINI)))
        assert repo.get_player("J999") is None


class TestNativeTotals:
    def test_applies_every_rule_of_the_metric_definitions(self, make_db):
        repo = Repository(connect_read_only(make_db(MINI)))
        totals = repo.native_totals("J1", window_for("2026-10-31"))
        # Only approved deposits and withdrawals, no adjustments, window edges included,
        # nothing before the window or after the cutoff.
        assert totals.deposits == 120
        assert totals.withdrawals == 40
        assert totals.staked == 40
        assert totals.paid_out == 50
        assert totals.n_bets == 2
        # Bonuses count in any state, by fecha_otorgado.
        assert totals.bonuses == 12


class TestMetrics90d:
    def test_converts_to_usd(self, make_db):
        repo = Repository(connect_read_only(make_db(MINI)))
        metrics = repo.metrics_90d("J1", "2026-10-31")
        assert metrics is not None
        assert metrics.as_dict() == {
            "depositos_aprobados": 60.0,
            "retiros_aprobados": 20.0,
            "monto_apostado": 20.0,
            "ggr": -5.0,
            "bonos_otorgados": 6.0,
            "n_apuestas": 2,
        }

    def test_unknown_player_has_no_metrics(self, make_db):
        repo = Repository(connect_read_only(make_db(MINI)))
        assert repo.metrics_90d("J999", "2026-10-31") is None

    def test_a_currency_without_rate_is_an_error_not_a_guess(self, make_db):
        repo = Repository(connect_read_only(make_db(MINI)))
        with pytest.raises(UnknownCurrencyError, match="EUR"):
            repo.metrics_90d("J2", "2026-10-31")


class TestAgainstTheRealDatabase:
    @pytest.mark.parametrize("case", REFERENCE_CASES, ids=lambda c: c["caso_id"])
    def test_reproduces_the_analyst_metrics(self, repo, case):
        metrics = repo.metrics_90d(case["jugador_id"], case["fecha_corte"])
        assert metrics is not None
        assert metrics.as_dict() == pytest.approx(case["metricas_90d_usd"], abs=1e-9)

    def test_the_player_missing_from_the_database(self, repo):
        assert repo.get_player("J103871") is None

    def test_ignores_activity_after_the_cutoff(self, repo):
        # Case 001 keeps betting until the extraction date (2026-11-10).
        all_bets = repo.conn.execute(
            "SELECT count(*) FROM apuestas WHERE jugador_id = 'J101602'"
        ).fetchone()[0]
        metrics = repo.metrics_90d("J101602", "2026-10-31")
        assert metrics is not None
        assert metrics.n_apuestas == 536
        assert all_bets > metrics.n_apuestas
