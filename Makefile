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

COMMON := src/graph.cpp src/graph.hpp

all: serial parallel

# serial uses omp_get_wtime() for timing only; it has no OpenMP pragmas.
serial: src/serial.cpp $(COMMON)
	$(CXX) $(CXXFLAGS) $(OMPFLAGS) -o $@ src/serial.cpp src/graph.cpp

parallel: src/parallel.cpp $(COMMON)
	$(CXX) $(CXXFLAGS) $(OMPFLAGS) -o $@ src/parallel.cpp src/graph.cpp

check: all
	./scripts/correctness.sh

clean:
	rm -f serial parallel

.PHONY: all check clean
