# xmlstreamer benchmarks

Date: 2026-10-14 | CPU: AMD Ryzen 7 5800X 8-Core Processor | Python 3.13.15 | xmlstreamer_ng 2.0.0, xmlstreamer (original) 2.2.0, lxml 6.1.3, xmltodict 1.0.4, simdxml 0.3.0, chardet 7.6.0

## Speed (parse-only, same in-memory bytes, best of N)

| feed | parser | items | seconds | items/s |
|---|---|---|---|---|
| plain | xmlstreamer-ng | 100,000 | 0.139 | 720,203 |
| plain | xmlstreamer (original) | 100,000 | 0.942 | 106,183 |
| plain | lxml iterparse (recover=True) | 100,000 | 0.311 | 321,611 |
| plain | stdlib ElementTree iterparse | 100,000 | 0.333 | 300,736 |
| plain | xmltodict | 100,000 | 0.987 | 101,340 |
| plain | xmltodict (streaming mode) | 100,000 | 0.943 | 106,061 |
| plain | simdxml (Rust engine) | 100,000 | 0.186 | 537,246 |
| plain | simdxml (Rust engine, parallel parse) | 100,000 | 0.158 | 633,037 |
| cdata | xmlstreamer-ng | 50,000 | 0.089 | 558,813 |
| cdata | xmlstreamer (original) | 50,000 | 0.598 | 83,599 |
| cdata | lxml iterparse (recover=True) | 50,000 | 0.256 | 195,416 |
| cdata | stdlib ElementTree iterparse | 50,000 | 0.185 | 270,312 |
| cdata | xmltodict | 50,000 | 0.536 | 93,299 |
| cdata | xmltodict (streaming mode) | 50,000 | 0.494 | 101,250 |
| cdata | simdxml (Rust engine) | 50,000 | 0.102 | 488,351 |
| cdata | simdxml (Rust engine, parallel parse) | 50,000 | 0.098 | 512,491 |
| plain | xmlstreamer end-to-end (HTTP) | 100,000 | 0.191 | 523,783 |

## Peak memory (one subprocess per parser, RSS)

| parser | feed MB | peak RSS MB | items | seconds |
|---|---|---|---|---|
| (python + imports baseline) | 121 | 16 | 0 | 0.00 |
| xmlstreamer-ng | 121 | 72 | 900,000 | 1.41 |
| xmlstreamer (original) | 121 | 32 | 900,000 | 8.46 |
| lxml iterparse (recover=True) | 121 | 23 | 900,000 | 2.69 |
| stdlib ElementTree iterparse | 121 | 17 | 900,000 | 2.91 |
| xmltodict (streaming mode) | 121 | 22 | 900,000 | 8.43 |
| xmltodict | 121 | 442 | 900,000 | 8.84 |

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
| plain 100,000 | quick-xml | 100,000 | 0.031 | 3,178,741 | 424.1 |
| plain 100,000 | simdxml | 100,000 | 0.066 | 1,509,730 | 201.4 |
| plain 100,000 | pugixml | 100,000 | 0.045 | 2,210,775 | 294.9 |
| cdata 50,000 | quick-xml | 50,000 | 0.023 | 2,193,367 | 1,035.0 |
| cdata 50,000 | simdxml | 50,000 | 0.049 | 1,022,432 | 482.4 |
| cdata 50,000 | pugixml | 50,000 | 0.028 | 1,793,400 | 846.2 |
| plain 128 MiB | quick-xml | 953,250 | 0.307 | 3,105,949 | 417.3 |
| plain 128 MiB | simdxml | 953,250 | 0.603 | 1,579,567 | 212.2 |
| plain 128 MiB | pugixml | 953,250 | 0.464 | 2,054,210 | 276.0 |

These binaries fully parse the file and count <item> elements. They carry none of the Python layer semantics (encoding detection, recovery contract, Arrow materialization): an upper-bound ruler, not a like-for-like parser comparison. Build them with benchmarks/native/build_native.sh.
