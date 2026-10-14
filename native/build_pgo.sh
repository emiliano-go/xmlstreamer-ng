#!/usr/bin/env bash
# Release-only PGO build of the xmlstreamer-ng native extension.
#
# Two-stage profile-guided optimization: an instrumented build is installed,
# a representative training workload is run to collect profiles, then the
# final build consumes them. The default (non-PGO) build is unchanged.
#
# Usage:
#   native/build_pgo.sh [trainer] [args...]
#
# `trainer` is a command run from the repo root that exercises the extension
# with representative input. It defaults to benchmarks/pgo_train.py, which
# covers the columnar and bounded-streaming paths (the streaming path used to
# be missed, so it gained little from PGO). Pass a custom command to override:
#   native/build_pgo.sh .venv/bin/python benchmarks/bench_rypipe.py --feed-mb 100
#
# Environment:
#   MATURIN       maturin executable (default: maturin on PATH)
#   PGO_DIR       scratch dir for profiles (default: native/.pgo)
#   LLVM_PROFDATA llvm-profdata executable (default: llvm-profdata on PATH)
#   TARGET_DIR    cargo target dir (default: native/target)
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
MANIFEST="$HERE/Cargo.toml"
PGO_DIR="${PGO_DIR:-$HERE/.pgo}"
MATURIN="${MATURIN:-maturin}"
LLVM_PROFDATA="${LLVM_PROFDATA:-llvm-profdata}"

if [ "$#" -eq 0 ]; then
    set -- .venv/bin/python benchmarks/pgo_train.py
fi

STEP_START=$(date +%s)
stage() { printf '[%s +%ss] %s\n' "$(date +%H:%M:%S)" "$(( $(date +%s) - STEP_START ))" "$*"; }

rm -rf "$PGO_DIR"
mkdir -p "$PGO_DIR"

stage "1/3 instrumented build (profile-generate)"
( cd "$ROOT" && RUSTFLAGS="-Cprofile-generate=$PGO_DIR ${RUSTFLAGS:-}" \
    "$MATURIN" develop --release --manifest-path "$MANIFEST" )

stage "2/3 training run: $*"
( cd "$ROOT" && "$@" )

stage "3/3 merging profiles"
shopt -s nullglob
PROFRAW=("$PGO_DIR"/*.profraw)
if [ "${#PROFRAW[@]}" -eq 0 ]; then
    echo "no .profraw files produced in $PGO_DIR (did the trainer call the extension?)" >&2
    exit 1
fi
stage "merging ${#PROFRAW[@]} profile(s)"
"$LLVM_PROFDATA" merge -o "$PGO_DIR/merged.profdata" "${PROFRAW[@]}"

stage "final optimized build (profile-use)"
( cd "$ROOT" && RUSTFLAGS="-Cprofile-use=$PGO_DIR/merged.profdata -Cllvm-args=-pgo-warn-missing-function ${RUSTFLAGS:-}" \
    "$MATURIN" develop --release --manifest-path "$MANIFEST" )

stage "done: PGO build installed"
