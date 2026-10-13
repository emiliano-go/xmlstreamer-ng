# Native parse-throughput references (speed only)

Date: 2026-10-13 | CPU: AMD Ryzen 7 5800X 8-Core Processor | quick-xml 0.37.5 (Rust 1.99.0, lto), simdxml 0.2.1 (git `github.com/simdxml/simdxml`, SIMD structural indexing), pugixml 1.15 (GCC 16.2.1, `-O3 -march=native`)

Measured by `benchmarks/native_bench.py` against the same deterministic
feeds the Python harness uses, best of 3 rounds inside each binary
(two outer shots, best kept).

| feed | parser | items | seconds | items/s | MB/s |
|---|---|---|---|---|---|
| plain 100,000 | quick-xml | 100,000 | 0.030 | 3,383,179 | 451.3 |
| plain 100,000 | simdxml | 100,000 | 0.042 | 2,355,269 | 314.2 |
| plain 100,000 | pugixml | 100,000 | 0.039 | 2,576,456 | 343.7 |
| cdata 50,000 | quick-xml | 50,000 | 0.022 | 2,293,157 | 1,082.0 |
| cdata 50,000 | simdxml | 50,000 | 0.029 | 1,713,620 | 808.6 |
| cdata 50,000 | pugixml | 50,000 | 0.023 | 2,210,042 | 1,042.8 |
| plain 128 MiB | quick-xml | 953,250 | 0.284 | 3,356,278 | 450.9 |
| plain 128 MiB | simdxml | 953,250 | 0.513 | 1,859,688 | 249.9 |
| plain 128 MiB | pugixml | 953,250 | 0.393 | 2,423,963 | 325.7 |

What these are, and what they are not:

- Each binary fully parses the file and counts `<item>` elements. That
  is raw parse throughput: no encoding sniffing, no broken-feed
  recovery, no dict/Arrow materialization, no Python at all. They are an
  upper-bound ruler for the Python-measurable numbers in adapter.md and
  scaling.md, not like-for-like parser comparisons.
- quick-xml (streaming events) is the fastest single-threaded scalar
  engine here; on the big feed xmlstreamer-ng's single-threaded
  `read_xml` (955k rows/s, 128 MB/s) runs it at about 30% of quick-xml's
  parse speed, and `read_xml_par` at chunks=2 already matches and at
  chunks=2-8 exceeds it by 1.6-2.2x in MB/s, because the parallel path
  splits the file while quick-xml's counter is single-threaded.
- simdxml wins on attribute-dense XML per its own README; this feed has
  almost no attributes, which is exactly where its flat-index advantage
  is smallest.
- The 100k/50k-feed rows are dominated by process startup and file read;
  the 128 MiB rows are the meaningful ones.

Reproduce: `benchmarks/native/build_native.sh` (needs `cargo` and `g++`,
clones simdxml into `/tmp/simdxml-workspace`), then
`python benchmarks/native_bench.py` or `run_all.py` (which appends this
section automatically when the binaries exist).
