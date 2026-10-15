//! Non-pyo3 entry points for the fuzz targets.
//!
//! Always compiled: the fuzz crate builds this library with
//! `--no-default-features`, so the Python bindings (and pyo3) are absent and
//! only the parser surface is linked. These thin wrappers expose the private
//! internals a fuzzer needs without widening the public API.

use std::collections::HashMap;

use rypipe_core::{MemoryBudget, NoopDiagnostics, Pipeline, RecordStream, StreamState};

use crate::parser::XmlParser;
use crate::splitter::XmlSplitter;
use crate::stream_parser::{StreamRecord, XmlStreamParser};

/// Cap fuzz input so one run stays fast even on large seeds.
const MAX_FUZZ_BYTES: usize = 1 << 20;
/// Separator used by every target; a valid name the fuzzer can match on.
const SEP: &str = "item";

fn bounded(bytes: &[u8]) -> &[u8] {
    &bytes[..bytes.len().min(MAX_FUZZ_BYTES)]
}

fn columnar_parser(strict: bool) -> XmlParser {
    XmlParser::new(SEP, HashMap::new(), None, strict, true)
}

/// Parse a whole (wrapped) item document. Returns `(parsed?, collisions)`.
pub fn parse_document(bytes: &[u8]) -> (bool, usize) {
    let result = crate::xml::parse_document(bounded(bytes));
    (result.parsed.is_some(), result.collisions.len())
}

/// Rows from the single-engine columnar read and the bounded spilling read.
/// The two must agree: the spill path only changes how batches are assembled.
pub fn columnar_rows(bytes: &[u8]) -> (usize, usize) {
    let bytes = bounded(bytes);
    let pipeline = Pipeline::new(XmlSplitter::new(SEP), columnar_parser(true));
    let single = pipeline
        .read_bytes(bytes)
        .map(|b| b.num_rows())
        .unwrap_or(usize::MAX);
    let streamed = pipeline
        .read_bytes_stream(bytes, MemoryBudget::new(1 << 20))
        .map(|batches| batches.iter().map(|b| b.num_rows()).sum())
        .unwrap_or(usize::MAX);
    (single, streamed)
}

/// Drive the streaming tokenizer over the bytes, returning the item count.
pub fn tokenizer_rows(bytes: &[u8]) -> usize {
    let bytes = bounded(bytes);
    let parser = XmlStreamParser::new(SEP, 128 * 1024, 16 * 1024 * 1024, true, None);
    let mut stream = RecordStream::new(parser);
    if stream.feed(bytes).is_err() {
        return 0;
    }
    let diag = NoopDiagnostics;
    let mut rows = 0usize;
    let drain = |stream: &mut RecordStream<XmlStreamParser>, rows: &mut usize| loop {
        let state = stream
            .parse(&mut |_rec: StreamRecord| *rows += 1, &diag)
            .unwrap_or(StreamState::Eof);
        match state {
            StreamState::Rows => continue,
            StreamState::NeedMore | StreamState::Eof => break,
        }
    };
    drain(&mut stream, &mut rows);
    stream.finish();
    drain(&mut stream, &mut rows);
    rows
}
