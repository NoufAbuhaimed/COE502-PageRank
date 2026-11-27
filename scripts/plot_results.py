#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["matplotlib"]
# ///
"""Turn results/raw_timings.csv (from benchmark.sh) into the report's tables and plots.

For every (dataset, version, threads) it takes the median of the runs, then:
  speedup     S_p = T1 / T_p        T1 = median time of the serial program
  efficiency  E_p = S_p / p
  Karp-Flatt  e_p = (1/S_p - 1/p) / (1 - 1/p)   (p > 1; effective serial fraction)

A Karp-Flatt value that stays flat as p grows points to serial work in the
algorithm. One that rises with p points to parallel overhead: barriers,
reductions, scheduling, memory bandwidth.

Writes:
  results/summary.csv              one row per configuration (all numbers above)
  plots/scaling_<dataset>.png      time, speedup, efficiency, Karp-Flatt vs threads
  plots/speedup_overview.png       speedup for all six graphs, uniform vs skewed
  plots/chunk_sweep.png            dynamic chunk size sweep (skewed graphs)

Usage: uv run scripts/plot_results.py [results/raw_timings.csv] [plots_dir]
"""
import csv
import os
import sys
from collections import defaultdict
from statistics import median

import matplotlib

matplotlib.use("Agg")  # no display needed (runs on the server)
import matplotlib.pyplot as plt  # noqa: E402

# The three parallel versions of the main experiment, in plotting order.
MAIN = ["static", "dynamic-64", "edge-balanced"]
STYLE = {
    "static": dict(color="#c0504d", marker="o", label="static"),
    "dynamic-64": dict(color="#4f81bd", marker="s", label="dynamic,64"),
    "edge-balanced": dict(color="#2e8b57", marker="^", label="edge-balanced (opt)"),
}
SIZE_ORDER = ["10k_100k", "100k_1m", "500k_5m"]


def split_name(ds):
    """pr_u10k_100k -> ('u', '10k_100k'); other names -> ('', name)."""
    if ds.startswith("pr_") and len(ds) > 4:
        return ds[3], ds[4:]
    return "", ds


def dataset_sort_key(ds):
    # Small -> large, uniform before skewed.
    kind, size = split_name(ds)
    return (SIZE_ORDER.index(size) if size in SIZE_ORDER else 99, kind != "u", ds)


def version_sort_key(v):
    # serial, the three main versions, then the chunk sweep by chunk size.
    if v == "serial":
        return (0, 0)
    if v in MAIN:
        return (1, MAIN.index(v))
    return (2, chunk_of(v)) if v.startswith("dynamic-") else (3, 0)


def chunk_of(version):
    return int(version.split("-")[1])


def load(path):
    """Group run times by (dataset, version, threads). Malformed rows are skipped."""
    times = defaultdict(list)
    with open(path) as f:
        for row in csv.DictReader(f):
            try:
                key = (row["dataset"], row["version"], int(row["threads"]))
                times[key].append(float(row["time_s"]))
            except (KeyError, TypeError, ValueError):
                continue
    return times


def summarize(times):
    """Median per configuration + speedup / efficiency / Karp-Flatt vs the serial median."""
    serial = {ds: median(t) for (ds, v, _), t in times.items() if v == "serial"}
    rows = []
    for (ds, v, p), t in sorted(times.items(), key=lambda kv: (dataset_sort_key(kv[0][0]),
                                                                version_sort_key(kv[0][1]),
                                                                kv[0][2])):
        med = median(t)
        r = dict(dataset=ds, version=v, threads=p, runs=len(t), median_s=med,
                 min_s=min(t), max_s=max(t), speedup=None, efficiency=None, karp_flatt=None)
        if ds in serial and med > 0:
            s = serial[ds] / med
            r["speedup"], r["efficiency"] = s, s / p
            if p > 1:
                r["karp_flatt"] = (1 / s - 1 / p) / (1 - 1 / p)
        rows.append(r)
    return rows, serial


