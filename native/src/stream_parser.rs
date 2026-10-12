//! The xmlstreamer scanner as a rypipe `StreamingRecordParser`.
//!
//! The resumable byte scanner stays in `crate::tokenizer::Engine` (it is the
//! format-specific part: section policy, delimiter validation, item
//! isolation). rypipe owns the driver, buffer compaction, EOF handshake and
//! the diagnostics channel; this adapter reports each isolated item as a
//! `StreamRecord` and forwards the engine's warnings.

use rypipe_core::{ParseDiagnostics, Result as RypipeResult, StreamingRecordParser};

use crate::tokenizer::{Engine, Log, Next};

/// One isolated item plus the metadata the Python `ParsedItem` carries.
pub struct StreamRecord {
    pub content: Vec<u8>,
    pub parsed: Option<Vec<(String, String)>>,
    pub replaced: bool,
    pub collisions: Vec<(String, String, String)>,
}

/// Format bytes the way Python's `repr(bytes)` does for the scanner warnings.
fn bytes_repr(bytes: &[u8]) -> String {
    // Python picks double quotes when the payload has a single quote but no
    // double quote; otherwise single quotes with escapes.
    let quote = if bytes.contains(&b'\'') && !bytes.contains(&b'"') {
        b'"'
    } else {
        b'\''
    };
    let mut out = String::from("b");
    out.push(quote as char);
    for &b in bytes {
        match b {
            b'\\' => out.push_str("\\\\"),
            c if c == quote => {
                out.push('\\');
                out.push(c as char);
            }
            b'\n' => out.push_str("\\n"),
            b'\r' => out.push_str("\\r"),
            b'\t' => out.push_str("\\t"),
            0x20..=0x7e => out.push(b as char),
            _ => out.push_str(&format!("\\x{b:02x}")),
        }
    }
    out.push(quote as char);
    out
}

fn report(log: Log, diag: &dyn ParseDiagnostics) {
    match log {
        Log::Unterminated {
            opener,
            limit,
            markup,
        } => diag.warning(
            "unterminated",
            &format!(
                "Unterminated {} after {} bytes: {}.",
                bytes_repr(&opener),
                limit,
                if markup {
                    "discarding whatever follows it"
                } else {
                    "reading it as text, not markup"
                }
            ),
        ),
        Log::MalformedTag { tag } => diag.warning(
            "malformed_tag",
            &format!(
                "Malformed separator tag {}: the item is delivered (its \
                 content parses), but the feed is not well-formed here.",
                bytes_repr(&tag)
            ),
        ),
        Log::EndedInItem { discarded } => diag.warning(
            "ended_in_item",
            &format!(
                "Feed ended inside an item: {} bytes discarded (the download \
                 was cut, or the last item is unclosed).",
                discarded
            ),
        ),
        Log::SectionEof { opener, discarded } => diag.warning(
            "section_eof",
            &format!(
                "Feed ended inside bytearray({}) that never closed: {} bytes discarded.",
                bytes_repr(&opener),
                discarded
            ),
        ),
        Log::FeedTimeout => diag.warning(
            "feed_timeout",
            "> XMLStreamer > Time budget exhausted while reading the feed: \
             stopping.",
        ),
    }
}

pub struct XmlStreamParser {
    engine: Engine,
}

impl XmlStreamParser {
    pub fn new(
        separator_tag: &str,
        buffer_size: usize,
        max_section_size: i64,
        on_limit_text: bool,
        deadline_secs: Option<f64>,
    ) -> Self {
        Self {
            engine: Engine::new(
                separator_tag,
                buffer_size,
                max_section_size,
                on_limit_text,
                deadline_secs,
            ),
        }
    }

    pub fn malformed_tags(&self) -> usize {
        self.engine.malformed_tags()
    }

    pub fn state_eof(&self) -> bool {
        matches!(self.engine.state(), crate::tokenizer::State::Eof)
    }
}

impl StreamingRecordParser for XmlStreamParser {
    type Record = StreamRecord;

    fn validate(&self, _bytes: &[u8]) -> RypipeResult<()> {
        // xmlstreamer tolerates invalid UTF-8 (bytes are replaced with
        // U+FFFD and counted), so no chunk-level rejection here.
        Ok(())
    }

    fn parse_available(
        &mut self,
        bytes: &[u8],
        eof: bool,
        emit: &mut dyn FnMut(StreamRecord),
        diag: &dyn ParseDiagnostics,
    ) -> RypipeResult<usize> {
        self.engine.feed(bytes);
        if eof {
            self.engine.finish();
        }
        loop {
            match self.engine.next_item() {
                Next::Item(item) => emit(StreamRecord {
                    content: item.content,
                    parsed: item.parsed,
                    replaced: item.replaced,
                    collisions: item.collisions,
                }),
                Next::NeedMore | Next::Eof => break,
            }
        }
        for log in self.engine.take_logs() {
            report(log, diag);
        }
        // The engine retains its own resumable buffer and partial-item bytes,
        // so everything the driver handed over has been absorbed.
        Ok(bytes.len())
    }
}
