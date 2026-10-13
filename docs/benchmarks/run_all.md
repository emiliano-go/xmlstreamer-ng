# xmlstreamer benchmarks

Date: 2026-10-12 | CPU: AMD Ryzen 7 5800X 8-Core Processor | Python 3.14.8 | xmlstreamer_ng 1.1.0, xmlstreamer (original) 2.2.0, lxml 6.1.3, xmltodict 1.0.4, chardet 7.6.0

## Speed (parse-only, same in-memory bytes, best of N)

| feed | parser | items | seconds | items/s |
|---|---|---|---|---|
| plain | xmlstreamer-ng | 100,000 | 0.317 | 315,410 |
| plain | xmlstreamer (original) | 100,000 | 1.230 | 81,308 |
| plain | lxml iterparse (recover=True) | 100,000 | 0.322 | 310,292 |
| plain | stdlib ElementTree iterparse | 100,000 | 0.419 | 238,816 |
| plain | xmltodict | 100,000 | 1.234 | 81,017 |
| plain | xmltodict (streaming mode) | 100,000 | 1.191 | 83,998 |
| cdata | xmlstreamer-ng | 50,000 | 0.203 | 246,843 |
| cdata | xmlstreamer (original) | 50,000 | 0.802 | 62,347 |
| cdata | lxml iterparse (recover=True) | 50,000 | 0.276 | 181,023 |
| cdata | stdlib ElementTree iterparse | 50,000 | 0.252 | 198,112 |
| cdata | xmltodict | 50,000 | 0.719 | 69,503 |
| cdata | xmltodict (streaming mode) | 50,000 | 0.677 | 73,885 |
| plain | xmlstreamer end-to-end (HTTP) | 100,000 | 0.382 | 261,829 |

## Peak memory (one subprocess per parser, RSS)

| parser | feed MB | peak RSS MB | items | seconds |
|---|---|---|---|---|
| (python + imports baseline) | 121 | 15 | 0 | 0.00 |
| xmlstreamer-ng | 121 | 75 | 900,000 | 3.27 |
| xmlstreamer (original) | 121 | 34 | 900,000 | 12.32 |
| lxml iterparse (recover=True) | 121 | 20 | 900,000 | 3.08 |
| stdlib ElementTree iterparse | 121 | 16 | 900,000 | 4.03 |
| xmltodict (streaming mode) | 121 | 24 | 900,000 | 11.23 |
| xmltodict | 121 | 444 | 900,000 | 11.72 |

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
