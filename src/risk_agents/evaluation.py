"""Evaluation: score runs against the analyst's 5 references and our hypotheses for the rest.

    uv run risk-agents-eval --system reglas=evaluacion/corridas/reglas \\
        --system groq=evaluacion/corridas/groq_1 --system groq=evaluacion/corridas/groq_2 ...

Each --system NAME=FOLDER adds one run (a folder with expedientes.jsonl, trazas.jsonl and
resumen_corrida.json); repeating a name groups several runs of the same system, so the report
shows ranges and how consistent the model is from run to run.

Two kinds of expectation, never mixed up in the report:
- "analista": the 5 cases of casos_referencia.json. Level, teams, accounts and metrics are the
  analyst's; a match is exact.
- "hipotesis": our reading of the data (docs/02_datos.md), with margins where it is ambiguous.
  Useful to catch clear mistakes, not ground truth.
"""

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from statistics import mean
from typing import Any

from risk_agents.case_file import validate
from risk_agents.untrusted import normalize

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_PATH = ROOT / "evaluacion" / "esperado.json"
REFERENCES_PATH = ROOT / "datos" / "casos_referencia.json"


@dataclass
class Expectation:
    case_id: str
    source: str  # "analista" or "hipotesis"
    state: str
    levels: set[str] | None = None
    teams_exact: set[str] | None = None
    teams_include: set[str] = field(default_factory=set)
    teams_exclude: set[str] = field(default_factory=set)
    accounts: set[str] | None = None
    metrics: dict[str, Any] | None = None
    facts: list[list[str]] = field(default_factory=list)
    alerts: list[list[str]] = field(default_factory=list)


def load_expectations(
    expected_path: Path = EXPECTED_PATH, references_path: Path = REFERENCES_PATH
) -> dict[str, Expectation]:
    references = {r["caso_id"]: r for r in json.loads(references_path.read_text(encoding="utf-8"))}
    expected = {}
    for case_id, e in json.loads(expected_path.read_text(encoding="utf-8"))["casos"].items():
        if e["fuente"] == "analista":
            r = references[case_id]
            expected[case_id] = Expectation(
                case_id,
                "analista",
                r["estado_investigacion"],
                levels={r["nivel_preocupacion"]},
                teams_exact=set(r["derivar_a"]),
                accounts=set(r["cuentas_relacionadas"]),
                metrics=r["metricas_90d_usd"],
                facts=e.get("hechos", []),
                alerts=e.get("alertas", []),
            )
        else:
            expected[case_id] = Expectation(
                case_id,
                "hipotesis",
                e["estado"],
                levels=set(e["niveles"]) if "niveles" in e else None,
                teams_include=set(e.get("derivar_incluye", [])),
                teams_exclude=set(e.get("derivar_excluye", [])),
                accounts=set(e["cuentas"]) if "cuentas" in e else None,
                facts=e.get("hechos", []),
                alerts=e.get("alertas", []),
            )
    return expected


@dataclass
class CaseScore:
    case_id: str
    source: str
    valid: bool
    state: bool
    level: bool | None
    teams: bool | None
    accounts: bool | None
    accounts_missing: int
    accounts_extra: int
    metrics: bool | None
    facts: tuple[int, int]
    alerts: bool | None
    level_value: str | None
    teams_value: list[str]


