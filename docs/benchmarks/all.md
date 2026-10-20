Common feed: synthetic plain feed (`feeds.py`), 128 MiB target, 951,898 items. Headline is the median of 5 rounds; best and p95 are shown beside it.

Date: 2026-10-20 | CPU: AMD Ryzen 7 5800X 8-Core Processor | Python 3.13.15 | xmlstreamer-ng 2.1.0, xmlstreamer (original) 2.2.0, lxml 6.1.3, xmltodict 1.0.4, simdxml (Python) 0.3.0, pyarrow 26.0.0; quick-xml 0.37.5, simdxml 0.2.1 (git), pugixml 1.15

| engine | items/s (median) | best items/s | p95 s | spread | MB/s | peak RSS MB | threads | API/notes |
|---|---|---|---|---|---|---|---|---|
| xmlstreamer-ng per-item | 917k | 930k | 1.363 | 32.7% | 123.2 | 73 | 1 | per-item dicts |
| XmlSource columnar | 4.6M | 4.8M | 0.236 | 17.2% | 621.6 | 297 | 1 | Arrow batches |
| XmlSource parallel (8 threads) | 15.8M | 17.7M | 0.063 | 15.0% | 2122.6 | 283 | 8 | Arrow batches, 8 threads |
| XmlSource bounded parallel streaming | 10.2M | 10.3M | 0.346 | 269.8% | 1364.7 | 202 | 8 | bounded batches, 8 threads |
| xmlstreamer (original) | 103k | 107k | 9.427 | 5.8% | 13.8 | 34 | 1 | per-item dicts |
| lxml iterparse (count) | 448k | 470k | 2.266 | 11.4% | 60.2 | 26 | 1 | iterparse + clear(), no records |
| stdlib ET iterparse (count) | 318k | 321k | 3.029 | 2.0% | 42.7 | 21 | 1 | iterparse + root.clear(), no records |
| lxml iterparse (dicts) | 304k | 318k | 3.137 | 4.5% | 40.8 | 26 | 1 | per-item dicts |
| stdlib ET iterparse (dicts) | 280k | 287k | 3.434 | 3.5% | 37.6 | 21 | 1 | per-item dicts |
| xmltodict | 100k | 100k | 9.601 | 1.3% | 13.4 | 469 | 1 | whole-document dict |
| simdxml (Python) | 496k | 546k | 1.981 | 12.4% | 66.6 | 1067 | 1 | per-item dicts, whole-doc parse |
| simdxml parallel (Python) | 505k | 521k | 1.909 | 4.3% | 67.8 | 1065 | 16 | per-item dicts, parallel SIMD parse |
| quick-xml 0.37.5 | 3.2M | 3.2M | 0.295 | 0.0% | 433.0 | 14 | 1 | parse+count only, no data; best of N |
| simdxml 0.2.1 (git) | 1.6M | 1.6M | 0.605 | 0.0% | 211.3 | 730 | 1 | parse+count only, no data; best of N |
| pugixml 1.15 | 2.0M | 2.0M | 0.483 | 0.0% | 264.9 | 772 | 1 | parse+count only, no data; best of N |

Native rows are speed-only references (parse and count, no encoding detection, recovery contract, or data materialization).
