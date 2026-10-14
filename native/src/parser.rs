//! `rypipe_core::RecordParser` for xmlstreamer feeds.
//!
//! A chunk is aligned to record starts by `XmlSplitter`; this walks the
//! complete items inside it, flattens each into the same `{path: text}`
//! columns the streaming parser produces, and skips items that do not parse.
//! Every skip is counted in `ColumnarStats`; the Python entry points log the
//! counters after the read completes. A trailing partial item is left alone:
//! the engine discards it.

use std::borrow::Cow;
use std::cell::RefCell;
use std::collections::{HashMap, HashSet};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;

use rypipe_core::{ColumnarSink, RecordParser, Value};

use crate::scan;
use crate::xml::{self, FlatEmitter, Scratch};

/// Drop counters for the columnar/parallel reads, shared with every clone of
/// the parser (the engine clones it across rayon workers). The Python entry
/// points read them after a read completes and log a warning for anything
/// non-zero, the way the streaming path logs per item.
#[derive(Default)]
pub struct ColumnarStats {
    /// Items dropped whole because they did not parse.
    pub malformed_items: AtomicU64,
    /// Rows whose closing delimiter carried junk (`</sep junk>`): accepted as
    /// a boundary (as in the streaming scanner) but counted, like the
    /// streaming MALFORMED_TAGS counter.
    pub malformed_closing_tags: AtomicU64,
    /// Comment/CDATA/PI/DOCTYPE sections that never closed: everything after
    /// them in the chunk was discarded.
    pub unterminated_sections: AtomicU64,
    /// Bytes discarded because of unterminated sections.
    pub discarded_bytes: AtomicU64,
}

impl ColumnarStats {
    /// `(malformed_items, malformed_closing_tags, unterminated_sections,
    /// discarded_bytes)`
    pub fn snapshot(&self) -> (u64, u64, u64, u64) {
        (
            self.malformed_items.load(Ordering::Relaxed),
            self.malformed_closing_tags.load(Ordering::Relaxed),
            self.unterminated_sections.load(Ordering::Relaxed),
            self.discarded_bytes.load(Ordering::Relaxed),
        )
    }

    pub fn is_empty(&self) -> bool {
        self.snapshot() == (0, 0, 0, 0)
    }
}

/// The subset of `field_types` the adapter can parse directly while scanning.
#[derive(Clone, Copy)]
pub enum FieldKind {
    Int64,
    Float64,
    Bool,
}

/// Map declared `field_types` strings to a scannable kind (others fall back to
/// string values; the engine still casts them).
pub fn field_kinds(types: Option<HashMap<String, String>>) -> HashMap<String, FieldKind> {
    types
        .unwrap_or_default()
        .into_iter()
        .filter_map(|(name, ty)| {
            let kind = match ty.trim().to_ascii_lowercase().as_str() {
                "int64" | "int" | "i64" => FieldKind::Int64,
                "float64" | "float" | "f64" | "double" => FieldKind::Float64,
                "bool" | "boolean" => FieldKind::Bool,
                _ => return None,
            };
            Some((name, kind))
        })
        .collect()
}

/// The declared projection as a lookup set of *source* tag names, or None.
///
/// `schema` names are output names after `field_mapping`, so each one is
/// mapped back to the raw tag it renames; otherwise a mapped subtree would
/// look unwanted and be skipped whole.
pub fn keep_set(
    schema: Option<&Vec<String>>,
    field_mapping: Option<&HashMap<String, String>>,
) -> Option<HashSet<String>> {
    let names = schema?;
    if names.is_empty() {
        return None;
    }
    let mut set: HashSet<String> = HashSet::with_capacity(names.len());
    for out_name in names {
        if let Some(mapping) = field_mapping {
            if let Some((raw, _)) = mapping.iter().find(|(_, renamed)| *renamed == out_name)
            {
                set.insert(raw.clone());
                continue;
            }
        }
        set.insert(out_name.clone());
    }
    Some(set)
}