def write_summary(rows, path):
    cols = ["dataset", "version", "threads", "runs", "median_s", "min_s", "max_s",
            "speedup", "efficiency", "karp_flatt"]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if r[c] is None else (f"{r[c]:.6g}" if isinstance(r[c], float) else r[c])
                        for c in cols])
    print(f"wrote {path}")


def series(rows, ds, version, field):
    pts = sorted((r["threads"], r[field]) for r in rows
                 if r["dataset"] == ds and r["version"] == version and r[field] is not None)
    return [p for p, _ in pts], [y for _, y in pts]


def plot_scaling(rows, serial, ds, out):
    """Four panels for one dataset: time, speedup, efficiency, Karp-Flatt vs threads."""
    fig, ax = plt.subplots(1, 4, figsize=(17, 3.8))
    all_p = set()
    for v in MAIN:
        p, t = series(rows, ds, v, "median_s")
        if not p:
            continue
        all_p.update(p)
        ax[0].plot(p, t, **STYLE[v])
        for i, field in enumerate(["speedup", "efficiency", "karp_flatt"], start=1):
            pp, y = series(rows, ds, v, field)
            if pp:
                ax[i].plot(pp, y, **STYLE[v])
    ps = sorted(all_p)
    if ds in serial:
        ax[0].axhline(serial[ds], color="gray", ls="--", lw=1, label="serial")
    if ps:
        ax[1].plot(ps, ps, color="gray", ls="--", lw=1, label="ideal")
        ax[2].axhline(1.0, color="gray", ls="--", lw=1, label="ideal")
    titles = ["Execution time (median)", "Speedup  T1/Tp", "Efficiency  Sp/p",
              "Karp–Flatt serial fraction"]
    ylabels = ["time (s)", "speedup", "efficiency", "e"]
    for a, title, yl in zip(ax, titles, ylabels):
        a.set_title(title, fontsize=10)
        a.set_xlabel("threads")
        a.set_ylabel(yl)
        a.set_xscale("log", base=2)
        if ps:
            a.set_xticks(ps)
            a.set_xticklabels(ps)
        a.grid(alpha=0.3)
        a.legend(fontsize=8)
    ax[0].set_yscale("log")
    ax[2].set_ylim(bottom=0)
    fig.suptitle(ds, fontsize=12)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"wrote {out}")


def plot_overview(rows, datasets, out):
    """Speedup for every graph on one page: columns = size, rows = uniform / skewed."""
    grid = {split_name(ds): ds for ds in datasets if ds.startswith("pr_")}
    sizes = [s for s in SIZE_ORDER if any(k[1] == s for k in grid)]
    if not sizes:
        return
    fig, ax = plt.subplots(2, len(sizes), figsize=(4.5 * len(sizes), 7), squeeze=False,
                           sharey=True)
    for i, kind in enumerate(["u", "s"]):
        for j, size in enumerate(sizes):
            a = ax[i][j]
            ds = grid.get((kind, size))
            if not ds:
                a.axis("off")
                continue
            ps = set()
            for v in MAIN:
                p, s = series(rows, ds, v, "speedup")
                if p:
                    a.plot(p, s, **STYLE[v])
                    ps.update(p)
            ps = sorted(ps)
            if ps:
                a.plot(ps, ps, color="gray", ls="--", lw=1, label="ideal")
                a.set_xscale("log", base=2)
                a.set_xticks(ps)
                a.set_xticklabels(ps)
            a.set_title(ds, fontsize=10)
            a.set_xlabel("threads")
            if j == 0:
                a.set_ylabel(("uniform" if kind == "u" else "skewed") + " — speedup")
            a.grid(alpha=0.3)
    ax[0][0].legend(fontsize=8)
    fig.suptitle("Speedup vs threads: uniform (top) and skewed (bottom)", fontsize=12)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"wrote {out}")


