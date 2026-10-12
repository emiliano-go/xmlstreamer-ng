//! XML name/char rules and the per-item document parser.
//!
//! These are a Rust port of the rules xmlstreamer previously delegated to
//! expat and of `ItemHandler`: a wrapped item is parsed in isolation into a
//! flat insertion-ordered `{path: text}` map, and anything not well formed
//! invalidates the item alone.

const XML_WHITESPACE: [u8; 4] = [b' ', b'\t', b'\r', b'\n'];
const NAME_STOP: [u8; 10] = [
    b' ', b'\t', b'\r', b'\n', b'=', b'/', b'<', b'>', b'"', b'\'',
];

// ---------------------------------------------------------------------------
// XML 1.0 character and name rules
// ---------------------------------------------------------------------------

fn is_name_start_char(c: char) -> bool {
    c == ':' || c == '_' || c.is_ascii_alphabetic()
        || ('\u{00C0}'..='\u{00D6}').contains(&c)
        || ('\u{00D8}'..='\u{00F6}').contains(&c)
        || ('\u{00F8}'..='\u{02FF}').contains(&c)
        || ('\u{0370}'..='\u{037D}').contains(&c)
        || ('\u{037F}'..='\u{1FFF}').contains(&c)
        || ('\u{200C}'..='\u{200D}').contains(&c)
        || ('\u{2070}'..='\u{218F}').contains(&c)
        || ('\u{2C00}'..='\u{2FEF}').contains(&c)
        || ('\u{3001}'..='\u{D7FF}').contains(&c)
        || ('\u{F900}'..='\u{FDCF}').contains(&c)
        || ('\u{FDF0}'..='\u{FFFD}').contains(&c)
        || ('\u{10000}'..='\u{EFFFF}').contains(&c)
}

fn is_name_char(c: char) -> bool {
    is_name_start_char(c)
        || c.is_ascii_digit()
        || c == '-'
        || c == '.'
        || c == '\u{00B7}'
        || ('\u{0300}'..='\u{036F}').contains(&c)
        || ('\u{203F}'..='\u{2040}').contains(&c)
}

pub fn is_xml_name(raw: &[u8]) -> bool {
    if raw.is_empty() {
        return false;
    }
    // ASCII fast path: most names never touch the Unicode tables.
    if raw.iter().all(|b| b.is_ascii()) {
        let first = raw[0];
        if !(first.is_ascii_alphabetic() || first == b'_' || first == b':') {
            return false;
        }
        return raw[1..].iter().all(|&b| {
            b.is_ascii_alphanumeric() || matches!(b, b'_' | b':' | b'-' | b'.')
        });
    }
    let s = match std::str::from_utf8(raw) {
        Ok(s) => s,
        Err(_) => return false,
    };
    let mut it = s.chars();
    let first = it.next().unwrap();
    if !is_name_start_char(first) {
        return false;
    }
    it.all(is_name_char)
}

pub fn is_xml_char(code: i64) -> bool {
    code == 0x9
        || code == 0xA
        || code == 0xD
        || (0x20..=0xD7FF).contains(&code)
        || (0xE000..=0xFFFD).contains(&code)
        || (0x10000..=0x10FFFF).contains(&code)
}

fn char_ref_code(digits: &str, base: u32) -> i64 {
    if digits.is_empty() {
        return -1;
    }
    let mut code: i64 = 0;
    for ch in digits.chars() {
        let d = match ch.to_digit(base) {
            Some(d) => d,
            None => return -1,
        };
        code = code * base as i64 + d as i64;
        if code > 0x10FFFF {
            return -1;
        }
    }
    code
}

fn has_forbidden_char(s: &str) -> bool {
    let bytes = s.as_bytes();
    // ASCII fast path: forbidden means a C0 control other than tab/LF/CR.
    if bytes.iter().all(|b| *b < 0x80) {
        return bytes
            .iter()
            .any(|&b| b < 0x20 && b != b'\t' && b != b'\n' && b != b'\r');
    }
    s.chars().any(|c| !is_xml_char(c as i64))
}

/// An attribute value is utf-8, holds no "<", carries only characters XML
/// allows, and every "&" opens a reference that resolves to one.
pub fn attvalue_is_well_formed(value: &[u8]) -> bool {
    if value.contains(&b'<') {
        return false;
    }
    // ASCII fast path with no entity reference: only control chars are illegal.
    if value.iter().all(|b| *b < 0x80) && !value.contains(&b'&') {
        return !value
            .iter()
            .any(|&b| b < 0x20 && b != b'\t' && b != b'\n' && b != b'\r');
    }
    let text = match std::str::from_utf8(value) {
        Ok(t) => t,
        Err(_) => return false,
    };
    if has_forbidden_char(text) {
        return false;
    }
    let bytes = text.as_bytes();
    let mut pos = 0usize;
    while let Some(rel) = memchr::memchr(b'&', &bytes[pos..]) {
        let amp = pos + rel;
        let semi = match memchr::memchr(b';', &bytes[amp + 1..]) {
            Some(r) => amp + 1 + r,
            None => return false,
        };
        let body = &text[amp + 1..semi];
        if body.starts_with("#x") {
            if !is_xml_char(char_ref_code(&body[2..], 16)) {
                return false;
            }
        } else if body.starts_with('#') {
            if !is_xml_char(char_ref_code(&body[1..], 10)) {
                return false;
            }
        } else if !matches!(body, "amp" | "lt" | "gt" | "quot" | "apos") {
            // Entity declarations are rejected, so only the five predefined
            // entities can ever resolve; expat rejects the rest.
            return false;
        }
        pos = semi + 1;
    }
    true
}

