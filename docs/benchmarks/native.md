# Native parse-throughput references (speed only)

Date: 2026-10-13 | CPU: AMD Ryzen 7 5800X 8-Core Processor | quick-xml 0.37.5 (Rust 1.99.0, lto), simdxml 0.2.1 (git `github.com/simdxml/simdxml`, SIMD structural indexing), pugixml 1.15 (GCC 16.2.1, `-O3 -march=native`)

Measured by `benchmarks/native_bench.py` against the same deterministic
feeds the Python harness uses, best of 3 rounds inside each binary
(two outer shots, best kept).

| feed | parser | items | seconds | items/s | MB/s |
|---|---|---|---|---|---|
| plain 100,000 | quick-xml | 100,000 | 0.029 | 3,436,899 | 458.5 |
| plain 100,000 | simdxml | 100,000 | 0.044 | 2,266,135 | 302.3 |
| plain 100,000 | pugixml | 100,000 | 0.041 | 2,445,048 | 326.2 |
| cdata 50,000 | quick-xml | 50,000 | 0.021 | 2,362,837 | 1,114.9 |
| cdata 50,000 | simdxml | 50,000 | 0.028 | 1,783,294 | 841.5 |
| cdata 50,000 | pugixml | 50,000 | 0.024 | 2,100,487 | 991.1 |
| plain 128 MiB | quick-xml | 953,250 | 0.277 | 3,443,101 | 462.6 |
| plain 128 MiB | simdxml | 953,250 | 0.427 | 2,234,173 | 300.2 |
| plain 128 MiB | pugixml | 953,250 | 0.382 | 2,497,969 | 335.6 |
