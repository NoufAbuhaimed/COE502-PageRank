// COE 502 PageRank - graph loading and incoming-CSR construction.
//
// Everything here runs serially, before the timer starts, so it is NOT part
// of the measured time (the assignment says not to time or parallelize I/O).
#include "graph.hpp"

#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>

[[noreturn]] static void die(const std::string &msg) {
    std::fprintf(stderr, "error: %s\n", msg.c_str());
    std::exit(1);
}

// Read the whole file into memory in one go. Parsing a buffer by hand is much
// faster than calling fscanf 5 million times on the large graphs.
// The extra '\0' at the end lets the parser stop without length checks.
static std::vector<char> read_file(const std::string &path) {
    FILE *f = std::fopen(path.c_str(), "rb");
    if (!f) die("cannot open " + path + ": " + std::strerror(errno));
    std::fseek(f, 0, SEEK_END);
    long size = std::ftell(f);
    std::fseek(f, 0, SEEK_SET);
    std::vector<char> buf(static_cast<size_t>(size) + 1);
    if (size > 0 && std::fread(buf.data(), 1, size, f) != static_cast<size_t>(size))
        die("cannot read " + path);
    std::fclose(f);
    buf[size] = '\0';
    return buf;
}

// Parse the next non-negative integer on the current line and move p past it.
// Returns false if the line has no more numbers (end of line or a non-digit).
static bool next_int(const char *&p, int64_t &out) {
    while (*p == ' ' || *p == '\t' || *p == '\r') ++p;
    if (*p < '0' || *p > '9') return false;
    int64_t v = 0;
    while (*p >= '0' && *p <= '9') v = v * 10 + (*p++ - '0');
    out = v;
    return true;
}

// Move p to the first character of the next line.
static void skip_line(const char *&p) {
    while (*p && *p != '\n') ++p;
    if (*p == '\n') ++p;
}

Graph load_graph(const std::string &path) {
    std::vector<char> buf = read_file(path);
    const char *p = buf.data();
    Graph g;
    bool have_header = false;
    std::vector<int32_t> src, dst;  // the raw edge list, in file order
    int64_t line_no = 0;

    // ---- Step 1: parse the text into (src, dst) pairs -------------------------
    while (*p) {
        ++line_no;
        const char *line = p;
        while (*line == ' ' || *line == '\t') ++line;
        // Skip comment lines and blank lines.
        if (*line == '#' || *line == '\n' || *line == '\r' || *line == '\0') {
            skip_line(p);
            continue;
        }
        p = line;
        int64_t a, b;
        if (!next_int(p, a) || !next_int(p, b))
            die("line " + std::to_string(line_no) + ": expected two integers");
        skip_line(p);

        // The first data line is the header "N M"; every line after it is an edge.
        if (!have_header) {
            if (a <= 0 || a > INT32_MAX || b < 0) die("bad header (N M)");
            g.N = static_cast<int32_t>(a);
            g.M = b;
            src.reserve(b);
            dst.reserve(b);
            have_header = true;
            continue;
        }
        if (a >= g.N || b >= g.N)
            die("line " + std::to_string(line_no) + ": node id out of range [0, N)");
        src.push_back(static_cast<int32_t>(a));
        dst.push_back(static_cast<int32_t>(b));
    }
    if (!have_header) die("no header line in " + path);
    if (static_cast<int64_t>(src.size()) != g.M)
        die("header says M=" + std::to_string(g.M) + " but file has " +
            std::to_string(src.size()) + " edges");

    // ---- Step 2: count out-degrees and in-degrees -----------------------------
    // in_offsets[v+1] temporarily holds the in-degree of v.
    g.out_degree.assign(g.N, 0);
    g.in_offsets.assign(static_cast<size_t>(g.N) + 1, 0);
    for (int64_t e = 0; e < g.M; ++e) {
        g.out_degree[src[e]]++;
        g.in_offsets[static_cast<size_t>(dst[e]) + 1]++;
    }

    // ---- Step 3: prefix sum turns in-degrees into start positions -------------
    // After this, node v's in-neighbours go in slots in_offsets[v] .. in_offsets[v+1]-1.
    for (int32_t v = 0; v < g.N; ++v) g.in_offsets[v + 1] += g.in_offsets[v];

    // ---- Step 4: place every edge in its target's slot (counting sort) --------
    // pos[v] is the next free slot for node v. Edges keep their file order
    // inside each node's list, so the layout (and the summation order later)
    // is the same every run.
    g.in_src.resize(g.M);
    std::vector<int64_t> pos(g.in_offsets.begin(), g.in_offsets.end() - 1);
    for (int64_t e = 0; e < g.M; ++e) g.in_src[pos[dst[e]]++] = src[e];
    return g;
}

Options parse_args(int argc, char **argv, const char *prog) {
    if (argc < 4 || argc > 5) {
        std::fprintf(stderr,
                     "usage: %s <graph> <max_iters> <tol> [ranks_out]\n"
                     "  tol <= 0 runs exactly max_iters iterations (timing mode)\n",
                     prog);
        std::exit(2);
    }
    Options o;
    o.graph_path = argv[1];
    o.max_iters = std::atoi(argv[2]);
    o.tol = std::atof(argv[3]);
    if (argc == 5) o.ranks_out = argv[4];
    if (o.max_iters <= 0) die("max_iters must be > 0");
    return o;
}

std::string dataset_name(const std::string &path) {
    size_t slash = path.find_last_of('/');
    std::string name = (slash == std::string::npos) ? path : path.substr(slash + 1);
    size_t dot = name.rfind(".txt");
    if (dot != std::string::npos && dot + 4 == name.size()) name.resize(dot);
    return name;
}

void write_ranks(const std::string &path, const std::vector<double> &r) {
    FILE *f = std::fopen(path.c_str(), "w");
    if (!f) die("cannot write " + path);
    // %.17g prints every bit of the double, so a later comparison is exact.
    for (size_t v = 0; v < r.size(); ++v) std::fprintf(f, "%zu %.17g\n", v, r[v]);
    std::fclose(f);
}
