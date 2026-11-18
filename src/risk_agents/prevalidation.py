"""Checks on the cases of the day that have an exact answer, run before any LLM call.

They do not depend on the model noticing a problem, and they cost no tokens
(docs/decisiones.md, D-004 and D-005). Alert texts are in Spanish: they reach the analyst.
"""

import enum
from dataclasses import dataclass, field

from risk_agents.cases import Case
from risk_agents.data.repository import Repository

SCORE_TOLERANCE = 1e-9


class Decision(enum.Enum):
    INVESTIGATE = "investigar"
    NO_DATA = "sin_datos"
    DUPLICATE = "omitido"


@dataclass
class Triage:
    case: Case
    decision: Decision
    alerts: list[str] = field(default_factory=list)
    duplicate_of: str | None = None


@dataclass
class BatchReport:
    triages: list[Triage]
    # cutoff -> [(jugador_id, score)] scored at or above the file's lowest score but absent
    missing_players: dict[str, list[tuple[str, float]]]
    alerts: list[str]


def prevalidate(cases: list[Case], repo: Repository) -> BatchReport:
    triages: list[Triage] = []
    first_seen: dict[tuple[str, str], str] = {}
    for case in cases:
        key = (case.jugador_id, case.fecha_corte)
        if key in first_seen:
            triages.append(_duplicate(case, first_seen[key]))
            continue
        first_seen[key] = case.caso_id
        triages.append(_check(case, repo))

    missing = _missing_players(cases, repo)
    return BatchReport(triages, missing, _repeated_ids(cases) + _missing_alerts(missing))


def _duplicate(case: Case, original: str) -> Triage:
    alert = (
        f"casos_del_dia.csv repite al jugador {case.jugador_id} con corte {case.fecha_corte}"
        f" en {original} y {case.caso_id}; se investigó solo {original}."
    )
    return Triage(case, Decision.DUPLICATE, [alert], duplicate_of=original)


def _check(case: Case, repo: Repository) -> Triage:
    if repo.get_player(case.jugador_id) is None:
        return Triage(case, Decision.NO_DATA, _unknown_player_alerts(case, repo))

    alerts = []
    model_score = repo.get_score(case.jugador_id, case.fecha_corte)
    if model_score is None:
        alerts.append(
            f"El score {case.score} de casos_del_dia.csv no está en scores_riesgo"
            f" para el corte {case.fecha_corte}."
        )
    elif abs(model_score - case.score) > SCORE_TOLERANCE:
        alerts.append(
            f"El score de casos_del_dia.csv ({case.score}) no coincide con scores_riesgo"
            f" ({model_score}) para el corte {case.fecha_corte}."
        )
    return Triage(case, Decision.INVESTIGATE, alerts)


def _unknown_player_alerts(case: Case, repo: Repository) -> list[str]:
    rows = repo.rows_per_table(case.jugador_id)
    if not rows:
        return [
            f"El jugador {case.jugador_id} no existe en la tabla jugadores ni aparece en"
            f" ninguna otra tabla, aunque casos_del_dia.csv le asigna score {case.score}."
            " Revisar el flujo que genera los casos."
        ]
    found = ", ".join(f"{table} ({n})" for table, n in rows.items())
    return [
        f"El jugador {case.jugador_id} no existe en la tabla jugadores, pero tiene filas en"
        f" {found}: datos sin titular registrado."
    ]


def _missing_players(cases: list[Case], repo: Repository) -> dict[str, list[tuple[str, float]]]:
    """Supposed selection rule (D-005): every player at or above the file's lowest score."""
    missing = {}
    for cutoff in sorted({c.fecha_corte for c in cases}):
        on_cutoff = [c for c in cases if c.fecha_corte == cutoff]
        listed = {c.jugador_id for c in on_cutoff}
        threshold = min(c.score for c in on_cutoff)
        absent = [(j, s) for j, s in repo.scores_at_least(cutoff, threshold) if j not in listed]
        if absent:
            missing[cutoff] = absent
    return missing


def _missing_alerts(missing: dict[str, list[tuple[str, float]]]) -> list[str]:
    return [
        f"Jugadores con score en el rango de los casos del corte {cutoff} que no están en"
        f" casos_del_dia.csv: {', '.join(f'{j} ({s})' for j, s in players)}."
        for cutoff, players in missing.items()
    ]


def _repeated_ids(cases: list[Case]) -> list[str]:
    seen, repeated = set(), []
    for c in cases:
        if c.caso_id in seen and c.caso_id not in repeated:
            repeated.append(c.caso_id)
        seen.add(c.caso_id)
    return [f"El caso_id {r} aparece más de una vez en casos_del_dia.csv." for r in repeated]
