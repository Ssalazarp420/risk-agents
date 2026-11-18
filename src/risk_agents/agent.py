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
from typing import Any, Literal

from jsonschema import Draft202012Validator

from risk_agents.cases import Case
from risk_agents.data.repository import Repository
from risk_agents.data.rules import window_for
from risk_agents.llm import ChatModel, LLMReply, Message
from risk_agents.tools import TOOL_SPECS, ToolBox

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "investigador_riesgo.md"
SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8")

# Model calls per case. The prompt asks for 4 to 7 tool calls; tools can be asked in parallel,
# so 10 model calls leave room for a correction or two without letting a loop run up the bill.
MAX_STEPS = 10

REMINDER = (
    "Para terminar tienes que llamar a la herramienta `concluir` con tu conclusión. Si te falta"
    " información, pide las herramientas que necesites."
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
        "alertas_del_codigo": alerts,
    }
    return (
        "Investiga este caso. Las métricas las calculó el código y son correctas.\n\n"
        + json.dumps(data, ensure_ascii=False, indent=1)
    )


def run_agent(
    llm: ChatModel, box: ToolBox, context: str, *, max_steps: int = MAX_STEPS
) -> AgentResult:
    messages: list[Message] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": context},
    ]
    tools = [*TOOL_SPECS, CONCLUDE_SPEC]
    run = _Run(box)
    try:
        for _ in range(max_steps):
            r = llm.complete(messages, tools)
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
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": c.id,
                        "content": json.dumps(output, ensure_ascii=False),
                    }
                )
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
                "texto": r.content,
            }
        )

    def record_tool(self, name: str, arguments: str, output: dict) -> None:
        self.trace.append(
            {
                "tipo": "herramienta",
                "nombre": name,
                "argumentos": arguments,
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