fn name_end(tag: &[u8], mut pos: usize, end: usize) -> i64 {
    let start = pos;
    while pos < end && !NAME_STOP.contains(&tag[pos]) {
        pos += 1;
    }
    if pos == start || !is_xml_name(&tag[start..pos]) {
        return -1;
    }
    pos as i64
}

/// A start tag as XML defines it. `tag` includes both `<` and `>`.
pub fn start_tag_is_well_formed(tag: &[u8]) -> bool {
    if tag.len() < 2 || tag[0] != b'<' || tag[tag.len() - 1] != b'>' {
        return false;
    }
    let mut end = tag.len() - 1; // the closing ">"
    if end > 0 && tag[end - 1] == b'/' {
        end -= 1; // empty-element tag: "/>" carries no space between
    }
    let mut pos = name_end(tag, 1, end);
    if pos == -1 {
        return false;
    }
    let mut seen: Vec<&[u8]> = Vec::new();
    let p = &mut pos;
    let mut idx = *p as usize;
    while idx < end {
        let mut spaced = false;
        while idx < end && XML_WHITESPACE.contains(&tag[idx]) {
            idx += 1;
            spaced = true;
        }
        if idx >= end {
            return true;
        }
        if !spaced {
            return false;
        }
        let stop = name_end(tag, idx, end);
        if stop == -1 {
            return false;
        }
        let name = &tag[idx..stop as usize];
        if seen.contains(&name) {
            return false;
        }
        seen.push(name);
        idx = stop as usize;
        while idx < end && XML_WHITESPACE.contains(&tag[idx]) {
            idx += 1;
        }
        if idx >= end || tag[idx] != b'=' {
            return false;
        }
        idx += 1;
        while idx < end && XML_WHITESPACE.contains(&tag[idx]) {
            idx += 1;
        }
        if idx >= end {
            return false;
        }
        let quote = tag[idx];
        if quote != b'"' && quote != b'\'' {
            return false;
        }
        let close = match memchr::memchr(quote, &tag[idx + 1..end]) {
            Some(r) => idx + 1 + r,
            None => return false,
        };
        if !attvalue_is_well_formed(&tag[idx + 1..close]) {
            return false;
        }
        idx = close + 1;
    }
    true
}

/// An end tag carries a name, optional whitespace, and nothing else.
pub fn end_tag_is_well_formed(tag: &[u8]) -> bool {
    if tag.len() < 3 || tag[0] != b'<' || tag[1] != b'/' || tag[tag.len() - 1] != b'>'
    {
        return false;
    }
    let end = tag.len() - 1;
    let pos = name_end(tag, 2, end);
    if pos == -1 {
        return false;
    }
    let mut idx = pos as usize;
    while idx < end && XML_WHITESPACE.contains(&tag[idx]) {
        idx += 1;
    }
    idx == end
}

// ---------------------------------------------------------------------------
// Per-item document parser (ItemHandler port)
// ---------------------------------------------------------------------------

struct Frame {
    tag: String,
    key: String,
    text: String,
    has_children: bool,
}

#[derive(Default)]
struct Sink {
    tags: Vec<(String, String)>,
    index: std::collections::HashMap<String, usize>,
    appearances: std::collections::HashMap<String, usize>,
    collisions: Vec<(String, String, String)>,
}

impl Sink {
    fn set(&mut self, key: String, value: String) {
        // rstrip("\n") mirrors the Python post-pass.
        let value = value.trim_end_matches('\n').to_string();
        if let Some(&i) = self.index.get(&key) {
            self.tags[i].1 = value;
        } else {
            self.index.insert(key.clone(), self.tags.len());
            self.tags.push((key, value));
        }
    }

    fn number(&mut self, path: &str, tag: &str) -> String {
        let key = match self.appearances.get_mut(path) {
            Some(count) => {
                *count += 1;
                format!("{path}_{count}")
            }
            None => {
                self.appearances.insert(path.to_string(), 0);
                path.to_string()
            }
        };
        let mut key = key;
        if self.index.contains_key(&key) {
            let taken = key.clone();
            loop {
                let count = self.appearances.get_mut(path).unwrap();
                *count += 1;
                key = format!("{path}_{count}");
                if !self.index.contains_key(&key) {
                    break;
                }
            }
            self.collisions
                .push((taken, tag.to_string(), key.clone()));
        }
        key
    }
}

pub struct DocResult {
    pub parsed: Option<Vec<(String, String)>>,
    pub collisions: Vec<(String, String, String)>,
}

fn err() -> DocResult {
    DocResult {
        parsed: None,
        collisions: Vec::new(),
    }
}

