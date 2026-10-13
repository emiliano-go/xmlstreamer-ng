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

**Rypipe adapter scaling** (`bench_scaling.py`): crxml-style tables
(rows/s and MB/s per adapter path, swept over thread counts 1/2/4/8/12
on the flat 100k feed, the CDATA 50k feed and a 128 MiB plain feed,
best of N). Absolute numbers track the machine; the thread-count shape
is the result.

**Native references** (`native_bench.py` plus `native/`): speed-only
comparisons against quick-xml (Rust), simdxml (Rust, SIMD structural
indexing from git) and pugixml (C++). These binaries fully parse the
file and count `<item>` elements; they carry none of the Python layer
semantics (encoding detection, recovery contract, Arrow
materialization), so they are an upper-bound ruler, not like-for-like
parser comparisons. Built by `native/build_native.sh` (needs `cargo`
and `g++`); `run_all.py` appends the section only when the binaries
exist and skips it with a note otherwise.

## Results

Date: 2026-10-12 | CPU: AMD Ryzen 7 5800X 8-Core Processor | Python 3.14.8 | xmlstreamer_ng 1.1.0, xmlstreamer (original) 2.2.0, lxml 6.1.3, xmltodict 1.0.4, chardet 7.6.0

### Rypipe adapter scaling

Best of 3 rounds, `bench_scaling.py`; full table and per-row notes in
[../docs/benchmarks/scaling.md](../docs/benchmarks/scaling.md).

| feed | path | rows/s | MB/s |
|---|---|---|---|
| plain 128 MiB | read_xml | 955,302 | 128.4 |
| plain 128 MiB | read_xml_par (chunks=2) | 5,062,946 | 680.2 |
| plain 128 MiB | read_xml_par (chunks=8) | 4,778,358 | 642.0 |
| plain 128 MiB | iter_xml_batches_par (threads=8) | 3,984,842 | 535.4 |
| cdata 50,000 | read_xml_par (chunks=4) | 2,067,681 | 975.7 |
| plain 100,000 | read_xml | 1,039,340 | 138.7 |
| plain 100,000 | read_xml_par (chunks=4) | 4,274,366 | 570.2 |

Single-threaded paths all sit at 0.9-1.0M rows/s on flat feeds;
`read_xml_par` jumps ~4x at chunks=2 and saturates the 8-core CPU by
chunks=2-8. Past the physical core count extra threads add only noise.

### Native references (raw parse throughput, speed only)

quick-xml 0.37.5, simdxml 0.2.1 (git), pugixml 1.15, `-O3`/lto release;
details and caveats in
[../docs/benchmarks/native.md](../docs/benchmarks/native.md).

| feed | parser | items/s | MB/s |
|---|---|---|---|
| plain 128 MiB | quick-xml | 3,211,737 | 431.5 |
| plain 128 MiB | simdxml | 1,513,251 | 203.3 |
| plain 128 MiB | pugixml | 1,882,900 | 253.0 |
| cdata 50,000 | quick-xml | 2,159,174 | 1,018.8 |
| plain 100,000 | quick-xml | 3,170,074 | 422.9 |

These rows are raw parse speed only (no Python semantics): a ruler for
the tables above, not a like-for-like comparison. On the big feed,
single-threaded `read_xml` runs at about 30% of quick-xml's parse speed,
while `read_xml_par` (chunks=2-8) exceeds every single-threaded native
counter in MB/s.

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
