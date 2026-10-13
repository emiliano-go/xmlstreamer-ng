# rypipe adapter scaling (crxml style)

Date: 2026-10-12 | CPU: AMD Ryzen 7 5800X 8-Core Processor | Python 3.14.8 | xmlstreamer_ng 1.1.0, pyarrow 26.0.0

Measured by `benchmarks/bench_scaling.py` (best of 3 rounds), the same
style as emiliano-go/crxml's benchmark tables: rows/s and MB/s per adapter
path, swept over thread counts on deterministic feeds. Absolute numbers
track the machine (CPU, page-cache state, background load); the
thread-count shape is the result.

| feed | path | rows | seconds | rows/s | MB/s |
|---|---|---|---|---|---|
| plain 100,000 | read_xml | 100,000 | 0.096 | 1,039,340 | 138.7 |
| plain 100,000 | read_xml_stream (64MiB) | 100,000 | 0.106 | 945,738 | 126.2 |
| plain 100,000 | read_xml_par (chunks=1) | 100,000 | 0.101 | 992,287 | 132.4 |
| plain 100,000 | read_xml_par (chunks=2) | 100,000 | 0.026 | 3,899,179 | 520.2 |
| plain 100,000 | read_xml_par (chunks=4) | 100,000 | 0.023 | 4,274,366 | 570.2 |
| plain 100,000 | read_xml_par (chunks=8) | 100,000 | 0.025 | 3,998,780 | 533.5 |
| plain 100,000 | read_xml_par (chunks=12) | 100,000 | 0.021 | 4,680,510 | 624.4 |
| plain 100,000 | iter_xml_batches_par (threads=1) | 100,000 | 0.100 | 998,554 | 133.2 |
| plain 100,000 | iter_xml_batches_par (threads=2) | 100,000 | 0.058 | 1,725,154 | 230.2 |
| plain 100,000 | iter_xml_batches_par (threads=4) | 100,000 | 0.046 | 2,153,911 | 287.4 |
| plain 100,000 | iter_xml_batches_par (threads=8) | 100,000 | 0.027 | 3,655,112 | 487.6 |
| plain 100,000 | iter_xml_batches_par (threads=12) | 100,000 | 0.026 | 3,789,809 | 505.6 |
| cdata 50,000 | read_xml | 50,000 | 0.077 | 646,312 | 305.0 |
| cdata 50,000 | read_xml_stream (64MiB) | 50,000 | 0.093 | 535,500 | 252.7 |
| cdata 50,000 | read_xml_par (chunks=1) | 50,000 | 0.081 | 616,098 | 290.7 |
| cdata 50,000 | read_xml_par (chunks=2) | 50,000 | 0.024 | 2,051,289 | 967.9 |
| cdata 50,000 | read_xml_par (chunks=4) | 50,000 | 0.024 | 2,067,681 | 975.7 |
| cdata 50,000 | read_xml_par (chunks=8) | 50,000 | 0.024 | 2,056,258 | 970.3 |
| cdata 50,000 | read_xml_par (chunks=12) | 50,000 | 0.024 | 2,106,336 | 993.9 |
| cdata 50,000 | iter_xml_batches_par (threads=1) | 50,000 | 0.100 | 502,324 | 237.0 |
| cdata 50,000 | iter_xml_batches_par (threads=2) | 50,000 | 0.059 | 847,962 | 400.1 |
| cdata 50,000 | iter_xml_batches_par (threads=4) | 50,000 | 0.040 | 1,262,939 | 595.9 |
| cdata 50,000 | iter_xml_batches_par (threads=8) | 50,000 | 0.034 | 1,454,213 | 686.2 |
| cdata 50,000 | iter_xml_batches_par (threads=12) | 50,000 | 0.042 | 1,199,261 | 565.9 |
| plain 128 MiB | read_xml | 953,250 | 0.998 | 955,302 | 128.4 |
| plain 128 MiB | read_xml_stream (64MiB) | 953,250 | 1.084 | 879,009 | 118.1 |
| plain 128 MiB | read_xml_par (chunks=1) | 953,250 | 0.946 | 1,007,594 | 135.4 |
| plain 128 MiB | read_xml_par (chunks=2) | 953,250 | 0.188 | 5,062,946 | 680.2 |
| plain 128 MiB | read_xml_par (chunks=4) | 953,250 | 0.237 | 4,027,869 | 541.2 |
| plain 128 MiB | read_xml_par (chunks=8) | 953,250 | 0.199 | 4,778,358 | 642.0 |
| plain 128 MiB | read_xml_par (chunks=12) | 953,250 | 0.237 | 4,014,069 | 539.3 |
| plain 128 MiB | iter_xml_batches_par (threads=1) | 953,250 | 1.093 | 872,395 | 117.2 |
| plain 128 MiB | iter_xml_batches_par (threads=2) | 953,250 | 0.508 | 1,878,129 | 252.3 |
| plain 128 MiB | iter_xml_batches_par (threads=4) | 953,250 | 0.289 | 3,303,339 | 443.8 |
| plain 128 MiB | iter_xml_batches_par (threads=8) | 953,250 | 0.239 | 3,984,842 | 535.4 |
| plain 128 MiB | iter_xml_batches_par (threads=12) | 953,250 | 0.202 | 4,707,961 | 632.5 |

Reading the shape:

- Single-threaded paths (read_xml, read_xml_stream, chunks=1,
  threads=1) all sit at 0.9-1.0M rows/s on the flat feeds; parallelism,
  not the parser, is the whole story below.
- `read_xml_par` jumps ~4x at chunks=2 and saturates the 8-core/16-thread
  CPU around chunks=2-8 on the big feed (5.1M rows/s, 680 MB/s at
  chunks=2 this run). Past the physical core count the extra threads
  only add noise (chunks=12 wobbles 539-690 MB/s between runs).
- The CDATA feed is bytes-heavier per row, so its rows/s look lower while
  its MB/s are the highest in the table (~1 GB/s at chunks>=2).
- `iter_xml_batches_par` scales more gradually: it pays bounded-memory
  batch production and Python-level iteration, so it peaks lower than
  `read_xml_par` (4.7M vs 5.1M rows/s on the big feed) in exchange for
  a flat memory profile (see adapter.md for RSS).
- On the small 100k/50k feeds the parallel numbers are inflated by
  fixed-cost amortization (a 20-100 ms run vs a ~10 ms mmap+thread
  spin-up); read them as "small files scale poorly, fixed costs
  dominate", the same caveat crxml documents for its 10 MB files.