fn typed_value<'a>(kind: FieldKind, value: &'a str) -> Value<'a> {
    match kind {
        FieldKind::Int64 => value
            .trim()
            .parse::<i64>()
            .map(Value::Int64)
            .unwrap_or(Value::Str(Cow::Borrowed(value))),
        FieldKind::Float64 => value
            .trim()
            .parse::<f64>()
            .map(Value::Float64)
            .unwrap_or(Value::Str(Cow::Borrowed(value))),
        FieldKind::Bool => {
            let t = value.trim();
            if t == "1" || t.eq_ignore_ascii_case("true") || t.eq_ignore_ascii_case("yes") {
                Value::Bool(true)
            } else if t == "0"
                || t.eq_ignore_ascii_case("false")
                || t.eq_ignore_ascii_case("no")
            {
                Value::Bool(false)
            } else {
                Value::Str(Cow::Borrowed(value))
            }
        }
    }
}

// One reusable parse scratch per OS thread. The engine shares a single parser
// across rayon workers (and clones it for streaming), so a parser-owned
// `Mutex<Scratch>` would serialize every worker; a thread-local keeps the
// buffers per worker with no contention.
thread_local! {
    static SCRATCH: RefCell<Scratch> = RefCell::new(Scratch::default());
}

#[derive(Clone)]
pub struct XmlParser {
    sep: Vec<u8>,
    types: HashMap<String, FieldKind>,
    // Declared projection (schema_order): depth-1 subtrees with no wanted
    // descendant are skipped whole.
    keep: Option<HashSet<String>>,
    // Strict validates attribute values / text characters; fast (opt-in)
    // validates only element names and structure.
    strict: bool,
    // Whether the execution plan is the identity (no rename, drop, projection
    // or filter): `ColumnarSink::wants` can only answer "true" then, so the
    // per-field resolve/hash round trip is skipped.
    identity: bool,
    // Shared by every clone (the engine clones the parser per worker), so
    // drops counted on any thread land in one place the caller can read.
    stats: Arc<ColumnarStats>,
}

/// Emits one row per item, using the engine's layout-prediction fast path.
struct RowEmitter<'a, S: ColumnarSink + ?Sized> {
    sink: &'a mut S,
    types: &'a HashMap<String, FieldKind>,
    identity: bool,
    ordinal: u32,
}

impl<S: ColumnarSink + ?Sized> FlatEmitter for RowEmitter<'_, S> {
    fn row_start(&mut self) {
        self.sink.begin_row();
        self.ordinal = 0;
    }

    fn field(&mut self, name: &str, value: &str) {
        // With the identity plan the sink wants every field; skip its
        // resolve (two hash lookups per field) entirely.
        if !self.identity && !self.sink.wants(name) {
            return;
        }
        // Locate-only mode (schema discovery): the sink needs the name, not
        // the value. Push a null so the name is still recorded and skip value
        // extraction/parsing entirely.
        if !self.sink.needs_value() {
            self.sink.put_field(name, Value::Null);
            self.ordinal += 1;
            return;
        }
        let matched = self
            .sink
            .expect_slot(self.ordinal)
            .map(|(slot, expected)| (slot, name.as_bytes() == expected));
        match matched {
            Some((slot, true)) => {
                if self.types.is_empty() {
                    // No declared types: a plain string. Push it without
                    // building a `Value` (the common case).
                    self.sink.put_str_at(slot, value);
                } else {
                    let v = match self.types.get(name) {
                        Some(kind) => typed_value(*kind, value),
                        None => Value::Str(Cow::Borrowed(value)),
                    };
                    self.sink.put_field_at(slot, v);
                }
            }
            Some((_, false)) => {
                self.sink.layout_broken(self.ordinal);
                let v = match self.types.get(name) {
                    Some(kind) => typed_value(*kind, value),
                    None => Value::Str(Cow::Borrowed(value)),
                };
                self.sink.put_field(name, v);
            }
            None => {
                let v = match self.types.get(name) {
                    Some(kind) => typed_value(*kind, value),
                    None => Value::Str(Cow::Borrowed(value)),
                };
                self.sink.put_field(name, v);
            }
        }
        self.ordinal += 1;
    }

    fn row_end(&mut self) {
        self.sink.end_row();
    }

    fn wants(&self, name: &str) -> bool {
        self.sink.wants(name)
    }
}

impl XmlParser {
    pub fn new(
        separator_tag: &str,
        types: HashMap<String, FieldKind>,
        keep: Option<HashSet<String>>,
        strict: bool,
        identity: bool,
    ) -> Self {
        Self {
            sep: separator_tag.as_bytes().to_vec(),
            types,
            keep,
            strict,
            identity,
            stats: Arc::new(ColumnarStats::default()),
        }
    }

