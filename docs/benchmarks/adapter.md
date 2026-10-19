# rypipe adapter benchmark

Date: 2026-10-19 | CPU: AMD Ryzen 7 5800X 8-Core Processor | Python 3.13.15 | xmlstreamer_ng 2.1.0, pyarrow 26.0.0

Synthetic plain feed (`feeds.py`): 127.9 MiB. Headline is the median of 5 rounds; best and p95 are shown beside it.

| engine | items | median s | best s | p95 s | spread | items/s (median) | MB/s | peak RSS MB |
|---|---|---|---|---|---|---|---|---|
| legacy (per-item) | 951,898 | 1.357 | 1.339 | 1.500 | 11.9% | 701,322 | 94.2 | 215.5 |
| rypipe columnar | 951,898 | 0.244 | 0.238 | 0.252 | 5.6% | 3,901,950 | 524.3 | 313.6 |
| rypipe par4 | 951,898 | 0.063 | 0.061 | 0.068 | 10.1% | 15,061,225 | 2,023.6 | 394.1 |
| rypipe par8 | 951,898 | 0.065 | 0.057 | 0.069 | 19.3% | 14,603,825 | 1,962.1 | 419.2 |
| rypipe par12 | 951,898 | 0.061 | 0.057 | 0.071 | 23.9% | 15,507,751 | 2,083.6 | 432.6 |
| rypipe stream64 | 951,898 | 0.267 | 0.260 | 0.280 | 7.4% | 3,562,754 | 478.7 | 296.3 |
| rypipe par-stream8 | 951,898 | 0.096 | 0.091 | 0.357 | 277.5% | 9,920,134 | 1,332.8 | 213.6 |
| rypipe columnar drop4 | 951,898 | 0.227 | 0.225 | 0.235 | 4.7% | 4,196,583 | 563.8 | 228.0 |
| rypipe columnar proj1 | 951,898 | 0.287 | 0.278 | 0.300 | 7.6% | 3,317,122 | 445.7 | 228.2 |
| rypipe par8 proj1 | 951,898 | 0.072 | 0.063 | 0.076 | 16.9% | 13,180,335 | 1,770.9 | 280.2 |
| stdlib ET iterparse | 951,898 | 2.976 | 2.941 | 3.013 | 2.4% | 319,881 | 43.0 | 20.5 |
| lxml iterparse (recover) | 951,898 | 1.954 | 1.943 | 2.035 | 4.7% | 487,122 | 65.4 | 25.8 |
