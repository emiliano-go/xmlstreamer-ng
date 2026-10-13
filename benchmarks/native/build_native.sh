#!/usr/bin/env bash
# Build the native parse-throughput reference binaries into benchmarks/native/bin/.
#
# These are speed-only references (raw parse throughput, no Python semantics):
#   - quick-xml   Rust crate, event-reader counting </item> tags
#   - simdxml     SIMD structural indexer, counting <item> tags (git clone;
#                 simdxml has no crates.io release pinned here, build from git)
#   - pugixml     C++ DOM parser, counting <item> elements
#
# Binaries land in benchmarks/native/bin/ (gitignored). simdxml's git clone
# lives in /tmp so nothing vendored ships in the sdist.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TARGET="$HERE/.target"
BIN="$HERE/bin"
mkdir -p "$BIN"

echo "== quick-xml =="
cargo build --release --manifest-path "$HERE/quick_xml_counter/Cargo.toml" \
    --target-dir "$TARGET"
cp "$TARGET/release/quick_xml_counter" "$BIN/"

echo "== simdxml (git) =="
SIMDXML_WS="${SIMDXML_WS:-/tmp/simdxml-workspace}"
if [ ! -d "$SIMDXML_WS/crates/simdxml" ]; then
    git clone --depth 1 https://github.com/simdxml/simdxml "$SIMDXML_WS"
fi
cargo build --release --manifest-path "$HERE/simdxml_counter/Cargo.toml" \
    --target-dir "$TARGET"
cp "$TARGET/release/simdxml_counter" "$BIN/"

echo "== pugixml =="
g++ -O3 -march=native -o "$BIN/pugixml_counter" \
    "$HERE/pugixml/counter.cpp" "$HERE/pugixml/pugixml.cpp"

echo "done: $BIN"
ls -la "$BIN"
