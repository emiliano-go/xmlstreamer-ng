# Native parse-throughput references (speed only)

Date: 2026-10-13 | CPU: AMD Ryzen 7 5800X 8-Core Processor | quick-xml 0.37.5 (Rust 1.99.0, lto), simdxml 0.2.1 (git `github.com/simdxml/simdxml`, SIMD structural indexing), pugixml 1.15 (GCC 16.2.1, `-O3 -march=native`)

Measured by `benchmarks/native_bench.py` against the same deterministic
feeds the Python harness uses, best of 3 rounds inside each binary
(two outer shots, best kept).

| feed | parser | items | seconds | items/s | MB/s |
|---|---|---|---|---|---|
| plain 100,000 | quick-xml | 100,000 | 0.029 | 3,434,420 | 458.2 |
| plain 100,000 | simdxml | 100,000 | 0.044 | 2,281,334 | 304.3 |
| plain 100,000 | pugixml | 100,000 | 0.038 | 2,601,118 | 347.0 |
| cdata 50,000 | quick-xml | 50,000 | 0.022 | 2,226,874 | 1,050.8 |
| cdata 50,000 | simdxml | 50,000 | 0.029 | 1,726,221 | 814.5 |
| cdata 50,000 | pugixml | 50,000 | 0.024 | 2,127,207 | 1,003.7 |
| plain 128 MiB | quick-xml | 953,250 | 0.274 | 3,481,581 | 467.8 |
| plain 128 MiB | simdxml | 953,250 | 0.430 | 2,219,436 | 298.2 |
| plain 128 MiB | pugixml | 953,250 | 0.370 | 2,575,955 | 346.1 |

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
