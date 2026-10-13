# xmlstreamer benchmarks

Date: 2026-10-13 | CPU: AMD Ryzen 7 5800X 8-Core Processor | Python 3.14.8 | xmlstreamer_ng 1.1.0, xmlstreamer (original) 2.2.0, lxml 6.1.3, xmltodict 1.0.4, simdxml 0.3.0, chardet 7.6.0

## Speed (parse-only, same in-memory bytes, best of N)

| feed | parser | items | seconds | items/s |
|---|---|---|---|---|
| plain | xmlstreamer-ng | 100,000 | 0.190 | 527,677 |
| plain | xmlstreamer (original) | 100,000 | 1.153 | 86,723 |
| plain | lxml iterparse (recover=True) | 100,000 | 0.312 | 320,585 |
| plain | stdlib ElementTree iterparse | 100,000 | 0.398 | 251,038 |
| plain | xmltodict | 100,000 | 1.153 | 86,713 |
| plain | xmltodict (streaming mode) | 100,000 | 1.117 | 89,540 |
| plain | simdxml (Rust engine) | 100,000 | 0.159 | 630,061 |
| plain | simdxml (Rust engine, parallel parse) | 100,000 | 0.157 | 636,401 |
| cdata | xmlstreamer-ng | 50,000 | 0.135 | 371,470 |
| cdata | xmlstreamer (original) | 50,000 | 0.734 | 68,118 |
| cdata | lxml iterparse (recover=True) | 50,000 | 0.249 | 200,892 |
| cdata | stdlib ElementTree iterparse | 50,000 | 0.247 | 202,352 |
| cdata | xmltodict | 50,000 | 0.634 | 78,813 |
| cdata | xmltodict (streaming mode) | 50,000 | 0.605 | 82,582 |
| cdata | simdxml (Rust engine) | 50,000 | 0.097 | 514,440 |
| cdata | simdxml (Rust engine, parallel parse) | 50,000 | 0.097 | 515,876 |
| plain | xmlstreamer end-to-end (HTTP) | 100,000 | 0.239 | 418,974 |

## Peak memory (one subprocess per parser, RSS)

| parser | feed MB | peak RSS MB | items | seconds |
|---|---|---|---|---|
| (python + imports baseline) | 121 | 15 | 0 | 0.00 |
| xmlstreamer-ng | 121 | 75 | 900,000 | 1.84 |
| xmlstreamer (original) | 121 | 33 | 900,000 | 10.76 |
| lxml iterparse (recover=True) | 121 | 20 | 900,000 | 2.91 |
| stdlib ElementTree iterparse | 121 | 16 | 900,000 | 3.77 |
| xmltodict (streaming mode) | 121 | 24 | 900,000 | 10.47 |
| xmltodict | 121 | 444 | 900,000 | 11.10 |

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

| feed | parser | items | seconds | items/s | MB/s |
|---|---|---|---|---|---|
| plain 100,000 | quick-xml | 100,000 | 0.030 | 3,340,794 | 445.7 |
| plain 100,000 | simdxml | 100,000 | 0.049 | 2,040,650 | 272.2 |
| plain 100,000 | pugixml | 100,000 | 0.041 | 2,430,075 | 324.2 |
| cdata 50,000 | quick-xml | 50,000 | 0.023 | 2,130,288 | 1,005.2 |
| cdata 50,000 | simdxml | 50,000 | 0.031 | 1,618,909 | 763.9 |
| cdata 50,000 | pugixml | 50,000 | 0.025 | 1,976,597 | 932.7 |
| plain 128 MiB | quick-xml | 953,250 | 0.292 | 3,261,148 | 438.2 |
| plain 128 MiB | simdxml | 953,250 | 0.451 | 2,114,987 | 284.2 |
| plain 128 MiB | pugixml | 953,250 | 0.418 | 2,282,922 | 306.7 |

These binaries fully parse the file and count <item> elements. They carry none of the Python layer semantics (encoding detection, recovery contract, Arrow materialization): an upper-bound ruler, not a like-for-like parser comparison. Build them with benchmarks/native/build_native.sh.
