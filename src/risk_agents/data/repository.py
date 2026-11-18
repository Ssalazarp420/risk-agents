"""Read-only access to transacciones.db.

The SQL only fetches rows and sums; every business rule lives in rules.py. All queries use
parameters (never string formatting) and every activity query is bounded by a Window.
"""

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from risk_agents.data.rules import Metrics90d, NativeTotals, Window, metrics_usd, window_for

ACTIVITY_TABLES = ("transacciones", "apuestas", "bonos", "dispositivos", "scores_riesgo")


class UnknownCurrencyError(LookupError):
    """A player's currency has no row in tasas_cambio: converting would mean guessing."""


def connect_read_only(path: str | Path) -> sqlite3.Connection:
    """Open the database so that SQLite itself rejects any write."""
    path = Path(path)
    # Checked here because sqlite's error for a missing file does not name the file.
    if not path.is_file():
        raise FileNotFoundError(f"Database not found: {path}")
    # mode=ro: any INSERT, UPDATE or DELETE fails with "attempt to write a readonly database".
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


@dataclass(frozen=True)
class Player:
    """What the agents may know about a player. Personal data is deliberately left out."""

    jugador_id: str
    marca: str
    pais: str
    moneda: str
    fecha_registro: str
    segmento: str
    estado_cuenta: str


class Repository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def get_player(self, jugador_id: str) -> Player | None:
        row = self.conn.execute(
            "SELECT jugador_id, marca, pais, moneda, fecha_registro, segmento, estado_cuenta"
            " FROM jugadores WHERE jugador_id = ?",
            (jugador_id,),
        ).fetchone()
        return Player(*row) if row else None

    def usd_rate(self, moneda: str) -> float:
        row = self.conn.execute(
            "SELECT usd_por_unidad FROM tasas_cambio WHERE moneda = ?", (moneda,)
        ).fetchone()
        if row is None:
            raise UnknownCurrencyError(f"No USD rate for currency {moneda!r} in tasas_cambio")
        return row[0]

    def native_totals(self, jugador_id: str, window: Window) -> NativeTotals:
        bounds = (jugador_id, window.start, window.end)
        deposits, withdrawals = self.conn.execute(
            "SELECT"
            " coalesce(sum(CASE WHEN tipo = 'deposito' THEN monto END), 0),"
            " coalesce(sum(CASE WHEN tipo = 'retiro' THEN monto END), 0)"
            " FROM transacciones"
            " WHERE jugador_id = ? AND fecha_hora BETWEEN ? AND ? AND estado = 'aprobada'",
            bounds,
        ).fetchone()
        staked, paid_out, n_bets = self.conn.execute(
            "SELECT coalesce(sum(monto), 0), coalesce(sum(ganancia), 0), count(*)"
            " FROM apuestas WHERE jugador_id = ? AND fecha_hora BETWEEN ? AND ?",
            bounds,
        ).fetchone()
        (bonuses,) = self.conn.execute(
            "SELECT coalesce(sum(monto), 0)"
            " FROM bonos WHERE jugador_id = ? AND fecha_otorgado BETWEEN ? AND ?",
            bounds,
        ).fetchone()
        return NativeTotals(deposits, withdrawals, staked, paid_out, bonuses, n_bets)

    def get_score(self, jugador_id: str, fecha_corte: str) -> float | None:
        row = self.conn.execute(
            "SELECT score FROM scores_riesgo WHERE jugador_id = ? AND fecha_corte = ?",
            (jugador_id, fecha_corte),
        ).fetchone()
        return row[0] if row else None

    def scores_at_least(self, fecha_corte: str, min_score: float) -> list[tuple[str, float]]:
        """Players scored at or above min_score on that cutoff, highest first."""
        return self.conn.execute(
            "SELECT jugador_id, score FROM scores_riesgo"
            " WHERE fecha_corte = ? AND score >= ? ORDER BY score DESC, jugador_id",
            (fecha_corte, min_score),
        ).fetchall()

    def rows_per_table(self, jugador_id: str) -> dict[str, int]:
        """How many rows mention the player in each table; tables with none are left out."""
        counts = {}
        for table in ACTIVITY_TABLES:
            # Table names cannot be SQL parameters; they come from a fixed tuple, never input.
            (n,) = self.conn.execute(
                f"SELECT count(*) FROM {table} WHERE jugador_id = ?", (jugador_id,)
            ).fetchone()
            if n:
                counts[table] = n
        return counts

    def metrics_90d(self, jugador_id: str, fecha_corte: str) -> Metrics90d | None:
        """metricas_90d_usd for a case, or None if the player does not exist."""
        player = self.get_player(jugador_id)
        if player is None:
            return None
        rate = self.usd_rate(player.moneda)
        return metrics_usd(self.native_totals(jugador_id, window_for(fecha_corte)), rate)
