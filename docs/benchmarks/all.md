# Consolidated comparison: all engines, one feed

Every engine reads the same synthetic plain feed from `feeds.py`:
128 MiB on disk, 953,250 items. This is the one feed all of them can
parse, so it is the common denominator for a single table. Timing is
best of 3 rounds.

Regenerate this table with:

```bash
python benchmarks/bench_all.py
```

`bench_all.py` writes the markdown to stdout (or a file with `--out`).
When the native binaries are not built it omits those rows and prints a
note; build them with `benchmarks/native/build_native.sh`.

## Results

Date: 2026-10-14 | CPU: AMD Ryzen 7 5800X 8-Core Processor | Python 3.13.15 | xmlstreamer-ng 2.0.0, xmlstreamer (original) 2.2.0, lxml 6.1.3, xmltodict 1.0.4, simdxml (Python) 0.3.0, pyarrow 26.0.0; quick-xml 0.37.5, simdxml 0.2.1 (git), pugixml 1.15

| engine | items/s | MB/s | peak RSS MB | threads | API/notes |
|---|---|---|---|---|---|
| xmlstreamer-ng per-item | 545k | 73.2 | 73 | 1 | per-item dicts |
| XmlSource columnar | 3.6M | 481.0 | 310 | 1 | Arrow batches |
| XmlSource parallel (8 threads) | 12.7M | 1704.2 | 285 | 8 | Arrow batches, 8 threads |
| XmlSource bounded parallel streaming | 10.6M | 1419.9 | 205 | 8 | bounded batches, 8 threads |
| xmlstreamer (original) | 98k | 13.2 | 33 | 1 | per-item dicts |
| lxml iterparse | 465k | 62.5 | 26 | 1 | iterparse + clear() |
| stdlib ET iterparse | 328k | 44.0 | 20 | 1 | iterparse + root.clear() |
| xmltodict | 98k | 13.1 | 469 | 1 | whole-document dict |
| simdxml (Python) | 489k | 65.7 | 1067 | 1 | per-item dicts, whole-doc parse |
| simdxml parallel (Python) | 455k | 61.1 | 1059 | 16 | per-item dicts, parallel SIMD parse |
| quick-xml 0.37.5 | 2.8M | 382.4 | 227 | 1 | parse+count only, no data |
| simdxml 0.2.1 (git) | 1.4M | 188.4 | 722 | 1 | parse+count only, no data |
| pugixml 1.15 | 2.0M | 267.7 | 773 | 1 | parse+count only, no data |

## How to read it

- items/s is derived from the measured MB/s and the known item count
  (953,250), rounded to 2-3 significant figures.
- Peak RSS for the Python engines is measured in a fresh `--worker`
  subprocess that runs the engine once and reports `VmHWM` from
  `/proc/self/status` (the convention used by `bench_memory.py` and
  `bench_rypipe.py`; `ru_maxrss` would inherit the forking parent's
  peak, and `VmHWM` restarts at exec).
- Peak RSS for the native counters has no Python layer to host a
  worker, so the binary is exec'd directly under `os.wait4` and its
  `ru_maxrss` is read from the returned rusage (no `/usr/bin/time`
  dependency).
- Native rows are speed-only references: those binaries parse and
  count elements but keep no records, do no encoding detection and
  have no recovery contract. Their RSS reflects that parse-only
  workload, so it is not comparable with the RSS of engines that
  materialize data (the xmlstreamer-ng parallel rows hold the full
  Arrow table; xmltodict holds the whole document dict).
- The two simdxml (Python) rows use the PyPI `simdxml` package
  (0.3.0, Rust engine with Python bindings): the whole document is
  parsed in memory, then per-item dicts are materialized from
  `xpath("//item")`. Its peak RSS is high because the parsed document
  and the element wrappers coexist in memory; the parallel variant
  (`parse(parallel=True)`) only parallelizes the SIMD structural
  indexing, not the Python-side record extraction, so it is barely
  faster on this feed.
- Per-feed speed, peak memory, adapter scaling and dirty-feed
  behavior live in the sibling documents (`run_all.md`, `scaling.md`,
  `native.md`); this table is the summary, those are the detail.

Absolute numbers track the machine; the ratios are stable across
runs.
