# xmlstreamer benchmarks

Date: 2026-10-12 | CPU: AMD Ryzen 7 5800X 8-Core Processor | Python 3.14.8 | xmlstreamer 2.2.0, lxml 6.1.3, xmltodict 1.0.4, chardet 7.6.0

## Speed (parse-only, same in-memory bytes, best of N)

| feed | parser | items | seconds | items/s |
|---|---|---|---|---|
| plain | xmlstreamer | 100,000 | 0.293 | 341,469 |
| plain | lxml iterparse (recover=True) | 100,000 | 0.316 | 316,885 |
| plain | stdlib ElementTree iterparse | 100,000 | 0.397 | 251,891 |
| plain | xmltodict | 100,000 | 1.141 | 87,664 |
| plain | xmltodict (streaming mode) | 100,000 | 1.076 | 92,964 |
| cdata | xmlstreamer | 50,000 | 0.180 | 277,948 |
| cdata | lxml iterparse (recover=True) | 50,000 | 0.249 | 200,701 |
| cdata | stdlib ElementTree iterparse | 50,000 | 0.231 | 216,207 |
| cdata | xmltodict | 50,000 | 0.642 | 77,937 |
| cdata | xmltodict (streaming mode) | 50,000 | 0.600 | 83,383 |
| plain | xmlstreamer end-to-end (HTTP) | 100,000 | 0.390 | 256,158 |

## Peak memory (one subprocess per parser, RSS)

| parser | feed MB | peak RSS MB | items | seconds |
|---|---|---|---|---|
| (python + imports baseline) | 121 | 15 | 0 | 0.00 |
| xmlstreamer | 121 | 88 | 900,000 | 3.96 |
| lxml iterparse (recover=True) | 121 | 22 | 900,000 | 3.15 |
| stdlib ElementTree iterparse | 121 | 16 | 900,000 | 3.91 |
| xmltodict (streaming mode) | 121 | 24 | 900,000 | 11.00 |
| xmltodict | 121 | 444 | 900,000 | 11.28 |

## Dirty-feed gauntlet (what each parser does to broken input)

| case | xmlstreamer | lxml (recover) | stdlib ET | xmltodict |
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
