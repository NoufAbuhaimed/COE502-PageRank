// COE 502 PageRank - OpenMP version.
//
// Same algorithm and output as serial.cpp. Both phases use work-sharing:
//   - Phase 1 (contributions): uniform cost per node -> schedule(static),
//     reduction(+) for the dangling mass.
//   - Phase 2 (pull update): cost ~ in-degree, very uneven on skewed graphs
//     -> schedule(runtime), so OMP_SCHEDULE picks static / dynamic,chunk
//     without recompiling; reduction(max) for the convergence check.
// The implicit barrier at the end of each loop is the iteration-boundary sync.
//
// Thread count: OMP_NUM_THREADS. Schedule: OMP_SCHEDULE (e.g. "static",
// "dynamic,64"). Pin with OMP_PROC_BIND=close OMP_PLACES=cores.
#include <omp.h>

#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

#include "graph.hpp"

static std::string schedule_label() {
    omp_sched_t kind;
    int chunk;
    omp_get_schedule(&kind, &chunk);
    std::string name;
    switch (kind & ~omp_sched_monotonic) {
        case omp_sched_static: name = "static"; break;
        case omp_sched_dynamic: name = "dynamic"; break;
        case omp_sched_guided: name = "guided"; break;
        default: name = "auto"; break;
    }
    if (chunk > 0 && !(name == "static" && chunk == 0)) name += "-" + std::to_string(chunk);
    return name;
}

int main(int argc, char **argv) {
    Options opt = parse_args(argc, argv, "parallel");
    Graph g = load_graph(opt.graph_path);  // not timed

    const int32_t N = g.N;
    const double d = DAMPING;
    std::vector<double> old_r(N), next_r(N), contrib(N);
    double *r = old_r.data(), *nr = next_r.data(), *c = contrib.data();
    const int32_t *outdeg = g.out_degree.data();
    const int64_t *off = g.in_offsets.data();
    const int32_t *in = g.in_src.data();

    // Initialise in parallel (first touch places pages near the threads that use them).
#pragma omp parallel for schedule(static)
    for (int32_t v = 0; v < N; ++v) {
        r[v] = 1.0 / N;
        nr[v] = 0.0;
        c[v] = 0.0;
    }

    int iters = 0;
    double max_change = 0.0;

    double t0 = omp_get_wtime();
    while (iters < opt.max_iters) {
        // Phase 1: per-node contribution and dangling mass.
        double dangling = 0.0;
#pragma omp parallel for schedule(static) reduction(+ : dangling)
        for (int32_t u = 0; u < N; ++u) {
            if (outdeg[u] > 0) {
                c[u] = r[u] / outdeg[u];
            } else {
                c[u] = 0.0;
                dangling += r[u];
            }
        }
        const double base = (1.0 - d) / N + d * dangling / N;

        // Phase 2: pull from in-neighbours; track max absolute change.
        double mc = 0.0;
#pragma omp parallel for schedule(runtime) reduction(max : mc)
        for (int32_t v = 0; v < N; ++v) {
            double s = 0.0;
            for (int64_t k = off[v]; k < off[v + 1]; ++k) s += c[in[k]];
            double val = base + d * s;
            double diff = std::fabs(val - r[v]);
            if (diff > mc) mc = diff;
            nr[v] = val;
        }
        max_change = mc;

        double *tmp = r; r = nr; nr = tmp;  // swap buffers
        ++iters;
        if (opt.tol > 0.0 && max_change < opt.tol) break;
    }
    double t1 = omp_get_wtime();

    std::vector<double> final_r(r, r + N);
    double sum = 0.0;
    for (int32_t v = 0; v < N; ++v) sum += final_r[v];

    std::printf("openmp,%s,%d,%s,%d,%.6e,%.15f,%.6f\n",
                dataset_name(opt.graph_path).c_str(), omp_get_max_threads(),
                schedule_label().c_str(), iters, max_change, sum, t1 - t0);
    if (!opt.ranks_out.empty()) write_ranks(opt.ranks_out, final_r);
    return 0;
}
