// COE 502 PageRank - graph loading and incoming-CSR construction.
#pragma once

#include <cstdint>
#include <string>
#include <vector>

// Directed graph stored as incoming adjacency (CSR):
//   in-neighbours of v are in_src[in_offsets[v] .. in_offsets[v+1])
struct Graph {
    int32_t N = 0;                   // number of nodes
    int64_t M = 0;                   // number of edges
    std::vector<int32_t> out_degree; // out-degree of each node
    std::vector<int64_t> in_offsets; // size N + 1
    std::vector<int32_t> in_src;     // size M
};

// Reads the course edge-list format:
//   lines starting with '#' are comments,
//   first non-comment line: N M,
//   then M lines "src dst" with 0 <= id < N.
// Exits with an error message on malformed input.
Graph load_graph(const std::string &path);

// Common settings and helpers shared by the serial and OpenMP programs.
struct Options {
    std::string graph_path;
    int max_iters = 100;
    double tol = 1e-10;      // tol <= 0: run exactly max_iters (timing mode)
    std::string ranks_out;   // optional: write final ranks here
};

constexpr double DAMPING = 0.85;

Options parse_args(int argc, char **argv, const char *prog);
std::string dataset_name(const std::string &path);
void write_ranks(const std::string &path, const std::vector<double> &r);
