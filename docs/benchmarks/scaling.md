# rypipe adapter scaling (crxml style)

Date: 2026-10-13 | CPU: AMD Ryzen 7 5800X 8-Core Processor | Python 3.14.8 | xmlstreamer_ng 1.1.0, pyarrow 26.0.0

Measured by `benchmarks/bench_scaling.py` (best of 3 rounds), the same
style as emiliano-go/crxml's benchmark tables: rows/s and MB/s per adapter
path, swept over thread counts on deterministic feeds. Absolute numbers
track the machine (CPU, page-cache state, background load); the
thread-count shape is the result.

| feed | path | rows | seconds | rows/s | MB/s |
|---|---|---|---|---|---|
| plain 100,000 | read_xml | 100,000 | 0.052 | 1,933,734 | 258.0 |
| plain 100,000 | read_xml_stream (64MiB) | 100,000 | 0.058 | 1,732,098 | 231.1 |
| plain 100,000 | read_xml_par (chunks=1) | 100,000 | 0.053 | 1,901,225 | 253.6 |
| plain 100,000 | read_xml_par (chunks=2) | 100,000 | 0.012 | 8,339,871 | 1,112.6 |
| plain 100,000 | read_xml_par (chunks=4) | 100,000 | 0.013 | 7,738,630 | 1,032.4 |
| plain 100,000 | read_xml_par (chunks=8) | 100,000 | 0.012 | 8,177,102 | 1,090.9 |
| plain 100,000 | read_xml_par (chunks=12) | 100,000 | 0.012 | 8,508,868 | 1,135.2 |
| plain 100,000 | iter_xml_batches_par (threads=1) | 100,000 | 0.058 | 1,727,446 | 230.5 |
| plain 100,000 | iter_xml_batches_par (threads=2) | 100,000 | 0.033 | 3,038,856 | 405.4 |
| plain 100,000 | iter_xml_batches_par (threads=4) | 100,000 | 0.020 | 5,109,359 | 681.6 |
| plain 100,000 | iter_xml_batches_par (threads=8) | 100,000 | 0.016 | 6,401,209 | 854.0 |
| plain 100,000 | iter_xml_batches_par (threads=12) | 100,000 | 0.012 | 8,140,701 | 1,086.0 |
| cdata 50,000 | read_xml | 50,000 | 0.056 | 891,781 | 420.8 |
| cdata 50,000 | read_xml_stream (64MiB) | 50,000 | 0.066 | 757,077 | 357.2 |
| cdata 50,000 | read_xml_par (chunks=1) | 50,000 | 0.053 | 939,916 | 443.5 |
| cdata 50,000 | read_xml_par (chunks=2) | 50,000 | 0.017 | 2,948,163 | 1,391.1 |
| cdata 50,000 | read_xml_par (chunks=4) | 50,000 | 0.018 | 2,703,618 | 1,275.7 |
| cdata 50,000 | read_xml_par (chunks=8) | 50,000 | 0.017 | 2,931,379 | 1,383.2 |
| cdata 50,000 | read_xml_par (chunks=12) | 50,000 | 0.018 | 2,767,502 | 1,305.9 |
| cdata 50,000 | iter_xml_batches_par (threads=1) | 50,000 | 0.072 | 698,478 | 329.6 |
| cdata 50,000 | iter_xml_batches_par (threads=2) | 50,000 | 0.043 | 1,157,471 | 546.2 |
| cdata 50,000 | iter_xml_batches_par (threads=4) | 50,000 | 0.028 | 1,774,036 | 837.1 |
| cdata 50,000 | iter_xml_batches_par (threads=8) | 50,000 | 0.024 | 2,093,845 | 988.0 |
| cdata 50,000 | iter_xml_batches_par (threads=12) | 50,000 | 0.025 | 2,005,551 | 946.3 |
| plain 128 MiB | read_xml | 953,250 | 0.503 | 1,895,145 | 254.6 |
| plain 128 MiB | read_xml_stream (64MiB) | 953,250 | 0.554 | 1,720,154 | 231.1 |
| plain 128 MiB | read_xml_par (chunks=1) | 953,250 | 0.511 | 1,865,422 | 250.6 |
| plain 128 MiB | read_xml_par (chunks=2) | 953,250 | 0.104 | 9,145,182 | 1,228.7 |
| plain 128 MiB | read_xml_par (chunks=4) | 953,250 | 0.097 | 9,836,313 | 1,321.6 |
| plain 128 MiB | read_xml_par (chunks=8) | 953,250 | 0.093 | 10,269,314 | 1,379.8 |
| plain 128 MiB | read_xml_par (chunks=12) | 953,250 | 0.099 | 9,627,719 | 1,293.6 |
| plain 128 MiB | iter_xml_batches_par (threads=1) | 953,250 | 0.522 | 1,826,309 | 245.4 |
| plain 128 MiB | iter_xml_batches_par (threads=2) | 953,250 | 0.289 | 3,294,553 | 442.6 |
| plain 128 MiB | iter_xml_batches_par (threads=4) | 953,250 | 0.160 | 5,960,893 | 800.9 |
| plain 128 MiB | iter_xml_batches_par (threads=8) | 953,250 | 0.113 | 8,464,295 | 1,137.2 |
| plain 128 MiB | iter_xml_batches_par (threads=12) | 953,250 | 0.106 | 8,968,635 | 1,205.0 |

Reading the shape:

- Single-threaded paths (read_xml, read_xml_stream, chunks=1,
  threads=1) all sit at 1.7-1.9M rows/s on the flat feeds;
  parallelism, not the parser, is the whole story below.
- `read_xml_par` jumps ~5x at chunks=2 and saturates the
  8-core/16-thread CPU around chunks=2-8 on the big feed (9.1M
  rows/s, 1229 MB/s at chunks=2 this run). Past the physical core
  count the extra threads only add noise (chunks=12 wobbles
  1194-1380 MB/s between runs).
- The CDATA feed is bytes-heavier per row, so its rows/s look lower
  while its MB/s are the highest in the table (~1.4 GB/s at
  chunks>=2).
- `iter_xml_batches_par` scales more gradually: it pays
  bounded-memory batch production and Python-level iteration, so it
  peaks lower than `read_xml_par` (9.0M vs 10.3M rows/s on the big
  feed) in exchange for a flat memory profile (see adapter.md for
  RSS).
- On the small 100k/50k feeds the parallel numbers are inflated by
  fixed-cost amortization (a 20-60 ms run vs a ~10 ms mmap+thread
  spin-up); read them as "small files scale poorly, fixed costs
  dominate", the same caveat crxml documents for its 10 MB files.
