"""The investigator agent's tools.

Rules shared by every tool:
- Read-only, through Repository; the database is opened with mode=ro.
- The window comes from the case (90 days ending on its cutoff). The model cannot choose dates,
  so it cannot read data from after the cutoff.
- Aggregates and capped lists only: the heaviest case has 49,196 bets in the window.
- No personal data: names, documents, emails, phones and IP prefixes never leave this module.
- Scope: the case's player, plus the accounts that cuentas_relacionadas has returned.
- A wrong call returns {"error": ...} with a message that lets the model fix it; any other
  exception is a bug and propagates to the orchestrator.

Tool and field names are in Spanish because the model and the analyst read them.
"""

import json
from collections.abc import Callable
from typing import Any

from jsonschema import Draft202012Validator

from risk_agents.cases import Case
from risk_agents.data.repository import Player, Repository
from risk_agents.data.rules import to_usd, window_for
from risk_agents.untrusted import THIRD_PARTY_NOTICE, looks_like_instruction

MAX_NOTES = 10
MAX_NOTE_CHARS = 300
MAX_BONUSES = 30
MAX_RELATED = 20
DEFAULT_ROWS = 10
MAX_ROWS = 20

HOUR_BLOCKS = ("madrugada_00_05", "manana_06_11", "tarde_12_17", "noche_18_23")

WEAK_NETWORK_NOTICE = (
    "Compartir red (ip_red) es una señal débil: una red de salida puede agrupar decenas de"
    " jugadores sin relación. No vincules cuentas solo por la red; los valores de ip no se"
    " muestran."
)


def _spec(name: str, description: str, **properties: dict) -> dict:
    """An OpenAI-style function definition. Its parameters double as a JSON Schema."""
    player = {
        "type": "string",
        "description": "Opcional. Por defecto, el jugador del caso. Otra cuenta solo si la"
        " devolvió cuentas_relacionadas.",
    }
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {"jugador_id": player, **properties},
                "additionalProperties": False,
            },
        },
    }


TOOL_SPECS = [
    _spec(
        "resumen_transacciones",
        "Depósitos, retiros y ajustes de la ventana de 90 días, en USD: totales por tipo y"
        " estado, por medio de pago y por mes, y las notas distintas (texto de terceros).",
    ),
    _spec(
        "resumen_apuestas",
        "Apuestas de la ventana de 90 días, en USD: por producto y juego (monto, ganancias,"
        " GGR, cuota media, uso de bono), por franja horaria, días activos y máximo diario.",
    ),
    _spec("bonos", "Bonos otorgados en la ventana de 90 días: tipo, monto en USD, fecha, estado."),
    _spec(
        "cuentas_relacionadas",
        "Cuentas que usaron el mismo dispositivo (device_id) hasta el corte, con su registro,"
        " score y si están en los casos del día. Además, cuántos jugadores comparten cada red"
        " (señal débil). Las cuentas devueltas quedan habilitadas para las demás herramientas.",
    ),
    _spec(
        "detalle_transacciones",
        "Transacciones individuales de la ventana en orden cronológico, como máximo 20. Útil para"
        " ver la secuencia de un patrón (depósito, bono, retiro).",
        tipo={"enum": ["deposito", "retiro", "ajuste"]},
        estado={"enum": ["aprobada", "pendiente", "rechazada", "revertida"]},
        limite={"type": "integer", "minimum": 1, "maximum": MAX_ROWS, "default": DEFAULT_ROWS},
    ),
]

_VALIDATORS = {
    spec["function"]["name"]: Draft202012Validator(spec["function"]["parameters"])
    for spec in TOOL_SPECS
}


class ToolError(Exception):
    """A call the model can fix: the message goes back to it."""


