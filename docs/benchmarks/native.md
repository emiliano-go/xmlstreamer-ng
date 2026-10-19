# Native parse-throughput references (speed only)

Date: 2026-10-19 | CPU: AMD Ryzen 7 5800X 8-Core Processor | quick-xml 0.37.5 (Rust, lto), simdxml 0.2.1 (git `github.com/simdxml/simdxml`, SIMD structural indexing), pugixml 1.15 (C++, `-O3 -march=native`)

Measured by `benchmarks/native_bench.py` against the same deterministic
feeds the Python harness uses, best of 3 rounds inside each binary
(two outer shots, best kept).

| feed | parser | items | best seconds | items/s | MB/s |
|---|---|---|---|---|---|
| plain 100,000 | quick-xml | 100,000 | 0.031 | 3,182,585 | 424.6 |
| plain 100,000 | simdxml | 100,000 | 0.059 | 1,705,757 | 227.6 |
| plain 100,000 | pugixml | 100,000 | 0.044 | 2,288,801 | 305.3 |
| cdata 50,000 | quick-xml | 50,000 | 0.022 | 2,266,443 | 1,069.4 |
| cdata 50,000 | simdxml | 50,000 | 0.043 | 1,176,166 | 555.0 |
| cdata 50,000 | pugixml | 50,000 | 0.025 | 2,013,612 | 950.1 |
| plain 128 MiB | quick-xml | 951,898 | 0.299 | 3,182,020 | 427.5 |
| plain 128 MiB | simdxml | 951,898 | 0.558 | 1,706,914 | 229.3 |
| plain 128 MiB | pugixml | 951,898 | 0.432 | 2,205,622 | 296.3 |

These binaries fully parse the file and count <item> elements. They carry none of the Python layer semantics (encoding detection, recovery contract, Arrow materialization): an upper-bound ruler, not a like-for-like parser comparison. Build them with benchmarks/native/build_native.sh.
