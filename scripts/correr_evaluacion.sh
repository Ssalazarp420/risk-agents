#!/usr/bin/env bash
# Runs the whole evaluation: the rule baseline, N runs with Groq, and the report.
#
#   scripts/correr_evaluacion.sh            # 3 runs with Groq (needs .env)
#   scripts/correr_evaluacion.sh 0          # baseline only, no API key
#
# Each Groq run starts from scratch (--fresh) so runs are independent. Outputs go to
# evaluacion/corridas/ and the report to evaluacion/reporte.md.
set -euo pipefail
cd "$(dirname "$0")/.."

RUNS="${1:-3}"
OUT=evaluacion/corridas

run() {  # name, extra args...
    local name=$1; shift
    uv run "$@" --fresh --out "$OUT/$name/expedientes.jsonl" --traces "$OUT/$name/trazas.jsonl"
}

run reglas risk-agents --llm reglas > /dev/null
systems=(--system "reglas=$OUT/reglas")

for i in $(seq 1 "$RUNS"); do
    echo "== Groq, corrida $i de $RUNS"
    run "groq_$i" --env-file .env risk-agents
    systems+=(--system "groq=$OUT/groq_$i")
done

uv run risk-agents-eval "${systems[@]}"
