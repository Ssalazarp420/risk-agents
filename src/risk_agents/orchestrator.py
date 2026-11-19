"""The daily batch: casos_del_dia.csv in, expedientes.jsonl and trazas.jsonl out.

For each case, in file order:
1. prevalidation decides it in code (sin_datos, omitido) or sends it to the agent;
2. the code computes the metrics and its own alerts, independent of the model;
3. the agent investigates; the assembler joins its conclusion with the code's fields;
4. the case file is validated against the official schema before it is written.

The output file is rewritten after every case, in file order, so an interrupted run loses at
most the case in progress. A new run keeps the finished cases and redoes only the missing or
`incompleto` ones (resume), unless `resume=False`.
"""

import json
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from risk_agents.agent import build_context, run_agent
from risk_agents.case_file import (
    CaseFile,
    incomplete_file,
    investigated_file,
    no_data_file,
    skipped_file,
    validate,
)
from risk_agents.cases import Case, load_cases
from risk_agents.data.repository import Repository
from risk_agents.data.rules import window_for
from risk_agents.llm import ChatModel
from risk_agents.prevalidation import Decision, Triage, prevalidate
from risk_agents.tools import ToolBox
from risk_agents.untrusted import looks_like_instruction

MAX_NOTES_SCANNED = 50


@dataclass
class RunSummary:
    by_state: dict[str, int]
    by_level: dict[str, int]
    investigated: int  # cases sent to the model in this run
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: Decimal | None = Decimal(0)
    seconds: float = 0.0
    batch_alerts: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "por_estado": self.by_state,
            "por_nivel": self.by_level,
            "investigados_en_esta_corrida": self.investigated,
            "tokens_entrada": self.input_tokens,
            "tokens_salida": self.output_tokens,
            "costo_usd": None if self.cost_usd is None else str(self.cost_usd),
            "segundos": round(self.seconds, 1),
            "alertas_del_lote": self.batch_alerts,
        }


def code_alerts(case: Case, repo: Repository, missing: dict[str, list[tuple[str, float]]]):
    """Alerts the code raises on its own, whatever the model does."""
    alerts = []
    window = window_for(case.fecha_corte)
    for text, tipo, _, first in repo.notes(case.jugador_id, window, MAX_NOTES_SCANNED):
        if looks_like_instruction(text):
            alerts.append(
                f"Una nota de {tipo} del {first[:10]} intenta dar instrucciones al sistema de"
                " revisión. Se trató como dato, no como instrucción."
            )
    missing_scores = dict(missing.get(case.fecha_corte, []))
    linked = sorted({other for other, _ in repo.shared_devices(case.jugador_id, window.end)})
    for other in linked:
        if other in missing_scores:
            alerts.append(
                f"{other} (score {missing_scores[other]}) comparte dispositivo con este jugador y"
                " no está en los casos del día: el flujo diario lo dejó fuera."
            )
    return alerts


def run_batch(
    cases_path: str | Path,
    repo: Repository,
    llm: ChatModel,
    out_path: str | Path,
    traces_path: str | Path,
    *,
    resume: bool = True,
    only: set[str] | None = None,
    on_case: Callable[[CaseFile, dict], None] | None = None,
) -> RunSummary:
    start = time.perf_counter()
    out_path, traces_path = Path(out_path), Path(traces_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    traces_path.parent.mkdir(parents=True, exist_ok=True)
    if not resume:
        traces_path.unlink(missing_ok=True)

    cases = load_cases(cases_path)
    report = prevalidate(cases, repo)
    case_players = frozenset(c.jugador_id for c in cases)
    previous = _read_previous(out_path) if resume else {}
    run_id = datetime.now(UTC).isoformat(timespec="seconds")

    results: dict[str, CaseFile] = {}
    summary = RunSummary(by_state={}, by_level={}, investigated=0, batch_alerts=report.alerts)
    for triage in report.triages:
        caso_id = triage.case.caso_id
        kept = previous.get(caso_id)
        if only is not None and caso_id not in only:
            if kept:
                results[caso_id] = kept
            continue
        if kept and kept["estado_investigacion"] != "incompleto":
            results[caso_id] = kept
            continue

        file, trace = _process(triage, repo, llm, report.missing_players, case_players)
        trace["corrida"] = run_id
        results[caso_id] = file
        if trace["decision"] == Decision.INVESTIGATE.value:
            summary.investigated += 1
            summary.input_tokens += trace["tokens_entrada"]
            summary.output_tokens += trace["tokens_salida"]
            cost = trace["costo_usd"]
            summary.cost_usd = (
                None
                if summary.cost_usd is None or cost is None
                else summary.cost_usd + Decimal(cost)
            )
        with traces_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(trace, ensure_ascii=False) + "\n")
        _write(out_path, results)
        if on_case:
            on_case(file, trace)

    _write(out_path, results)
    summary.by_state = dict(Counter(f["estado_investigacion"] for f in results.values()))
    summary.by_level = dict(
        Counter(f["nivel_preocupacion"] for f in results.values() if f["nivel_preocupacion"])
    )
    summary.seconds = time.perf_counter() - start
    return summary


