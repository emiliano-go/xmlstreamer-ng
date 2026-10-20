# rypipe adapter benchmark

Date: 2026-10-20 | CPU: AMD Ryzen 7 5800X 8-Core Processor | Python 3.13.15 | xmlstreamer_ng 2.1.0, pyarrow 26.0.0

Synthetic plain feed (`feeds.py`): 127.9 MiB. Headline is the median of 5 rounds; best and p95 are shown beside it.

| engine | items | median s | best s | p95 s | spread | items/s (median) | MB/s | peak RSS MB |
|---|---|---|---|---|---|---|---|---|
| legacy (per-item) | 951,898 | 1.100 | 1.064 | 1.158 | 8.6% | 865,364 | 116.3 | 200.8 |
| rypipe columnar | 951,898 | 0.200 | 0.192 | 0.239 | 23.5% | 4,753,412 | 638.7 | 296.8 |
| rypipe par4 | 951,898 | 0.057 | 0.056 | 0.067 | 18.9% | 16,770,233 | 2,253.2 | 283.1 |
| rypipe par8 | 951,898 | 0.056 | 0.054 | 0.061 | 12.6% | 16,902,684 | 2,271.0 | 282.5 |
| rypipe par12 | 951,898 | 0.055 | 0.054 | 0.060 | 11.8% | 17,250,930 | 2,317.8 | 282.9 |
| rypipe stream64 | 951,898 | 0.217 | 0.204 | 0.239 | 15.7% | 4,387,192 | 589.4 | 267.5 |
| rypipe par-stream8 | 951,898 | 0.096 | 0.096 | 0.326 | 240.4% | 9,933,651 | 1,334.7 | 200.7 |
| rypipe columnar drop4 | 951,898 | 0.191 | 0.191 | 0.199 | 4.4% | 4,980,247 | 669.1 | 214.8 |
| rypipe columnar proj1 | 951,898 | 0.297 | 0.285 | 0.305 | 6.7% | 3,210,192 | 431.3 | 214.9 |
| rypipe par8 proj1 | 951,898 | 0.068 | 0.066 | 0.076 | 15.2% | 14,025,142 | 1,884.4 | 211.6 |
| stdlib ET iterparse | 951,898 | 2.796 | 2.772 | 2.826 | 1.9% | 340,456 | 45.7 | 20.5 |
| lxml iterparse (recover) | 951,898 | 1.950 | 1.941 | 2.009 | 3.5% | 488,190 | 65.6 | 25.7 |
