# corpus benchmark

Date: 2026-10-19 | CPU: AMD Ryzen 7 5800X 8-Core Processor | Python 3.13.15 | xmlstreamer_ng 2.1.0, lxml 6.1.3

Corpus: `benchmarks/corpus/valid` (9 files). Median of 50 rounds; spread is not shown because a trace fixture's runtime is dominated by fixed per-call overhead.

| file | parser | items | median ms | best ms | p95 ms | items/s | MB/s |
|---|---|---|---|---|---|---|---|
| attributes.xml | xmlstreamer-ng | 2 | 0.007 | 0.007 | 0.021 | 268,132 | 35.80 |
| attributes.xml | lxml | 2 | 0.017 | 0.013 | 0.032 | 115,254 | 15.39 |
| attributes.xml | stdlib ET | 2 | 0.026 | 0.020 | 0.045 | 77,239 | 10.31 |
| bom_utf8.xml | xmlstreamer-ng | 1 | 0.005 | 0.005 | 0.010 | 187,970 | 15.24 |
| bom_utf8.xml | lxml | 1 | 0.011 | 0.009 | 0.026 | 92,503 | 7.50 |
| bom_utf8.xml | stdlib ET | 1 | 0.017 | 0.015 | 0.028 | 60,129 | 4.87 |
| cdata_mixed.xml | xmlstreamer-ng | 2 | 0.010 | 0.008 | 0.016 | 195,418 | 34.76 |
| cdata_mixed.xml | lxml | 2 | 0.021 | 0.013 | 0.034 | 94,429 | 16.80 |
| cdata_mixed.xml | stdlib ET | 2 | 0.023 | 0.020 | 0.047 | 85,308 | 15.17 |
| charrefs.xml | xmlstreamer-ng | 2 | 0.007 | 0.007 | 0.016 | 278,804 | 23.93 |
| charrefs.xml | lxml | 2 | 0.012 | 0.011 | 0.016 | 167,469 | 14.37 |
| charrefs.xml | stdlib ET | 2 | 0.018 | 0.017 | 0.029 | 110,626 | 9.50 |
| comments_pi.xml | xmlstreamer-ng | 2 | 0.008 | 0.007 | 0.015 | 261,130 | 37.48 |
| comments_pi.xml | lxml | 2 | 0.014 | 0.013 | 0.029 | 141,583 | 20.32 |
| comments_pi.xml | stdlib ET | 2 | 0.019 | 0.017 | 0.037 | 106,607 | 15.30 |
| deep_nesting.xml | xmlstreamer-ng | 2 | 0.007 | 0.007 | 0.014 | 271,242 | 23.67 |
| deep_nesting.xml | lxml | 2 | 0.012 | 0.012 | 0.030 | 164,298 | 14.34 |
| deep_nesting.xml | stdlib ET | 2 | 0.020 | 0.019 | 0.029 | 100,740 | 8.79 |
| encoding_latin1.xml | xmlstreamer-ng | 1 | 0.082 | 0.078 | 0.104 | 12,210 | 1.19 |
| encoding_latin1.xml | lxml | 1 | 0.011 | 0.010 | 0.017 | 95,152 | 9.26 |
| encoding_latin1.xml | stdlib ET | 1 | 0.015 | 0.014 | 0.027 | 66,609 | 6.48 |
| namespaces.xml | xmlstreamer-ng | 2 | 0.007 | 0.006 | 0.013 | 299,289 | 45.53 |
| namespaces.xml | lxml | 2 | 0.017 | 0.014 | 0.033 | 118,263 | 17.99 |
| namespaces.xml | stdlib ET | 2 | 0.037 | 0.023 | 0.048 | 54,490 | 8.29 |
| repeated_fields.xml | xmlstreamer-ng | 2 | 0.008 | 0.007 | 0.019 | 250,470 | 27.47 |
| repeated_fields.xml | lxml | 2 | 0.022 | 0.014 | 0.028 | 90,122 | 9.88 |
| repeated_fields.xml | stdlib ET | 2 | 0.021 | 0.019 | 0.032 | 96,740 | 10.61 |
