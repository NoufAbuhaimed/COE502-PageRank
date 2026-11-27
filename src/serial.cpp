// COE 502 PageRank - serial baseline.
//
//   PR_{t+1}(v) = (1-d)/N + d * D_t/N + d * sum_{u in In(v)} PR_t(u) / outdeg(u)
//
// D_t = total rank of dangling nodes (out-degree 0), spread evenly over all
// nodes so the rank sum stays 1. Double-buffered: reads `old`, writes `next`.
//
// Output (one CSV line on stdout):
//   impl,dataset,threads,schedule,iters,max_change,rank_sum,time_s
#include <omp.h>

#include <cmath>
#include <cstdio>
#include <vector>

#include "graph.hpp"

int main(int argc, char **argv) {
    Options opt = parse_args(argc, argv, "serial");
    Graph g = load_graph(opt.graph_path);  // not timed

    const int32_t N = g.N;
    const double d = DAMPING;
    std::vector<double> old_r(N, 1.0 / N), next_r(N), contrib(N);
    double *r = old_r.data(), *nr = next_r.data(), *c = contrib.data();
    const int32_t *outdeg = g.out_degree.data();
    const int64_t *off = g.in_offsets.data();
    const int32_t *in = g.in_src.data();

    int iters = 0;
    double max_change = 0.0;

    double t0 = omp_get_wtime();
    while (iters < opt.max_iters) {
        // Phase 1: per-node contribution and dangling mass.
        double dangling = 0.0;
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
        max_change = 0.0;
        for (int32_t v = 0; v < N; ++v) {
            double s = 0.0;
            for (int64_t k = off[v]; k < off[v + 1]; ++k) s += c[in[k]];
            double val = base + d * s;
            double diff = std::fabs(val - r[v]);
            if (diff > max_change) max_change = diff;
            nr[v] = val;
        }

        double *tmp = r; r = nr; nr = tmp;  // swap buffers
        ++iters;
        if (opt.tol > 0.0 && max_change < opt.tol) break;
    }
    double t1 = omp_get_wtime();

    std::vector<double> final_r(r, r + N);
    double sum = 0.0;
    for (int32_t v = 0; v < N; ++v) sum += final_r[v];

    std::printf("serial,%s,1,none,%d,%.6e,%.15f,%.6f\n",
                dataset_name(opt.graph_path).c_str(), iters, max_change, sum, t1 - t0);
    if (!opt.ranks_out.empty()) write_ranks(opt.ranks_out, final_r);
    return 0;
}
