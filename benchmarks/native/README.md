# Native parse-throughput references

Speed-only comparisons against three fastest-in-class native XML engines:
[quick-xml](https://crates.io/crates/quick-xml) (Rust, streaming events),
[pugixml](https://pugixml.org/) (C++, in-place DOM) and
[simdxml](https://github.com/simdxml/simdxml) (Rust, SIMD structural
indexing, simdjson's XML successor). These binaries fully parse a feed file
and count `<item>` elements. They are raw parse throughput only: no Python
semantics, no encoding detection, no recovery contract, no Arrow materialization.
Use them as an upper-bound ruler for the Python-measurable numbers, never as
like-for-like parser comparisons.

## Build

```bash
benchmarks/native/build_native.sh
```

Requires `cargo` and `g++`. Builds with `lto`/`-O3 -march=native` into the
gitignored `bin/` directory. The simdxml counter builds against a git clone
of `github.com/simdxml/simdxml` placed in `/tmp/simdxml-workspace`
(override with `SIMDXML_WS`), because simdxml is consumed from git rather
than a pinned release. `target/` directories are local (`.target/`,
gitignored) so nothing native ships in the sdist.

## Run

Each binary takes a file and a round count, and prints
`<items>\t<best_seconds>`:

```bash
bin/quick_xml_counter feed.xml 3
bin/simdxml_counter feed.xml 3
bin/pugixml_counter feed.xml 3
```

`run_all.py` appends a native section automatically when `bin/` exists and
skips it (with a note) otherwise.