def score_case(file: dict | None, e: Expectation) -> CaseScore:
    """None means the check does not apply to this case."""
    file = file or {}
    valid = bool(file) and validate(file) == []
    completed = file.get("estado_investigacion") == "completo"
    judged = e.state == "completo"
    got_level = file.get("nivel_preocupacion")
    got_teams = set(file.get("derivar_a", []))
    got_accounts = set(file.get("cuentas_relacionadas", []))

    level = (completed and got_level in e.levels) if judged and e.levels else None
    if not judged:
        teams = None
    elif e.teams_exact is not None:
        teams = completed and got_teams == e.teams_exact
    elif e.teams_include or e.teams_exclude:
        teams = completed and e.teams_include <= got_teams and not (got_teams & e.teams_exclude)
    else:
        teams = None
    accounts = (got_accounts == e.accounts) if judged and e.accounts is not None else None
    expected_accounts = e.accounts or set()

    findings = " ".join(
        f"{h.get('descripcion', '')} {h.get('evidencia', '')}" for h in file.get("hallazgos", [])
    )
    text = normalize(f"{findings} {file.get('resumen', '')}")
    alert_text = normalize(" ".join(file.get("alertas_calidad_datos", [])))
    hits = sum(any(normalize(w) in text for w in group) for group in e.facts)

    return CaseScore(
        case_id=e.case_id,
        source=e.source,
        valid=valid,
        state=file.get("estado_investigacion") == e.state,
        level=level,
        teams=teams,
        accounts=accounts,
        accounts_missing=len(expected_accounts - got_accounts) if accounts is not None else 0,
        accounts_extra=len(got_accounts - expected_accounts) if accounts is not None else 0,
        metrics=(file.get("metricas_90d_usd") == e.metrics) if e.metrics is not None else None,
        facts=(hits, len(e.facts)),
        alerts=(
            all(any(normalize(w) in alert_text for w in group) for group in e.alerts)
            if e.alerts
            else None
        ),
        level_value=got_level,
        teams_value=sorted(got_teams),
    )


@dataclass
class RunScore:
    folder: str
    model: str | None
    cases: dict[str, CaseScore]
    valid: int
    cost_usd: float | None
    input_tokens: int
    output_tokens: int
    steps: list[int]  # per investigated case
    seconds_per_case: list[float]  # model latency per investigated case, retries included
    retries: int
    incomplete: int
    known_cost_per_case: float | None = None  # from the trace; rejected calls are not priced
    rejected_calls: int = 0


def _lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def score_run(folder: str | Path, expectations: dict[str, Expectation] | None = None) -> RunScore:
    folder = Path(folder)
    expectations = expectations or load_expectations()
    files = {f["caso_id"]: f for f in _lines(folder / "expedientes.jsonl")}
    traces = [t for t in _lines(folder / "trazas.jsonl") if t["decision"] == "investigar"]
    summary_path = folder / "resumen_corrida.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    cases = {cid: score_case(files.get(cid), e) for cid, e in expectations.items()}
    llm_events = [[e for e in t["eventos"] if e["tipo"] == "llm"] for t in traces]
    cost = summary.get("costo_usd")
    return RunScore(
        folder=str(folder),
        model=summary.get("modelo"),
        cases=cases,
        valid=sum(s.valid for s in cases.values()),
        cost_usd=None if cost is None else float(cost),
        input_tokens=summary.get("tokens_entrada", 0),
        output_tokens=summary.get("tokens_salida", 0),
        steps=[t["pasos"] for t in traces],
        seconds_per_case=[sum(e["latencia_ms"] for e in ev) / 1000 for ev in llm_events],
        retries=sum(e.get("reintentos", 0) for ev in llm_events for e in ev),
        incomplete=sum(f["estado_investigacion"] == "incompleto" for f in files.values()),
        known_cost_per_case=(
            sum(float(e["costo_usd"] or 0) for ev in llm_events for e in ev) / len(traces)
            if traces
            else None
        ),
        rejected_calls=sum(bool(e.get("rechazada")) for ev in llm_events for e in ev),
    )


# --- aggregation ---


def _ratio(scores: list[CaseScore], attr: str, source: str | None = None) -> tuple[int, int]:
    values = [
        getattr(s, attr)
        for s in scores
        if getattr(s, attr) is not None and (source is None or s.source == source)
    ]
    return sum(bool(v) for v in values), len(values)


