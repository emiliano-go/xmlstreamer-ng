# rypipe adapter benchmark

Date: 2026-10-20 | CPU: AMD Ryzen 7 5800X 8-Core Processor | Python 3.13.15 | xmlstreamer_ng 2.1.0, pyarrow 26.0.0

Synthetic plain feed (`feeds.py`): 127.9 MiB. Headline is the median of 5 rounds; best and p95 are shown beside it.

| engine | items | median s | best s | p95 s | spread | items/s (median) | MB/s | peak RSS MB |
|---|---|---|---|---|---|---|---|---|
| legacy (per-item) | 951,898 | 1.082 | 1.072 | 1.197 | 11.5% | 879,646 | 118.2 | 200.4 |
| rypipe columnar | 951,898 | 0.201 | 0.197 | 0.235 | 18.9% | 4,737,789 | 636.6 | 294.9 |
| rypipe par4 | 951,898 | 0.058 | 0.053 | 0.062 | 14.7% | 16,288,917 | 2,188.5 | 282.4 |
| rypipe par8 | 951,898 | 0.061 | 0.054 | 0.063 | 13.7% | 15,620,296 | 2,098.7 | 282.4 |
| rypipe par12 | 951,898 | 0.055 | 0.051 | 0.066 | 28.2% | 17,411,315 | 2,339.3 | 282.3 |
| rypipe stream64 | 951,898 | 0.202 | 0.201 | 0.231 | 14.8% | 4,704,057 | 632.0 | 266.8 |
| rypipe par-stream8 | 951,898 | 0.086 | 0.082 | 0.321 | 277.0% | 11,034,742 | 1,482.6 | 201.2 |
| rypipe columnar drop4 | 951,898 | 0.187 | 0.183 | 0.203 | 10.3% | 5,082,199 | 682.8 | 215.4 |
| rypipe columnar proj1 | 951,898 | 0.295 | 0.281 | 0.317 | 12.4% | 3,226,438 | 433.5 | 214.9 |
| rypipe par8 proj1 | 951,898 | 0.071 | 0.064 | 0.074 | 14.4% | 13,418,551 | 1,802.9 | 211.3 |
| stdlib ET iterparse | 951,898 | 2.758 | 2.708 | 2.862 | 5.6% | 345,190 | 46.4 | 20.5 |
| lxml iterparse (recover) | 951,898 | 1.943 | 1.872 | 1.949 | 3.9% | 489,814 | 65.8 | 25.7 |