/// Parse a whole item document (wrapper included) into flat fields.
pub fn parse_document(doc: &[u8]) -> DocResult {
    let n = doc.len();
    // A leading byte-order mark is not part of the document.
    let mut i = if doc.starts_with(b"\xef\xbb\xbf") { 3 } else { 0 };
    let mut stack: Vec<Frame> = Vec::new();
    let mut sink = Sink::default();
    let mut root_closed = false;
    let mut root_seen = false;

    // Document prolog/epilog: only whitespace, comments, PIs, and a leading
    // DOCTYPE are allowed outside the root element.
    let mut in_prolog = true;

    while i < n {
        if doc[i] != b'<' {
            // Ordinary text.
            if stack.is_empty() {
                // Outside the root: whitespace only.
                while i < n && doc[i] != b'<' {
                    if !XML_WHITESPACE.contains(&doc[i]) {
                        return err();
                    }
                    i += 1;
                }
                continue;
            }
            let (text, next) = match decode_text(doc, i) {
                Some(v) => v,
                None => return err(),
            };
            stack.last_mut().unwrap().text.push_str(&text);
            i = next;
            continue;
        }

        if doc[i..].starts_with(b"<!--") {
            match find_seq(doc, i + 4, b"-->") {
                Some(end) => {
                    if !comment_is_well_formed(&doc[i + 4..end]) {
                        return err();
                    }
                    i = end + 3;
                    continue;
                }
                None => return err(),
            }
        }
        if doc[i..].starts_with(b"<![CDATA[") {
            if stack.is_empty() {
                return err();
            }
            match find_seq(doc, i + 9, b"]]>") {
                Some(end) => {
                    let raw = &doc[i + 9..end];
                    let text = match std::str::from_utf8(raw) {
                        Ok(t) => t,
                        Err(_) => return err(),
                    };
                    if has_forbidden_char(text) {
                        return err();
                    }
                    push_normalized(
                        &mut stack.last_mut().unwrap().text,
                        text,
                    );
                    i = end + 3;
                    continue;
                }
                None => return err(),
            }
        }
        if doc[i..].starts_with(b"<?") {
            match find_seq(doc, i + 2, b"?>") {
                Some(end) => {
                    if pi_end(doc, i).is_none() {
                        return err();
                    }
                    i = end + 2;
                    continue;
                }
                None => return err(),
            }
        }
        if doc[i..].starts_with(b"<!DOCTYPE") {
            if !stack.is_empty() || root_seen {
                return err();
            }
            match scan_doctype(doc, i) {
                Some(end) => {
                    in_prolog = true;
                    i = end;
                    continue;
                }
                None => return err(),
            }
        }
        if doc[i..].starts_with(b"<!") {
            return err();
        }

        if i + 1 < n && doc[i + 1] == b'/' {
            // End tag.
            if stack.is_empty() {
                return err();
            }
            let end = match find_tag_end(doc, i + 1) {
                Some(e) => e,
                None => return err(),
            };
            let tag = &doc[i..end];
            if !end_tag_is_well_formed(tag) {
                return err();
            }
            let name = end_tag_name(tag);
            if name != stack.last().unwrap().tag.as_bytes() {
                return err();
            }
            let frame = stack.pop().unwrap();
            let is_root = stack.is_empty();
            emit(&mut sink, frame, is_root);
            i = end;
            if is_root {
                root_closed = true;
                in_prolog = false;
            }
            continue;
        }

        // Start tag.
        if root_closed {
            return err();
        }
        let end = match find_tag_end(doc, i + 1) {
            Some(e) => e,
            None => return err(),
        };
        let tag_bytes = &doc[i..end];
        if !start_tag_is_well_formed(tag_bytes) {
            return err();
        }
        let name = match start_tag_name(tag_bytes) {
            Some(n) => match std::str::from_utf8(n) {
                Ok(s) => s.to_string(),
                Err(_) => return err(),
            },
            None => return err(),
        };
        let self_closing = is_self_closing(tag_bytes);

        if stack.is_empty() {
            root_seen = true;
            in_prolog = false;
            stack.push(Frame {
                tag: name.clone(),
                key: name,
                text: String::new(),
                has_children: false,
            });
        } else {
            stack.last_mut().unwrap().has_children = true;
            let path = if stack.len() > 1 {
                format!("{}/{}", stack.last().unwrap().key, name)
            } else {
                name.clone()
            };
            let key = sink.number(&path, &name);
            stack.push(Frame {
                tag: name,
                key,
                text: String::new(),
                has_children: false,
            });
        }
        i = end;

        if self_closing {
            let frame = stack.pop().unwrap();
            let is_root = stack.is_empty();
            emit(&mut sink, frame, is_root);
            if is_root {
                root_closed = true;
                in_prolog = false;
            }
        }
        let _ = in_prolog;
    }

    if !stack.is_empty() || !root_seen || !root_closed {
        return err();
    }

    DocResult {
        parsed: Some(sink.tags),
        collisions: sink.collisions,
    }
}

fn emit(sink: &mut Sink, frame: Frame, is_root: bool) {
    if is_root {
        if !frame.has_children {
            sink.set(frame.key, frame.text);
        }
        return;
    }
    if !frame.has_children || !frame.text.trim().is_empty() {
        sink.set(frame.key, frame.text);
    }
}

fn find_seq(bytes: &[u8], from: usize, seq: &[u8]) -> Option<usize> {
    memchr::memmem::find(&bytes[from..], seq).map(|r| from + r)
}

