#!/usr/bin/env bash
# Runs the evaluation: the rule baseline, N runs with Groq, and the report.
#
#   scripts/correr_evaluacion.sh                 # 3 runs with Groq, tagged groq (needs .env)
#   scripts/correr_evaluacion.sh 3 groq_v2       # 3 runs tagged groq_v2
#   scripts/correr_evaluacion.sh 0               # baseline and report only, no API key
#
# Each Groq run starts from scratch (--fresh) so runs are independent. Runs are kept in
# evaluacion/corridas/<tag>_<n>/; the report groups every saved run by tag, so earlier versions
# stay in the comparison.
set -euo pipefail
cd "$(dirname "$0")/.."

RUNS="${1:-3}"
TAG="${2:-groq}"
OUT=evaluacion/corridas

run() {  # name, extra args...
    local name=$1; shift
    uv run "$@" --fresh --out "$OUT/$name/expedientes.jsonl" --traces "$OUT/$name/trazas.jsonl"
}

run reglas risk-agents --llm reglas > /dev/null

for i in $(seq 1 "$RUNS"); do
    echo "== $TAG, corrida $i de $RUNS"
    run "${TAG}_$i" --env-file .env risk-agents
done

systems=(--system "reglas=$OUT/reglas")
for dir in "$OUT"/*_[0-9]*/; do
    [ -d "$dir" ] || continue
    name=$(basename "$dir")
    systems+=(--system "${name%_*}=$OUT/$name")
done
uv run risk-agents-eval "${systems[@]}"
