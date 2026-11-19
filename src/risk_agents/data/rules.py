"""Business rules with no database access, so they can be tested in isolation.

Definitions come from esquema_expediente.json and were checked against the five analyst
cases in casos_referencia.json (docs/decisiones.md, D-003).
"""

import dataclasses
import datetime as dt
from bisect import bisect_right
from dataclasses import dataclass

WINDOW_DAYS = 90


@dataclass(frozen=True)
class Window:
    """Inclusive timestamp bounds in the database format (YYYY-MM-DD HH:MM:SS, local time)."""

    start: str
    end: str

    def contains(self, timestamp: str) -> bool:
        # The fixed-width format sorts as text in chronological order.
        return self.start <= timestamp <= self.end


def window_for(cutoff: str | dt.date, days: int = WINDOW_DAYS) -> Window:
    """The `days` calendar days that end on the cutoff date, cutoff day included."""
    if days < 1:
        raise ValueError(f"days must be at least 1, got {days}")
    end = cutoff if isinstance(cutoff, dt.date) else dt.date.fromisoformat(cutoff)
    start = end - dt.timedelta(days=days - 1)
    return Window(f"{start.isoformat()} 00:00:00", f"{end.isoformat()} 23:59:59")


def to_usd(amount: float, rate: float) -> float:
    """Convert an amount in the brand currency to USD, rounded to cents."""
    if rate <= 0:
        raise ValueError(f"rate must be positive, got {rate}")
    # Adding 0.0 turns a -0.0 from rounding a tiny negative number into 0.0.
    return round(amount * rate, 2) + 0.0


@dataclass(frozen=True)
class NativeTotals:
    """Sums over a window, in the player's own currency, before conversion."""

    deposits: float  # approved deposits
    withdrawals: float  # approved withdrawals
    staked: float  # every bet, with or without bonus
    paid_out: float  # winnings paid to the player
    bonuses: float  # bonuses granted, in any state
    n_bets: int


@dataclass(frozen=True)
class Metrics90d:
    """metricas_90d_usd of the case file; field names and order follow the schema."""

    depositos_aprobados: float
    retiros_aprobados: float
    monto_apostado: float
    ggr: float
    bonos_otorgados: float
    n_apuestas: int

    def as_dict(self) -> dict[str, float | int]:
        return dataclasses.asdict(self)


def metrics_usd(totals: NativeTotals, rate: float) -> Metrics90d:
    """Convert native totals to the schema metrics. GGR is rounded after subtracting."""
    return Metrics90d(
        depositos_aprobados=to_usd(totals.deposits, rate),
        retiros_aprobados=to_usd(totals.withdrawals, rate),
        monto_apostado=to_usd(totals.staked, rate),
        ggr=to_usd(totals.staked - totals.paid_out, rate),
        bonos_otorgados=to_usd(totals.bonuses, rate),
        n_apuestas=totals.n_bets,
    )


def percentile_rank(sorted_values: list[float], value: float) -> int | None:
    """Share of the population at or below `value`, from 0 to 100. Ties count as below, so the
    largest value is at 100. `sorted_values` must be sorted ascending."""
    if not sorted_values:
        return None
    return round(100 * bisect_right(sorted_values, value) / len(sorted_values))
