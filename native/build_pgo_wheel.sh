#!/usr/bin/env bash
# Prepare a profile-guided build of the Linux wheel.
#
# Source this script, then run the real wheel build; the final `export` below
# is what makes that build consume the profile:
#
#   source native/build_pgo_wheel.sh
#   maturin build --release --out dist --manifest-path native/Cargo.toml
#
# This is the same command sequence `maturin-action` runs: it injects this file
# as `before-script-linux` inside the manylinux container, then runs `maturin
# build` in the same shell, so the exported RUSTFLAGS reach it. macOS/Windows
# ignore `before-script-linux`, so only the Linux wheel is PGO-built.
#
# Stages: instrumented wheel -> install + train -> merge -> export profile-use.
# The training workload is benchmarks/pgo_train.py (columnar, streaming,
# parallel and per-item paths).
#
# Environment:
#   PGO_DIR        profile dir (default: native/.pgo)
#   PGO_GEN_DIR    instrumented wheel dir (default: /tmp/pgo-gen)
#   PGO_VENV_DIR   training venv (default: /tmp/pgo-venv)
#   PGO_TRAIN_MB   trainer feed size (default: 16)
#   MATURIN        maturin executable (default: maturin on PATH)
set -euo pipefail

ROOT="${GITHUB_WORKSPACE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
HERE="$ROOT/native"
PGO_DIR="${PGO_DIR:-$HERE/.pgo}"
GEN_DIR="${PGO_GEN_DIR:-/tmp/pgo-gen}"
VENV_DIR="${PGO_VENV_DIR:-/tmp/pgo-venv}"
TRAIN_MB="${PGO_TRAIN_MB:-16}"
MATURIN="${MATURIN:-maturin}"

STEP_START=$(date +%s)
stage() { printf '[%s +%ss] %s\n' "$(date +%H:%M:%S)" "$(( $(date +%s) - STEP_START ))" "$*"; }

rm -rf "$PGO_DIR" "$GEN_DIR" "$VENV_DIR"
mkdir -p "$PGO_DIR" "$GEN_DIR"

stage "1/4 instrumented wheel (profile-generate)"
( cd "$ROOT" && RUSTFLAGS="-Cprofile-generate=$PGO_DIR ${RUSTFLAGS:-}" \
    "$MATURIN" build --release --out "$GEN_DIR" --manifest-path "$HERE/Cargo.toml" )

# Build scripts also run instrumented and leave their own profiles behind;
# keep only what the trainer produces.
rm -f "$PGO_DIR"/*.profraw

stage "2/4 install and train"
uv venv --python 3.11 "$VENV_DIR"
uv pip install --python "$VENV_DIR/bin/python" "$GEN_DIR"/*.whl
( cd "$ROOT" && "$VENV_DIR/bin/python" benchmarks/pgo_train.py --mb "$TRAIN_MB" )

shopt -s nullglob
PROFRAW=("$PGO_DIR"/*.profraw)
if [ "${#PROFRAW[@]}" -eq 0 ]; then
    echo "no .profraw files in $PGO_DIR (did the trainer call the extension?)" >&2
    exit 1
fi

stage "3/4 merge ${#PROFRAW[@]} profile(s)"
HOST="$(rustc -vV | sed -n 's/^host: //p')"
# Prefer the toolchain's copy (guaranteed LLVM version match); distro rustc
# builds keep it elsewhere, so fall back to PATH.
PROFDATA="$(rustc --print sysroot)/lib/rustlib/$HOST/bin/llvm-profdata"
if [ ! -x "$PROFDATA" ]; then
    PROFDATA="$(command -v llvm-profdata || true)"
fi
if [ -z "$PROFDATA" ] || [ ! -x "$PROFDATA" ]; then
    echo "no llvm-profdata: rustup component add llvm-tools-preview, or install LLVM" >&2
    exit 1
fi
"$PROFDATA" merge -o "$PGO_DIR/merged.profdata" "${PROFRAW[@]}"

stage "4/4 export profile-use for the caller's wheel build"
export RUSTFLAGS="-Cprofile-use=$PGO_DIR/merged.profdata -Cllvm-args=-pgo-warn-missing-function ${RUSTFLAGS:-}"
