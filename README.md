# COE 502 — OpenMP Parallel PageRank

Serial and OpenMP PageRank in C++ (d = 0.85, ranks start at 1/N, double-buffered ranks, dangling-node rank spread evenly over all nodes).

## Report workflow

Step-by-step, copy-paste guides from a fresh server to the finished report:
[Q1 speedup & efficiency](docs/Q1.md) (setup + benchmark) · [Q2 serial fraction](docs/Q2.md) ·
[Q3 architectural analysis](docs/Q3.md) · [Q4 plots](docs/Q4.md) · [Q5 final report](docs/Q5.md).
`uv run scripts/report_tables.py <section>` prints each report table as Markdown.

## Prerequisites

You need a C++17 compiler with OpenMP, `make`, `bash` and [uv](https://docs.astral.sh/uv/). Every Python script runs with `uv run scripts/<name>.py`; uv reads the dependencies listed at the top of each script (e.g. matplotlib) and installs them by itself, so no pip or system Python packages are needed.

**Automatic setup.** This script detects the platform, installs the packages and checks that the compiler can build OpenMP code:

```bash
./scripts/setup.sh
```

**Manual install**, by platform:

| Platform | Command |
| --- | --- |
| Ubuntu / Debian | `sudo apt-get install -y build-essential make curl && curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Fedora / RHEL | `sudo dnf install -y gcc-c++ make curl && curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Arch | `sudo pacman -S --needed gcc make uv` |
| macOS | `xcode-select --install && brew install libomp uv` |
| Windows (WSL2, recommended) | `wsl --install -d Ubuntu` in PowerShell, then use the Ubuntu command inside WSL |
| Windows (MSYS2 UCRT64 shell) | `pacman -S --needed make mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-uv` |

Notes:
- macOS uses Apple clang, which needs Homebrew's `libomp` and the special build command shown under **Build**.
- Native Windows with MSVC is not supported because the Makefile and scripts need `bash`. Use WSL2 or MSYS2.

## Build

```bash
make            # builds ./serial, ./parallel, ./parallel_opt (g++ -O3 -mcpu=native -fopenmp)
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
OMP_NUM_THREADS=16 OMP_SCHEDULE="dynamic,64" ./parallel /workspace/coe502/datasets/pr_s500k_5m.txt 500 0
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
uv run scripts/validate.py ranks_a.txt ranks_b.txt [tol]   # compare two rank files
```

## Timing experiments

```bash
make bench      # = ./scripts/benchmark.sh  -> results/raw_timings.csv, results/system_info.txt
make plots      # = uv run scripts/plot_results.py -> results/summary.csv, plots/*.png
```

`benchmark.sh` runs every configuration RUNS times (default 5) with a fixed ITERS (default 1000, tol = 0):

- **Main:** serial, plus `static`, `dynamic,64` and `edge-balanced` at 1, 2, 4, 8 and 16 threads, on all six graphs.
- **Chunk sweep:** `dynamic` with chunk 16, 64, 256, 1024 and 4096 at 8 and 16 threads, on `pr_s100k_1m` and `pr_s500k_5m`.

It is resumable. A run that is already in the CSV is skipped, so after a Spot VM stop you just run it again. If a stop cut the last line short, that line is dropped and the run is redone. The script refuses to mix iteration counts in one CSV.

Settings come from the environment: `RUNS`, `ITERS`, `THREADS`, `GRAPHS`, `SWEEP_GRAPHS`, `SWEEP_CHUNKS`, `SWEEP_THREADS`, `DATA` (graph folder, see Datasets), `OUT`.

`plot_results.py` takes the median of each configuration. It computes speedup (T1 = serial median), efficiency and the Karp–Flatt serial fraction, and writes:

- `plots/scaling_<graph>.png`
- `plots/speedup_overview.png`
- `plots/chunk_sweep.png`

## Extra experiments

**Optimized version (`parallel_opt`).** This uses an edge-balanced static split: each thread gets a contiguous node range with about the same number of in-edges. It runs one parallel region for the whole computation, and it fuses the contribution pass into the rank update. It produces the same CSV line (impl `openmp_opt`, schedule `edge-balanced`) and is covered by `make check`.

```bash
OMP_NUM_THREADS=16 ./parallel_opt /workspace/coe502/datasets/pr_s500k_5m.txt 500 0
```

**Load-imbalance profile.** This measures each thread's busy time vs time spent waiting at the barrier, for static, dynamic,64 and edge-balanced:

```bash
make imbalance          # builds *_prof binaries, writes results/thread_times.csv
                        # and plots/thread_imbalance.png (via uv)
THREADS=8 ITERS=100 ./scripts/imbalance.sh   # other settings
```

The `*_prof` binaries add timing calls, so use them only for the imbalance plot, not for the speedup tables.

## Datasets

The provided graphs (`pr_[u|s][N]_[M].txt`, about 160 MB) are not in Git. All scripts read them from one place, set in `scripts/data_dir.sh`:

| Machine | Graph folder |
| --- | --- |
| Course server | `/workspace/coe502/datasets` (used whenever it exists) |
| Our own machines | `../datasets`, next to the repo (unpack `dataset.zip` there) |

`DATA=<folder>` overrides both, e.g. `DATA=~/graphs make check`. The hand-made `tiny_dangling.txt` stays in the repo's `datasets/`.

| File | Nodes | Edges | Kind |
| --- | --- | --- | --- |
| tiny_dangling.txt (in repo) | 5 | 6 | hand-made, node 4 dangling |
| pr_u10k_100k.txt / pr_s10k_100k.txt | 10,000 | 100,000 | uniform / skewed |
| pr_u100k_1m.txt / pr_s100k_1m.txt | 100,000 | 1,000,000 | uniform / skewed |
| pr_u500k_5m.txt / pr_s500k_5m.txt | 500,000 | 5,000,000 | uniform / skewed |

## Layout

```
src/        graph.hpp/.cpp (loader + incoming CSR), serial.cpp, parallel.cpp,
            parallel_opt.cpp (optimized extra), thread_times.hpp (profiling)
scripts/    setup.sh (prerequisites), validate.py, correctness.sh, imbalance.sh, plot_thread_times.py,
            benchmark.sh, plot_results.py, report_tables.py
docs/       Q1.md - Q5.md (report steps)
datasets/   tiny_dangling.txt (provided graphs: /workspace/coe502/datasets or ../datasets)
results/    correctness.csv, convergence.csv, thread_times.csv,
            raw_timings.csv + system_info.txt (benchmark.sh), summary.csv (plot_results.py)
plots/      thread_imbalance.png, scaling_<graph>.png, speedup_overview.png, chunk_sweep.png
```
