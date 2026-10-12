# rypipe adapter benchmark

feed: /tmp/tmpc8ch3hh0.xml (128.1 MiB)

| engine | items | seconds | items/s | MB/s | peak RSS MB |
|---|---|---|---|---|---|
| legacy (per-item) | 953,250 | 3.295 | 289,308 | 38.9 | 202.0 |
| rypipe columnar | 953,250 | 1.224 | 778,766 | 104.6 | 310.0 |
| rypipe par4 | 953,250 | 0.267 | 3,566,801 | 479.2 | 283.2 |
| rypipe par8 | 953,250 | 0.280 | 3,399,745 | 456.8 | 283.3 |
| rypipe par12 | 953,250 | 0.279 | 3,414,598 | 458.8 | 282.9 |
| rypipe stream64 | 953,250 | 1.192 | 799,854 | 107.5 | 146.0 |
| rypipe par-stream8 | 953,250 | 0.341 | 2,797,294 | 375.8 | 146.4 |
| rypipe columnar drop4 | 953,250 | 0.570 | 1,673,114 | 224.8 | 217.2 |
| rypipe columnar proj1 | 953,250 | 0.511 | 1,866,339 | 250.8 | 217.6 |
| rypipe par8 proj1 | 953,250 | 0.131 | 7,255,648 | 974.8 | 212.9 |
| stdlib ET iterparse | 953,250 | 3.223 | 295,756 | 39.7 | 17.6 |
| lxml iterparse (recover) | 953,250 | 2.727 | 349,523 | 47.0 | 24.7 |
