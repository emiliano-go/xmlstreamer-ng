# rypipe adapter benchmark

feed: /tmp/tmp7_ec3rse.xml (128.1 MiB)

| engine | items | seconds | items/s | MB/s | peak RSS MB |
|---|---|---|---|---|---|
| legacy (per-item) | 953,250 | 3.244 | 293,837 | 39.5 | 217.1 |
| rypipe columnar | 953,250 | 0.969 | 983,437 | 132.1 | 291.6 |
| rypipe par4 | 953,250 | 0.491 | 1,943,220 | 261.1 | 290.8 |
| rypipe par8 | 953,250 | 0.461 | 2,069,375 | 278.0 | 298.1 |
| rypipe par12 | 953,250 | 0.591 | 1,612,872 | 216.7 | 304.2 |
| rypipe stream64 | 953,250 | 1.105 | 862,602 | 115.9 | 208.9 |
| rypipe par-stream8 | 953,250 | 0.240 | 3,964,141 | 532.6 | 210.7 |
| rypipe columnar drop4 | 953,250 | 1.106 | 861,885 | 115.8 | 231.9 |
| rypipe columnar proj1 | 953,250 | 0.955 | 998,633 | 134.2 | 231.1 |
| rypipe par8 proj1 | 953,250 | 0.230 | 4,149,721 | 557.5 | 254.6 |
| stdlib ET iterparse | 953,250 | 4.257 | 223,945 | 30.1 | 18.4 |
| lxml iterparse (recover) | 953,250 | 2.036 | 468,301 | 62.9 | 22.8 |
