#!/usr/bin/env python3
"""Compare two rank files written by serial/parallel (lines: "node rank").

Usage: python3 scripts/validate.py ranks_serial.txt ranks_parallel.txt [tolerance]
Exit code 0 = match within tolerance (default 1e-12), 1 = mismatch.
"""
import sys


def load(path):
    ranks = {}
    with open(path) as f:
        for line in f:
            parts = line.split()
            if len(parts) == 2:
                ranks[int(parts[0])] = float(parts[1])
    return ranks


def main():
    if len(sys.argv) not in (3, 4):
        print(__doc__)
        sys.exit(2)
    a, b = load(sys.argv[1]), load(sys.argv[2])
    tol = float(sys.argv[3]) if len(sys.argv) == 4 else 1e-12
    if a.keys() != b.keys():
        print(f"FAIL: node sets differ ({len(a)} vs {len(b)} nodes)")
        sys.exit(1)
    worst_node, worst = max(((v, abs(a[v] - b[v])) for v in a), key=lambda t: t[1])
    ok = worst <= tol
    print(f"{'PASS' if ok else 'FAIL'}: nodes={len(a)} max_abs_diff={worst:.3e} "
          f"(node {worst_node}) tol={tol:.0e} sum_a={sum(a.values()):.15f} "
          f"sum_b={sum(b.values()):.15f}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
