# Benchmark corpus

Small, hand-authored XML fixtures used by the corpus runner and the
conformance tests. Nothing here is third-party data.

- `valid/` holds well-formed feeds the parsers should ingest identically
  (modulo this library's documented record model: attributes are dropped,
  repeated tags are numbered, and output is a flat `{path: text}` map).
- `dirty/` holds damaged feeds used to compare recovery behavior. They
  are loaded by `benchmarks/corpus.py` and can be added to the gauntlet.

Keep files small (a few KiB) so a corpus run stays cheap. To add a feed,
drop it in the appropriate directory; deterministic fixtures only.

Run the corpus benchmark with:

```bash
uv run --group bench python benchmarks/bench_corpus.py
```
