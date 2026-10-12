# xmlstreamer benchmarks

Date: 2026-10-01 | CPU: 13th Gen Intel(R) Core(TM) i5-1335U | Python 3.13.13 | xmlstreamer 2.0.0, lxml 6.1.3, xmltodict 1.0.4, chardet 7.6.0

## Speed (parse-only, same in-memory bytes, best of N)

| feed | parser | items | seconds | items/s |
|---|---|---|---|---|
| plain | xmlstreamer | 100,000 | 0.490 | 204,220 |
| plain | lxml iterparse (recover=True) | 100,000 | 0.601 | 166,302 |
| plain | stdlib ElementTree iterparse | 100,000 | 0.545 | 183,649 |
| plain | xmltodict | 100,000 | 1.697 | 58,916 |
| plain | xmltodict (streaming mode) | 100,000 | 1.685 | 59,341 |
| cdata | xmlstreamer | 50,000 | 0.275 | 181,678 |
| cdata | lxml iterparse (recover=True) | 50,000 | 0.347 | 144,067 |
| cdata | stdlib ElementTree iterparse | 50,000 | 0.249 | 200,829 |
| cdata | xmltodict | 50,000 | 0.761 | 65,678 |
| cdata | xmltodict (streaming mode) | 50,000 | 0.873 | 57,302 |
| plain | xmlstreamer end-to-end (HTTP) | 100,000 | 0.577 | 173,448 |

## Peak memory (one subprocess per parser, RSS)

| parser | feed MB | peak RSS MB | items | seconds |
|---|---|---|---|---|
| (python + imports baseline) | 121 | 16 | 0 | 0.00 |
| xmlstreamer | 121 | 73 | 900,000 | 5.29 |
| lxml iterparse (recover=True) | 121 | 24 | 900,000 | 5.57 |
| stdlib ElementTree iterparse | 121 | 17 | 900,000 | 5.86 |
| xmltodict (streaming mode) | 121 | 22 | 900,000 | 18.08 |
| xmltodict | 121 | 443 | 900,000 | 17.25 |

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
