# xmlstreamer-ng benchmarks

Reproducible comparison against the original carlosplanchon `xmlstreamer`
package (PyPI: `xmlstreamer`), lxml, the stdlib and xmltodict, on three
axes: speed, peak memory, and behavior on broken input. Everything
runs with a single command:

```bash
uv run --group bench python benchmarks/run_all.py
```

For one consolidated table with every engine (Python and native) on the
same 128 MiB feed, run `bench_all.py`.

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
everyone equally, and the median of N rounds is the headline (best and
p95 are reported alongside). One extra row
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

**Dirty-feed gauntlet** (`gauntlet.py`): small feeds with
real-world damage (unclosed tags, raw `&`/`<`, lying encoding
declarations, truncated downloads, separator tags inside CDATA and
comments, a nested separator). Each case declares the items an honest
parser can deliver without guessing; verdicts are classified
automatically by comparing what each parser emitted against that
expectation. The failure modes that matter are the silent ones: items
lost with no signal, or text corrupted with no signal.

**Hand-authored corpus** (`corpus/` + `bench_corpus.py`): small valid and
dirty XML fixtures covering namespaces, attributes, CDATA, character
references, comments/PIs, deep nesting, repeated fields, encodings and
truncation. `tests/test_conformance.py` pins each fixture's expected
records and cross-checks the flat model against lxml.

**Rypipe adapter scaling** (`bench_scaling.py`): crxml-style tables
(rows/s and MB/s per adapter path, swept over thread counts 1/2/4/8/12
on the flat 100k feed, the CDATA 50k feed and a 128 MiB plain feed,
median of N rounds). Absolute numbers track the machine; the thread-count
shape is the result.

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

Results live in the generated documents under
[`../docs/benchmarks/`](../docs/benchmarks/), not here, so they cannot
drift from the harness output:

- [`run_all.md`](../docs/benchmarks/run_all.md) - speed, peak memory,
  dirty-feed gauntlet and native references (one command).
- [`all.md`](../docs/benchmarks/all.md) - the consolidated table, every
  engine on the same 128 MiB feed.
- [`adapter.md`](../docs/benchmarks/adapter.md) - adapter paths with
  projection and thread counts.
- [`scaling.md`](../docs/benchmarks/scaling.md) - crxml-style scaling
  sweep.
- [`corpus.md`](../docs/benchmarks/corpus.md) - the hand-authored
  corpus.
- [`native.md`](../docs/benchmarks/native.md) - the native counters.

The README's Performance section summarizes these; read the ratios
within a single table, not across documents from different runs.
