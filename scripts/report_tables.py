#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["matplotlib"]
# ///
"""Print the report's tables as Markdown, ready to paste into Google Docs
(Edit -> Paste from Markdown).

Usage: uv run scripts/report_tables.py <section> [<section> ...]

Sections:
  system       machine the timings ran on          (results/system_info.txt)
  datasets     graph sizes and skew                 (reads the graph files in $DATA)
  correctness  serial vs OpenMP rank comparison     (results/correctness.csv)
  convergence  iterations to converge, rank sum     (results/convergence.csv)
  speedup      time / speedup / efficiency per P    (results/raw_timings.csv)
  knee         where more threads stop helping      (results/raw_timings.csv)
  karpflatt    Karp-Flatt serial fraction per P     (results/raw_timings.csv)
  sweep        dynamic chunk-size sweep             (results/raw_timings.csv)
  imbalance    per-thread busy / idle summary       (results/thread_times.csv)
  bandwidth    effective memory bandwidth per P     (raw_timings + graph headers)
  all          everything above

Environment: DATA (graph folder; default /workspace/coe502/datasets if it exists, else
../datasets), RESULTS (default results).
"""
import csv
import os
import re
import sys
from collections import defaultdict
from statistics import median

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plot_results import MAIN, dataset_sort_key, load, split_name, summarize  # noqa: E402

# Same rule as scripts/data_dir.sh: the course server path if it exists, else ../datasets.
DATA = os.environ.get("DATA") or ("/workspace/coe502/datasets"
                                  if os.path.isdir("/workspace/coe502/datasets") else "../datasets")
RESULTS = os.environ.get("RESULTS", "results")
LABEL = {"serial": "serial", "static": "static", "dynamic-64": "dynamic,64",
         "edge-balanced": "edge-balanced"}
SIZE_ROLE = {"10k_100k": "small (correctness)", "100k_1m": "medium (main)",
             "500k_5m": "large (scalability)"}