def run_metrics(run: RunScore) -> dict[str, tuple[int, int]]:
    s = list(run.cases.values())
    c = run.cases
    return {
        "Expedientes válidos (esquema)": (run.valid, len(s)),
        "Estado correcto": _ratio(s, "state"),
        "Nivel · referencias del analista": _ratio(s, "level", "analista"),
        "Nivel · nuestras hipótesis": _ratio(s, "level", "hipotesis"),
        "Derivación · referencias del analista": _ratio(s, "teams", "analista"),
        "Derivación · nuestras hipótesis": _ratio(s, "teams", "hipotesis"),
        "Cuentas relacionadas exactas": _ratio(s, "accounts"),
        "Métricas al centavo · referencias": _ratio(s, "metrics"),
        "Hechos clave mencionados": (sum(x.facts[0] for x in s), sum(x.facts[1] for x in s)),
        "Alertas esperadas presentes": _ratio(s, "alerts"),
        "T3 · inyección (011 alto, riesgo, reportada)": _all(
            c["C-20261101-011"].level,
            c["C-20261101-011"].teams,
            c["C-20261101-011"].alerts,
        ),
        "T6 · no vincula por red (005, 012)": _all(
            c["C-20261101-005"].accounts, c["C-20261101-012"].accounts
        ),
        "T8 · factores que no cuadran (002, 025)": _all(
            c["C-20261101-002"].alerts, c["C-20261101-025"].alerts
        ),
        "T9 · anillo completo (016, 020)": _all(
            c["C-20261101-016"].accounts, c["C-20261101-020"].accounts
        ),
    }


def _all(*checks: bool | None) -> tuple[int, int]:
    return int(all(bool(x) for x in checks)), 1


def _cell(values: list[tuple[int, int]]) -> str:
    oks = [ok for ok, _ in values]
    total = values[0][1]
    if min(oks) == max(oks):
        return f"{oks[0]}/{total}"
    return f"{min(oks)}–{max(oks)}/{total}"


def _span(values: list[float], fmt: str) -> str:
    values = [v for v in values if v is not None]
    if not values:
        return "?"
    lo, hi = min(values), max(values)
    return format(lo, fmt) if lo == hi else f"{format(lo, fmt)}–{format(hi, fmt)}"


def consistency(runs: list[RunScore]) -> tuple[int, int]:
    """Investigated cases whose level and teams are the same in every run."""
    ids = [cid for cid, s in runs[0].cases.items() if s.level is not None]
    same = sum(
        len({(r.cases[cid].level_value, tuple(r.cases[cid].teams_value)) for r in runs}) == 1
        for cid in ids
    )
    return same, len(ids)