/// Position just past the `>` that closes tag starting at `from` (which
/// points at the byte after `<`). A `>` inside quotes closes nothing.
fn find_tag_end(bytes: &[u8], from: usize) -> Option<usize> {
    let mut i = from;
    let n = bytes.len();
    while i < n {
        match bytes[i] {
            b'>' => return Some(i + 1),
            b'"' | b'\'' => {
                let quote = bytes[i];
                let close = memchr::memchr(quote, &bytes[i + 1..])?;
                i = i + 1 + close + 1;
            }
            _ => i += 1,
        }
    }
    None
}

fn start_tag_name(tag: &[u8]) -> Option<&[u8]> {
    let end = tag.len() - 1;
    let pos = name_end(tag, 1, end);
    if pos == -1 {
        return None;
    }
    Some(&tag[1..pos as usize])
}

/// The tag name starting at `start`, or `None` when it is not a valid name.
fn tag_name_at(tag: &[u8], start: usize) -> Option<&[u8]> {
    if tag.len() < start + 2 {
        return None;
    }
    let end = tag.len() - 1;
    let pos = name_end(tag, start, end);
    if pos == -1 {
        return None;
    }
    Some(&tag[start..pos as usize])
}

fn end_tag_name(tag: &[u8]) -> &[u8] {
    let end = tag.len() - 1;
    let pos = name_end(tag, 2, end);
    &tag[2..pos as usize]
}

fn is_self_closing(tag: &[u8]) -> bool {
    let mut end = tag.len() - 1; // '>'
    while end > 0 && XML_WHITESPACE.contains(&tag[end - 1]) {
        end -= 1;
    }
    end > 0 && tag[end - 1] == b'/'
}

/// Scan a DOCTYPE declaration, returning the position after its closing `>`.
/// Any `<!ENTITY` inside the internal subset is rejected.
fn scan_doctype(bytes: &[u8], start: usize) -> Option<usize> {
    let n = bytes.len();
    let mut i = start + 9; // past "<!DOCTYPE"
    let mut depth: i32 = 0;
    let mut quote: u8 = 0;
    while i < n {
        if quote != 0 {
            if bytes[i] == quote {
                quote = 0;
            }
            i += 1;
            continue;
        }
        if bytes[i..].starts_with(b"<!--") {
            let end = find_seq(bytes, i + 4, b"-->")?;
            i = end + 3;
            continue;
        }
        if bytes[i..].starts_with(b"<?") {
            let end = find_seq(bytes, i + 2, b"?>")?;
            i = end + 2;
            continue;
        }
        if bytes[i..].starts_with(b"<!ENTITY") {
            return None;
        }
        match bytes[i] {
            b'"' | b'\'' => {
                quote = bytes[i];
                i += 1;
            }
            b'[' => {
                depth += 1;
                i += 1;
            }
            b']' => {
                depth -= 1;
                i += 1;
            }
            b'>' => {
                if depth <= 0 {
                    return Some(i + 1);
                }
                i += 1;
            }
            _ => i += 1,
        }
    }
    None
}

/// XML 1.0 §2.11: literal `\r\n` and `\r` normalize to `\n`. Character
/// references are exempt, so this applies to raw text runs only.
fn push_normalized(out: &mut String, raw: &str) {
    if !raw.contains('\r') {
        out.push_str(raw);
        return;
    }
    let mut chars = raw.chars().peekable();
    while let Some(c) = chars.next() {
        if c == '\r' {
            if chars.peek() == Some(&'\n') {
                chars.next();
            }
            out.push('\n');
        } else {
            out.push(c);
        }
    }
}

/// A comment body may not contain `--` nor end with `-` (XML 1.0 §2.5).
fn comment_is_well_formed(body: &[u8]) -> bool {
    memchr::memmem::find(body, b"--").is_none() && !body.ends_with(b"-")
}

/// End of a processing instruction starting at `start` (its `<`), or `None`
/// when the target is not a name other than `xml`.
fn pi_end(bytes: &[u8], start: usize) -> Option<usize> {
    let n = bytes.len();
    let mut i = start + 2;
    let name_start = i;
    while i < n && !NAME_STOP.contains(&bytes[i]) && bytes[i] != b'?' {
        i += 1;
    }
    if i == name_start || !is_xml_name(&bytes[name_start..i]) {
        return None;
    }
    if bytes[name_start..i].eq_ignore_ascii_case(b"xml") {
        return None;
    }
    if i < n && bytes[i] != b'?' && !XML_WHITESPACE.contains(&bytes[i]) {
        return None;
    }
    find_seq(bytes, i, b"?>").map(|end| end + 2)
}

/// The item's close tag is located lexically: `</sep>` or `</sep junk>` end
/// the item even when the tag itself is malformed, matching the scanner.
fn closes_separator(tag: &[u8], sep: &[u8]) -> Option<usize> {
    if !tag.starts_with(b"</") {
        return None;
    }
    let name = match tag_name_at(tag, 2) {
        Some(name) => name,
        None => return None,
    };
    if name != sep {
        return None;
    }
    match tag.get(2 + sep.len()) {
        Some(b'>') => Some(3 + sep.len()),
        Some(&b) if crate::scan::is_ws(b) => Some(tag.len()),
        _ => None,
    }
}

