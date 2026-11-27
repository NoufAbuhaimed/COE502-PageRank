#!/usr/bin/env bash
# Correctness experiment: serial vs OpenMP ranks on the small graphs
# (plus the dangling-node test), for 1-16 threads, static / dynamic,64,
# and the optimized edge-balanced version.
# Writes results/correctness.csv. Run from the repo root after `make`.
set -euo pipefail

. "$(dirname "$0")/data_dir.sh"   # DATA = /workspace/coe502/datasets on the server, else ../datasets
TOL=${TOL:-1e-10}
MAX_ITERS=${MAX_ITERS:-100}
OUT=results/correctness.csv
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

mkdir -p results
echo "dataset,threads,schedule,iters,max_change,rank_sum,max_abs_diff_vs_serial,result" > "$OUT"

for g in tiny_dangling pr_u10k_100k pr_s10k_100k; do
    # tiny_dangling is our own test graph, kept in the repo; the others are the provided graphs.
    if [ "$g" = tiny_dangling ]; then f="datasets/$g.txt"; else f="$DATA/$g.txt"; fi
    [ -f "$f" ] || { echo "missing $f (set DATA=<folder with the graphs>)" >&2; exit 1; }
    ./serial "$f" "$MAX_ITERS" "$TOL" "$TMP/serial.txt" > "$TMP/serial.csv"
    IFS=, read -r _ _ _ _ it mc sum _ < "$TMP/serial.csv"
    echo "$g,serial,none,$it,$mc,$sum,0,REF" >> "$OUT"
    for sched in static "dynamic,64" opt; do
        for t in 1 2 4 8 16; do
            if [ "$sched" = opt ]; then
                line=$(OMP_NUM_THREADS=$t ./parallel_opt "$f" "$MAX_ITERS" "$TOL" "$TMP/par.txt")
            else
                line=$(OMP_NUM_THREADS=$t OMP_SCHEDULE=$sched \
                       ./parallel "$f" "$MAX_ITERS" "$TOL" "$TMP/par.txt")
            fi
            IFS=, read -r _ _ th sc it mc sum _ <<< "$line"
            v=$(uv run --quiet scripts/validate.py "$TMP/serial.txt" "$TMP/par.txt" || true)
            diff=$(sed -n 's/.*max_abs_diff=\([^ ]*\).*/\1/p' <<< "$v")
            res=${v%%:*}
            echo "$g,$th,$sc,$it,$mc,$sum,$diff,$res" >> "$OUT"
        done
    done
done
(command -v column >/dev/null && column -s, -t < "$OUT") || cat "$OUT"
grep -q FAIL "$OUT" && { echo "Some checks FAILED" >&2; exit 1; } || echo "All checks passed."
