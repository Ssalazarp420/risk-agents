"""A rule-based stand-in for the LLM: runs without an API key and is the baseline to beat.

It speaks the same protocol as GroqClient (ChatModel): on its first turn it asks for four
tools, on the second it reads their results, applies fixed rules and calls `concluir`. It sees
exactly what the LLM would see, so the evaluation can ask whether the model adds judgement
beyond a few thresholds.

The thresholds were written after looking at the 25 cases of the day (docs/02_datos.md), so
the baseline's score on those cases is optimistic. That is stated in the evaluation.
"""

import json
from decimal import Decimal
from typing import Any

from risk_agents.llm import LLMReply, Message, ToolCall

FIRST_TOOLS = ("cuentas_relacionadas", "resumen_transacciones", "resumen_apuestas", "bonos")
LEVELS = ("bajo", "medio", "alto")

# Bonus abuse: most bets placed with a bonus at near-certain odds.
BONUS_SHARE = 0.5
LOW_ODDS = 1.5
# Payment fraud.
MIN_CHARGEBACKS = 2
MIN_REVERSED_DEPOSITS = 3
# Responsible gambling.
EXTREME_BETS = 5000
EXTREME_BETS_PER_DAY = 300
NIGHT_SHARE = 0.5
DEPOSIT_GROWTH = 3
# Money moved without play.
BIG_DEPOSITS_USD = 1000


class RuleBasedLLM:
    model = "reglas"

    def complete(self, messages: list[Message], tools: list[dict] | None = None) -> LLMReply:
        outputs = {
            m["tool_call_id"]: json.loads(m["content"]) for m in messages if m["role"] == "tool"
        }
        if not all(name in outputs for name in FIRST_TOOLS):
            return _reply([ToolCall(name, name, "{}") for name in FIRST_TOOLS])
        context = json.loads(messages[1]["content"].split("\n\n", 1)[1])
        conclusion = judge(context, outputs)
        return _reply(
            [ToolCall("concluir", "concluir", json.dumps(conclusion, ensure_ascii=False))]
        )