# ---- helpers ------------------------------------------------------------------
def table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join(" --- " for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    print("\n".join(out) + "\n")


def need(path):
    if not os.path.exists(path):
        print(f"_missing {path}: run the step that creates it first_\n")
        return False
    return True


def fmt(x, spec):
    return "–" if x is None else format(x, spec)


def timing_rows():
    path = os.path.join(RESULTS, "raw_timings.csv")
    if not need(path):
        return None, None, None
    times = load(path)
    rows, serial = summarize(times)
    with open(path) as f:
        iters = {r["iters"] for r in csv.DictReader(f) if r.get("iters")}
    return rows, serial, iters


def graph_header(name):
    """(N, M) from the first non-comment line of a graph file, or None."""
    path = os.path.join(DATA, name + ".txt")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        for line in f:
            if line.strip() and not line.lstrip().startswith("#"):
                n, m = line.split()[:2]
                return int(n), int(m)
    return None


def bytes_per_iter(n, m):
    """Rough memory traffic of one iteration of parallel.cpp, in bytes.
    Phase 1: read r (8N) + outdeg (4N), write c (8N).
    Phase 2: read in_offsets (8N) + in_src (4M) + c[in[k]] (8M, a random gather)
             + r (8N), write nr (8N).
    Total ~ 44N + 12M. A lower bound: it ignores cache misses that waste a line."""
    return 44 * n + 12 * m


# ---- sections -----------------------------------------------------------------
def s_system():
    print("### System configuration\n")
    path = os.path.join(RESULTS, "system_info.txt")
    if not need(path):
        return
    info = {}
    with open(path) as f:
        for line in f:
            if ":" in line:
                k, v = line.split(":", 1)
                info.setdefault(k.strip(), v.strip())
    keys = [("Machine type (cloud)", "machine_type"), ("CPU model", "Model name"),
            ("Sockets", "Socket(s)"), ("Physical cores per socket", "Core(s) per socket"),
            ("Hardware threads per core", "Thread(s) per core"), ("Logical CPUs", "CPU(s)"),
            ("NUMA nodes", "NUMA node(s)"), ("L1d cache", "L1d cache"), ("L2 cache", "L2 cache"),
            ("L3 cache", "L3 cache"), ("Memory", "memory"), ("Operating system", "os"),
            ("Kernel", "uname"), ("Compiler", "compiler"), ("Measured on", "date")]
    rows = [(label, info[k]) for label, k in keys if info.get(k)]
    try:
        phys = int(info["Socket(s)"]) * int(info["Core(s) per socket"])
        rows.insert(4, ("Physical cores (total)", phys))
    except (KeyError, ValueError):
        pass
    rows.append(("OpenMP binding", "OMP_PROC_BIND=close, OMP_PLACES=cores"))
    rows.append(("Build flags", "-O3 -march/-mcpu=native -std=c++17 -fopenmp"))
    table(["Item", "Value"], rows)


def s_datasets():
    print("### Datasets\n")
    names = sorted({os.path.basename(p)[:-4] for p in os.listdir(DATA)
                    if p.startswith("pr_") and p.endswith(".txt")}, key=dataset_sort_key) \
        if os.path.isdir(DATA) else []
    if not names:
        print(f"_no pr_*.txt graphs in {DATA}/ (set DATA=...)_\n")
        return
    rows = []
    for name in names:
        n, m = graph_header(name)
        indeg, outdeg = [0] * n, [0] * n
        with open(os.path.join(DATA, name + ".txt")) as f:
            header_seen = False
            for line in f:
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                if not header_seen:
                    header_seen = True
                    continue
                a, b = line.split()
                outdeg[int(a)] += 1
                indeg[int(b)] += 1
        top = sorted(indeg, reverse=True)[:max(1, n // 100)]
        kind, size = split_name(name)
        rows.append((name, "uniform" if kind == "u" else "skewed", SIZE_ROLE.get(size, ""),
                     f"{n:,}", f"{m:,}", f"{m / n:.1f}", f"{max(indeg):,}",
                     f"{100 * sum(top) / m:.1f}%", f"{sum(1 for d in outdeg if d == 0):,}",
                     f"{bytes_per_iter(n, m) / 2**20:.0f}"))
    table(["Graph", "Distribution", "Role", "Nodes N", "Edges M", "Avg degree",
           "Max in-degree", "Edges into top 1% nodes", "Dangling nodes",
           "Data touched / iter (MiB)"], rows)


def s_correctness():
    print("### Correctness: serial vs OpenMP ranks\n")
    path = os.path.join(RESULTS, "correctness.csv")
    if not need(path):
        return
    by = defaultdict(list)
    with open(path) as f:
        for r in csv.DictReader(f):
            by[r["dataset"]].append(r)
    rows = []
    for ds in sorted(by, key=dataset_sort_key):
        ref = next(r for r in by[ds] if r["result"] == "REF")
        par = [r for r in by[ds] if r["result"] != "REF"]
        worst = max(float(r["max_abs_diff_vs_serial"] or 0) for r in par)
        npass = sum(r["result"] == "PASS" for r in par)
        rows.append((ds, ref["iters"], ref["max_change"], ref["rank_sum"],
                     len(par), f"{npass}/{len(par)}", f"{worst:.1e}"))
    table(["Graph", "Iterations", "Final max change", "Rank sum (serial)",
           "OpenMP runs compared", "PASS", "Largest rank difference"], rows)
    print("_OpenMP runs: 1, 2, 4, 8, 16 threads × static, dynamic,64, edge-balanced; "
          "tolerance 1e-10._\n")


def s_convergence():
    print("### Convergence with the stopping rule (tol = 1e-10)\n")
    path = os.path.join(RESULTS, "convergence.csv")
    if not need(path):
        return
    with open(path) as f:
        rows = [r.split(",") for r in f.read().split("\n") if r.strip()]
    rows = [r for r in rows if r[0] != "impl"]
    table(["Version", "Graph", "Threads", "Schedule", "Iterations", "Final max change",
           "Rank sum", "Time (s)"],
          [(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7]) for r in rows])


def s_speedup():
    rows, serial, iters = timing_rows()
    if rows is None:
        return
    print(f"### Speedup and efficiency (median of runs, {'/'.join(sorted(iters))} iterations)\n")
    for ds in sorted({r["dataset"] for r in rows}, key=dataset_sort_key):
        get = {(r["version"], r["threads"]): r for r in rows if r["dataset"] == ds}
        ps = sorted({p for v, p in get if v in MAIN})
        print(f"**{ds}**: serial T1 = {fmt(serial.get(ds), '.4f')} s\n")
        out = []
        for p in ps:
            line = [p]
            for v in MAIN:
                r = get.get((v, p))
                line += [fmt(r and r["median_s"], ".4f"), fmt(r and r["speedup"], ".2f"),
                         fmt(r and r["efficiency"], ".2f")]
            out.append(line)
        hdr = ["P"]
        for v in MAIN:
            hdr += [f"{LABEL[v]} T (s)", "S", "E"]
        table(hdr, out)


def s_knee():
    rows, _, _ = timing_rows()
    if rows is None:
        return
    print("### Where adding threads stops helping\n")
    print("_Diminishing from = first P where doubling the threads gives less than "
          "20% more speedup (S(P) / S(P/2) < 1.2)._\n")
    out = []
    for ds in sorted({r["dataset"] for r in rows}, key=dataset_sort_key):
        for v in MAIN:
            pts = sorted((r["threads"], r) for r in rows
                         if r["dataset"] == ds and r["version"] == v and r["speedup"])
            if not pts:
                continue
            best_p, best = min(pts, key=lambda t: t[1]["median_s"])
            by_p = dict(pts)
            knee = next((p for p, r in pts if p // 2 in by_p
                         and r["speedup"] / by_p[p // 2]["speedup"] < 1.2), None)
            last_p, last = pts[-1]
            out.append((ds, LABEL[v], best_p, f"{best['speedup']:.2f}",
                        f"{last['speedup']:.2f} (P={last_p})",
                        f"{last['efficiency']:.2f}", knee or "not reached"))
    table(["Graph", "Version", "Fastest at P", "Best speedup", "Speedup at max P",
           "Efficiency at max P", "Diminishing from P"], out)


def s_karpflatt():
    rows, _, _ = timing_rows()
    if rows is None:
        return
    print("### Effective serial fraction (Karp–Flatt)\n")
    print("_e = (1/S − 1/P) / (1 − 1/P). Flat e: serial work in the algorithm. "
          "e rising with P: parallel overhead growing with P._\n")
    for ds in sorted({r["dataset"] for r in rows}, key=dataset_sort_key):
        get = {(r["version"], r["threads"]): r for r in rows if r["dataset"] == ds}
        ps = sorted({p for v, p in get if v in MAIN and p > 1})
        if not ps:
            continue
        out = [[p] + [fmt(get.get((v, p), {}).get("karp_flatt"), ".3f") for v in MAIN]
               for p in ps]
        trend = ["e(max P) − e(2)"]
        for v in MAIN:
            a, b = get.get((v, ps[0]), {}).get("karp_flatt"), get.get((v, ps[-1]), {}).get(
                "karp_flatt")
            trend.append(fmt(None if a is None or b is None else b - a, "+.3f"))
        out.append(trend)
        print(f"**{ds}**\n")
        table(["P"] + [LABEL[v] for v in MAIN], out)


def s_sweep():
    rows, _, _ = timing_rows()
    if rows is None:
        return
    print("### schedule(dynamic, chunk) sweep (median time, s)\n")
    chunks = defaultdict(dict)
    for r in rows:
        if r["version"].startswith("dynamic-"):
            chunks[(r["dataset"], r["threads"])][int(r["version"][8:])] = r["median_s"]
    swept = {k: v for k, v in chunks.items() if len(v) > 1}
    if not swept:
        print("_no chunk sweep runs yet_\n")
        return
    all_c = sorted(set().union(*(v.keys() for v in swept.values())))
    ref = {(r["dataset"], r["version"], r["threads"]): r["median_s"] for r in rows}
    out = []
    for (ds, p) in sorted(swept, key=lambda k: (dataset_sort_key(k[0]), k[1])):
        c = swept[(ds, p)]
        best = min(c, key=c.get)
        out.append([ds, p] + [fmt(c.get(x), ".4f") for x in all_c] +
                   [best, fmt(ref.get((ds, "static", p)), ".4f"),
                    fmt(ref.get((ds, "edge-balanced", p)), ".4f")])
    table(["Graph", "P"] + [f"chunk {x}" for x in all_c] +
          ["Best chunk", "static", "edge-balanced"], out)


def s_imbalance():
    print("### Load imbalance in the rank-update loop (per-thread busy time)\n")
    path = os.path.join(RESULTS, "thread_times.csv")
    if not need(path):
        return
    by = defaultdict(list)
    with open(path) as f:
        for r in csv.DictReader(f):
            by[(r["dataset"], r["schedule"], r["threads"], r["iters"])].append(r)
    out = []
    for (ds, sch, p, it), rs in sorted(by.items(), key=lambda kv: dataset_sort_key(kv[0][0])):
        busy = [float(r["busy_s"]) for r in rs]
        loop = float(rs[0]["loop_s"])
        mean = sum(busy) / len(busy)
        idle = sum(float(r["idle_s"]) for r in rs) / (loop * len(rs)) if loop else 0
        out.append((ds, LABEL.get(sch, sch.replace("-", ",")), p, it, f"{loop:.3f}",
                    f"{max(busy):.3f}", f"{mean:.3f}", f"{max(busy) / mean:.2f}",
                    f"{100 * idle:.0f}%"))
    table(["Graph", "Schedule", "P", "Iterations", "Loop time (s)", "Max busy (s)",
           "Mean busy (s)", "Max / mean", "Avg not-busy share"], out)
    print("_Busy = time a thread spends in its share of the rank-update loop. Not-busy = the "
          "rest of the timed loop: waiting at the barrier, plus phase 1 and fork/join in "
          "parallel.cpp. Max / mean = 1.00 means perfectly balanced._\n")


def s_bandwidth():
    rows, _, iters = timing_rows()
    if rows is None:
        return
    if len(iters) != 1:
        print("_mixed iteration counts in raw_timings.csv_\n")
        return
    it = int(next(iter(iters)))
    print(f"### Effective memory bandwidth (estimate, GB/s, {it} iterations)\n")
    print("_Bytes per iteration ≈ 44·N + 12·M (ranks, contributions, offsets, edge list "
          "and the random gather of c[in[k]]); GB/s = bytes × iterations / median time. "
          "A lower bound on real traffic._\n")
    out = []
    for ds in sorted({r["dataset"] for r in rows}, key=dataset_sort_key):
        hdr = graph_header(ds)
        if not hdr:
            continue
        b = bytes_per_iter(*hdr) * it
        get = {(r["version"], r["threads"]): r["median_s"] for r in rows if r["dataset"] == ds}
        ps = sorted({p for v, p in get if v in MAIN})
        for v in ["serial"] + MAIN:
            line = [ds, LABEL[v]]
            for p in ps:
                t = get.get((v, 1 if v == "serial" else p))
                line.append(fmt(t and b / t / 1e9, ".1f") if (v != "serial" or p == 1) else "")
            out.append(line)
        ps_hdr = ps
    if out:
        table(["Graph", "Version"] + [f"P={p}" for p in ps_hdr], out)
    else:
        print(f"_graph files not found in {DATA}/ (set DATA=...)_\n")


SECTIONS = {"system": s_system, "datasets": s_datasets, "correctness": s_correctness,
            "convergence": s_convergence, "speedup": s_speedup, "knee": s_knee,
            "karpflatt": s_karpflatt, "sweep": s_sweep, "imbalance": s_imbalance,
            "bandwidth": s_bandwidth}


def main():
    args = sys.argv[1:] or ["all"]
    if "all" in args:
        args = list(SECTIONS)
    bad = [a for a in args if a not in SECTIONS]
    if bad:
        sys.exit(f"unknown section(s): {', '.join(bad)}\n\n{__doc__}")
    for a in args:
        SECTIONS[a]()


if __name__ == "__main__":
    main()