def render_report(systems: dict[str, list[RunScore]]) -> str:
    names = list(systems)
    header = "| Métrica | " + " | ".join(
        f"{n} ({len(systems[n])} corrida{'s' if len(systems[n]) > 1 else ''})" for n in names
    )
    lines = [
        "# Reporte de evaluación",
        "",
        "Generado por `uv run risk-agents-eval`. No editar a mano.",
        "",
        "Con varias corridas de un mismo sistema, cada celda muestra el rango (mínimo–máximo).",
        "Las filas de **referencias** comparan con el analista; las de **hipótesis**, con nuestra"
        " lectura de los datos (`docs/02_datos.md`), que no es una verdad.",
        "",
        "## Resumen",
        "",
        header + " |",
        "|---|" + "---|" * len(names),
    ]
    metric_names = list(run_metrics(systems[names[0]][0]))
    per_system = {n: [run_metrics(r) for r in systems[n]] for n in names}
    for m in metric_names:
        lines.append(
            f"| {m} | " + " | ".join(_cell([x[m] for x in per_system[n]]) for n in names) + " |"
        )

    lines += ["", "## Costo, pasos y tiempo", "", header + " |", "|---|" + "---|" * len(names)]
    rows = {
        "Costo por corrida (USD)": lambda rs: _span([r.cost_usd for r in rs], ".4f"),
        "Costo conocido por caso investigado (USD)": lambda rs: _span(
            [r.known_cost_per_case for r in rs], ".4f"
        ),
        "Llamadas rechazadas por el proveedor (costo no informado)": lambda rs: _span(
            [r.rejected_calls for r in rs], "d"
        ),
        "Tokens de entrada por corrida": lambda rs: _span([r.input_tokens for r in rs], ",.0f"),
        "Tokens de salida por corrida": lambda rs: _span([r.output_tokens for r in rs], ",.0f"),
        "Pasos del modelo por caso (promedio)": lambda rs: _span(
            [mean(r.steps) if r.steps else 0 for r in rs], ".1f"
        ),
        "Segundos de modelo por caso (promedio)": lambda rs: _span(
            [mean(r.seconds_per_case) if r.seconds_per_case else 0 for r in rs], ".1f"
        ),
        "Reintentos del proveedor por corrida": lambda rs: _span([r.retries for r in rs], "d"),
        "Casos incompletos por corrida": lambda rs: _span([r.incomplete for r in rs], "d"),
    }
    for label, fn in rows.items():
        lines.append(f"| {label} | " + " | ".join(fn(systems[n]) for n in names) + " |")

    lines += ["", "## Consistencia entre corridas", ""]
    for n in names:
        if len(systems[n]) > 1:
            same, total = consistency(systems[n])
            lines.append(
                f"- **{n}**: {same} de {total} casos investigados con el mismo nivel y la misma"
                f" derivación en las {len(systems[n])} corridas ({round(100 * same / total)} %)."
            )
    if not any(len(systems[n]) > 1 for n in names):
        lines.append("- Hace falta más de una corrida de un sistema.")

    lines += ["", "## Caso por caso", ""]
    lines.append("Cada celda: nivel · equipos por corrida. ✗ = no coincide con lo esperado.")
    lines += ["", "| Caso | Fuente | Esperado | " + " | ".join(names) + " |"]
    lines.append("|---|---|---|" + "---|" * len(names))
    expectations = load_expectations()
    for cid, e in expectations.items():
        expected = _expected_text(e)
        cells = []
        for n in names:
            cells.append(" / ".join(_got_text(r.cases[cid]) for r in systems[n]))
        lines.append(f"| {cid} | {e.source} | {expected} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def _expected_text(e: Expectation) -> str:
    if e.state != "completo":
        return e.state
    teams = (
        ",".join(sorted(e.teams_exact)) or "—"
        if e.teams_exact is not None
        else "+".join(sorted(e.teams_include)) or ("—" if e.teams_exclude else "?")
    )
    return f"{'/'.join(sorted(e.levels or []))} · {teams}"


def _got_text(s: CaseScore) -> str:
    if s.level is None:
        return "ok" if s.state else "✗"
    mark = "" if s.level and s.teams is not False else " ✗"
    return f"{s.level_value or 'incompleto'} · {','.join(s.teams_value) or '—'}{mark}"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="risk-agents-eval", description=__doc__.split("\n")[0])
    p.add_argument("--system", action="append", required=True, metavar="NOMBRE=CARPETA")
    p.add_argument("--out", type=Path, default=ROOT / "evaluacion" / "reporte.md")
    a = p.parse_args(argv)
    expectations = load_expectations()
    systems: dict[str, list[RunScore]] = defaultdict(list)
    for item in a.system:
        name, _, folder = item.partition("=")
        systems[name].append(score_run(folder, expectations))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(render_report(dict(systems)), encoding="utf-8")
    data = {
        "sistemas": {
            n: [
                {
                    "carpeta": r.folder,
                    "modelo": r.model,
                    "metricas": {k: list(v) for k, v in run_metrics(r).items()},
                    "casos": {cid: asdict(s) for cid, s in r.cases.items()},
                }
                for r in runs
            ]
            for n, runs in systems.items()
        }
    }
    a.out.with_suffix(".json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1, default=list) + "\n", encoding="utf-8"
    )
    print(f"Reporte: {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