/// Decode a run of character data up to the next `<`.
fn decode_text(bytes: &[u8], start: usize) -> Option<(String, usize)> {
    let n = bytes.len();
    let mut i = start;
    let mut out = String::new();
    while i < n && bytes[i] != b'<' {
        if bytes[i] == b'&' {
            let (decoded, next) = decode_ref(bytes, i)?;
            out.push_str(&decoded);
            i = next;
            continue;
        }
        let run_start = i;
        while i < n && bytes[i] != b'<' && bytes[i] != b'&' {
            i += 1;
        }
        let raw = &bytes[run_start..i];
        if memchr::memmem::find(raw, b"]]>").is_some() {
            return None;
        }
        let run = std::str::from_utf8(raw).ok()?;
        if has_forbidden_char(run) {
            return None;
        }
        push_normalized(&mut out, run);
    }
    Some((out, i))
}

fn decode_ref(bytes: &[u8], amp: usize) -> Option<(String, usize)> {
    let semi = memchr::memchr(b';', &bytes[amp + 1..])? + amp + 1;
    let body = &bytes[amp + 1..semi];
    let replacement: String = match body {
        b"amp" => "&".to_string(),
        b"lt" => "<".to_string(),
        b"gt" => ">".to_string(),
        b"quot" => "\"".to_string(),
        b"apos" => "'".to_string(),
        _ => {
            let text = std::str::from_utf8(body).ok()?;
            if let Some(hex) = text.strip_prefix("#x") {
                let code = char_ref_code(hex, 16);
                if !is_xml_char(code) {
                    return None;
                }
                char::from_u32(code as u32)?.to_string()
            } else if let Some(dec) = text.strip_prefix('#') {
                let code = char_ref_code(dec, 10);
                if !is_xml_char(code) {
                    return None;
                }
                char::from_u32(code as u32)?.to_string()
            } else {
                return None; // undefined entity
            }
        }
    };
    Some((replacement, semi + 1))
}

// ---------------------------------------------------------------------------
// Borrow-first item fields (adapter path)
// ---------------------------------------------------------------------------
//
// The adapter reuses one `Scratch` across items: depth-1 keys and leaf text
// borrow the chunk, mixed content / entity-decoded text is the only thing
// materialized, and the field list is validated before anything is emitted
// (a malformed item is dropped whole, like the streaming parser).

use std::borrow::Cow;

/// Where a key's bytes live.
#[derive(Clone, Copy)]
enum KeySrc {
    Content(usize, usize),
    Arena(u32, u32),
}

/// Reusable parse state, one per parser (per chunk/thread).
#[derive(Default)]
pub struct Scratch {
    stack: Vec<FlatFrame>,
    pending: Vec<FlatPending>,
    appearances: Vec<(KeySrc, usize)>,
    emitted: Vec<KeySrc>,
    key_arena: String,
}

struct FlatFrame {
    tag: (usize, usize),
    key: KeySrc,
    text: TextBuf,
    has_children: bool,
}

struct FlatPending {
    key: KeySrc,
    value: PendingVal,
}

enum PendingVal {
    Empty,
    Content(usize, usize),
    Owned(String),
}

/// Sink for a validated item: one row per item, one field per flatten result.
pub trait FlatEmitter {
    fn row_start(&mut self);
    fn field(&mut self, name: &str, value: &str);
    fn row_end(&mut self);

    /// Whether a field with this final name is wanted. Used to skip scanning
    /// pure-text leaves whose column is dropped/projected out.
    fn wants(&self, _name: &str) -> bool {
        true
    }
}

#[inline]
fn key_slice<'a>(key: KeySrc, content: &'a [u8], arena: &'a str) -> &'a str {
    match key {
        // SAFETY: keys point at tag bytes inside a UTF-8-validated chunk.
        KeySrc::Content(s, e) => unsafe { std::str::from_utf8_unchecked(&content[s..e]) },
        KeySrc::Arena(s, e) => &arena[s as usize..(s + e) as usize],
    }
}

#[inline]
fn key_eq(a: KeySrc, b: KeySrc, content: &[u8], arena: &str) -> bool {
    key_slice(a, content, arena) == key_slice(b, content, arena)
}

/// Accumulates an element's direct character data, borrowing a single run.
#[derive(Default)]
struct TextBuf {
    has: bool,
    start: usize,
    end: usize,
    owned: Option<String>,
}

impl TextBuf {
    fn materialize(&mut self, content: &[u8]) {
        if self.owned.is_none() {
            let mut out = String::new();
            if self.has {
                out.push_str(std::str::from_utf8(&content[self.start..self.end]).unwrap_or(""));
            }
            self.owned = Some(out);
            self.has = false;
        }
    }

    fn push_run(&mut self, content: &[u8], start: usize, end: usize) {
        let run = std::str::from_utf8(&content[start..end]).unwrap_or("");
        if let Some(owned) = self.owned.as_mut() {
            owned.push_str(run);
            return;
        }
        if !self.has {
            self.has = true;
            self.start = start;
            self.end = end;
        } else if self.end == start {
            self.end = end;
        } else {
            self.materialize(content);
            self.owned.as_mut().unwrap().push_str(run);
        }
    }

    fn push_owned(&mut self, content: &[u8], text: String) {
        self.materialize(content);
        self.owned.as_mut().unwrap().push_str(&text);
    }

    fn into_pending(self) -> PendingVal {
        if let Some(owned) = self.owned {
            PendingVal::Owned(owned)
        } else if self.has {
            PendingVal::Content(self.start, self.end)
        } else {
            PendingVal::Empty
        }
    }
}

