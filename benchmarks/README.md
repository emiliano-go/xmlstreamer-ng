# xmlstreamer benchmarks

Reproducible comparison against lxml, the stdlib and xmltodict, on three
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
mode (`item_depth`/`item_callback`). xmlstreamer runs its full local
pipeline including the startup encoding sniff. Rounds are interleaved
across parsers so CPU frequency drift hits everyone equally, and the
best of 7 rounds is kept. One extra row measures xmlstreamer end to end
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

Date: 2026-08-08 | CPU: 11th Gen Intel(R) Core(TM) i5-1135G7 @ 2.40GHz | Python 3.14.6 | xmlstreamer 2.0.0, lxml 6.1.1, xmltodict 1.0.4, chardet 7.4.3

### Speed (parse-only, same in-memory bytes, best of N)

| feed | parser | items | seconds | items/s |
|---|---|---|---|---|
| plain | xmlstreamer | 100,000 | 1.109 | 90,180 |
| plain | lxml iterparse (recover=True) | 100,000 | 0.399 | 250,668 |
| plain | stdlib ElementTree iterparse | 100,000 | 0.490 | 204,287 |
| plain | xmltodict | 100,000 | 1.676 | 59,653 |
| plain | xmltodict (streaming mode) | 100,000 | 1.626 | 61,497 |
| cdata | xmlstreamer | 50,000 | 0.826 | 60,554 |
| cdata | lxml iterparse (recover=True) | 50,000 | 0.450 | 111,133 |
| cdata | stdlib ElementTree iterparse | 50,000 | 0.404 | 123,726 |
| cdata | xmltodict | 50,000 | 0.986 | 50,699 |
| cdata | xmltodict (streaming mode) | 50,000 | 0.934 | 53,518 |
| plain | xmlstreamer end-to-end (HTTP) | 100,000 | 1.810 | 55,254 |

### Peak memory (one subprocess per parser, RSS)

| parser | feed MB | peak RSS MB | items | seconds |
|---|---|---|---|---|
| (python + imports baseline) | 121 | 17 | 0 | 0.00 |
| xmlstreamer | 121 | 31 | 900,000 | 14.98 |
| lxml iterparse (recover=True) | 121 | 25 | 900,000 | 5.74 |
| stdlib ElementTree iterparse | 121 | 18 | 900,000 | 7.19 |
| xmltodict (streaming mode) | 121 | 23 | 900,000 | 19.37 |
| xmltodict | 121 | 444 | 900,000 | 19.35 |

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

- On raw parse speed lxml and stdlib ElementTree are roughly 2-3x
  faster than xmlstreamer; xmltodict trails
  xmlstreamer on both feed shapes in the current run. Tens of
  thousands of items per second is still far more than a feed pipeline
  typically needs.
- On memory, every streaming parser is flat (18-31 MB on this run)
  and xmlstreamer sits with the pack: encoding detection is skipped
  entirely when the sample is already valid utf-8, and only
  legacy-encoded feeds pay chardet's transient startup peak.
  Whole-document parsing (xmltodict as commonly used) grows with the
  feed instead.
- The gauntlet is why this library exists: the recovery-mode column
  fabricates items and silently corrupts text, the strict columns lose
  the whole feed on the first broken byte. xmlstreamer delivers every
  intact item and logs what it drops. The nested-separator row is the
  documented limit of its contract, shown rather than hidden.
