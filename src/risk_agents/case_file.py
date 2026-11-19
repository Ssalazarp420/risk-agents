"""The case file (expediente): builders for the files decided in code, and schema validation.

Field names follow esquema_expediente.json exactly. Texts are in Spanish: they reach the analyst.
"""

import json
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from risk_agents.cases import Case

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "esquema_expediente.json"

CaseFile = dict[str, Any]


@cache
def _validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    # Without a format checker, "format": "date" is only an annotation and is not checked.
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


def validate(file: CaseFile) -> list[str]:
    """Every schema violation as 'path: message'; an empty list means the file is valid."""
    errors = sorted(_validator().iter_errors(file), key=lambda e: list(e.absolute_path))
    return [f"{'.'.join(map(str, e.absolute_path)) or '(raíz)'}: {e.message}" for e in errors]


def _empty(case: Case, estado: str, resumen: str, alerts: list[str]) -> CaseFile:
    return {
        "caso_id": case.caso_id,
        "jugador_id": case.jugador_id,
        "fecha_corte": case.fecha_corte,
        "estado_investigacion": estado,
        "metricas_90d_usd": None,
        "cuentas_relacionadas": [],
        "hallazgos": [],
        "nivel_preocupacion": None,
        "derivar_a": [],
        "resumen": resumen,
        "alertas_calidad_datos": list(alerts),
    }


def no_data_file(case: Case, alerts: list[str]) -> CaseFile:
    resumen = (
        f"No hay información para investigar: el jugador {case.jugador_id} no está registrado"
        " en la base. No se calcularon métricas ni se emitió una conclusión. Conviene revisar"
        " por qué el flujo diario generó este caso."
    )
    return _empty(case, "sin_datos", resumen, alerts)


def skipped_file(case: Case, original_caso_id: str, alerts: list[str]) -> CaseFile:
    resumen = (
        f"Caso duplicado de {original_caso_id}: mismo jugador ({case.jugador_id}) y misma fecha"
        f" de corte ({case.fecha_corte}). No se investigó de nuevo; la investigación está en el"
        f" expediente de {original_caso_id}."
    )
    return _empty(case, "omitido", resumen, alerts)


def investigated_file(
    case: Case,
    metrics: dict[str, Any],
    conclusion: dict[str, Any],
    related_seen: frozenset[str],
    alerts: list[str],
) -> CaseFile:
    """A completed investigation. Ids, state and metrics come from the code; the judgement
    fields come from the agent's conclusion, which already passed the `concluir` schema.

    A related account is kept only if cuentas_relacionadas actually returned it: the model
    cannot add an account it never saw.
    """
    kept, dropped = [], []
    for jugador_id in dict.fromkeys(conclusion["cuentas_relacionadas"]):
        if jugador_id == case.jugador_id:
            continue
        (kept if jugador_id in related_seen else dropped).append(jugador_id)
    dropped_alerts = [
        f"El agente propuso {j} como cuenta relacionada, pero cuentas_relacionadas no la"
        " devolvió; se descartó."
        for j in dropped
    ]
    return {
        "caso_id": case.caso_id,
        "jugador_id": case.jugador_id,
        "fecha_corte": case.fecha_corte,
        "estado_investigacion": "completo",
        "metricas_90d_usd": metrics,
        "cuentas_relacionadas": kept,
        "hallazgos": conclusion["hallazgos"],
        "nivel_preocupacion": conclusion["nivel_preocupacion"],
        "derivar_a": conclusion["derivar_a"],
        "resumen": conclusion["resumen"],
        "alertas_calidad_datos": _unique(
            [*alerts, *conclusion["alertas_calidad_datos"], *dropped_alerts]
        ),
    }


def incomplete_file(
    case: Case, metrics: dict[str, Any] | None, reason: str, alerts: list[str]
) -> CaseFile:
    """The investigation started but did not finish. The metrics, if computed, are kept: they
    are correct regardless of the agent."""
    reason = _cut(reason, 500)
    resumen = (
        f"La investigación no terminó: {reason} No hay conclusión del agente."
        + (" Las métricas de 90 días sí están calculadas." if metrics else "")
        + " Requiere revisión manual."
    )
    file = _empty(
        case, "incompleto", resumen, _unique([*alerts, f"Investigación incompleta: {reason}"])
    )
    file["metricas_90d_usd"] = metrics
    return file


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"
