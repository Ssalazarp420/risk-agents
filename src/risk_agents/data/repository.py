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

    def score_history(self, jugador_id: str, until: str) -> list[tuple[str, float, str, str]]:
        """(fecha_corte, score, version_modelo, factores as JSON text) up to `until`, oldest
        first."""
        return self.conn.execute(
            "SELECT fecha_corte, score, version_modelo, factores FROM scores_riesgo"
            " WHERE jugador_id = ? AND fecha_corte <= ? ORDER BY fecha_corte",
            (jugador_id, until),
        ).fetchall()

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

    # --- Queries behind the agent's tools. Amounts are in the player's currency. ---

    def transactions_by(self, jugador_id: str, window: Window, column: str) -> list[tuple]:
        """(tipo, <column>, count, sum) for column 'estado' or 'medio_pago'."""
        if column not in ("estado", "medio_pago"):
            raise ValueError(f"Cannot group transactions by {column!r}")
        # The column name comes from the fixed pair above, never from input.
        return self.conn.execute(
            f"SELECT tipo, {column}, count(*), sum(monto) FROM transacciones"
            " WHERE jugador_id = ? AND fecha_hora BETWEEN ? AND ?"
            f" GROUP BY tipo, {column} ORDER BY tipo, {column}",
            (jugador_id, window.start, window.end),
        ).fetchall()

    def approved_by_month(self, jugador_id: str, window: Window) -> list[tuple]:
        """(YYYY-MM, approved deposits, approved withdrawals) for months with any of them."""
        return self.conn.execute(
            "SELECT substr(fecha_hora, 1, 7) AS mes,"
            " coalesce(sum(CASE WHEN tipo = 'deposito' THEN monto END), 0),"
            " coalesce(sum(CASE WHEN tipo = 'retiro' THEN monto END), 0)"
            " FROM transacciones"
            " WHERE jugador_id = ? AND fecha_hora BETWEEN ? AND ? AND estado = 'aprobada'"
            " AND tipo IN ('deposito', 'retiro')"
            " GROUP BY mes ORDER BY mes",
            (jugador_id, window.start, window.end),
        ).fetchall()

    def notes(self, jugador_id: str, window: Window, limit: int) -> list[tuple]:
        """(nota, tipo, count, first fecha_hora) of the distinct non-empty notes."""
        return self.conn.execute(
            "SELECT nota, tipo, count(*), min(fecha_hora) FROM transacciones"
            " WHERE jugador_id = ? AND fecha_hora BETWEEN ? AND ? AND coalesce(nota, '') <> ''"
            " GROUP BY nota, tipo ORDER BY min(fecha_hora) LIMIT ?",
            (jugador_id, window.start, window.end, limit),
        ).fetchall()

    def transactions(
        self,
        jugador_id: str,
        window: Window,
        tipo: str | None,
        estado: str | None,
        limit: int,
    ) -> tuple[int, list[tuple]]:
        """(how many match, the first `limit` of them by date)."""
        where = (
            " FROM transacciones WHERE jugador_id = ? AND fecha_hora BETWEEN ? AND ?"
            " AND (? IS NULL OR tipo = ?) AND (? IS NULL OR estado = ?)"
        )
        params = (jugador_id, window.start, window.end, tipo, tipo, estado, estado)
        (total,) = self.conn.execute("SELECT count(*)" + where, params).fetchone()
        rows = self.conn.execute(
            "SELECT tx_id, fecha_hora, tipo, medio_pago, monto, estado, nota"
            + where
            + " ORDER BY fecha_hora, tx_id LIMIT ?",
            (*params, limit),
        ).fetchall()
        return total, rows

    def bets_by_game(self, jugador_id: str, window: Window) -> list[tuple]:
        """(producto, detalle, count, staked, paid out, mean odds, bets with bonus)."""
        return self.conn.execute(
            "SELECT producto, detalle, count(*), sum(monto), sum(ganancia), avg(cuota),"
            " sum(con_bono) FROM apuestas WHERE jugador_id = ? AND fecha_hora BETWEEN ? AND ?"
            " GROUP BY producto, detalle ORDER BY sum(monto) DESC",
            (jugador_id, window.start, window.end),
        ).fetchall()

    def bets_by_hour_block(self, jugador_id: str, window: Window) -> dict[int, int]:
        """Bets per 6-hour block of the day: 0 = 00-05 h, 1 = 06-11 h, 2 = 12-17 h, 3 = 18-23 h."""
        rows = self.conn.execute(
            "SELECT cast(substr(fecha_hora, 12, 2) AS INTEGER) / 6, count(*) FROM apuestas"
            " WHERE jugador_id = ? AND fecha_hora BETWEEN ? AND ? GROUP BY 1",
            (jugador_id, window.start, window.end),
        ).fetchall()
        return dict(rows)

    def betting_days(self, jugador_id: str, window: Window) -> tuple[int, int]:
        """(days with at least one bet, most bets in a single day)."""
        return self.conn.execute(
            "SELECT count(*), coalesce(max(n), 0) FROM ("
            " SELECT count(*) AS n FROM apuestas"
            " WHERE jugador_id = ? AND fecha_hora BETWEEN ? AND ?"
            " GROUP BY substr(fecha_hora, 1, 10))",
            (jugador_id, window.start, window.end),
        ).fetchone()

    def bonuses(self, jugador_id: str, window: Window, limit: int) -> list[tuple]:
        """(tipo, monto, fecha_otorgado, estado) of the bonuses granted in the window."""
        return self.conn.execute(
            "SELECT tipo, monto, fecha_otorgado, estado FROM bonos"
            " WHERE jugador_id = ? AND fecha_otorgado BETWEEN ? AND ?"
            " ORDER BY fecha_otorgado LIMIT ?",
            (jugador_id, window.start, window.end, limit),
        ).fetchall()

    def shared_devices(self, jugador_id: str, until: str) -> list[tuple[str, str]]:
        """(other jugador_id, device_id) for devices both used up to `until`."""
        return self.conn.execute(
            "SELECT DISTINCT o.jugador_id, o.device_id FROM dispositivos o"
            " WHERE o.device_id IN ("
            "  SELECT device_id FROM dispositivos WHERE jugador_id = ? AND fecha_hora <= ?)"
            " AND o.jugador_id <> ? AND o.fecha_hora <= ?"
            " ORDER BY o.jugador_id, o.device_id",
            (jugador_id, until, jugador_id, until),
        ).fetchall()

    def shared_networks(self, jugador_id: str, until: str) -> list[tuple[str, int]]:
        """(ip_red, how many other players used it) for each network the player used."""
        return self.conn.execute(
            "SELECT m.ip_red, count(DISTINCT o.jugador_id) FROM"
            " (SELECT DISTINCT ip_red FROM dispositivos"
            "  WHERE jugador_id = ? AND fecha_hora <= ?) AS m"
            " LEFT JOIN dispositivos o"
            "  ON o.ip_red = m.ip_red AND o.jugador_id <> ? AND o.fecha_hora <= ?"
            " GROUP BY m.ip_red ORDER BY m.ip_red",
            (jugador_id, until, jugador_id, until),
        ).fetchall()

    def metrics_90d(self, jugador_id: str, fecha_corte: str) -> Metrics90d | None:
        """metricas_90d_usd for a case, or None if the player does not exist."""
        player = self.get_player(jugador_id)
        if player is None:
            return None
        rate = self.usd_rate(player.moneda)
        return metrics_usd(self.native_totals(jugador_id, window_for(fecha_corte)), rate)
