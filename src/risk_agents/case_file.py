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
