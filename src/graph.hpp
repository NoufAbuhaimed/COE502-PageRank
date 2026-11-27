// COE 502 PageRank - shared pieces used by all three programs:
// the graph structure, the edge-list loader, command-line parsing and output.
// See docs/graph-format.md for the file format and the CSR layout.
#pragma once

#include <cstdint>
#include <string>
#include <vector>

// Directed graph stored as incoming adjacency in CSR form (compressed sparse row).
//
// PageRank needs, for every node v, the list of nodes that link TO v. CSR keeps
// all those lists back to back in one array, in_src, and in_offsets says where
// each node's list starts:
//
//   in-neighbours of v = in_src[in_offsets[v] .. in_offsets[v+1])
//   in-degree of v     = in_offsets[v+1] - in_offsets[v]
//
// Example (tiny_dangling.txt): edges 0->1 0->2 1->2 2->0 3->2 3->4
//   in_offsets = [0, 1, 2, 5, 5, 6]
//   in_src     = [2 | 0 | 0 1 3 | | 3]      (node 3 has no in-edges)
//   out_degree = [2, 1, 1, 2, 0]            (node 4 is dangling)
struct Graph {
    int32_t N = 0;                   // number of nodes, ids 0 .. N-1
    int64_t M = 0;                   // number of directed edges
    std::vector<int32_t> out_degree; // out_degree[u] = edges leaving u (0 = dangling node)
    std::vector<int64_t> in_offsets; // size N + 1; in_offsets[N] == M
    std::vector<int32_t> in_src;     // size M; source node of each incoming edge, grouped by target
};

// Reads the course edge-list format:
//   lines starting with '#' are comments (blank lines are skipped too),
//   first non-comment line: N M,
//   then M lines "src dst" with 0 <= id < N.
// Exits with an error message on malformed input (bad header, id out of
// range, or an edge count that doesn't match M).
Graph load_graph(const std::string &path);

// Command-line settings, the same for serial, parallel and parallel_opt:
//   <prog> <graph> <max_iters> <tol> [ranks_out]
struct Options {
    std::string graph_path;
    int max_iters = 100;
    double tol = 1e-10;      // tol > 0: stop when max change < tol (convergence run)
                             // tol <= 0: run exactly max_iters (timing run)
    std::string ranks_out;   // optional: write final ranks here, one "node rank" per line
};

constexpr double DAMPING = 0.85;  // d in the PageRank formula (fixed by the assignment)

Options parse_args(int argc, char **argv, const char *prog);

// "/workspace/coe502/datasets/pr_s500k_5m.txt" -> "pr_s500k_5m" (used as the dataset column in the CSV output).
std::string dataset_name(const std::string &path);

// Writes "node rank" lines with full double precision, for scripts/validate.py.
void write_ranks(const std::string &path, const std::vector<double> &r);
