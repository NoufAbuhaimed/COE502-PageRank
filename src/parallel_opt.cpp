// COE 502 PageRank - optimized OpenMP version (extra experiment).
//
// Same algorithm, inputs and output as parallel.cpp, with three changes:
//
// 1. Edge-balanced static partition. Thread t owns a contiguous node range
//    chosen so every thread gets about the same work, where work(v) =
//    in-degree(v) + 1. On skewed graphs, schedule(static) splits by node
//    count, so the thread holding the high in-degree nodes does most of the
//    work. dynamic fixes that but pays a shared-counter cost per chunk.
//    This split is balanced with zero per-iteration scheduling cost.
//    (Computed once from in_offsets before timing, like the CSR itself.)
//
// 2. One parallel region for the whole run instead of 2 fork/joins per
//    iteration. Threads stay alive; one barrier + one `single` per iteration.
//
// 3. Fused phases. While writing new rank nr[v], the thread also writes
//    v's next contribution cn[v] = nr[v] / outdeg(v) and accumulates the next
//    dangling mass, so the separate contribution pass disappears. The
//    contribution array is double-buffered like the ranks.
//
// Per-thread partial results are padded to one cache line each to avoid
// false sharing.
#include <omp.h>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <vector>

#include "graph.hpp"
#include "thread_times.hpp"

// bounds[t] .. bounds[t+1] = nodes owned by thread t.
// Cumulative work up to node v is in_offsets[v] + v (monotonic), so each
// boundary is a binary search for the t/P fraction of total work.
static std::vector<int32_t> edge_balanced_bounds(const Graph &g, int P) {
    std::vector<int32_t> b(P + 1);
    const int64_t total = g.M + g.N;
    b[0] = 0;
    b[P] = g.N;
    for (int t = 1; t < P; ++t) {
        const int64_t target = total * t / P;
        int32_t lo = 0, hi = g.N;  // first v with in_offsets[v] + v >= target
        while (lo < hi) {
            int32_t mid = lo + (hi - lo) / 2;
            if (g.in_offsets[mid] + mid < target) lo = mid + 1;
            else hi = mid;
        }
        b[t] = std::max(lo, b[t - 1]);
    }
    return b;
}

int main(int argc, char **argv) {
    Options opt = parse_args(argc, argv, "parallel_opt");
    Graph g = load_graph(opt.graph_path);  // not timed

    const int32_t N = g.N;
    const double d = DAMPING;
    const int P = omp_get_max_threads();
    const std::vector<int32_t> bounds = edge_balanced_bounds(g, P);  // not timed

    std::vector<double> r_a(N), r_b(N), c_a(N), c_b(N);
    double *r = r_a.data(), *nr = r_b.data();  // ranks: old / new
    double *c = c_a.data(), *cn = c_b.data();  // contributions: old / new
    const int32_t *outdeg = g.out_degree.data();
    const int64_t *off = g.in_offsets.data();
    const int32_t *in = g.in_src.data();

    std::vector<PaddedDouble> part_mc(P), part_dang(P), busy(P);
    double dangling = 0.0;  // dangling mass of the current ranks
    int iters = 0;
    double max_change = 0.0;
    bool done = false;

    // Initial ranks and contributions; each thread touches its own range first.
#pragma omp parallel num_threads(P) reduction(+ : dangling)
    {
        const int t = omp_get_thread_num();
        for (int32_t v = bounds[t]; v < bounds[t + 1]; ++v) {
            r[v] = 1.0 / N;
            nr[v] = 0.0;
            cn[v] = 0.0;
            if (outdeg[v] > 0) c[v] = r[v] / outdeg[v];
            else { c[v] = 0.0; dangling += r[v]; }
        }
    }

    double t0 = omp_get_wtime();
#pragma omp parallel num_threads(P)
    {
        const int t = omp_get_thread_num();
        const int32_t lo = bounds[t], hi = bounds[t + 1];
        while (true) {
#ifdef PROFILE_THREADS
            double ts = omp_get_wtime();
#endif
            // All threads read the shared pointers/base set by the last `single`.
            const double base = (1.0 - d) / N + d * dangling / N;
            double mc = 0.0, dang_next = 0.0;
            for (int32_t v = lo; v < hi; ++v) {
                double s = 0.0;
                for (int64_t k = off[v]; k < off[v + 1]; ++k) s += c[in[k]];
                double val = base + d * s;
                double diff = std::fabs(val - r[v]);
                if (diff > mc) mc = diff;
                nr[v] = val;
                if (outdeg[v] > 0) cn[v] = val / outdeg[v];  // fused next contribution
                else { cn[v] = 0.0; dang_next += val; }
            }
            part_mc[t].v = mc;
            part_dang[t].v = dang_next;
#ifdef PROFILE_THREADS
            busy[t].v += omp_get_wtime() - ts;
#endif
#pragma omp barrier
#pragma omp single
            {
                double m = 0.0, dn = 0.0;
                for (int i = 0; i < P; ++i) {
                    m = std::max(m, part_mc[i].v);
                    dn += part_dang[i].v;
                }
                max_change = m;
                dangling = dn;
                std::swap(r, nr);
                std::swap(c, cn);
                ++iters;
                done = (iters >= opt.max_iters) || (opt.tol > 0.0 && max_change < opt.tol);
            }  // implicit barrier: everyone sees the swap and `done`
            if (done) break;
        }
    }
    double t1 = omp_get_wtime();

    std::vector<double> final_r(r, r + N);
    double sum = 0.0;
    for (int32_t v = 0; v < N; ++v) sum += final_r[v];

    std::printf("openmp_opt,%s,%d,edge-balanced,%d,%.6e,%.15f,%.6f\n",
                dataset_name(opt.graph_path).c_str(), P, iters, max_change, sum, t1 - t0);
    if (!opt.ranks_out.empty()) write_ranks(opt.ranks_out, final_r);
#ifdef PROFILE_THREADS
    write_thread_times("openmp_opt", dataset_name(opt.graph_path), "edge-balanced", iters, t1 - t0,
                       busy);
#endif
    return 0;
}
