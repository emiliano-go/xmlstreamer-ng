# xmlstreamer benchmarks

Date: 2026-10-19 | CPU: AMD Ryzen 7 5800X 8-Core Processor | Python 3.13.15 | xmlstreamer_ng 2.1.0, xmlstreamer (original) 2.2.0, lxml 6.1.3, xmltodict 1.0.4, simdxml 0.3.0, chardet 7.6.0

## Speed (parse-only, same in-memory bytes, median of N rounds)

| feed | parser | items | median s | best s | p95 s | spread | items/s (median) |
|---|---|---|---|---|---|---|---|
| plain | xmlstreamer-ng | 100,000 | 0.150 | 0.144 | 0.272 | 85.7% | 668,128 |
| plain | xmlstreamer (original) | 100,000 | 0.916 | 0.889 | 0.982 | 10.1% | 109,130 |
| plain | lxml iterparse (recover=True) | 100,000 | 0.311 | 0.298 | 0.336 | 12.2% | 321,529 |
| plain | stdlib ElementTree iterparse | 100,000 | 0.332 | 0.322 | 0.357 | 10.5% | 301,071 |
| plain | xmltodict | 100,000 | 0.963 | 0.927 | 0.979 | 5.4% | 103,882 |
| plain | xmltodict (streaming mode) | 100,000 | 0.914 | 0.887 | 0.941 | 5.9% | 109,358 |
| plain | simdxml (Rust engine) | 100,000 | 0.153 | 0.148 | 0.168 | 13.4% | 652,991 |
| plain | simdxml (Rust engine, parallel parse) | 100,000 | 0.151 | 0.144 | 0.163 | 12.9% | 661,678 |
| cdata | xmlstreamer-ng | 50,000 | 0.092 | 0.088 | 0.096 | 8.7% | 544,408 |
| cdata | xmlstreamer (original) | 50,000 | 0.574 | 0.564 | 0.602 | 6.6% | 87,071 |
| cdata | lxml iterparse (recover=True) | 50,000 | 0.248 | 0.241 | 0.249 | 3.4% | 201,875 |
| cdata | stdlib ElementTree iterparse | 50,000 | 0.186 | 0.184 | 0.190 | 3.0% | 268,481 |
| cdata | xmltodict | 50,000 | 0.503 | 0.491 | 0.513 | 4.2% | 99,391 |
| cdata | xmltodict (streaming mode) | 50,000 | 0.470 | 0.460 | 0.486 | 5.6% | 106,411 |
| cdata | simdxml (Rust engine) | 50,000 | 0.094 | 0.090 | 0.099 | 9.0% | 530,563 |
| cdata | simdxml (Rust engine, parallel parse) | 50,000 | 0.091 | 0.089 | 0.100 | 12.4% | 552,107 |
| plain | xmlstreamer end-to-end (HTTP) | 100,000 | 0.179 | 0.175 | 0.189 | 7.5% | 557,692 |

## Peak memory (one subprocess per parser, RSS)

| parser | feed MB | peak RSS MB | items | seconds |
|---|---|---|---|---|
| (python + imports baseline) | 121 | 16 | 0 | 0.00 |
| xmlstreamer-ng | 121 | 87 | 900,000 | 1.36 |
| xmlstreamer (original) | 121 | 32 | 900,000 | 8.17 |
| lxml iterparse (recover=True) | 121 | 24 | 900,000 | 2.58 |
| stdlib ElementTree iterparse | 121 | 17 | 900,000 | 2.90 |
| xmltodict (streaming mode) | 121 | 22 | 900,000 | 8.20 |
| xmltodict | 121 | 442 | 900,000 | 8.29 |

## Dirty-feed gauntlet (what each parser does to broken input)

| case | xmlstreamer_ng | lxml (recover) | stdlib ET | xmltodict |
|---|---|---|---|---|
| healthy feed | OK | OK | OK | OK |
| malformed item between healthy ones | OK: drops broken loudly (warning logged) | FABRICATES: emits 3 where 2 are real | LOUD FAILURE: ParseError, feed lost (emitted 1 of 2 first) | LOUD FAILURE: ExpatError, feed lost (emitted 0 of 2 first) |
| raw ampersand and raw < in text | OK: drops broken loudly (warning logged) | FABRICATES: emits 2 where 1 are real | LOUD FAILURE: ParseError, feed lost (emitted 0 of 1 first) | LOUD FAILURE: ExpatError, feed lost (emitted 0 of 1 first) |
| declaration lies: says iso-8859-1, bytes are utf-8 | OK | SILENT CORRUPTION: {'t': 'coraÃ§Ã£o'} instead of {'t': 'coração'} | SILENT CORRUPTION: {'t': 'coraÃ§Ã£o'} instead of {'t': 'coração'} | SILENT CORRUPTION: {'t': 'coraÃ§Ã£o'} instead of {'t': 'coração'} |
| declaration lies: says utf-8, bytes are latin-1 | OK | SILENT CORRUPTION: {'t': 'programaci�n regi�n caf�'} instead of {'t': 'programación región café'} | LOUD FAILURE: ParseError, feed lost (emitted 0 of 5 first) | LOUD FAILURE: ExpatError, feed lost (emitted 0 of 5 first) |
| CDATA with literal </item> plus commented-out item | OK | OK | OK | OK |
| download truncated mid-item | OK | FABRICATES: emits 3 where 2 are real | LOUD FAILURE: ParseError, feed lost (emitted 2 of 2 first) | LOUD FAILURE: ExpatError, feed lost (emitted 0 of 2 first) |
| nested separator (out of xmlstreamer's contract) | unsupported (documented contract) | parses it (emits 2) | parses it (emits 2) | parses it (emits 1) |

- malformed item between healthy ones: item b never closes its tag
- raw ampersand and raw < in text: only the clean item is deliverable without guessing
- download truncated mid-item: the third item never arrived; inventing it is corruption
- nested separator (out of xmlstreamer's contract): xmlstreamer documents this as unsupported

## Native references (raw parse throughput, speed only)

| feed | parser | items | best s | items/s | MB/s |
|---|---|---|---|---|---|
| plain 100,000 | quick-xml | 100,000 | 0.030 | 3,288,392 | 438.7 |
| plain 100,000 | simdxml | 100,000 | 0.043 | 2,303,882 | 307.4 |
| plain 100,000 | pugixml | 100,000 | 0.041 | 2,455,012 | 327.5 |
| cdata 50,000 | quick-xml | 50,000 | 0.022 | 2,324,176 | 1,096.7 |
| cdata 50,000 | simdxml | 50,000 | 0.027 | 1,833,449 | 865.1 |
| cdata 50,000 | pugixml | 50,000 | 0.022 | 2,286,028 | 1,078.7 |
| plain 128 MiB | quick-xml | 951,898 | 0.283 | 3,357,997 | 451.2 |
| plain 128 MiB | simdxml | 951,898 | 0.432 | 2,204,345 | 296.2 |
| plain 128 MiB | pugixml | 951,898 | 0.369 | 2,579,313 | 346.5 |

These binaries fully parse the file and count <item> elements. They carry none of the Python layer semantics (encoding detection, recovery contract, Arrow materialization): an upper-bound ruler, not a like-for-like parser comparison. Build them with benchmarks/native/build_native.sh.
