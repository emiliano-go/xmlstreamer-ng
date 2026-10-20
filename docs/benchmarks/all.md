Common feed: synthetic plain feed (`feeds.py`), 128 MiB target, 951,898 items. Headline is the median of 5 rounds; best and p95 are shown beside it.

Date: 2026-10-20 | CPU: AMD Ryzen 7 5800X 8-Core Processor | Python 3.13.15 | xmlstreamer-ng 2.1.0, xmlstreamer (original) 2.2.0, lxml 6.1.3, xmltodict 1.0.4, simdxml (Python) 0.3.0, pyarrow 26.0.0; quick-xml 0.37.5, simdxml 0.2.1 (git), pugixml 1.15

| engine | items/s (median) | best items/s | p95 s | spread | MB/s | peak RSS MB | threads | API/notes |
|---|---|---|---|---|---|---|---|---|
| xmlstreamer-ng per-item | 911k | 926k | 1.202 | 16.7% | 122.3 | 74 | 1 | per-item dicts |
| XmlSource columnar | 4.7M | 4.8M | 0.246 | 23.6% | 631.9 | 297 | 1 | Arrow batches |
| XmlSource parallel (8 threads) | 16.6M | 17.6M | 0.059 | 9.0% | 2225.9 | 284 | 8 | Arrow batches, 8 threads |
| XmlSource bounded parallel streaming | 10.6M | 11.1M | 0.320 | 262.0% | 1430.6 | 202 | 8 | bounded batches, 8 threads |
| xmlstreamer (original) | 111k | 112k | 8.764 | 3.1% | 14.9 | 34 | 1 | per-item dicts |
| lxml iterparse (count) | 503k | 510k | 1.960 | 4.9% | 67.5 | 26 | 1 | iterparse + clear(), no records |
| stdlib ET iterparse (count) | 350k | 355k | 2.880 | 7.3% | 47.0 | 21 | 1 | iterparse + root.clear(), no records |
| lxml iterparse (dicts) | 338k | 344k | 2.840 | 2.5% | 45.5 | 26 | 1 | per-item dicts |
| stdlib ET iterparse (dicts) | 317k | 319k | 3.045 | 2.0% | 42.6 | 21 | 1 | per-item dicts |
| xmltodict | 107k | 108k | 9.264 | 5.0% | 14.4 | 469 | 1 | whole-document dict |
| simdxml (Python) | 527k | 573k | 1.819 | 8.7% | 70.8 | 1062 | 1 | per-item dicts, whole-doc parse |
| simdxml parallel (Python) | 545k | 552k | 1.770 | 2.7% | 73.2 | 1066 | 16 | per-item dicts, parallel SIMD parse |
| quick-xml 0.37.5 | 3.3M | 3.3M | 0.285 | 0.0% | 449.3 | 14 | 1 | parse+count only, no data; best of N |
| simdxml 0.2.1 (git) | 1.7M | 1.7M | 0.576 | 0.0% | 222.1 | 730 | 1 | parse+count only, no data; best of N |
| pugixml 1.15 | 2.2M | 2.2M | 0.442 | 0.0% | 289.6 | 772 | 1 | parse+count only, no data; best of N |

Native rows are speed-only references (parse and count, no encoding detection, recovery contract, or data materialization).
