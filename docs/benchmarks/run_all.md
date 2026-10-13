# xmlstreamer benchmarks

Date: 2026-10-13 | CPU: AMD Ryzen 7 5800X 8-Core Processor | Python 3.14.8 | xmlstreamer_ng 1.1.0, xmlstreamer (original) 2.2.0, lxml 6.1.3, xmltodict 1.0.4, simdxml 0.3.0, chardet 7.6.0

## Speed (parse-only, same in-memory bytes, best of N)

| feed | parser | items | seconds | items/s |
|---|---|---|---|---|
| plain | xmlstreamer-ng | 100,000 | 0.292 | 341,955 |
| plain | xmlstreamer (original) | 100,000 | 1.144 | 87,450 |
| plain | lxml iterparse (recover=True) | 100,000 | 0.312 | 320,639 |
| plain | stdlib ElementTree iterparse | 100,000 | 0.397 | 251,872 |
| plain | xmltodict | 100,000 | 1.153 | 86,694 |
| plain | xmltodict (streaming mode) | 100,000 | 1.112 | 89,960 |
| plain | simdxml (Rust engine) | 100,000 | 0.176 | 567,171 |
| plain | simdxml (Rust engine, parallel parse) | 100,000 | 0.161 | 622,415 |
| cdata | xmlstreamer-ng | 50,000 | 0.187 | 268,008 |
| cdata | xmlstreamer (original) | 50,000 | 0.746 | 67,014 |
| cdata | lxml iterparse (recover=True) | 50,000 | 0.248 | 201,219 |
| cdata | stdlib ElementTree iterparse | 50,000 | 0.234 | 213,485 |
| cdata | xmltodict | 50,000 | 0.626 | 79,905 |
| cdata | xmltodict (streaming mode) | 50,000 | 0.593 | 84,266 |
| cdata | simdxml (Rust engine) | 50,000 | 0.095 | 523,781 |
| cdata | simdxml (Rust engine, parallel parse) | 50,000 | 0.094 | 533,244 |
| plain | xmlstreamer end-to-end (HTTP) | 100,000 | 0.355 | 281,826 |

## Peak memory (one subprocess per parser, RSS)

| parser | feed MB | peak RSS MB | items | seconds |
|---|---|---|---|---|
| (python + imports baseline) | 121 | 15 | 0 | 0.00 |
| xmlstreamer-ng | 121 | 76 | 900,000 | 2.89 |
| xmlstreamer (original) | 121 | 34 | 900,000 | 10.78 |
| lxml iterparse (recover=True) | 121 | 20 | 900,000 | 2.91 |
| stdlib ElementTree iterparse | 121 | 16 | 900,000 | 3.83 |
| xmltodict (streaming mode) | 121 | 24 | 900,000 | 10.34 |
| xmltodict | 121 | 444 | 900,000 | 11.15 |

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
| plain 100,000 | quick-xml | 100,000 | 0.032 | 3,135,484 | 418.3 |
| plain 100,000 | simdxml | 100,000 | 0.046 | 2,160,527 | 288.2 |
| plain 100,000 | pugixml | 100,000 | 0.043 | 2,350,287 | 313.5 |
| cdata 50,000 | quick-xml | 50,000 | 0.024 | 2,077,016 | 980.1 |
| cdata 50,000 | simdxml | 50,000 | 0.041 | 1,230,224 | 580.5 |
| cdata 50,000 | pugixml | 50,000 | 0.025 | 2,014,992 | 950.8 |
| plain 128 MiB | quick-xml | 953,250 | 0.306 | 3,117,070 | 418.8 |
| plain 128 MiB | simdxml | 953,250 | 0.569 | 1,674,890 | 225.0 |
| plain 128 MiB | pugixml | 953,250 | 0.432 | 2,204,046 | 296.1 |

These binaries fully parse the file and count <item> elements. They carry none of the Python layer semantics (encoding detection, recovery contract, Arrow materialization): an upper-bound ruler, not a like-for-like parser comparison. Build them with benchmarks/native/build_native.sh.
