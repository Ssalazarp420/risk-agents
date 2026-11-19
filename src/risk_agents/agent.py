"""The investigator agent: a model in a tool-calling loop that ends by calling `concluir`.

The loop is deliberately small (D-009, D-013):
- the code builds the starting context (profile, score history, metrics, alerts);
- the model asks for tools; each result goes back as a `tool` message;
- the model finishes by calling `concluir`, whose arguments are checked against a JSON Schema;
  a wrong conclusion goes back to the model with the errors, like a wrong tool call;
- a step limit, a cut output or any exception ends the case as `incompleto` with the reason.
  One case never stops the run.

Every model call and tool call is recorded in the trace, with tokens and cost.
"""

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Any, Literal

from jsonschema import Draft202012Validator
from openai import BadRequestError

from risk_agents.cases import Case
from risk_agents.data.repository import Repository
from risk_agents.data.rules import percentile_rank, window_for
from risk_agents.llm import ChatModel, LLMReply, Message, ToolCall
from risk_agents.tools import TOOL_SPECS, ToolBox

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "investigador_riesgo.md"
SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8")

# Tools the prompt says to use on every case. The code runs them before the first model call,
# for the case's player, and puts them in the history as if the model had asked: one model step
# and its re-sent history saved per tool (failure case 5, D-015).
PRELOADED_TOOLS = ("cuentas_relacionadas", "resumen_transacciones", "resumen_apuestas")

# Model calls per case. The prompt asks for 4 to 7 tool calls; tools can be asked in parallel,
# so 10 model calls leave room for a correction or two without letting a loop run up the bill.
MAX_STEPS = 10

REMINDER = (
    "Para terminar tienes que llamar a la herramienta `concluir` con tu conclusión. Si te falta"
    " información, pide las herramientas que necesites."
)

REJECTED_CALL = (
    "Tu última llamada a una herramienta no cumplió su esquema y no se ejecutó: {error}"
    " Revisa los valores permitidos y vuelve a llamarla."
)

CONCLUDE_SPEC = {
    "type": "function",
    "function": {
        "name": "concluir",
        "description": "Entrega la conclusión de la investigación. Llámala una sola vez, al final.",
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "hallazgos",
                "nivel_preocupacion",
                "derivar_a",
                "resumen",
                "cuentas_relacionadas",
                "alertas_calidad_datos",
            ],
            "properties": {
                "hallazgos": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 5,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["descripcion", "evidencia"],
                        "properties": {
                            "descripcion": {"type": "string", "minLength": 1},
                            "evidencia": {
                                "type": "string",
                                "minLength": 1,
                                "description": "Herramienta y cifra de donde sale.",
                            },
                        },
                    },
                },
                "nivel_preocupacion": {"enum": ["bajo", "medio", "alto"]},
                "derivar_a": {
                    "type": "array",
                    "uniqueItems": True,
                    "items": {"enum": ["riesgo", "juego_responsable"]},
                },
                "resumen": {"type": "string", "minLength": 1, "maxLength": 800},
                "cuentas_relacionadas": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "jugador_id devueltos por cuentas_relacionadas que crees de"
                    " la misma persona o grupo.",
                },
                "alertas_calidad_datos": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
}

_CONCLUSION = Draft202012Validator(CONCLUDE_SPEC["function"]["parameters"])


@dataclass(frozen=True)
class AgentResult:
    status: Literal["completo", "incompleto"]
    conclusion: dict[str, Any] | None
    related_seen: frozenset[str]  # accounts that cuentas_relacionadas actually returned
    steps: int  # model calls
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal | None  # None if any call had an unknown cost
    trace: list[dict[str, Any]]
    error: str | None = None


