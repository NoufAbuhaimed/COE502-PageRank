// COE 502 PageRank - serial baseline.
//
// This is the reference for correctness (the OpenMP ranks are compared to its
// ranks) and for speed (T1 in speedup = T1 / Tp). See docs/algorithm.md.
//
// Each iteration computes, for every node v:
//
//   PR_{t+1}(v) = (1-d)/N + d * D_t/N + d * sum_{u in In(v)} PR_t(u) / outdeg(u)
//
//   d   = 0.85 (damping)
//   D_t = total rank held by dangling nodes (out-degree 0). They have no links
//         to pass their rank along, so it is spread evenly over all N nodes.
//         Without this term the rank sum would drop below 1 every iteration.
//
// Double-buffered: every update in iteration t reads only the old ranks (r)
// and writes only the new ranks (nr). Then the two buffers swap.
//
// Output (one CSV line on stdout):
//   impl,dataset,threads,schedule,iters,max_change,rank_sum,time_s
#include <omp.h>  // only for omp_get_wtime(); this file has no OpenMP pragmas

#include <cmath>
#include <cstdio>
#include <vector>

#include "graph.hpp"

int main(int argc, char **argv) {
    Options opt = parse_args(argc, argv, "serial");
    Graph g = load_graph(opt.graph_path);  // file I/O + CSR build: not timed

    const int32_t N = g.N;
    const double d = DAMPING;
    // r = ranks of iteration t (start at 1/N), nr = ranks of iteration t+1,
    // c = contribution each node sends along each of its out-links.
    std::vector<double> old_r(N, 1.0 / N), next_r(N), contrib(N);
    double *r = old_r.data(), *nr = next_r.data(), *c = contrib.data();
    const int32_t *outdeg = g.out_degree.data();
    const int64_t *off = g.in_offsets.data();
    const int32_t *in = g.in_src.data();

    int iters = 0;
    double max_change = 0.0;

    double t0 = omp_get_wtime();  // ---- timed region starts ----
    while (iters < opt.max_iters) {
        // Phase 1: what each node sends per out-link, c[u] = PR(u) / outdeg(u).
        // Dangling nodes send nothing; their rank is added up in `dangling`.
        double dangling = 0.0;
        for (int32_t u = 0; u < N; ++u) {
            if (outdeg[u] > 0) {
                c[u] = r[u] / outdeg[u];
            } else {
                c[u] = 0.0;
                dangling += r[u];
            }
        }
        // The part of the formula that is the same for every node.
        const double base = (1.0 - d) / N + d * dangling / N;

        // Phase 2: each node pulls the contributions of the nodes that link to it.
        // Also track the largest change of any rank, for the stopping test.
        max_change = 0.0;
        for (int32_t v = 0; v < N; ++v) {
            double s = 0.0;
            for (int64_t k = off[v]; k < off[v + 1]; ++k) s += c[in[k]];
            double val = base + d * s;
            double diff = std::fabs(val - r[v]);
            if (diff > max_change) max_change = diff;
            nr[v] = val;
        }

        double *tmp = r; r = nr; nr = tmp;  // swap buffers: new ranks become the old ones
        ++iters;
        // Convergence run: stop once no rank moved more than tol.
        // Timing run (tol <= 0): never stop early, always do max_iters.
        if (opt.tol > 0.0 && max_change < opt.tol) break;
    }
    double t1 = omp_get_wtime();  // ---- timed region ends ----

    // Sanity check reported in the output: the ranks should still sum to ~1.0.
    std::vector<double> final_r(r, r + N);
    double sum = 0.0;
    for (int32_t v = 0; v < N; ++v) sum += final_r[v];

    std::printf("serial,%s,1,none,%d,%.6e,%.15f,%.6f\n",
                dataset_name(opt.graph_path).c_str(), iters, max_change, sum, t1 - t0);
    if (!opt.ranks_out.empty()) write_ranks(opt.ranks_out, final_r);
    return 0;
}