    /// The shared drop counters; clone the handle before moving the parser
    /// into the engine to inspect them after the read completes.
    pub fn stats(&self) -> Arc<ColumnarStats> {
        Arc::clone(&self.stats)
    }

    fn parse_into<S: ColumnarSink + ?Sized>(&self, bytes: &[u8], sink: &mut S) {
        let sep = std::str::from_utf8(&self.sep).unwrap_or("item");
        SCRATCH.with(|cell| {
            let mut scratch = cell.borrow_mut();
            self.scan_and_emit(bytes, sep, &mut scratch, sink);
        });
    }

    fn scan_and_emit<S: ColumnarSink + ?Sized>(
        &self,
        bytes: &[u8],
        sep: &str,
        scratch: &mut Scratch,
        sink: &mut S,
    ) {
        let stats = &*self.stats;
        let mut i = 0usize;
        loop {
            let mut open_unterminated = false;
            let Some((start, after_open)) =
                scan::find_open_sep_ex(bytes, i, &self.sep, &mut open_unterminated)
            else {
                if open_unterminated {
                    // A comment/CDATA/PI/DOCTYPE never closes: everything
                    // after it in this chunk is discarded. Count it loudly;
                    // the caller logs after the read completes.
                    stats.unterminated_sections.fetch_add(1, Ordering::Relaxed);
                    stats
                        .discarded_bytes
                        .fetch_add((bytes.len() - i) as u64, Ordering::Relaxed);
                }
                break;
            };
            if scan::is_self_closing(&bytes[start..after_open]) {
                i = after_open;
                continue;
            }

            let mut emitter = RowEmitter {
                sink: &mut *sink,
                types: &self.types,
                identity: self.identity,
                ordinal: 0,
            };
            // Fused scan + parse: one pass over the item's bytes. A malformed
            // item emits nothing; resync on its close tag and drop it.
            let mut malformed_close = 0u64;
            match xml::parse_item_fused(
                scratch,
                bytes,
                after_open,
                sep,
                self.keep.as_ref(),
                self.strict,
                &mut emitter,
                &mut malformed_close,
            ) {
                xml::Fused::Complete { resume } => {
                    stats
                        .malformed_closing_tags
                        .fetch_add(malformed_close, Ordering::Relaxed);
                    i = resume;
                }
                xml::Fused::Incomplete => {
                    // The item is incomplete in this chunk: the engine drops
                    // the trailing partial row.
                    break;
                }
                xml::Fused::Unterminated => {
                    // A section inside the item never closes: the item and
                    // everything after it in this chunk are discarded.
                    stats.unterminated_sections.fetch_add(1, Ordering::Relaxed);
                    stats
                        .discarded_bytes
                        .fetch_add((bytes.len() - start) as u64, Ordering::Relaxed);
                    break;
                }
                xml::Fused::Malformed => {
                    stats.malformed_items.fetch_add(1, Ordering::Relaxed);
                    let mut close_unterminated = false;
                    match scan::find_close_sep_ex(
                        bytes,
                        after_open,
                        &self.sep,
                        &mut close_unterminated,
                        &mut malformed_close,
                    ) {
                        Some((_close, after_close)) => {
                            stats
                                .malformed_closing_tags
                                .fetch_add(malformed_close, Ordering::Relaxed);
                            i = after_close;
                        }
                        None => {
                            if close_unterminated {
                                stats
                                    .unterminated_sections
                                    .fetch_add(1, Ordering::Relaxed);
                                stats
                                    .discarded_bytes
                                    .fetch_add((bytes.len() - start) as u64, Ordering::Relaxed);
                            }
                            break;
                        }
                    }
                }
            }
        }
    }
}

impl RecordParser for XmlParser {
    fn validate(&self, _bytes: &[u8]) -> rypipe_core::Result<()> {
        // Invalid utf-8 is not an error: text runs replace bad sequences
        // with U+FFFD, exactly like the streaming parser, so one broken byte
        // costs one replacement instead of the whole read.
        Ok(())
    }

    fn parse_chunk(&self, bytes: &[u8], sink: &mut dyn ColumnarSink) -> rypipe_core::Result<()> {
        self.parse_into(bytes, sink);
        Ok(())
    }

    fn parse_chunk_generic<S: ColumnarSink>(
        &self,
        bytes: &[u8],
        sink: &mut S,
    ) -> rypipe_core::Result<()> {
        self.parse_into(bytes, sink);
        Ok(())
    }
}