def judge(context: dict, out: dict[str, dict]) -> dict[str, Any]:
    """Fixed rules over the case context and the four tool results."""
    related, tx, bets, bonuses = (out[name] for name in FIRST_TOOLS)
    findings: list[dict[str, str]] = []
    signals: list[tuple[str, str]] = []  # (level, team)
    alerts: list[str] = []

    def found(level: str, team: str, descripcion: str, evidencia: str) -> None:
        signals.append((level, team))
        findings.append({"descripcion": descripcion, "evidencia": evidencia})

    # Shared device.
    accounts = related["cuentas"]
    if accounts:
        ids = [a["jugador_id"] for a in accounts]
        devices = sorted({d for a in accounts for d in a["dispositivos_compartidos"]})
        found(
            "alto",
            "riesgo",
            f"Comparte dispositivo con {len(ids)} cuenta(s): {', '.join(ids)}",
            f"cuentas_relacionadas: {', '.join(devices)}",
        )
        for a in accounts:
            if not a["en_casos_del_dia"] and (a["score_al_corte"] or 0) >= 0.7:
                alerts.append(
                    f"{a['jugador_id']} (score {a['score_al_corte']}) comparte dispositivo y no"
                    " está en los casos del día."
                )

    # Bonus abuse.
    n_bets = bets["n_apuestas"]
    sports = [g for g in bets["por_juego"] if g["cuota_media"] is not None]
    odds = (
        sum(g["cuota_media"] * g["n"] for g in sports) / sum(g["n"] for g in sports)
        if sports
        else None
    )
    bonus_share = bets["n_con_bono"] / n_bets if n_bets else 0
    if bonuses["total_usd"] > 0 and bonus_share >= BONUS_SHARE and odds and odds <= LOW_ODDS:
        found(
            "alto",
            "riesgo",
            "La mayoría de las apuestas usan bono y a cuotas bajas: patrón de abuso de bonos",
            f"resumen_apuestas: {bets['n_con_bono']} de {n_bets} con bono, cuota media"
            f" {odds:.2f}; bonos: {bonuses['total_usd']} USD",
        )

    # Free text that tries to give orders.
    notes = tx["notas"]["items"]
    if any(n["parece_instruccion"] for n in notes):
        found(
            "medio",
            "riesgo",
            "Una nota de transacción intenta dar instrucciones al sistema de revisión",
            "resumen_transacciones: nota marcada con parece_instruccion",
        )
        alerts.append("Nota con texto que intenta dar instrucciones; se trató como dato.")

    # Payment fraud.
    chargebacks = sum(n["veces"] for n in notes if "contracargo" in n["texto_de_terceros"].lower())
    reversed_deposits = sum(
        r["n"]
        for r in tx["por_tipo_y_estado"]
        if r["tipo"] == "deposito" and r["estado"] == "revertida"
    )
    if chargebacks >= MIN_CHARGEBACKS or reversed_deposits >= MIN_REVERSED_DEPOSITS:
        found(
            "alto",
            "riesgo",
            "Depósitos revertidos por contracargo",
            f"resumen_transacciones: {reversed_deposits} depósitos revertidos,"
            f" {chargebacks} notas de contracargo",
        )

    # Responsible gambling.
    blocks = bets["por_franja_horaria"]
    night_share = blocks["madrugada_00_05"] / n_bets if n_bets else 0
    months = [m["depositos_aprobados_usd"] for m in tx["por_mes"] if m["depositos_aprobados_usd"]]
    growth = months[-1] / months[0] if len(months) >= 2 else 1
    if n_bets >= EXTREME_BETS or bets["max_apuestas_en_un_dia"] >= EXTREME_BETS_PER_DAY:
        found(
            "alto",
            "juego_responsable",
            "Volumen de juego extremo",
            f"resumen_apuestas: {n_bets} apuestas, hasta {bets['max_apuestas_en_un_dia']} en un"
            f" día, {bets['dias_activos']} días activos",
        )
    if night_share >= NIGHT_SHARE:
        level = "alto" if growth >= DEPOSIT_GROWTH else "medio"
        found(
            level,
            "juego_responsable",
            "La mayoría de las apuestas son de madrugada"
            + (" y los depósitos crecen mes a mes" if level == "alto" else ""),
            f"resumen_apuestas: {night_share:.0%} entre 0 y 5 h; depósitos del último mes"
            f" {growth:.1f} veces los del primero",
        )

    # Money moved without play.
    metrics = context["metricas_90d_usd"]
    deposits = metrics["depositos_aprobados"]
    if (
        deposits >= BIG_DEPOSITS_USD
        and metrics["monto_apostado"] < 0.5 * deposits
        and metrics["retiros_aprobados"] >= 0.5 * deposits
    ):
        found(
            "alto",
            "riesgo",
            "Deposita y retira montos grandes apostando poco",
            f"métricas: depósitos {deposits}, apostado {metrics['monto_apostado']}, retiros"
            f" {metrics['retiros_aprobados']} USD",
        )

    # Score factors that the data does not support.
    factors = context["scores_riesgo"][-1]["factores"] if context["scores_riesgo"] else []
    if "actividad_nocturna" in factors and n_bets and blocks["madrugada_00_05"] == 0:
        alerts.append(
            "El factor actividad_nocturna no se ve en los datos: 0 apuestas entre 0 y 5 h."
        )
    withdrew = any(
        r["tipo"] == "retiro" and r["estado"] == "aprobada" for r in tx["por_tipo_y_estado"]
    )
    if "retiro_rapido" in factors and not withdrew:
        alerts.append("El factor retiro_rapido no se ve en los datos: no hay retiros aprobados.")

    if not signals:
        findings.append(
            {
                "descripcion": "Ninguna regla de riesgo ni de juego responsable se activa",
                "evidencia": f"resumen_transacciones y resumen_apuestas: {n_bets} apuestas,"
                f" depósitos {deposits} USD",
            }
        )
    level = max((lvl for lvl, _ in signals), key=LEVELS.index, default="bajo")
    teams = list(dict.fromkeys(team for _, team in signals))
    resumen = (
        f"Reglas fijas, nivel {level}. "
        + ". ".join(f["descripcion"] for f in findings)
        + "."
        + (" Se sugiere revisión por " + " y ".join(teams) + "." if teams else "")
    )
    return {
        "hallazgos": findings[:5],
        "nivel_preocupacion": level,
        "derivar_a": teams,
        "resumen": resumen[:800],
        "cuentas_relacionadas": [a["jugador_id"] for a in accounts],
        "alertas_calidad_datos": alerts,
    }


def _reply(calls: list[ToolCall]) -> LLMReply:
    return LLMReply(None, tuple(calls), "reglas", 0, 0, 0.0, Decimal(0), "tool_calls")
