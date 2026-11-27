#!/usr/bin/env bash
# Load-imbalance experiment: per-thread busy time for static, dynamic,64 and
# the edge-balanced optimized version, on the uniform and skewed graphs.
# Uses the *_prof binaries (make prof). Writes results/thread_times.csv and,
# plots/thread_imbalance.png (via uv, which brings matplotlib).
#
#   ITERS=50 THREADS=16 ./scripts/imbalance.sh
set -euo pipefail

. "$(dirname "$0")/data_dir.sh"   # DATA = /workspace/coe502/datasets on the server, else ../datasets
ITERS=${ITERS:-50}
THREADS=${THREADS:-16}
GRAPHS=${GRAPHS:-"pr_u500k_5m pr_s500k_5m"}
export THREAD_TIMES_CSV=${THREAD_TIMES_CSV:-results/thread_times.csv}
export OMP_PROC_BIND=${OMP_PROC_BIND:-close} OMP_PLACES=${OMP_PLACES:-cores}

mkdir -p results plots
rm -f "$THREAD_TIMES_CSV"
for g in $GRAPHS; do
    f="$DATA/$g.txt"
    [ -f "$f" ] || { echo "missing $f (set DATA=<folder with the graphs>)" >&2; exit 1; }
    OMP_NUM_THREADS=$THREADS OMP_SCHEDULE=static     ./parallel_prof     "$f" "$ITERS" 0
    OMP_NUM_THREADS=$THREADS OMP_SCHEDULE=dynamic,64 ./parallel_prof     "$f" "$ITERS" 0
    OMP_NUM_THREADS=$THREADS                         ./parallel_opt_prof "$f" "$ITERS" 0
done
echo "wrote $THREAD_TIMES_CSV"
uv run --quiet scripts/plot_thread_times.py "$THREAD_TIMES_CSV" plots/thread_imbalance.png \
    || echo "plot skipped (needs uv: run ./scripts/setup.sh)"
