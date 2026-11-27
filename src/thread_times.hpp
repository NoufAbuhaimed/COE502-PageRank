// Optional per-thread busy-time profiling (build with -DPROFILE_THREADS).
// Each thread's busy time = time spent inside its share of the rank-update
// loop, summed over all iterations. Idle time = loop time - busy time, i.e.
// time spent waiting at the barrier for slower threads (load imbalance).
#pragma once

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

// One cache line per thread so threads don't share (false-share) a line.
struct alignas(64) PaddedDouble {
    double v = 0.0;
};

// Appends one row per thread to $THREAD_TIMES_CSV (default results/thread_times.csv)
// and prints a one-line summary to stderr.
inline void write_thread_times(const std::string &impl, const std::string &dataset,
                               const std::string &schedule, int iters, double loop_s,
                               const std::vector<PaddedDouble> &busy) {
    const char *env = std::getenv("THREAD_TIMES_CSV");
    std::string path = env ? env : "results/thread_times.csv";
    FILE *probe = std::fopen(path.c_str(), "r");
    bool new_file = (probe == nullptr);
    if (probe) std::fclose(probe);
    FILE *f = std::fopen(path.c_str(), "a");
    if (!f) {
        std::fprintf(stderr, "warning: cannot write %s\n", path.c_str());
        return;
    }
    if (new_file)
        std::fprintf(f, "impl,dataset,threads,schedule,iters,thread,busy_s,idle_s,loop_s\n");
    double sum = 0.0, mx = 0.0;
    const int P = static_cast<int>(busy.size());
    for (int t = 0; t < P; ++t) {
        double b = busy[t].v;
        sum += b;
        mx = std::max(mx, b);
        std::fprintf(f, "%s,%s,%d,%s,%d,%d,%.6f,%.6f,%.6f\n", impl.c_str(), dataset.c_str(), P,
                     schedule.c_str(), iters, t, b, std::max(0.0, loop_s - b), loop_s);
    }
    std::fclose(f);
    double mean = sum / P;
    std::fprintf(stderr, "[thread-times] %s %s P=%d %s: max/mean busy = %.2f\n", impl.c_str(),
                 dataset.c_str(), P, schedule.c_str(), mean > 0 ? mx / mean : 0.0);
}