def build_context(case: Case, repo: Repository, alerts: list[str]) -> str:
    """The first user message: what the code already knows, so the model does not spend steps
    on it. No personal data: Player has none, and the rest are numbers and ids."""
    player = repo.get_player(case.jugador_id)
    window = window_for(case.fecha_corte)
    metrics = repo.metrics_90d(case.jugador_id, case.fecha_corte)
    scores = [
        {"fecha_corte": cutoff, "score": score, "version_modelo": version, "factores": _json(f)}
        for cutoff, score, version, f in repo.score_history(case.jugador_id, case.fecha_corte)
    ][-2:]
    data = {
        "caso": {
            "caso_id": case.caso_id,
            "jugador_id": case.jugador_id,
            "fecha_corte": case.fecha_corte,
            "ventana": {"desde": window.start[:10], "hasta": window.end[:10]},
            "score_del_caso": case.score,
        },
        "perfil": {
            "marca": player.marca,
            "pais": player.pais,
            "moneda": player.moneda,
            "fecha_registro": player.fecha_registro,
            "segmento": player.segmento,
            "estado_cuenta": player.estado_cuenta,
        }
        if player
        else None,
        "scores_riesgo": scores,
        "metricas_90d_usd": metrics.as_dict() if metrics else None,
        "referencias_poblacion": _scale(case, repo, metrics),
        "alertas_del_codigo": alerts,
    }
    return (
        "Investiga este caso. Las métricas las calculó el código y son correctas.\n\n"
        + json.dumps(data, ensure_ascii=False, indent=1)
    )


def _scale(case: Case, repo: Repository, metrics) -> dict[str, Any] | None:
    """Where the player stands among all players active in the same window. A model judges
    patterns well and magnitudes badly without a reference (failure case 6)."""
    if metrics is None:
        return None
    window = window_for(case.fecha_corte)
    population = repo.activity_distribution(window)
    days, busiest = repo.betting_days(case.jugador_id, window)
    values = {
        "n_apuestas": metrics.n_apuestas,
        "max_apuestas_en_un_dia": busiest,
        "dias_activos": days,
        "depositos_aprobados_usd": metrics.depositos_aprobados,
    }
    scale: dict[str, Any] = {
        "descripcion": "Percentil del jugador entre los jugadores con actividad en la misma"
        " ventana (100 = el mayor). Calculado por el código.",
    }
    for name, value in values.items():
        dist = population[name]
        p99 = dist[min(len(dist) - 1, int(0.99 * len(dist)))] if dist else None
        scale[name] = {
            "valor": value,
            "percentil": percentile_rank(dist, value),
            "mediana": round(median(dist), 2) if dist else None,
            "p99": round(p99, 2) if p99 is not None else None,
            # How many times the 99th percentile: the population is skewed (most players bet
            # little), so a high percentile alone is not extreme (evaluation run v2).
            "veces_p99": round(value / p99, 1) if p99 else None,
            "maximo": round(dist[-1], 2) if dist else None,
            "jugadores": len(dist),
        }
    return scale


def run_agent(
    llm: ChatModel,
    box: ToolBox,
    context: str,
    *,
    max_steps: int = MAX_STEPS,
    preload: tuple[str, ...] = PRELOADED_TOOLS,
) -> AgentResult:
    messages: list[Message] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": context},
    ]
    tools = [*TOOL_SPECS, CONCLUDE_SPEC]
    run = _Run(box)
    try:
        if preload:
            calls = [ToolCall(f"precarga_{name}", name, "{}") for name in preload]
            messages.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {"name": c.name, "arguments": c.arguments},
                        }
                        for c in calls
                    ],
                }
            )
            for c in calls:
                output = box.call(c.name, c.arguments)
                run.record_tool(c.name, c.arguments, output, preloaded=True)
                messages.append(_tool_message(c.id, output))
        for _ in range(max_steps):
            try:
                r = llm.complete(messages, tools)
            except BadRequestError as e:
                # Groq checks tool arguments against the schema on its side and answers 400
                # instead of returning the call (failure case 7). Treat it like a wrong tool
                # call: tell the model and let it fix the call on the next step.
                if "tool call validation failed" not in str(e):
                    raise
                run.record_rejected(str(e))
                messages.append({"role": "user", "content": REJECTED_CALL.format(error=e)})
                continue
            run.record(r)
            if r.finish_reason == "length":
                return run.result(error="La salida del modelo se cortó por el tope de tokens.")
            messages.append(r.as_message())
            if not r.tool_calls:
                messages.append({"role": "user", "content": REMINDER})
                continue
            for c in r.tool_calls:
                if c.name == "concluir":
                    conclusion, errors = _check_conclusion(c.arguments)
                    if not errors:
                        run.trace.append({"tipo": "conclusion"})
                        return run.result(conclusion=conclusion)
                    output: dict = {"error": "La conclusión no es válida: " + "; ".join(errors)}
                else:
                    output = box.call(c.name, c.arguments)
                run.record_tool(c.name, c.arguments, output)
                messages.append(_tool_message(c.id, output))
        return run.result(error=f"Se alcanzó el límite de {max_steps} pasos sin una conclusión.")
    except Exception as e:  # provider errors after retries, or a bug: the case, not the run
        return run.result(error=f"{type(e).__name__}: {e}")


