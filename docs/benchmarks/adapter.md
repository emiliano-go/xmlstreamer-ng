# rypipe adapter benchmark

feed: /tmp/tmprfd8u2rk.xml (128.1 MiB)

| engine | items | seconds | items/s | MB/s | peak RSS MB |
|---|---|---|---|---|---|
| legacy (per-item) | 953,250 | 1.664 | 572,978 | 77.0 | 203.2 |
| rypipe columnar | 953,250 | 0.528 | 1,805,611 | 242.6 | 318.3 |
| rypipe par4 | 953,250 | 0.101 | 9,451,846 | 1,269.9 | 306.6 |
| rypipe par8 | 953,250 | 0.098 | 9,760,615 | 1,311.4 | 308.8 |
| rypipe par12 | 953,250 | 0.100 | 9,505,147 | 1,277.1 | 310.0 |
| rypipe stream64 | 953,250 | 0.575 | 1,658,828 | 222.9 | 198.5 |
| rypipe par-stream8 | 953,250 | 0.130 | 7,342,539 | 986.5 | 203.8 |
| rypipe columnar drop4 | 953,250 | 0.500 | 1,906,528 | 256.2 | 218.4 |
| rypipe columnar proj1 | 953,250 | 0.514 | 1,853,616 | 249.0 | 217.6 |
| rypipe par8 proj1 | 953,250 | 0.098 | 9,694,294 | 1,302.5 | 278.9 |
| stdlib ET iterparse | 953,250 | 3.212 | 296,811 | 39.9 | 18.4 |
| lxml iterparse (recover) | 953,250 | 1.778 | 536,071 | 72.0 | 20.9 |
