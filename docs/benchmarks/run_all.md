# xmlstreamer benchmarks

Date: 2026-10-13 | CPU: AMD Ryzen 7 5800X 8-Core Processor | Python 3.14.8 | xmlstreamer_ng 1.1.0, xmlstreamer (original) 2.2.0, lxml 6.1.3, xmltodict 1.0.4, simdxml 0.3.0, chardet 7.6.0

## Speed (parse-only, same in-memory bytes, best of N)

| feed | parser | items | seconds | items/s |
|---|---|---|---|---|
| plain | xmlstreamer-ng | 100,000 | 0.180 | 556,467 |
| plain | xmlstreamer (original) | 100,000 | 1.067 | 93,678 |
| plain | lxml iterparse (recover=True) | 100,000 | 0.293 | 341,521 |
| plain | stdlib ElementTree iterparse | 100,000 | 0.376 | 266,213 |
| plain | xmltodict | 100,000 | 1.088 | 91,951 |
| plain | xmltodict (streaming mode) | 100,000 | 1.050 | 95,207 |
| plain | simdxml (Rust engine) | 100,000 | 0.150 | 668,832 |
| plain | simdxml (Rust engine, parallel parse) | 100,000 | 0.146 | 685,844 |
| cdata | xmlstreamer-ng | 50,000 | 0.133 | 375,467 |
| cdata | xmlstreamer (original) | 50,000 | 0.696 | 71,865 |
| cdata | lxml iterparse (recover=True) | 50,000 | 0.237 | 210,833 |
| cdata | stdlib ElementTree iterparse | 50,000 | 0.226 | 221,693 |
| cdata | xmltodict | 50,000 | 0.599 | 83,508 |
| cdata | xmltodict (streaming mode) | 50,000 | 0.554 | 90,225 |
| cdata | simdxml (Rust engine) | 50,000 | 0.091 | 551,728 |
| cdata | simdxml (Rust engine, parallel parse) | 50,000 | 0.093 | 537,791 |
| plain | xmlstreamer end-to-end (HTTP) | 100,000 | 0.227 | 440,908 |

## Peak memory (one subprocess per parser, RSS)

| parser | feed MB | peak RSS MB | items | seconds |
|---|---|---|---|---|
| (python + imports baseline) | 121 | 15 | 0 | 0.00 |
| xmlstreamer-ng | 121 | 75 | 900,000 | 1.78 |
| xmlstreamer (original) | 121 | 34 | 900,000 | 9.83 |
| lxml iterparse (recover=True) | 121 | 20 | 900,000 | 2.68 |
| stdlib ElementTree iterparse | 121 | 16 | 900,000 | 3.52 |
| xmltodict (streaming mode) | 121 | 24 | 900,000 | 9.63 |
| xmltodict | 121 | 444 | 900,000 | 10.00 |

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
| plain 100,000 | quick-xml | 100,000 | 0.029 | 3,434,420 | 458.2 |
| plain 100,000 | simdxml | 100,000 | 0.044 | 2,281,334 | 304.3 |
| plain 100,000 | pugixml | 100,000 | 0.038 | 2,601,118 | 347.0 |
| cdata 50,000 | quick-xml | 50,000 | 0.022 | 2,226,874 | 1,050.8 |
| cdata 50,000 | simdxml | 50,000 | 0.029 | 1,726,221 | 814.5 |
| cdata 50,000 | pugixml | 50,000 | 0.024 | 2,127,207 | 1,003.7 |
| plain 128 MiB | quick-xml | 953,250 | 0.274 | 3,481,581 | 467.8 |
| plain 128 MiB | simdxml | 953,250 | 0.430 | 2,219,436 | 298.2 |
| plain 128 MiB | pugixml | 953,250 | 0.370 | 2,575,955 | 346.1 |

These binaries fully parse the file and count <item> elements. They carry none of the Python layer semantics (encoding detection, recovery contract, Arrow materialization): an upper-bound ruler, not a like-for-like parser comparison. Build them with benchmarks/native/build_native.sh.