def plot_chunk_sweep(rows, out):
    """Median time vs dynamic chunk size, one panel per graph, one line per thread count.
    Dotted lines show static and edge-balanced at the same thread counts for reference."""
    sweep = [r for r in rows if r["version"].startswith("dynamic-")]
    chunks_at = defaultdict(set)  # (dataset, threads) -> chunk sizes measured
    for r in sweep:
        chunks_at[(r["dataset"], r["threads"])].add(chunk_of(r["version"]))
    # Only (graph, P) pairs with several chunk sizes are part of the sweep;
    # dynamic-64 alone at P=1..4 comes from the main experiment.
    swept = {k for k, c in chunks_at.items() if len(c) > 1}
    graphs = sorted({ds for ds, _ in swept}, key=dataset_sort_key)
    if not graphs:
        return
    fig, ax = plt.subplots(1, len(graphs), figsize=(5.5 * len(graphs), 4), squeeze=False)
    colors = ["#4f81bd", "#9bbb59", "#8064a2", "#f79646"]
    for a, ds in zip(ax[0], graphs):
        threads = sorted(p for d, p in swept if d == ds)
        for k, p in enumerate(threads):
            pts = sorted((chunk_of(r["version"]), r["median_s"]) for r in sweep
                         if r["dataset"] == ds and r["threads"] == p)
            col = colors[k % len(colors)]
            a.plot([c for c, _ in pts], [t for _, t in pts], marker="o", color=col,
                   label=f"dynamic, P={p}")
            for v, ls in (("static", ":"), ("edge-balanced", "-.")):
                ref = [r["median_s"] for r in rows if r["dataset"] == ds
                       and r["version"] == v and r["threads"] == p]
                if ref:
                    a.axhline(ref[0], color=col, ls=ls, lw=1, label=f"{v}, P={p}")
        a.set_xscale("log", base=2)
        chunks = sorted(set().union(*(chunks_at[(ds, p)] for p in threads)))
        a.set_xticks(chunks)
        a.set_xticklabels(chunks)
        a.set_title(ds, fontsize=10)
        a.set_xlabel("chunk size")
        a.set_ylabel("time (s)")
        a.grid(alpha=0.3)
        a.legend(fontsize=7)
    fig.suptitle("schedule(dynamic, chunk): balancing vs scheduling overhead", fontsize=11)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"wrote {out}")


def print_table(rows, datasets):
    """Console table for the report: median time / speedup / efficiency per thread count."""
    for ds in datasets:
        print(f"\n{ds}")
        print(f"  {'version':<15}{'P':>4}{'runs':>6}{'median s':>11}{'speedup':>9}"
              f"{'eff':>7}{'K-F e':>8}")
        for r in rows:
            if r["dataset"] != ds or not (r["version"] in MAIN or r["version"] == "serial"):
                continue
            f = lambda x, fmt: (fmt % x) if x is not None else "-"  # noqa: E731
            print(f"  {r['version']:<15}{r['threads']:>4}{r['runs']:>6}{r['median_s']:>11.4f}"
                  f"{f(r['speedup'], '%9.2f'):>9}{f(r['efficiency'], '%7.2f'):>7}"
                  f"{f(r['karp_flatt'], '%8.3f'):>8}")


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "results/raw_timings.csv"
    plots = sys.argv[2] if len(sys.argv) > 2 else "plots"
    times = load(src)
    if not times:
        sys.exit(f"no runs in {src}")
    rows, serial = summarize(times)
    datasets = sorted({r["dataset"] for r in rows}, key=dataset_sort_key)
    missing = [ds for ds in datasets if ds not in serial]
    if missing:
        print(f"warning: no serial runs for {', '.join(missing)}: no speedup for those")

    os.makedirs(plots, exist_ok=True)
    write_summary(rows, os.path.join(os.path.dirname(src) or ".", "summary.csv"))
    for ds in datasets:
        plot_scaling(rows, serial, ds, os.path.join(plots, f"scaling_{ds}.png"))
    plot_overview(rows, datasets, os.path.join(plots, "speedup_overview.png"))
    plot_chunk_sweep(rows, os.path.join(plots, "chunk_sweep.png"))
    print_table(rows, datasets)


if __name__ == "__main__":
    main()
