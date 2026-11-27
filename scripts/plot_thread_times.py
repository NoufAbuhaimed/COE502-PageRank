#!/usr/bin/env python3
"""Plot per-thread busy vs idle time from results/thread_times.csv.

One panel per (dataset, version); one stacked bar per thread:
busy = time in its share of the update loop, idle = waiting at the barrier.

Usage: python3 scripts/plot_thread_times.py results/thread_times.csv plots/thread_imbalance.png
"""
import csv
import sys
from collections import OrderedDict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

LABELS = {"static": "static", "dynamic-64": "dynamic,64", "edge-balanced": "edge-balanced (opt)"}


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "results/thread_times.csv"
    out = sys.argv[2] if len(sys.argv) > 2 else "plots/thread_imbalance.png"
    groups = OrderedDict()
    with open(src) as f:
        for row in csv.DictReader(f):
            key = (row["dataset"], row["schedule"])
            groups.setdefault(key, []).append(row)

    datasets = list(OrderedDict.fromkeys(k[0] for k in groups))
    versions = list(OrderedDict.fromkeys(k[1] for k in groups))
    fig, axes = plt.subplots(len(datasets), len(versions), sharey="row",
                             figsize=(4.2 * len(versions), 3.2 * len(datasets)), squeeze=False)
    for i, ds in enumerate(datasets):
        for j, ver in enumerate(versions):
            ax = axes[i][j]
            rows = sorted(groups.get((ds, ver), []), key=lambda r: int(r["thread"]))
            if not rows:
                ax.axis("off")
                continue
            tids = [int(r["thread"]) for r in rows]
            busy = [float(r["busy_s"]) for r in rows]
            idle = [float(r["idle_s"]) for r in rows]
            loop = float(rows[0]["loop_s"])
            ratio = max(busy) / (sum(busy) / len(busy))
            ax.bar(tids, busy, color="#3b6fb6", label="busy")
            ax.bar(tids, idle, bottom=busy, color="#d9d9d9", label="idle (waiting)")
            ax.set_title(f"{ds} · {LABELS.get(ver, ver)}\nloop {loop:.2f} s · max/mean {ratio:.2f}",
                         fontsize=9)
            ax.set_xlabel("thread")
            ax.set_xticks(tids if len(tids) <= 16 else tids[::2])
            if j == 0:
                ax.set_ylabel("time (s)")
            ax.tick_params(labelsize=8)
    axes[0][0].legend(fontsize=8, loc="upper right")
    fig.suptitle("Per-thread busy vs idle time in the rank-update loop", fontsize=11)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