fn pending_str<'a>(value: &'a PendingVal, content: &'a [u8]) -> Cow<'a, str> {
    match value {
        PendingVal::Empty => Cow::Borrowed(""),
        // SAFETY: text runs come from a UTF-8-validated chunk.
        PendingVal::Content(s, e) => {
            Cow::Borrowed(unsafe { std::str::from_utf8_unchecked(&content[*s..*e]) })
        }
        PendingVal::Owned(s) => Cow::Borrowed(s.as_str()),
    }
}

fn pending_trim_is_empty(value: &PendingVal, content: &[u8]) -> bool {
    pending_str(value, content).trim().is_empty()
}

/// Append `"{path}_{count}"` to the arena and return its range.
fn arena_key(scratch: &mut Scratch, content: &[u8], path: KeySrc, count: usize) -> KeySrc {
    let path_owned = key_slice(path, content, &scratch.key_arena).to_string();
    let off = scratch.key_arena.len() as u32;
    scratch.key_arena.push_str(&path_owned);
    scratch.key_arena.push('_');
    scratch.key_arena.push_str(&count.to_string());
    let len = scratch.key_arena.len() as u32 - off;
    KeySrc::Arena(off, len)
}

/// Build (and cache) the output key for `path`, handling sibling numbering
/// and literal-key collisions the same way the streaming parser does.
fn number_key(scratch: &mut Scratch, content: &[u8], path: KeySrc) -> KeySrc {
    let found = scratch
        .appearances
        .iter()
        .position(|(k, _)| key_eq(*k, path, content, &scratch.key_arena));
    let mut key = match found {
        Some(idx) => {
            scratch.appearances[idx].1 += 1;
            let count = scratch.appearances[idx].1;
            arena_key(scratch, content, path, count)
        }
        None => {
            scratch.appearances.push((path, 0));
            path
        }
    };
    loop {
        let collision = scratch
            .emitted
            .iter()
            .any(|k| key_eq(*k, key, content, &scratch.key_arena));
        if !collision {
            break;
        }
        let idx = scratch
            .appearances
            .iter()
            .position(|(k, _)| key_eq(*k, path, content, &scratch.key_arena))
            .unwrap();
        scratch.appearances[idx].1 += 1;
        let count = scratch.appearances[idx].1;
        key = arena_key(scratch, content, path, count);
    }
    key
}

/// Whether a projected schema keeps `tag` or anything under it.
fn subtree_wanted(keep: &std::collections::HashSet<String>, tag: &str) -> bool {
    keep.iter().any(|name| {
        name == tag
            || name
                .strip_prefix(tag)
                .map_or(false, |rest| rest.starts_with('/'))
    })
}

/// Build the nested path `parent/tag` into the arena.
fn nested_path(
    scratch: &mut Scratch,
    content: &[u8],
    parent: KeySrc,
    tag: (usize, usize),
) -> Option<KeySrc> {
    let parent_owned = key_slice(parent, content, &scratch.key_arena).to_string();
    let tag_str = std::str::from_utf8(&content[tag.0..tag.1]).ok()?;
    let off = scratch.key_arena.len() as u32;
    scratch.key_arena.push_str(&parent_owned);
    scratch.key_arena.push('/');
    scratch.key_arena.push_str(tag_str);
    let len = scratch.key_arena.len() as u32 - off;
    Some(KeySrc::Arena(off, len))
}

fn read_text_run(
    content: &[u8],
    mut i: usize,
    strict: bool,
    target: &mut TextBuf,
) -> Option<usize> {
    let n = content.len();
    while i < n && content[i] != b'<' {
        if content[i] == b'&' {
            let (decoded, next) = decode_ref(content, i)?;
            target.push_owned(content, decoded);
            i = next;
            continue;
        }
        let start = i;
        while i < n && content[i] != b'<' && content[i] != b'&' {
            i += 1;
        }
        let raw = &content[start..i];
        if memchr::memmem::find(raw, b"]]>").is_some() {
            return None;
        }
        match std::str::from_utf8(raw) {
            Ok(run) => {
                if strict && has_forbidden_char(run) {
                    return None;
                }
                if run.contains('\r') {
                    let mut normalized = String::with_capacity(run.len());
                    push_normalized(&mut normalized, run);
                    target.push_owned(content, normalized);
                } else {
                    target.push_run(content, start, i);
                }
            }
            Err(_) => {
                // Invalid utf-8 is replaced, exactly like the streaming
                // parser: a broken byte drops nothing.
                let run = String::from_utf8_lossy(raw);
                if strict && has_forbidden_char(&run) {
                    return None;
                }
                let mut normalized = String::with_capacity(run.len());
                push_normalized(&mut normalized, &run);
                target.push_owned(content, normalized);
            }
        }
    }
    Some(i)
}

