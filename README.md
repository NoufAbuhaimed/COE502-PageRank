# COE 502 — OpenMP Parallel PageRank

Serial and OpenMP PageRank in C++ (d = 0.85, ranks start at 1/N, double-buffered ranks, dangling-node rank spread evenly over all nodes).

## Build

```bash
make            # builds ./serial and ./parallel (g++ -O3 -mcpu=native -fopenmp)
make clean
```

On macOS (Apple clang + Homebrew libomp), for local testing only:

```bash
make OMPFLAGS="-Xpreprocessor -fopenmp -I$(brew --prefix libomp)/include -L$(brew --prefix libomp)/lib -lomp" CPUFLAG=
```

## Run

```bash
./serial   <graph> <max_iters> <tol> [ranks_out]
./parallel <graph> <max_iters> <tol> [ranks_out]
```

- `tol > 0`: stop when the max absolute rank change < `tol` or after `max_iters` (convergence runs).
- `tol <= 0`: run exactly `max_iters` iterations (timing runs).
- `ranks_out`: optional file of final ranks (`node rank`).

OpenMP settings come from the environment:

```bash
export OMP_PROC_BIND=close OMP_PLACES=cores
OMP_NUM_THREADS=16 OMP_SCHEDULE="dynamic,64" ./parallel datasets/pr_s500k_5m.txt 500 0
```

Each run prints one CSV line:

```
impl,dataset,threads,schedule,iters,max_change,rank_sum,time_s
```

`time_s` is measured with `omp_get_wtime()` around the iteration loop only. File reading and graph construction are not timed.

## Correctness

```bash
make check      # serial vs OpenMP on tiny_dangling + both 10k graphs,
                # 1/2/4/8/16 threads, static and dynamic,64 -> results/correctness.csv
python3 scripts/validate.py ranks_a.txt ranks_b.txt [tol]   # compare two rank files
```

## Datasets

The provided graphs (`pr_[u|s][N]_[M].txt`) are not in Git (about 160 MB). Put them in `datasets/`. On the shared server they live in `/workspace/coe502/datasets`.

| File | Nodes | Edges | Kind |
| --- | --- | --- | --- |
| tiny_dangling.txt (in repo) | 5 | 6 | hand-made, node 4 dangling |
| pr_u10k_100k.txt / pr_s10k_100k.txt | 10,000 | 100,000 | uniform / skewed |
| pr_u100k_1m.txt / pr_s100k_1m.txt | 100,000 | 1,000,000 | uniform / skewed |
| pr_u500k_5m.txt / pr_s500k_5m.txt | 500,000 | 5,000,000 | uniform / skewed |

## Layout

```
src/        graph.hpp/.cpp (loader + incoming CSR), serial.cpp, parallel.cpp
scripts/    validate.py, correctness.sh (A); benchmark.sh, plot_results.py (B)
datasets/   tiny_dangling.txt (+ provided graphs, not in Git)
results/    correctness.csv, raw_timings.csv, system_info.txt
plots/      runtime, speedup, efficiency, scheduling
report/
```
