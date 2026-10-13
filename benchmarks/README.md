# xmlstreamer-ng benchmarks

Reproducible comparison against the original carlosplanchon `xmlstreamer`
package (PyPI: `xmlstreamer`), lxml, the stdlib and xmltodict, on three
axes: speed, peak memory, and behavior on broken input. Everything
runs with a single command:

```bash
uv run --group bench python benchmarks/run_all.py
```

For one consolidated table with every engine (Python and native) on the
same 128 MiB feed, run `bench_all.py`; its output feeds the README
Performance section and [../docs/benchmarks/all.md](../docs/benchmarks/all.md).

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
mode (`item_depth`/`item_callback`). The simdxml rows use the PyPI
`simdxml` package (Rust engine with Python bindings): the whole document
is parsed in memory, then per-item dicts are materialized from
`xpath("//item")`; the parallel row passes `parallel=True` to the parse.
xmlstreamer-ng runs its full local
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

Date: 2026-10-13 | CPU: AMD Ryzen 7 5800X 8-Core Processor | Python 3.14.8 | xmlstreamer_ng 1.1.0, xmlstreamer (original) 2.2.0, lxml 6.1.3, xmltodict 1.0.4, simdxml 0.3.0, chardet 7.6.0

### All engines, one feed (consolidated)

Best of 3 rounds, `bench_all.py`; same table in the README Performance
section and in [../docs/benchmarks/all.md](../docs/benchmarks/all.md).
Every engine reads the same 128 MiB plain feed (953,250 items). Peak RSS
for the Python engines is measured in a fresh subprocess; for the native
counters it comes from the process rusage.

Date: 2026-10-13 | CPU: AMD Ryzen 7 5800X 8-Core Processor | Python 3.14.8 | xmlstreamer-ng 1.1.0, xmlstreamer (original) 2.2.0, lxml 6.1.3, xmltodict 1.0.4, simdxml (Python) 0.3.0, pyarrow 26.0.0; quick-xml 0.37.5, simdxml 0.2.1 (git), pugixml 1.15

| engine | items/s | MB/s | peak RSS MB | threads | API/notes |
|---|---|---|---|---|---|
| xmlstreamer-ng per-item | 458k | 61.6 | 76 | 1 | per-item dicts |
| XmlSource columnar | 1.9M | 250.6 | 319 | 1 | Arrow batches |
| XmlSource parallel (8 threads) | 9.5M | 1269.9 | 369 | 8 | Arrow batches, 8 threads |
| XmlSource bounded parallel streaming | 8.0M | 1076.0 | 204 | 8 | bounded batches, 8 threads |
| xmlstreamer (original) | 93k | 12.5 | 35 | 1 | per-item dicts |
| lxml iterparse | 550k | 73.9 | 22 | 1 | iterparse + clear() |
| stdlib ET iterparse | 302k | 40.6 | 20 | 1 | iterparse + root.clear() |
| xmltodict | 90k | 12.0 | 471 | 1 | whole-document dict |
| simdxml (Python) | 591k | 79.4 | 1061 | 1 | per-item dicts, whole-doc parse |
| simdxml parallel (Python) | 555k | 74.6 | 1060 | 16 | per-item dicts, parallel SIMD parse |
| quick-xml 0.37.5 | 3.5M | 464.6 | 300 | 1 | parse+count only, no data |
| simdxml 0.2.1 (git) | 2.0M | 262.4 | 722 | 1 | parse+count only, no data |
| pugixml 1.15 | 2.5M | 339.6 | 773 | 1 | parse+count only, no data |

Native rows are speed-only references (parse and count, no encoding
detection, recovery contract, or data materialization); their RSS
reflects a parse-only workload that keeps no records. If the native
binaries are not built, `bench_all.py` omits those rows and says so.

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
| plain 128 MiB | quick-xml | 3,481,581 | 467.8 |
| plain 128 MiB | simdxml | 2,219,436 | 298.2 |
| plain 128 MiB | pugixml | 2,575,955 | 346.1 |
| cdata 50,000 | quick-xml | 2,226,874 | 1,050.8 |
| plain 100,000 | quick-xml | 3,434,420 | 458.2 |

These rows are raw parse speed only (no Python semantics): a ruler for
the tables above, not a like-for-like comparison. On the big feed,
single-threaded `read_xml` runs at about 30% of quick-xml's parse speed,
while `read_xml_par` (chunks=2-8) exceeds every single-threaded native
counter in MB/s.

### Speed (parse-only, same in-memory bytes, best of N)

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

### Peak memory (one subprocess per parser, RSS)

| parser | feed MB | peak RSS MB | items | seconds |
|---|---|---|---|---|
| (python + imports baseline) | 121 | 15 | 0 | 0.00 |
| xmlstreamer-ng | 121 | 75 | 900,000 | 1.78 |
| xmlstreamer (original) | 121 | 34 | 900,000 | 9.83 |
| lxml iterparse (recover=True) | 121 | 20 | 900,000 | 2.68 |
| stdlib ElementTree iterparse | 121 | 16 | 900,000 | 3.52 |
| xmltodict (streaming mode) | 121 | 24 | 900,000 | 9.63 |
| xmltodict | 121 | 444 | 900,000 | 10.00 |

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
  the stdlib on both feed shapes in this run, and ~5.9x (flat) to ~5.2x
  (CDATA) ahead of the original pure-Python xmlstreamer 2.2.0, the fork's
  baseline; xmltodict trails on both. The simdxml (Rust engine) rows are
  faster still on both feeds, but they are whole-document parsers: no
  streaming contract, no recovery semantics, and ~1 GB peak RSS on the
  128 MiB feed (see the consolidated table). Absolute numbers move with
  the machine's thermal state between runs; the ratios between parsers
  are far more stable, and those are the numbers worth reading.
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
