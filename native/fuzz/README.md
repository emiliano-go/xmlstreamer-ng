# xmlstreamer-ng fuzz targets

Coverage-guided fuzzing for the Rust parser. The targets link the crate with
`--no-default-features`, so the pyo3 bindings are absent and only the parser
surface is compiled; the entry points live in `src/fuzz_api.rs`.

Targets:

- `fuzz_parse_document`: whole-document parse (`xml::parse_document`), the
  per-item parser and its `unsafe` UTF-8 borrows.
- `fuzz_columnar`: `Pipeline::read_bytes` vs `read_bytes_stream`; the bounded
  spilling path must agree with the single-engine path (guards `SpillSink`).
- `fuzz_tokenizer`: the resumable streaming tokenizer over arbitrary bytes.

Run (needs a nightly toolchain and cargo-fuzz):

```bash
cargo install cargo-fuzz --locked
cd native
cargo +nightly fuzz run fuzz_parse_document
cargo +nightly fuzz run fuzz_columnar
cargo +nightly fuzz run fuzz_tokenizer
```

`seeds/` holds a few small starting inputs; CI copies them into each target's
corpus before a short smoke run.

## Why not Miri

Miri cannot run the engine: `rypipe-core` pulls in Arrow, whose SIMD and
`unsafe` do not run under Miri, and the crate is a `cdylib` with pyo3. The
fuzz targets above compile with cargo-fuzz's AddressSanitizer, which is the
practical sanitizer coverage for the `unsafe` UTF-8 borrows in `xml.rs`.