def _process(
    triage: Triage,
    repo: Repository,
    llm: ChatModel,
    missing: dict[str, list[tuple[str, float]]],
    case_players: frozenset[str],
) -> tuple[CaseFile, dict[str, Any]]:
    case = triage.case
    trace: dict[str, Any] = {
        "caso_id": case.caso_id,
        "jugador_id": case.jugador_id,
        "decision": triage.decision.value,
        "modelo": None,
        "pasos": 0,
        "tokens_entrada": 0,
        "tokens_salida": 0,
        "costo_usd": "0",
        "error": None,
        "eventos": [],
    }
    if triage.decision is Decision.NO_DATA:
        file = no_data_file(case, triage.alerts)
    elif triage.decision is Decision.DUPLICATE:
        file = skipped_file(case, triage.duplicate_of or "", triage.alerts)
    else:
        file = _investigate(triage, repo, llm, missing, case_players, trace)
    trace["estado"] = file["estado_investigacion"]
    return file, trace


def _investigate(triage, repo, llm, missing, case_players, trace) -> CaseFile:
    case = triage.case
    metrics = None
    alerts = list(triage.alerts)
    try:
        found = repo.metrics_90d(case.jugador_id, case.fecha_corte)
        metrics = found.as_dict() if found else None
        alerts += code_alerts(case, repo, missing)
        box = ToolBox(repo, case, case_players)
        result = run_agent(llm, box, build_context(case, repo, alerts))
    except Exception as e:  # a data problem in the code's own steps: this case, not the run
        trace["error"] = f"{type(e).__name__}: {e}"
        return incomplete_file(case, metrics, trace["error"], alerts)

    trace.update(
        modelo=llm.model,
        pasos=result.steps,
        tokens_entrada=result.input_tokens,
        tokens_salida=result.output_tokens,
        costo_usd=None if result.cost_usd is None else str(result.cost_usd),
        error=result.error,
        eventos=result.trace,
    )
    if result.conclusion is None or metrics is None:
        return incomplete_file(case, metrics, result.error or "sin métricas", alerts)
    file = investigated_file(case, metrics, result.conclusion, result.related_seen, alerts)
    errors = validate(file)
    if errors:
        trace["error"] = "El expediente no cumple el esquema: " + "; ".join(errors)
        return incomplete_file(case, metrics, trace["error"], alerts)
    return file


def _read_previous(path: Path) -> dict[str, CaseFile]:
    """Valid case files from an earlier run; anything unreadable is simply redone."""
    if not path.exists():
        return {}
    previous = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            file = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(file, dict) and not validate(file):
            previous[file["caso_id"]] = file
    return previous


def _write(path: Path, results: dict[str, CaseFile]) -> None:
    """Rewrite the whole file and replace it atomically, so a crash never leaves a half-written
    file. `results` is filled in case order, so the file keeps the order of the input."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for file in results.values():
            f.write(json.dumps(file, ensure_ascii=False) + "\n")
    tmp.replace(path)
