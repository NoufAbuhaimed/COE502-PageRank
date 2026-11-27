#!/usr/bin/env bash
# Timing experiments for the report. Appends one row per run to
# results/raw_timings.csv. Resumable: rows already in the CSV are skipped, so
# after a Spot preemption just run it again.
#
#   ./scripts/benchmark.sh                  # everything, defaults below
#   RUNS=3 ITERS=500 ./scripts/benchmark.sh # other settings
#
# Experiments (all timing runs: tol = 0, so every run does exactly ITERS iterations):
#   main  : serial (1 thread) + static, dynamic-64, edge-balanced at THREADS,
#           on all GRAPHS
#   sweep : dynamic with chunk SWEEP_CHUNKS at SWEEP_THREADS, on SWEEP_GRAPHS
#
# Loop order is run -> graph -> config, so each "round" does one run of every
# configuration. An interrupted benchmark leaves complete rounds, not some
# configs with 5 runs and others with none, and slow drift on the machine
# (thermal, noisy neighbours) hits all configs alike.
set -euo pipefail

. "$(dirname "$0")/data_dir.sh"   # DATA = /workspace/coe502/datasets on the server, else ../datasets
OUT=${OUT:-results/raw_timings.csv}
RUNS=${RUNS:-5}
ITERS=${ITERS:-1000}   # serial on pr_s500k_5m is ~9 ms/iter -> ~9 s (the PDF asks for 5-15 s)
THREADS=${THREADS:-"1 2 4 8 16"}
GRAPHS=${GRAPHS:-"pr_u10k_100k pr_s10k_100k pr_u100k_1m pr_s100k_1m pr_u500k_5m pr_s500k_5m"}
SWEEP_GRAPHS=${SWEEP_GRAPHS:-"pr_s100k_1m pr_s500k_5m"}
SWEEP_CHUNKS=${SWEEP_CHUNKS:-"16 64 256 1024 4096"}
SWEEP_THREADS=${SWEEP_THREADS:-"8 16"}

export OMP_PROC_BIND=${OMP_PROC_BIND:-close} OMP_PLACES=${OMP_PLACES:-cores}
HEADER="version,run,impl,dataset,threads,schedule,iters,max_change,rank_sum,time_s"

# ---- Checks before starting -------------------------------------------------
for b in serial parallel parallel_opt; do
    [ -x "./$b" ] || { echo "missing ./$b: run make first" >&2; exit 1; }
done
for g in $GRAPHS $SWEEP_GRAPHS; do
    [ -f "$DATA/$g.txt" ] || { echo "missing $DATA/$g.txt (set DATA=<folder with the graphs>)" >&2; exit 1; }
done
max_t=1
for t in $THREADS $SWEEP_THREADS; do [ "$t" -gt "$max_t" ] && max_t=$t; done
cores=$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 0)
[ "$cores" -ge "$max_t" ] || echo "warning: $max_t threads requested but only $cores CPUs online" >&2

mkdir -p "$(dirname "$OUT")"

