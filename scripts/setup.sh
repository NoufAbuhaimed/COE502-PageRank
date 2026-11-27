#!/usr/bin/env bash
# Install the build/run prerequisites for this project on the current platform:
#   C++17 compiler with OpenMP, make, bash, and uv (runs the Python scripts and
#   brings their dependencies, e.g. matplotlib, by itself: no pip, no system packages).
# Supports Ubuntu/Debian, Fedora/RHEL, Arch, openSUSE, macOS (Homebrew) and
# Windows via WSL2 (runs as Ubuntu) or MSYS2 (UCRT64 shell).
#
#   ./scripts/setup.sh
set -euo pipefail

need_sudo() { if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null; then echo sudo; fi; }

# uv's official installer puts it in ~/.local/bin.
install_uv() {
    command -v uv >/dev/null && return 0
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
}

OS=$(uname -s)
case "$OS" in
Linux)
    S=$(need_sudo)
    if command -v apt-get >/dev/null; then        # Ubuntu / Debian / WSL2
        $S apt-get update
        $S apt-get install -y build-essential make curl
    elif command -v dnf >/dev/null; then          # Fedora / RHEL / Rocky
        $S dnf install -y gcc-c++ make curl
    elif command -v pacman >/dev/null; then       # Arch / Manjaro
        $S pacman -S --needed --noconfirm gcc make curl
    elif command -v zypper >/dev/null; then       # openSUSE
        $S zypper install -y gcc-c++ make curl
    else
        echo "Unknown Linux package manager: install g++ (with OpenMP), make and curl." >&2
        exit 1
    fi
    install_uv
    ;;
Darwin)
    xcode-select -p >/dev/null 2>&1 || { xcode-select --install; echo "Re-run after the Xcode tools finish installing."; exit 1; }
    command -v brew >/dev/null || { echo "Install Homebrew first: https://brew.sh" >&2; exit 1; }
    brew install libomp uv
    echo
    echo "macOS build command (Apple clang + libomp):"
    echo "  make OMPFLAGS=\"-Xpreprocessor -fopenmp -I\$(brew --prefix libomp)/include -L\$(brew --prefix libomp)/lib -lomp\" CPUFLAG="
    ;;
MINGW*|MSYS*|UCRT*|CLANG*)                         # Windows, MSYS2 shell
    P=${MINGW_PACKAGE_PREFIX:-mingw-w64-ucrt-x86_64}
    pacman -S --needed --noconfirm make "$P-gcc"
    command -v uv >/dev/null || pacman -S --needed --noconfirm "$P-uv" || install_uv
    ;;
*)
    echo "Unsupported OS '$OS'. On Windows use WSL2 (Ubuntu) or an MSYS2 UCRT64 shell." >&2
    exit 1
    ;;
esac

echo
echo "Checking OpenMP compiler support..."
CXX=${CXX:-g++}
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
printf '#include <omp.h>\nint main(){return omp_get_max_threads()>0?0:1;}\n' > "$tmp/t.cpp"
if [ "$OS" = Darwin ]; then
    LIBOMP=$(brew --prefix libomp)
    FLAGS="-Xpreprocessor -fopenmp -I$LIBOMP/include -L$LIBOMP/lib -lomp"
else
    FLAGS="-fopenmp"
fi
# shellcheck disable=SC2086
if $CXX -std=c++17 $FLAGS "$tmp/t.cpp" -o "$tmp/t" && "$tmp/t"; then
    echo "OK: $CXX builds and runs OpenMP code."
else
    echo "FAILED: $CXX could not build an OpenMP program." >&2
    exit 1
fi

# First run also downloads matplotlib (and a Python if needed) into uv's cache.
echo
echo "Checking uv and the Python scripts' dependencies..."
if uv run --quiet --no-project --with matplotlib python -c "import matplotlib" ; then
    echo "OK: $(uv --version) runs the Python scripts (matplotlib available)."
else
    echo "FAILED: uv could not set up Python with matplotlib." >&2
    exit 1
fi
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *)
    if [ -x "$HOME/.local/bin/uv" ]; then
        echo "Note: add uv to your PATH: export PATH=\"\$HOME/.local/bin:\$PATH\""
    fi ;;
esac
