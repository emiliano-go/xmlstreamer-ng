Common feed: synthetic plain feed (`feeds.py`), 128 MiB target, 951,898 items. Headline is the median of 5 rounds; best and p95 are shown beside it.

Date: 2026-10-19 | CPU: AMD Ryzen 7 5800X 8-Core Processor | Python 3.13.15 | xmlstreamer-ng 2.1.0, xmlstreamer (original) 2.2.0, lxml 6.1.3, xmltodict 1.0.4, simdxml (Python) 0.3.0, pyarrow 26.0.0; quick-xml 0.37.5, simdxml 0.2.1 (git), pugixml 1.15

| engine | items/s (median) | best items/s | p95 s | spread | MB/s | peak RSS MB | threads | API/notes |
|---|---|---|---|---|---|---|---|---|
| xmlstreamer-ng per-item | 567k | 600k | 1.723 | 8.0% | 76.2 | 88 | 1 | per-item dicts |
| XmlSource columnar | 3.9M | 3.9M | 0.250 | 3.4% | 527.6 | 315 | 1 | Arrow batches |
| XmlSource parallel (8 threads) | 16.5M | 17.2M | 0.062 | 12.3% | 2214.1 | 326 | 8 | Arrow batches, 8 threads |
| XmlSource bounded parallel streaming | 11.2M | 11.9M | 0.331 | 294.4% | 1501.0 | 214 | 8 | bounded batches, 8 threads |
| xmlstreamer (original) | 111k | 112k | 8.762 | 2.9% | 14.9 | 34 | 1 | per-item dicts |
| lxml iterparse (count) | 493k | 508k | 1.945 | 3.7% | 66.2 | 26 | 1 | iterparse + clear(), no records |
| stdlib ET iterparse (count) | 339k | 347k | 2.888 | 5.1% | 45.6 | 21 | 1 | iterparse + root.clear(), no records |
| lxml iterparse (dicts) | 334k | 335k | 2.927 | 3.1% | 44.9 | 26 | 1 | per-item dicts |
| stdlib ET iterparse (dicts) | 308k | 310k | 3.153 | 2.7% | 41.4 | 21 | 1 | per-item dicts |
| xmltodict | 101k | 109k | 9.513 | 7.9% | 13.5 | 469 | 1 | whole-document dict |
| simdxml (Python) | 506k | 531k | 1.899 | 5.6% | 67.9 | 1066 | 1 | per-item dicts, whole-doc parse |
| simdxml parallel (Python) | 531k | 535k | 1.858 | 4.4% | 71.4 | 1067 | 16 | per-item dicts, parallel SIMD parse |
| quick-xml 0.37.5 | 3.2M | 3.2M | 0.297 | 0.0% | 429.9 | 14 | 1 | parse+count only, no data; best of N |
| simdxml 0.2.1 (git) | 1.7M | 1.7M | 0.546 | 0.0% | 234.0 | 730 | 1 | parse+count only, no data; best of N |
| pugixml 1.15 | 2.3M | 2.3M | 0.415 | 0.0% | 308.2 | 773 | 1 | parse+count only, no data; best of N |

Native rows are speed-only references (parse and count, no encoding detection, recovery contract, or data materialization).
