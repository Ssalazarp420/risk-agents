"""Command line: `uv run risk-agents` processes the cases of the day.

Examples:
    uv run --env-file .env risk-agents                 # Groq, resumes a previous run
    uv run risk-agents --llm reglas                    # no API key: fixed rules
    uv run --env-file .env risk-agents --only C-20261101-011 --fresh
"""

import argparse
import json
import sys
from pathlib import Path

from risk_agents.baseline import RuleBasedLLM
from risk_agents.cases import CaseFileError
from risk_agents.data.repository import Repository, connect_read_only
from risk_agents.llm import DEFAULT_MODEL, ChatModel, GroqClient, MissingApiKeyError
from risk_agents.orchestrator import run_batch

ROOT = Path(__file__).resolve().parents[2]


def parse(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="risk-agents",
        description="Investiga los casos del día y escribe un expediente por caso.",
    )
    p.add_argument(
        "--llm",
        choices=["groq", "reglas"],
        default="groq",
        help="groq (necesita GROQ_API_KEY) o reglas fijas, sin red. Por defecto: groq",
    )
    p.add_argument(
        "--model", default=DEFAULT_MODEL, help=f"Modelo de Groq. Por defecto: {DEFAULT_MODEL}"
    )
    p.add_argument("--cases", default=ROOT / "datos" / "casos_del_dia.csv", type=Path)
    p.add_argument("--db", default=ROOT / "datos" / "transacciones.db", type=Path)
    p.add_argument("--out", default=ROOT / "salidas" / "expedientes.jsonl", type=Path)
    p.add_argument("--traces", default=ROOT / "salidas" / "trazas.jsonl", type=Path)
    p.add_argument("--only", nargs="+", metavar="CASO_ID", help="Procesar solo estos casos")
    p.add_argument(
        "--fresh",
        action="store_true",
        help="Empezar de cero en vez de reanudar la corrida anterior",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    a = parse(argv)
    try:
        llm: ChatModel = RuleBasedLLM() if a.llm == "reglas" else GroqClient.from_env(a.model)
        repo = Repository(connect_read_only(a.db))
    except MissingApiKeyError as e:
        print(f"{e} Para correr sin clave: --llm reglas", file=sys.stderr)
        return 2
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 2

    def progress(file: dict, trace: dict) -> None:
        cost = trace["costo_usd"]
        print(
            f"{file['caso_id']}  {file['estado_investigacion']:<10}"
            f" {file['nivel_preocupacion'] or '-':<6} {','.join(file['derivar_a']) or '-':<28}"
            f" pasos={trace['pasos']:<2} costo={cost if cost is not None else '?'}"
            + (f"  error: {trace['error']}" if trace["error"] else "")
        )

    try:
        summary = run_batch(
            a.cases,
            repo,
            llm,
            a.out,
            a.traces,
            resume=not a.fresh,
            only=set(a.only) if a.only else None,
            on_case=progress,
        )
    except CaseFileError as e:
        print(f"El archivo de casos no se puede leer: {e}", file=sys.stderr)
        return 2

    report = {"modelo": llm.model, **summary.as_dict()}
    summary_path = a.out.parent / "resumen_corrida.json"
    summary_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\nExpedientes: {a.out}\nTrazas: {a.traces}\nResumen: {summary_path}")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
