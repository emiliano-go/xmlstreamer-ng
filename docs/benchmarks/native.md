# Native parse-throughput references (speed only)

Date: 2026-10-14 | CPU: AMD Ryzen 7 5800X 8-Core Processor | quick-xml 0.37.5 (Rust, lto), simdxml 0.2.1 (git `github.com/simdxml/simdxml`, SIMD structural indexing), pugixml 1.15 (C++, `-O3 -march=native`)

Measured by `benchmarks/native_bench.py` against the same deterministic
feeds the Python harness uses, best of 3 rounds inside each binary
(two outer shots, best kept).

| feed | parser | items | seconds | items/s | MB/s |
|---|---|---|---|---|---|
| plain 100,000 | quick-xml | 100,000 | 0.034 | 2,922,012 | 389.8 |
| plain 100,000 | simdxml | 100,000 | 0.064 | 1,569,046 | 209.3 |
| plain 100,000 | pugixml | 100,000 | 0.047 | 2,115,551 | 282.2 |
| cdata 50,000 | quick-xml | 50,000 | 0.025 | 2,034,919 | 960.2 |
| cdata 50,000 | simdxml | 50,000 | 0.048 | 1,051,989 | 496.4 |
| cdata 50,000 | pugixml | 50,000 | 0.028 | 1,755,988 | 828.6 |
| plain 128 MiB | quick-xml | 953,250 | 0.324 | 2,938,402 | 394.8 |
| plain 128 MiB | simdxml | 953,250 | 0.599 | 1,592,325 | 213.9 |
| plain 128 MiB | pugixml | 953,250 | 0.461 | 2,067,375 | 277.8 |

These binaries fully parse the file and count <item> elements. They carry none of the Python layer semantics (encoding detection, recovery contract, Arrow materialization): an upper-bound ruler, not a like-for-like parser comparison. Build them with benchmarks/native/build_native.sh.
