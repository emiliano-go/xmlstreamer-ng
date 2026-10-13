# xmlstreamer-ng benchmarks

Reproducible comparison against the original carlosplanchon `xmlstreamer`
package (PyPI: `xmlstreamer`), lxml, the stdlib and xmltodict, on three
axes: speed, peak memory, and behavior on broken input. Everything
runs with a single command:

```bash
uv run --group bench python benchmarks/run_all.py
```

`--quick` runs the same harness on tiny datasets (a smoke test for
automation; its numbers mean nothing). All feeds are synthetic and deterministic (`feeds.py`):
same call, same bytes, no randomness, no real-world data.

## What is measured, and how

**Speed** (`bench_speed.py`): parse-only throughput. Every parser
consumes the same in-memory bytes through the adapters in `parsers.py`,
each written in that library's best streaming idiom: lxml gets
`iterparse` plus the documented `clear()`/delete-siblings cleanup,
stdlib ElementTree gets `iterparse` plus `root.clear()`, xmltodict is
measured both as commonly used (whole document) and in its streaming
mode (`item_depth`/`item_callback`). xmlstreamer-ng runs its full local
pipeline including the startup encoding sniff, and the original
`xmlstreamer` 2.2.0 runs its `StreamInterpreter` over the same bytes.
Rounds are interleaved across parsers so CPU frequency drift hits
everyone equally, and the best of 7 rounds is kept. One extra row
measures xmlstreamer-ng end to end
over HTTP loopback (download + gzip check + encoding detection +
parsing); it is informative, not comparable with parse-only rows.
Absolute numbers move with the machine's thermal state between runs;
the ratios between parsers are far more stable, and those are the
numbers worth reading. One caveat measured on this hardware: deep
sustained throttling narrows every gap (a slower clock hurts the
fastest parsers most), so the published ratios come from the
less-throttled regime - the one LEAST favorable to xmlstreamer.

**Peak memory** (`bench_memory.py`): each parser runs alone in a fresh
subprocess and reports its own peak RSS - the high-water mark of
physical RAM the process occupied (`VmHWM` from `/proc/self/status`; `ru_maxrss` is not used because it survives
`exec()` and would report the parent's peak). The feed is written to
disk first and each parser reads it as it prefers. RSS is used instead
of `tracemalloc` because `tracemalloc` cannot see lxml/expat C
allocations.

**Dirty-feed gauntlet** (`gauntlet.py`): eight small feeds with
real-world damage (unclosed tags, raw `&`/`<`, lying encoding
declarations, truncated downloads, separator tags inside CDATA and
comments, a nested separator). Each case declares the items an honest
parser can deliver without guessing; verdicts are classified
automatically by comparing what each parser emitted against that
expectation. The failure modes that matter are the silent ones: items
lost with no signal, or text corrupted with no signal.

## Results

Date: 2026-10-12 | CPU: AMD Ryzen 7 5800X 8-Core Processor | Python 3.14.8 | xmlstreamer_ng 1.1.0, xmlstreamer (original) 2.2.0, lxml 6.1.3, xmltodict 1.0.4, chardet 7.6.0

### Speed (parse-only, same in-memory bytes, best of N)

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

### Peak memory (one subprocess per parser, RSS)

| parser | feed MB | peak RSS MB | items | seconds |
|---|---|---|---|---|
| (python + imports baseline) | 121 | 15 | 0 | 0.00 |
| xmlstreamer-ng | 121 | 75 | 900,000 | 3.27 |
| xmlstreamer (original) | 121 | 34 | 900,000 | 12.32 |
| lxml iterparse (recover=True) | 121 | 20 | 900,000 | 3.08 |
| stdlib ElementTree iterparse | 121 | 16 | 900,000 | 4.03 |
| xmltodict (streaming mode) | 121 | 24 | 900,000 | 11.23 |
| xmltodict | 121 | 444 | 900,000 | 11.72 |

### Dirty-feed gauntlet (what each parser does to broken input)

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

## Reading the results honestly

- On raw parse speed the Rust engine put xmlstreamer-ng ahead of lxml and
  the stdlib on both feed shapes in this run, and ~3.9x (flat) to ~4.0x
  (CDATA) ahead of the original pure-Python xmlstreamer 2.2.0, the fork's
  baseline; xmltodict trails on both. Absolute numbers move with the
  machine's thermal state between runs; the ratios between parsers are far
  more stable, and those are the numbers worth reading.
- On memory, every streaming parser is flat (16-75 MB on this run). The
  original xmlstreamer 2.2.0 peaked lowest (34 MB): its per-item Python
  dicts are transient, while xmlstreamer-ng's 75 MB carries the Rust
  engine plus Python-level plumbing. Both stay flat as the feed grows;
  whole-document parsing (xmltodict as commonly used) grows with the
  feed instead.
- The gauntlet is why this library exists: the recovery-mode column
  fabricates items and silently corrupts text, the strict columns lose
  the whole feed on the first broken byte. xmlstreamer delivers every
  intact item and logs what it drops. The nested-separator row is the
  documented limit of its contract, shown rather than hidden.