# ---- System information (once; the PDF asks for CPU, cores and OS) ----------
INFO=$(dirname "$OUT")/system_info.txt
if [ ! -f "$INFO" ]; then
    {
        echo "date: $(date -u '+%Y-%m-%d %H:%M UTC')"
        echo "uname: $(uname -srm)"
        [ -f /etc/os-release ] && echo "os: $(. /etc/os-release && echo "$PRETTY_NAME")"
        echo "compiler: $(${CXX:-c++} --version 2>/dev/null | head -1)"
        echo "OMP_PROC_BIND=$OMP_PROC_BIND OMP_PLACES=$OMP_PLACES"
        command -v free >/dev/null && echo "memory: $(free -h | awk '/^Mem:/ {print $2}')"
        # On Google Cloud: the VM type (e.g. c2-standard-16 = 16 vCPUs = 8 physical cores).
        mt=$(curl -s -m 2 -H 'Metadata-Flavor: Google' \
             http://metadata.google.internal/computeMetadata/v1/instance/machine-type 2>/dev/null || true)
        [ -n "$mt" ] && echo "machine_type: ${mt##*/}"
        echo
        if command -v lscpu >/dev/null; then lscpu
        else sysctl -n machdep.cpu.brand_string hw.physicalcpu hw.logicalcpu 2>/dev/null || true
        fi
    } > "$INFO"
    echo "wrote $INFO"
fi

# ---- Resume: repair the CSV and collect what is already done ---------------
if [ ! -s "$OUT" ]; then
    echo "$HEADER" > "$OUT"
else
    # A preemption during a write can leave a last line without '\n'. It may be
    # cut short (e.g. "0.0" instead of "0.012217"), so drop it and redo that run.
    if [ -n "$(tail -c1 "$OUT")" ]; then
        sed '$d' "$OUT" > "$OUT.tmp" && mv "$OUT.tmp" "$OUT"
        echo "removed a partial last line from $OUT"
    fi
    # Comparisons need the same iteration count everywhere: refuse to mix.
    other=$(awk -F, -v it="$ITERS" 'NR > 1 && NF == 10 && $7 != it {print $7; exit}' "$OUT")
    if [ -n "$other" ]; then
        echo "$OUT has runs with iters=$other but ITERS=$ITERS." >&2
        echo "Use ITERS=$other to resume, or move the file away to start over." >&2
        exit 1
    fi
fi

# Key of a finished run: version|dataset|threads|run
DONE=$(mktemp)
trap 'rm -f "$DONE" "$OUT.tmp"' EXIT
awk -F, 'NR > 1 && NF == 10 {print $1 "|" $4 "|" $5 "|" $2}' "$OUT" > "$DONE"

# ---- Build the plan: one line "version graph threads run" per run ----------
PLAN=$(mktemp)
trap 'rm -f "$DONE" "$PLAN" "$OUT.tmp"' EXIT
for run in $(seq 1 "$RUNS"); do
    for g in $GRAPHS; do
        echo "serial $g 1 $run"
        for t in $THREADS; do
            for v in static dynamic-64 edge-balanced; do echo "$v $g $t $run"; done
        done
    done
    for g in $SWEEP_GRAPHS; do
        for t in $SWEEP_THREADS; do
            for c in $SWEEP_CHUNKS; do echo "dynamic-$c $g $t $run"; done
        done
    done
done | awk '!seen[$0]++' > "$PLAN"   # dynamic-64 is in both experiments: run it once

total=$(wc -l < "$PLAN" | tr -d ' ')
todo=0
while read -r v g t run; do
    grep -qxF "$v|$g|$t|$run" "$DONE" || todo=$((todo + 1))
done < "$PLAN"
echo "graphs: $DATA"
echo "plan: $total runs, $((total - todo)) already in $OUT, $todo to do (ITERS=$ITERS)"

# ---- Run ---------------------------------------------------------------------
i=0
while read -r v g t run; do
    i=$((i + 1))
    grep -qxF "$v|$g|$t|$run" "$DONE" && continue
    f="$DATA/$g.txt"
    case "$v" in
        serial)        line=$(./serial "$f" "$ITERS" 0 < /dev/null) ;;
        edge-balanced) line=$(OMP_NUM_THREADS=$t ./parallel_opt "$f" "$ITERS" 0 < /dev/null) ;;
        static)        line=$(OMP_NUM_THREADS=$t OMP_SCHEDULE=static ./parallel "$f" "$ITERS" 0 < /dev/null) ;;
        dynamic-*)     line=$(OMP_NUM_THREADS=$t OMP_SCHEDULE="dynamic,${v#dynamic-}" \
                              ./parallel "$f" "$ITERS" 0 < /dev/null) ;;
    esac
    IFS=, read -r _ _ got_t _ got_it _ _ secs <<< "$line"
    if [ "$got_t" != "$t" ] || [ "$got_it" != "$ITERS" ]; then
        echo "unexpected output for $v $g P=$t: $line" >&2
        exit 1
    fi
    # One printf = one short write, so a preemption loses at most this run.
    printf '%s,%s,%s\n' "$v" "$run" "$line" >> "$OUT"
    printf '[%d/%d] %-14s %-14s P=%-2s run %s: %s s\n' "$i" "$total" "$v" "$g" "$t" "$run" "$secs"
done < "$PLAN"

echo "done: $OUT"