/// Skip an unwanted depth-1 subtree, returning the index just past its
/// matching end tag. Strict mode validates every tag, attribute and text run
/// inside it; fast mode skips lexically (the caller opted out of validation).
fn skip_subtree_checked(
    bytes: &[u8],
    after_open: usize,
    name: &[u8],
    strict: bool,
) -> Option<usize> {
    if !strict {
        return crate::scan::skip_element(bytes, after_open, name);
    }
    let n = bytes.len();
    let mut stack: Vec<&[u8]> = vec![name];
    let mut i = after_open;
    while i < n {
        if bytes[i] != b'<' {
            let mut scratch = TextBuf::default();
            i = read_text_run(bytes, i, true, &mut scratch)?;
            continue;
        }
        if bytes[i..].starts_with(b"<!DOCTYPE") {
            return None;
        }
        match crate::scan::section_end(bytes, i) {
            crate::scan::Section::End(end) => {
                i = end;
                continue;
            }
            crate::scan::Section::Unterminated => return None,
            crate::scan::Section::No => {}
        }
        let end = find_tag_end(bytes, i + 1)?;
        let tag = &bytes[i..end];
        if tag.starts_with(b"</") {
            if !end_tag_is_well_formed(tag) {
                return None;
            }
            let close = end_tag_name(tag);
            if stack.pop()? != close {
                return None;
            }
            if stack.is_empty() {
                return Some(end);
            }
        } else {
            if !start_tag_is_well_formed(tag) {
                return None;
            }
            let raw = start_tag_name(tag)?;
            if !is_self_closing(tag) {
                stack.push(raw);
            }
        }
        i = end;
    }
    None
}

/// Result of parsing one item in place (fused scan + parse).
pub enum Fused {
    /// The item was handled; resume scanning just past its close tag.
    Complete { resume: usize },
    /// The item's close tag is not in these bytes (partial trailing record).
    Incomplete,
    /// The item is malformed; the caller resyncs and drops it.
    Malformed,
}

/// Parse one item starting just past its opening separator tag, emitting a row
/// for it, and return where scanning resumes.
///
/// Locating the `</sep>` is fused with field parsing: the item's bytes are
/// walked once. A malformed item emits nothing; the caller resyncs with
/// `find_close_sep` and drops it, matching the streaming parser.
pub fn parse_item_fused<E: FlatEmitter>(
    scratch: &mut Scratch,
    bytes: &[u8],
    start: usize,
    sep: &str,
    keep: Option<&std::collections::HashSet<String>>,
    strict: bool,
    emitter: &mut E,
) -> Fused {
    scratch.stack.clear();
    scratch.pending.clear();
    scratch.appearances.clear();
    scratch.emitted.clear();
    scratch.key_arena.clear();

    let n = bytes.len();
    let mut i = start;
    let mut root = TextBuf::default();
    let mut seen_child = false;

    while i < n {
        if bytes[i] != b'<' {
            let target = match scratch.stack.last_mut() {
                Some(frame) => &mut frame.text,
                None => &mut root,
            };
            match read_text_run(bytes, i, strict, target) {
                Some(next) => i = next,
                None => return Fused::Malformed,
            }
            continue;
        }

        if bytes[i..].starts_with(b"<!--") {
            let end = match find_seq(bytes, i + 4, b"-->") {
                Some(end) => end,
                None => return Fused::Incomplete,
            };
            if !comment_is_well_formed(&bytes[i + 4..end]) {
                return Fused::Malformed;
            }
            i = end + 3;
            continue;
        }
        if bytes[i..].starts_with(b"<![CDATA[") {
            let end = match find_seq(bytes, i + 9, b"]]>") {
                Some(end) => end,
                None => return Fused::Incomplete,
            };
            let raw = &bytes[i + 9..end];
            let text = String::from_utf8_lossy(raw);
            if strict && has_forbidden_char(&text) {
                return Fused::Malformed;
            }
            let target = match scratch.stack.last_mut() {
                Some(frame) => &mut frame.text,
                None => &mut root,
            };
            let mut normalized = String::with_capacity(text.len());
            push_normalized(&mut normalized, &text);
            target.push_owned(bytes, normalized);
            i = end + 3;
            continue;
        }
        if bytes[i..].starts_with(b"<?") {
            let end = match find_seq(bytes, i + 2, b"?>") {
                Some(end) => end,
                None => return Fused::Incomplete,
            };
            if pi_end(bytes, i).is_none() {
                return Fused::Malformed;
            }
            i = end + 2;
            continue;
        }
        if bytes[i..].starts_with(b"<!") {
            return Fused::Malformed;
        }

        if i + 1 < n && bytes[i + 1] == b'/' {
            let end = match find_tag_end(bytes, i + 1) {
                Some(end) => end,
                None => return Fused::Incomplete,
            };
            let tag = &bytes[i..end];
            if scratch.stack.is_empty() {
                // The delimiter is located lexically: junk in the closing
                // tag still ends the item, whose content was parsed above.
                if closes_separator(tag, sep.as_bytes()).is_none() {
                    return Fused::Malformed;
                }
                return finish_item(scratch, bytes, sep, &mut root, seen_child, emitter, end);
            }
            if !end_tag_is_well_formed(tag) {
                return Fused::Malformed;
            }
            let name = end_tag_name(tag);
            let frame = scratch.stack.pop().unwrap();
            if name != &bytes[frame.tag.0..frame.tag.1] {
                return Fused::Malformed;
            }
            i = end;
            let value = frame.text.into_pending();
            if !frame.has_children || !pending_trim_is_empty(&value, bytes) {
                scratch.emitted.push(frame.key);
                scratch.pending.push(FlatPending {
                    key: frame.key,
                    value,
                });
            }
            continue;
        }

        let end = match find_tag_end(bytes, i + 1) {
            Some(end) => end,
            None => return Fused::Incomplete,
        };
        let tag = &bytes[i..end];
        let tag_ok = if strict {
            start_tag_is_well_formed(tag)
        } else {
            // Fast mode: validate the element name, skip attribute-value
            // well-formedness (a trusted-feed optimization).
            start_tag_name(tag).is_some()
        };
        if !tag_ok {
            return Fused::Malformed;
        }
        let name = match start_tag_name(tag) {
            Some(raw) => match std::str::from_utf8(raw) {
                Ok(s) => s,
                Err(_) => return Fused::Malformed,
            },
            None => return Fused::Malformed,
        };
        let tag_span = (i + 1, i + 1 + name.len());
        let self_closing = is_self_closing(tag);

        // Projection pushdown: a depth-1, first-occurrence, unwanted text
        // leaf is skipped without scanning its value; numbering state is
        // kept so later siblings number as before. Strict mode only skips an
        // empty leaf, so no unvalidated content can slip through; fast mode
        // (the caller opted out of validation) skips any leaf.
        if scratch.stack.is_empty() && !self_closing && !emitter.wants(name) {
            let path = KeySrc::Content(tag_span.0, tag_span.1);
            let first = !scratch
                .appearances
                .iter()
                .any(|(k, _)| key_eq(*k, path, bytes, &scratch.key_arena))
                && !scratch
                    .emitted
                    .iter()
                    .any(|k| key_eq(*k, path, bytes, &scratch.key_arena));
            if first {
                if let Some(lt) = rypipe_core::scan::find(bytes, end, b'<') {
                    let after = lt + 2;
                    let tag_bytes = &bytes[tag_span.0..tag_span.1];
                    if (!strict || lt == end)
                        && bytes.get(lt..lt + 2) == Some(b"</")
                        && after + tag_bytes.len() + 1 <= n
                        && &bytes[after..after + tag_bytes.len()] == tag_bytes
                        && bytes[after + tag_bytes.len()] == b'>'
                    {
                        scratch.appearances.push((path, 0));
                        seen_child = true;
                        i = after + tag_bytes.len() + 1;
                        continue;
                    }
                }
            }
        }

        // Projection pushdown: under a declared schema, a depth-1 subtree with
        // no wanted descendant is skipped whole. Strict mode still validates
        // everything inside it, so a malformed item can never slip through.
        if scratch.stack.is_empty() && !self_closing {
            if let Some(keep) = keep {
                if !subtree_wanted(keep, name) {
                    if let Some(after) =
                        skip_subtree_checked(bytes, end, name.as_bytes(), strict)
                    {
                        let _ = number_key(
                            scratch,
                            bytes,
                            KeySrc::Content(tag_span.0, tag_span.1),
                        );
                        seen_child = true;
                        i = after;
                        continue;
                    }
                }
            }
        }

        let key = if scratch.stack.is_empty() {
            seen_child = true;
            number_key(scratch, bytes, KeySrc::Content(tag_span.0, tag_span.1))
        } else {
            scratch.stack.last_mut().unwrap().has_children = true;
            let parent = scratch.stack.last().unwrap().key;
            let path = match nested_path(scratch, bytes, parent, tag_span) {
                Some(p) => p,
                None => return Fused::Malformed,
            };
            number_key(scratch, bytes, path)
        };
        i = end;
        scratch.stack.push(FlatFrame {
            tag: tag_span,
            key,
            text: TextBuf::default(),
            has_children: false,
        });
        if self_closing {
            let frame = scratch.stack.pop().unwrap();
            let value = frame.text.into_pending();
            if !frame.has_children || !pending_trim_is_empty(&value, bytes) {
                scratch.emitted.push(frame.key);
                scratch.pending.push(FlatPending {
                    key: frame.key,
                    value,
                });
            }
        }
    }

    Fused::Incomplete
}