class ToolBox:
    def __init__(self, repo: Repository, case: Case, case_players: frozenset[str]) -> None:
        self.repo = repo
        self.case = case
        self.case_players = case_players
        self.window = window_for(case.fecha_corte)
        self.allowed = {case.jugador_id}
        self.tools: dict[str, Callable[..., dict]] = {
            "resumen_transacciones": self.transaction_summary,
            "resumen_apuestas": self.bet_summary,
            "bonos": self.bonuses,
            "cuentas_relacionadas": self.related_accounts,
            "detalle_transacciones": self.transaction_detail,
        }

    def call(self, name: str, arguments: str | dict | None) -> dict:
        try:
            tool = self.tools.get(name)
            if tool is None:
                raise ToolError(
                    f"No existe la herramienta {name!r}. Disponibles: {', '.join(self.tools)}."
                )
            args = _parse(arguments)
            errors = [
                f"{'.'.join(map(str, e.absolute_path)) or 'argumentos'}: {e.message}"
                for e in _VALIDATORS[name].iter_errors(args)
            ]
            if errors:
                raise ToolError(f"Argumentos inválidos para {name}: {'; '.join(errors)}")
            return tool(**args)
        except ToolError as e:
            return {"error": str(e)}

    # --- helpers ---

    def _player(self, jugador_id: str | None) -> tuple[Player, float]:
        jugador_id = jugador_id or self.case.jugador_id
        if jugador_id not in self.allowed:
            raise ToolError(
                f"{jugador_id} no está disponible: solo puedes consultar al jugador del caso"
                f" ({self.case.jugador_id}) o las cuentas que devuelva cuentas_relacionadas."
            )
        player = self.repo.get_player(jugador_id)
        if player is None:
            raise ToolError(f"{jugador_id} no está registrado en la tabla jugadores.")
        return player, self.repo.usd_rate(player.moneda)

    def _header(self, player: Player) -> dict[str, Any]:
        return {
            "jugador_id": player.jugador_id,
            "ventana": {"desde": self.window.start[:10], "hasta": self.window.end[:10]},
            "moneda_original": player.moneda,
        }

    # --- tools ---

    def transaction_summary(self, jugador_id: str | None = None) -> dict:
        player, rate = self._player(jugador_id)
        jid, w = player.jugador_id, self.window
        notes = self.repo.notes(jid, w, MAX_NOTES)
        return {
            **self._header(player),
            "por_tipo_y_estado": [
                {"tipo": t, "estado": s, "n": n, "monto_usd": to_usd(total, rate)}
                for t, s, n, total in self.repo.transactions_by(jid, w, "estado")
            ],
            "por_medio_pago": [
                {"tipo": t, "medio_pago": m, "n": n, "monto_usd": to_usd(total, rate)}
                for t, m, n, total in self.repo.transactions_by(jid, w, "medio_pago")
            ],
            "por_mes": [
                {
                    "mes": month,
                    "depositos_aprobados_usd": to_usd(deposits, rate),
                    "retiros_aprobados_usd": to_usd(withdrawals, rate),
                }
                for month, deposits, withdrawals in self.repo.approved_by_month(jid, w)
            ],
            "notas": {
                "aviso": THIRD_PARTY_NOTICE,
                "items": [_note(text, tipo, n, first) for text, tipo, n, first in notes],
                "recortadas": len(notes) == MAX_NOTES,
            },
        }

    def bet_summary(self, jugador_id: str | None = None) -> dict:
        player, rate = self._player(jugador_id)
        jid, w = player.jugador_id, self.window
        games = [
            {
                "producto": product,
                "detalle": detail,
                "n": n,
                "monto_usd": to_usd(staked, rate),
                "ganancia_pagada_usd": to_usd(paid, rate),
                "ggr_usd": to_usd(staked - paid, rate),
                # Casino bets have no odds in the data; only sports bets do.
                "cuota_media": round(odds, 2) if odds is not None else None,
                "n_con_bono": with_bonus,
            }
            for product, detail, n, staked, paid, odds, with_bonus in self.repo.bets_by_game(jid, w)
        ]
        blocks = self.repo.bets_by_hour_block(jid, w)
        days, busiest = self.repo.betting_days(jid, w)
        return {
            **self._header(player),
            "n_apuestas": sum(g["n"] for g in games),
            "n_con_bono": sum(g["n_con_bono"] for g in games),
            "por_juego": games,
            "por_franja_horaria": {name: blocks.get(i, 0) for i, name in enumerate(HOUR_BLOCKS)},
            "dias_activos": days,
            "max_apuestas_en_un_dia": busiest,
        }

    def bonuses(self, jugador_id: str | None = None) -> dict:
        player, rate = self._player(jugador_id)
        rows = self.repo.bonuses(player.jugador_id, self.window, MAX_BONUSES)
        listed = [
            {"tipo": t, "monto_usd": to_usd(amount, rate), "fecha_otorgado": d[:10], "estado": s}
            for t, amount, d, s in rows
        ]
        return {
            **self._header(player),
            "bonos": listed,
            "total_usd": to_usd(sum(amount for _, amount, _, _ in rows), rate),
            "recortados": len(rows) == MAX_BONUSES,
        }

    def related_accounts(self, jugador_id: str | None = None) -> dict:
        player, _ = self._player(jugador_id)
        until = self.window.end
        devices: dict[str, list[str]] = {}
        for other, device in self.repo.shared_devices(player.jugador_id, until):
            devices.setdefault(other, []).append(device)
        accounts = []
        for other, shared in list(devices.items())[:MAX_RELATED]:
            info = self.repo.get_player(other)
            accounts.append(
                {
                    "jugador_id": other,
                    "dispositivos_compartidos": shared,
                    "fecha_registro": info.fecha_registro if info else None,
                    "estado_cuenta": info.estado_cuenta if info else None,
                    "score_al_corte": self.repo.get_score(other, self.case.fecha_corte),
                    "en_casos_del_dia": other in self.case_players,
                }
            )
            if info:
                self.allowed.add(other)
        networks = self.repo.shared_networks(player.jugador_id, until)
        return {
            "jugador_id": player.jugador_id,
            "criterio": "Mismo device_id usado por ambas cuentas hasta la fecha de corte.",
            "cuentas": accounts,
            "total_cuentas": len(devices),
            "redes": [
                {"red": f"red_{i}", "otros_jugadores": n}
                for i, (_, n) in enumerate(networks, start=1)
            ],
            "aviso_redes": WEAK_NETWORK_NOTICE,
        }

    def transaction_detail(
        self,
        jugador_id: str | None = None,
        tipo: str | None = None,
        estado: str | None = None,
        limite: int = DEFAULT_ROWS,
    ) -> dict:
        player, rate = self._player(jugador_id)
        total, rows = self.repo.transactions(player.jugador_id, self.window, tipo, estado, limite)
        listed = []
        for tx_id, when, t, method, amount, s, text in rows:
            row = {
                "tx_id": tx_id,
                "fecha_hora": when,
                "tipo": t,
                "medio_pago": method,
                "monto_usd": to_usd(amount, rate),
                "estado": s,
            }
            if text:
                row["nota"] = _note(text)
            listed.append(row)
        return {
            **self._header(player),
            "filtros": {"tipo": tipo, "estado": estado},
            "total_coincidencias": total,
            "transacciones": listed,
        }


def _parse(arguments: str | dict | None) -> dict:
    """Models send arguments as a JSON string; an empty one means no arguments."""
    if isinstance(arguments, dict):
        return arguments
    if not arguments or not arguments.strip():
        return {}
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError as e:
        raise ToolError(f"Los argumentos no son JSON válido: {e.msg}.") from None
    if not isinstance(parsed, dict):
        raise ToolError("Los argumentos deben ser un objeto JSON.")
    return parsed


def _note(text: str, tipo: str | None = None, n: int | None = None, first: str | None = None):
    note: dict[str, Any] = {
        "texto_de_terceros": text[:MAX_NOTE_CHARS],
        "parece_instruccion": looks_like_instruction(text),
    }
    if tipo is not None:
        note |= {"tipo": tipo, "veces": n, "primera_fecha": first[:10]}
    return note
