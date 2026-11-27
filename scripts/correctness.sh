#!/usr/bin/env bash
# Correctness experiment: serial vs OpenMP ranks on the small graphs
# (plus the dangling-node test), for 1-16 threads and both schedules.
# Writes results/correctness.csv. Run from the repo root after `make`.
set -euo pipefail

DATA=${DATA:-datasets}
TOL=${TOL:-1e-10}
MAX_ITERS=${MAX_ITERS:-100}
OUT=results/correctness.csv
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

mkdir -p results
echo "dataset,threads,schedule,iters,max_change,rank_sum,max_abs_diff_vs_serial,result" > "$OUT"

for g in tiny_dangling pr_u10k_100k pr_s10k_100k; do
    f="$DATA/$g.txt"
    [ -f "$f" ] || { echo "missing $f" >&2; exit 1; }
    ./serial "$f" "$MAX_ITERS" "$TOL" "$TMP/serial.txt" > "$TMP/serial.csv"
    IFS=, read -r _ _ _ _ it mc sum _ < "$TMP/serial.csv"
    echo "$g,serial,none,$it,$mc,$sum,0,REF" >> "$OUT"
    for sched in static "dynamic,64"; do
        for t in 1 2 4 8 16; do
            line=$(OMP_NUM_THREADS=$t OMP_SCHEDULE=$sched \
                   ./parallel "$f" "$MAX_ITERS" "$TOL" "$TMP/par.txt")
            IFS=, read -r _ _ th sc it mc sum _ <<< "$line"
            v=$(python3 scripts/validate.py "$TMP/serial.txt" "$TMP/par.txt" || true)
            diff=$(sed -n 's/.*max_abs_diff=\([^ ]*\).*/\1/p' <<< "$v")
            res=${v%%:*}
            echo "$g,$th,$sc,$it,$mc,$sum,$diff,$res" >> "$OUT"
        done
    done
done
(command -v column >/dev/null && column -s, -t < "$OUT") || cat "$OUT"
grep -q FAIL "$OUT" && { echo "Some checks FAILED" >&2; exit 1; } || echo "All checks passed."
