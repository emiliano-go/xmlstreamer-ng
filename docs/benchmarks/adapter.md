# rypipe adapter benchmark

feed: /tmp/tmp5zulbpee.xml (128.1 MiB)

| engine | items | seconds | items/s | MB/s | peak RSS MB |
|---|---|---|---|---|---|
| legacy (per-item) | 953,250 | 1.398 | 681,884 | 91.6 | 201.2 |
| rypipe columnar | 953,250 | 0.258 | 3,697,114 | 496.7 | 308.4 |
| rypipe par4 | 953,250 | 0.070 | 13,637,406 | 1,832.3 | 284.7 |
| rypipe par8 | 953,250 | 0.069 | 13,877,722 | 1,864.6 | 284.9 |
| rypipe par12 | 953,250 | 0.068 | 14,013,047 | 1,882.7 | 284.9 |
| rypipe stream64 | 953,250 | 0.279 | 3,414,620 | 458.8 | 268.5 |
| rypipe par-stream8 | 953,250 | 0.094 | 10,191,722 | 1,369.3 | 203.9 |
| rypipe columnar drop4 | 953,250 | 0.241 | 3,959,402 | 532.0 | 216.2 |
| rypipe columnar proj1 | 953,250 | 0.302 | 3,153,942 | 423.8 | 215.3 |
| rypipe par8 proj1 | 953,250 | 0.072 | 13,178,084 | 1,770.6 | 212.6 |
| stdlib ET iterparse | 953,250 | 2.811 | 339,090 | 45.6 | 17.5 |
| lxml iterparse (recover) | 953,250 | 1.929 | 494,183 | 66.4 | 24.1 |
