# rypipe adapter benchmark

feed: /tmp/tmpq7jw8z37.xml (128.1 MiB)

| engine | items | seconds | items/s | MB/s | peak RSS MB |
|---|---|---|---|---|---|
| legacy (per-item) | 953,250 | 3.359 | 283,757 | 38.1 | 204.0 |
| rypipe columnar | 953,250 | 1.129 | 843,980 | 113.4 | 303.3 |
| rypipe par4 | 953,250 | 0.202 | 4,715,889 | 633.6 | 273.6 |
| rypipe par8 | 953,250 | 0.194 | 4,917,898 | 660.8 | 273.1 |
| rypipe par12 | 953,250 | 0.210 | 4,539,805 | 610.0 | 273.7 |
| rypipe stream64 | 953,250 | 1.148 | 830,417 | 111.6 | 188.5 |
| rypipe par-stream8 | 953,250 | 0.260 | 3,671,388 | 493.3 | 192.6 |
| rypipe columnar drop4 | 953,250 | 1.128 | 845,290 | 113.6 | 207.8 |
| rypipe columnar proj1 | 953,250 | 1.047 | 910,265 | 122.3 | 207.5 |
| rypipe par8 proj1 | 953,250 | 0.177 | 5,395,467 | 724.9 | 216.6 |
| stdlib ET iterparse | 953,250 | 3.943 | 241,773 | 32.5 | 18.4 |
| lxml iterparse (recover) | 953,250 | 2.290 | 416,351 | 55.9 | 20.9 |