class _Run:
    """Accumulates usage and trace for one case."""

    def __init__(self, box: ToolBox) -> None:
        self.box = box
        self.steps = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost: Decimal | None = Decimal(0)
        self.trace: list[dict[str, Any]] = []

    def record(self, r: LLMReply) -> None:
        self.steps += 1
        self.input_tokens += r.input_tokens
        self.output_tokens += r.output_tokens
        self.cost = None if self.cost is None or r.cost_usd is None else self.cost + r.cost_usd
        self.trace.append(
            {
                "tipo": "llm",
                "paso": self.steps,
                "modelo": r.model,
                "tokens_entrada": r.input_tokens,
                "tokens_salida": r.output_tokens,
                "costo_usd": None if r.cost_usd is None else str(r.cost_usd),
                "latencia_ms": round(r.latency_ms),
                "fin": r.finish_reason,
                "reintentos": r.retries,
                "texto": r.content,
            }
        )

    def record_rejected(self, error: str) -> None:
        """A model call the provider rejected. It may have been billed, but the provider does
        not report its tokens, so the total cost becomes unknown rather than understated."""
        self.steps += 1
        self.cost = None
        self.trace.append(
            {
                "tipo": "llm",
                "paso": self.steps,
                "rechazada": True,
                "error": error[:500],
                "tokens_entrada": 0,
                "tokens_salida": 0,
                "costo_usd": None,
                "latencia_ms": 0,
                "reintentos": 0,
            }
        )

    def record_tool(
        self, name: str, arguments: str, output: dict, *, preloaded: bool = False
    ) -> None:
        self.trace.append(
            {
                "tipo": "herramienta",
                "nombre": name,
                "argumentos": arguments,
                "precargada": preloaded,
                "error": "error" in output,
                "resultado": output,
            }
        )

    def result(self, conclusion: dict | None = None, error: str | None = None) -> AgentResult:
        return AgentResult(
            status="completo" if conclusion is not None else "incompleto",
            conclusion=conclusion,
            related_seen=frozenset(self.box.allowed - {self.box.case.jugador_id}),
            steps=self.steps,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            cost_usd=self.cost,
            trace=self.trace,
            error=error,
        )


def _tool_message(call_id: str, output: dict) -> Message:
    return {
        "role": "tool",
        "tool_call_id": call_id,
        "content": json.dumps(output, ensure_ascii=False),
    }


def _check_conclusion(arguments: str) -> tuple[dict | None, list[str]]:
    try:
        conclusion = json.loads(arguments or "{}")
    except json.JSONDecodeError as e:
        return None, [f"los argumentos no son JSON válido ({e.msg})"]
    errors = [
        f"{'.'.join(map(str, e.absolute_path)) or 'argumentos'}: {e.message}"
        for e in _CONCLUSION.iter_errors(conclusion)
    ]
    return (None, errors) if errors else (conclusion, [])


def _json(text: str | None) -> Any:
    """factores is JSON text in the database; keep it as text if it does not parse."""
    try:
        return json.loads(text) if text else []
    except json.JSONDecodeError:
        return text