/// Finish a completed item: emit its row unless it is empty / comment-only.
fn finish_item<E: FlatEmitter>(
    scratch: &mut Scratch,
    bytes: &[u8],
    sep: &str,
    root: &mut TextBuf,
    seen_child: bool,
    emitter: &mut E,
    resume: usize,
) -> Fused {
    if !seen_child {
        let value = std::mem::take(root).into_pending();
        if pending_trim_is_empty(&value, bytes) {
            return Fused::Complete { resume };
        }
        emitter.row_start();
        emitter.field(sep, pending_str(&value, bytes).trim_end_matches('\n'));
        emitter.row_end();
        return Fused::Complete { resume };
    }

    if scratch.pending.is_empty() {
        // The item had children but every emitted field was projected out:
        // the record still exists (with nulls), matching rypipe semantics.
        emitter.row_start();
        emitter.row_end();
        return Fused::Complete { resume };
    }
    if scratch.pending.len() == 1 {
        let p = &scratch.pending[0];
        let key = key_slice(p.key, bytes, &scratch.key_arena);
        if key == sep && pending_trim_is_empty(&p.value, bytes) {
            return Fused::Complete { resume };
        }
    }

    let Scratch {
        pending,
        key_arena,
        ..
    } = scratch;
    emitter.row_start();
    for p in pending.iter() {
        let name = match p.key {
            KeySrc::Content(s, e) => unsafe {
                std::str::from_utf8_unchecked(&bytes[s..e])
            },
            KeySrc::Arena(s, e) => &key_arena[s as usize..(s + e) as usize],
        };
        emitter.field(name, &pending_str(&p.value, bytes).trim_end_matches('\n'));
    }
    emitter.row_end();
    Fused::Complete { resume }
}
