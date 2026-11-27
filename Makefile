CXX      ?= g++
ARCH     := $(shell uname -m)
ifeq ($(ARCH),aarch64)
  CPUFLAG ?= -mcpu=native
else ifeq ($(ARCH),arm64)
  CPUFLAG ?= -mcpu=native
else
  CPUFLAG ?= -march=native
endif
CXXFLAGS ?= -O3 $(CPUFLAG) -std=c++17 -Wall -Wextra
OMPFLAGS ?= -fopenmp

COMMON := src/graph.cpp src/graph.hpp src/thread_times.hpp

# serial, parallel   : required versions (timing experiments)
# parallel_opt       : optimized extra (edge-balanced, one region, fused phases)
# *_prof             : same code + per-thread busy-time profiling (imbalance plots only;
#                      don't use these binaries for the speedup timings)
all: serial parallel parallel_opt
prof: parallel_prof parallel_opt_prof

# serial uses omp_get_wtime() for timing only; it has no OpenMP pragmas.
serial: src/serial.cpp $(COMMON)
	$(CXX) $(CXXFLAGS) $(OMPFLAGS) -o $@ src/serial.cpp src/graph.cpp

parallel: src/parallel.cpp $(COMMON)
	$(CXX) $(CXXFLAGS) $(OMPFLAGS) -o $@ src/parallel.cpp src/graph.cpp

parallel_opt: src/parallel_opt.cpp $(COMMON)
	$(CXX) $(CXXFLAGS) $(OMPFLAGS) -o $@ src/parallel_opt.cpp src/graph.cpp

parallel_prof: src/parallel.cpp $(COMMON)
	$(CXX) $(CXXFLAGS) $(OMPFLAGS) -DPROFILE_THREADS -o $@ src/parallel.cpp src/graph.cpp

parallel_opt_prof: src/parallel_opt.cpp $(COMMON)
	$(CXX) $(CXXFLAGS) $(OMPFLAGS) -DPROFILE_THREADS -o $@ src/parallel_opt.cpp src/graph.cpp

check: all
	./scripts/correctness.sh

imbalance: prof
	./scripts/imbalance.sh

clean:
	rm -f serial parallel parallel_opt parallel_prof parallel_opt_prof

.PHONY: all prof check imbalance clean
