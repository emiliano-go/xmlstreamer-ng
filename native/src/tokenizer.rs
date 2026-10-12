//! Byte-level tokenizer: cut one item's worth of bytes at a time out of a
//! feed, skipping markup sections and locating delimiter tags lexically.
//!
//! A direct port of the Python `Tokenizer` state machine, with the feed
//! driven across the FFI boundary: `feed` hands bytes in, `next_item` asks
//! for more with a distinct status. The scanning cursors only move forward,
//! so a huge comment or attribute value costs one pass, not one per refill.

use std::collections::VecDeque;

use crate::xml;

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum State {
    SeekOpen,
    SeekClose,
    ItemParsed,
    Eof,
}

pub enum Flow {
    Continue,
    NeedMore,
    Eof,
}

pub enum Next {
    Item(PendingItem),
    NeedMore,
    Eof,
}

pub struct PendingItem {
    pub content: Vec<u8>,
    pub parsed: Option<Vec<(String, String)>>,
    pub replaced: bool,
    pub collisions: Vec<(String, String, String)>,
}

pub enum Log {
    Unterminated {
        opener: Vec<u8>,
        limit: i64,
        markup: bool,
    },
    MalformedTag {
        tag: Vec<u8>,
    },
    EndedInItem {
        discarded: usize,
    },
    SectionEof {
        opener: Vec<u8>,
        discarded: usize,
    },
    FeedTimeout,
}

struct TagMatch {
    start: usize,
    end: usize,
    has_attrs: bool,
}

enum Classify {
    None,
    NeedMore,
    Section {
        terminator: &'static [u8],
        header: usize,
        limit: i64,
        is_doctype: bool,
    },
}

const SECTION_PREFIXES: [&[u8]; 4] = [b"<!--", b"<![CDATA[", b"<!DOCTYPE", b"<?"];
const LONGEST_SECTION_PREFIX: usize = 9;

pub struct Engine {
    sep: Vec<u8>,
    buffer: Vec<u8>,
    chunks: VecDeque<Vec<u8>>,
    eof_input: bool,

    pos: usize,
    scan: usize,
    state: State,

    sections_max_size: i64,
    on_limit_text: bool,
    deadline: Option<std::time::Instant>,

    section: Option<Vec<u8>>,
    section_open_at: i64,
    section_limit: i64,
    section_is_doctype: bool,
    section_given_up: bool,
    dtd_depth: i32,
    dtd_quote: u8,
    dtd_inner: Vec<u8>,

    tag_open_at: i64,
    tag_scan: usize,
    tag_quote: u8,

    buffer_size: usize,
    timed_out: bool,
    malformed_tags: usize,
    logs: Vec<Log>,
    pending: Option<PendingItem>,
}

impl Engine {
    pub fn new(
        separator_tag: &str,
        buffer_size: usize,
        max_section_size: i64,
        on_limit_text: bool,
        deadline_secs: Option<f64>,
    ) -> Self {
        let deadline = deadline_secs.and_then(|s| {
            let secs = if s.is_nan() { 0.0 } else { s.clamp(0.0, 1.0e9) };
            std::time::Instant::now()
                .checked_add(std::time::Duration::from_secs_f64(secs))
        });
        Engine {
            sep: separator_tag.as_bytes().to_vec(),
            buffer: Vec::new(),
            chunks: VecDeque::new(),
            eof_input: false,
            pos: 0,
            scan: 0,
            state: State::SeekOpen,
            sections_max_size: max_section_size,
            on_limit_text,
            deadline,
            section: None,
            section_open_at: -1,
            section_limit: 0,
            section_is_doctype: false,
            section_given_up: false,
            dtd_depth: 0,
            dtd_quote: 0,
            dtd_inner: Vec::new(),
            tag_open_at: -1,
            tag_scan: 0,
            tag_quote: 0,
            buffer_size,
            timed_out: false,
            malformed_tags: 0,
            logs: Vec::new(),
            pending: None,
        }
    }

    pub fn feed(&mut self, chunk: &[u8]) {
        self.chunks.push_back(chunk.to_vec());
    }

    pub fn finish(&mut self) {
        self.eof_input = true;
    }

    pub fn state(&self) -> State {
        self.state
    }

    pub fn malformed_tags(&self) -> usize {
        self.malformed_tags
    }


    pub fn take_logs(&mut self) -> Vec<Log> {
        std::mem::take(&mut self.logs)
    }

    pub fn next_item(&mut self) -> Next {
        loop {
            match self.state {
                State::Eof => return Next::Eof,
                State::ItemParsed => {
                    let item = self.pending_take();
                    self.state = State::SeekOpen;
                    return Next::Item(item);
                }
                _ => match self.step() {
                    Flow::Continue => continue,
                    Flow::NeedMore => return Next::NeedMore,
                    Flow::Eof => return Next::Eof,
                },
            }
        }
    }

    fn pending_take(&mut self) -> PendingItem {
        self.pending
            .take()
            .expect("ItemParsed without a pending item")
    }

    fn step(&mut self) -> Flow {
        match self.state {
            State::SeekOpen => match self.advance_to(true) {
                Some(m) => {
                    self.pos = m.end;
                    self.scan = m.end;
                    let opening = self.buffer[m.start..m.end].to_vec();
                    if m.has_attrs {
                        self.check_delimiter(&opening, xml::start_tag_is_well_formed);
                    }
                    if !is_self_closing(&opening) {
                        self.state = State::SeekClose;
                    }
                    Flow::Continue
                }
                None => {
                    if self.section.is_some() && !self.section_given_up {
                        self.pos = self.section_open_at as usize;
                    } else {
                        self.pos = self.scan;
                    }
                    match self.feed_origin_buffer() {
                        Flow::Continue => Flow::Continue,
                        Flow::NeedMore => Flow::NeedMore,
                        Flow::Eof => {
                            self.warn_unterminated_at_eof();
                            self.state = State::Eof;
                            Flow::Eof
                        }
                    }
                }
            },
            State::SeekClose => match self.advance_to(false) {
                Some(m) => {
                    if m.has_attrs {
                        let closing = self.buffer[m.start..m.end].to_vec();
                        self.check_delimiter(&closing, xml::end_tag_is_well_formed);
                    }
                    let content: Vec<u8> = self.buffer[self.pos..m.start].to_vec();
                    self.pos = m.end;
                    self.scan = m.end;

                    if content.is_empty() || content.iter().all(|&b| is_ws(b)) {
                        self.state = State::SeekOpen;
                        return Flow::Continue;
                    }

                    let (parsed, replaced, collisions) =
                        parse_wrapped(&content, &self.sep);
                    if let Some(ref p) = parsed {
                        let only_wrapper = p.len() == 1
                            && p[0].0.as_bytes() == self.sep.as_slice()
                            && p[0].1.trim().is_empty();
                        if p.is_empty() || only_wrapper {
                            self.state = State::SeekOpen;
                            return Flow::Continue;
                        }
                    }
                    self.pending = Some(PendingItem {
                        content,
                        parsed,
                        replaced,
                        collisions,
                    });
                    self.state = State::ItemParsed;
                    Flow::Continue
                }
                None => match self.feed_origin_buffer() {
                    Flow::Continue => Flow::Continue,
                    Flow::NeedMore => Flow::NeedMore,
                    Flow::Eof => {
                        if !self.timed_out {
                            self.logs.push(Log::EndedInItem {
                                discarded: self.buffer.len() - self.pos,
                            });
                        }
                        self.warn_unterminated_at_eof();
                        self.state = State::Eof;
                        Flow::Eof
                    }
                },
            },
            State::ItemParsed => {
                self.pending = None;
                self.state = State::SeekOpen;
                Flow::Continue
            }
            State::Eof => Flow::Eof,
        }
    }

    fn feed_origin_buffer(&mut self) -> Flow {
        if self.pos > 0 {
            self.buffer.drain(..self.pos);
            self.scan = self.scan.saturating_sub(self.pos);
            self.tag_scan = self.tag_scan.saturating_sub(self.pos);
            if self.section_open_at >= 0 {
                self.section_open_at =
                    (self.section_open_at - self.pos as i64).max(0);
            }
            if self.tag_open_at >= 0 {
                self.tag_open_at =
                    (self.tag_open_at - self.pos as i64).max(0);
            }
            self.pos = 0;
        }
        let mut content_present = false;
        while self.buffer.len() < self.buffer_size || !content_present {
            if let Some(deadline) = self.deadline {
                if std::time::Instant::now() > deadline {
                    self.timed_out = true;
                    self.logs.push(Log::FeedTimeout);
                    return Flow::Eof;
                }
            }
            if let Some(chunk) = self.chunks.pop_front() {
                self.buffer.extend_from_slice(&chunk);
                content_present = true;
            } else if self.eof_input {
                break;
            } else {
                return Flow::NeedMore;
            }
        }
        if content_present {
            Flow::Continue
        } else {
            Flow::Eof
        }
    }

    fn clear_section(&mut self) {
        self.section = None;
        self.section_is_doctype = false;
        self.section_given_up = false;
        self.dtd_depth = 0;
        self.dtd_quote = 0;
        self.dtd_inner.clear();
    }

    fn advance_to(&mut self, open: bool) -> Option<TagMatch> {
        loop {
            // The resumable tag walk is only meaningful while looking for an
            // opening separator tag (its attributes may hold `>` inside
            // quotes). Looking for a closing tag, an unterminated run of
            // `<...quote` is not a real tag and must not block the closing
            // search: a stray `<` inside item text would otherwise swallow
            // every following item. Reset the pending walk for open=false.
            if open {
                if self.tag_open_at >= 0 {
                    if self.resume_tag_scan() == -1 {
                        return None;
                    }
                    self.tag_open_at = -1;
                }
            } else {
                self.tag_open_at = -1;
            }

            if let Some(terminator) = self.section.clone() {
                let window = self.section_open_at + self.section_limit;
                let mut stop = self.buffer.len() as i64;
                if !self.section_given_up && window < stop {
                    stop = window;
                }
                let end: i64 = if self.section_is_doctype {
                    self.resume_doctype_scan(stop)
                } else {
                    find(&self.buffer, &terminator, self.scan, stop as usize)
                };

                if end == -1 {
                    if (self.buffer.len() as i64) < window {
                        if !self.section_is_doctype {
                            let keep = self.buffer.len() as i64
                                - terminator.len() as i64
                                + 1;
                            if keep > self.scan as i64 {
                                self.scan = keep as usize;
                            }
                        }
                        return None;
                    }
                    if self.section_given_up {
                        return None;
                    }
                    let open_at = (self.section_open_at.max(0) as usize)
                        .min(self.buffer.len());
                    self.logs.push(Log::Unterminated {
                        opener: self.buffer
                            [open_at..(open_at + 9).min(self.buffer.len())]
                            .to_vec(),
                        limit: self.section_limit,
                        markup: !self.on_limit_text,
                    });
                    if self.on_limit_text {
                        self.scan = (self.section_open_at + 2) as usize;
                        self.clear_section();
                        continue;
                    }
                    self.section_given_up = true;
                    continue;
                }
                self.scan = end as usize + terminator.len();
                self.clear_section();
                continue;
            }

            let m = if open {
                find_open_tag(&self.buffer, self.scan, &self.sep)
            } else {
                find_close_tag(&self.buffer, self.scan, &self.sep)
            };
            let endpos = m.as_ref().map(|x| x.start).unwrap_or(self.buffer.len());
            let opener = self.next_section_opener(self.scan, endpos);
            if opener == -1 {
                if m.is_none() {
                    self.scan = self.pending_tag_tail(self.scan);
                }
                return m;
            }

            match self.classify_section(opener as usize) {
                Classify::None => {
                    self.scan = opener as usize + 2;
                    continue;
                }
                Classify::NeedMore => {
                    self.scan = opener as usize;
                    return None;
                }
                Classify::Section {
                    terminator,
                    header,
                    limit,
                    is_doctype,
                } => {
                    if !is_doctype {
                        let stop =
                            std::cmp::min(opener + limit, self.buffer.len() as i64);
                        let end = find(
                            &self.buffer,
                            terminator,
                            opener as usize + header,
                            stop as usize,
                        );
                        if end != -1 {
                            self.scan = end as usize + terminator.len();
                            continue;
                        }
                    }
                    self.section = Some(terminator.to_vec());
                    self.section_open_at = opener;
                    self.section_limit = limit;
                    self.section_is_doctype = is_doctype;
                    self.section_given_up = false;
                    self.dtd_depth = 0;
                    self.dtd_quote = 0;
                    self.dtd_inner.clear();
                    self.scan = opener as usize + header;
                }
            }
        }
    }

    fn classify_section(&self, start: usize) -> Classify {
        let b = &self.buffer;
        let limit = self.sections_max_size;
        if starts_with(b, start, b"<!--") {
            return Classify::Section {
                terminator: b"-->",
                header: 4,
                limit,
                is_doctype: false,
            };
        }
        if starts_with(b, start, b"<![CDATA[") {
            return Classify::Section {
                terminator: b"]]>",
                header: 9,
                limit,
                is_doctype: false,
            };
        }
        if starts_with(b, start, b"<?") {
            return Classify::Section {
                terminator: b"?>",
                header: 2,
                limit,
                is_doctype: false,
            };
        }
        if starts_with(b, start, b"<!DOCTYPE") {
            return Classify::Section {
                terminator: b">",
                header: 9,
                limit,
                is_doctype: true,
            };
        }
        if b.len() - start < LONGEST_SECTION_PREFIX {
            let tail = &b[start..];
            if SECTION_PREFIXES.iter().any(|p| p.starts_with(tail)) {
                return Classify::NeedMore;
            }
        }
        Classify::None
    }

    fn next_section_opener(&self, start: usize, endpos: usize) -> i64 {
        let endpos = endpos.min(self.buffer.len());
        let mut i = start;
        while i + 1 < endpos {
            match memchr::memchr(b'<', &self.buffer[i..endpos]) {
                Some(r) => {
                    let idx = i + r;
                    if idx + 1 < endpos {
                        let c = self.buffer[idx + 1];
                        if c == b'!' || c == b'?' {
                            return idx as i64;
                        }
                    }
                    i = idx + 1;
                }
                None => break,
            }
        }
        -1
    }

    fn resume_doctype_scan(&mut self, stop: i64) -> i64 {
        let stop = stop.max(0) as usize;
        let mut pos = self.scan;
        loop {
            if !self.dtd_inner.is_empty() {
                let inner = self.dtd_inner.clone();
                let end = find(&self.buffer, &inner, pos, stop);
                if end == -1 {
                    let keep = stop as i64 - inner.len() as i64 + 1;
                    self.scan = if keep > pos as i64 {
                        keep as usize
                    } else {
                        pos
                    };
                    return -1;
                }
                pos = end as usize + inner.len();
                self.dtd_inner.clear();
                continue;
            }
            if self.dtd_quote != 0 {
                match find_byte(&self.buffer, self.dtd_quote, pos, stop) {
                    Some(close) => {
                        pos = close + 1;
                        self.dtd_quote = 0;
                        continue;
                    }
                    None => {
                        self.scan = stop;
                        return -1;
                    }
                }
            }
            match find_any_doctype(&self.buffer, pos, stop) {
                None => {
                    self.scan = stop;
                    return -1;
                }
                Some(idx) => {
                    let c = self.buffer[idx];
                    match c {
                        b'>' => {
                            if self.dtd_depth <= 0 {
                                self.scan = idx;
                                return idx as i64;
                            }
                            pos = idx + 1;
                        }
                        b'[' => {
                            self.dtd_depth += 1;
                            pos = idx + 1;
                        }
                        b']' => {
                            self.dtd_depth -= 1;
                            pos = idx + 1;
                        }
                        b'<' => {
                            if self.buffer[idx..].starts_with(b"<!--") {
                                self.dtd_inner = b"-->".to_vec();
                                pos = idx + 4;
                            } else if self.buffer[idx..].starts_with(b"<?") {
                                self.dtd_inner = b"?>".to_vec();
                                pos = idx + 2;
                            } else if stop - idx < 4
                                && b"<!--".starts_with(&self.buffer[idx..stop])
                            {
                                self.scan = idx;
                                return -1;
                            } else {
                                pos = idx + 1;
                            }
                        }
                        _ => {
                            self.dtd_quote = c;
                            pos = idx + 1;
                        }
                    }
                }
            }
        }
    }

    fn resume_tag_scan(&mut self) -> i64 {
        let mut pos = self.tag_scan;
        loop {
            if self.tag_quote != 0 {
                match memchr::memchr(self.tag_quote, &self.buffer[pos..]) {
                    Some(r) => {
                        self.tag_quote = 0;
                        pos = pos + r + 1;
                    }
                    None => {
                        self.tag_scan = self.buffer.len();
                        return -1;
                    }
                }
                continue;
            }
            match memchr::memchr3(b'>', b'"', b'\'', &self.buffer[pos..]) {
                None => {
                    self.tag_scan = self.buffer.len();
                    return -1;
                }
                Some(r) => {
                    let idx = pos + r;
                    let c = self.buffer[idx];
                    if c == b'>' {
                        self.tag_scan = idx;
                        return idx as i64;
                    }
                    self.tag_quote = c;
                    pos = idx + 1;
                }
            }
        }
    }

    fn pending_tag_tail(&mut self, floor: usize) -> usize {
        // Keep the earliest suffix that can still grow into a separator open
        // tag, a separator close tag or a markup section. Anchoring on the
        // last `<` is unsafe: it may sit inside a quoted attribute value (or
        // inside a section opener like `<!--`), and its quote state would
        // then swallow the rest of the feed at some chunk sizes.
        let mut p = floor;
        while let Some(r) = memchr::memchr(b'<', &self.buffer[p..]) {
            let idx = p + r;
            match self.classify_section(idx) {
                Classify::NeedMore | Classify::Section { .. } => {
                    // A complete or growable section opener: leave it to
                    // classify_section on the next pass, never to the tag
                    // walk.
                    self.tag_open_at = -1;
                    return idx;
                }
                Classify::None => {}
            }
            let tail = &self.buffer[idx + 1..];
            let open_prefix = self.sep.starts_with(tail);
            let open_tag = !open_prefix
                && tail.len() > self.sep.len()
                && tail.starts_with(&self.sep)
                && matches!(tail[self.sep.len()], b'>' | b' ' | b'\t' | b'\r' | b'\n');
            let after_slash = tail.strip_prefix(b"/");
            let close_candidate = match after_slash {
                // `</`, `</i`, `</item`, `</item>` or `</item ...`: either a
                // partial name or a name that already matches lexically and
                // still needs its `>`.
                Some(rest) => {
                    self.sep.starts_with(rest)
                        || (rest.len() > self.sep.len()
                            && rest.starts_with(&self.sep)
                            && (rest[self.sep.len()] == b'>'
                                || is_ws(rest[self.sep.len()])))
                }
                None => false,
            };
            if open_prefix || open_tag {
                if self.tag_open_at != idx as i64 {
                    self.tag_open_at = idx as i64;
                    self.tag_scan = idx + 1;
                    self.tag_quote = 0;
                }
                if self.resume_tag_scan() == -1 {
                    return idx;
                }
                // The tag completed and is not our separator: keep looking.
                self.tag_open_at = -1;
            } else if close_candidate {
                // A closing tag has no quoted attributes to resume; keep the
                // marker for the close search on the next pass.
                self.tag_open_at = -1;
                return idx;
            }
            p = idx + 1;
        }
        self.buffer.len()
    }

    fn check_delimiter(&mut self, tag: &[u8], shape: fn(&[u8]) -> bool) {
        if shape(tag) {
            return;
        }
        self.malformed_tags += 1;
        if self.malformed_tags == 1 {
            self.logs.push(Log::MalformedTag {
                tag: tag[..tag.len().min(80)].to_vec(),
            });
        }
    }

    fn warn_unterminated_at_eof(&mut self) {
        if self.section.is_none() || self.timed_out {
            return;
        }
        let open_at = (self.section_open_at.max(0) as usize)
            .min(self.buffer.len());
        self.logs.push(Log::SectionEof {
            opener: self.buffer
                [open_at..(open_at + 9).min(self.buffer.len())]
                .to_vec(),
            discarded: self.buffer.len() - open_at,
        });
    }
}

fn parse_wrapped(
    content: &[u8],
    sep: &[u8],
) -> (
    Option<Vec<(String, String)>>,
    bool,
    Vec<(String, String, String)>,
) {
    let mut doc = Vec::with_capacity(content.len() + 2 * sep.len() + 5);
    doc.push(b'<');
    doc.extend_from_slice(sep);
    doc.push(b'>');
    doc.extend_from_slice(content);
    doc.extend_from_slice(b"</");
    doc.extend_from_slice(sep);
    doc.push(b'>');
    let replaced = std::str::from_utf8(&doc).is_err();
    let lossy = String::from_utf8_lossy(&doc);
    let result = xml::parse_document(lossy.as_bytes());
    (result.parsed, replaced, result.collisions)
}

fn starts_with(buf: &[u8], start: usize, prefix: &[u8]) -> bool {
    start + prefix.len() <= buf.len() && &buf[start..start + prefix.len()] == prefix
}

/// Python's bytes `\s` / `str.isspace()` set, which is what the scanner's
/// tag patterns and the empty-item check use.
fn is_ws(b: u8) -> bool {
    matches!(b, b' ' | b'\t' | b'\r' | b'\n' | b'\x0b' | b'\x0c')
}

fn is_self_closing(opening: &[u8]) -> bool {
    let mut end = opening.len() - 1; // '>'
    while end > 0 && is_ws(opening[end - 1]) {
        end -= 1;
    }
    end > 0 && opening[end - 1] == b'/'
}

/// `bytearray.find(needle, from, stop)`, or -1.
fn find(buf: &[u8], needle: &[u8], from: usize, stop: usize) -> i64 {
    if from > stop || from > buf.len() {
        return -1;
    }
    let stop = stop.min(buf.len());
    match memchr::memmem::find(&buf[from..stop], needle) {
        Some(r) => (from + r) as i64,
        None => -1,
    }
}

fn find_byte(buf: &[u8], byte: u8, from: usize, stop: usize) -> Option<usize> {
    if from > stop || from > buf.len() {
        return None;
    }
    let stop = stop.min(buf.len());
    memchr::memchr(byte, &buf[from..stop]).map(|r| from + r)
}

fn find_any_doctype(buf: &[u8], from: usize, stop: usize) -> Option<usize> {
    if from >= stop {
        return None;
    }
    let stop = stop.min(buf.len());
    buf[from..stop]
        .iter()
        .position(|b| matches!(b, b'<' | b'>' | b'[' | b']' | b'"' | b'\''))
        .map(|r| from + r)
}

/// Straight run of attribute bytes up to the tag-closing `>`, or None.
fn scan_attr_end(buf: &[u8], from: usize) -> Option<usize> {
    let n = buf.len();
    let mut i = from;
    while i < n {
        match buf[i] {
            b'>' => return Some(i + 1),
            b'"' | b'\'' => {
                let close = memchr::memchr(buf[i], &buf[i + 1..])?;
                i = i + 1 + close + 1;
            }
            _ => i += 1,
        }
    }
    None
}

fn find_open_tag(buf: &[u8], from: usize, sep: &[u8]) -> Option<TagMatch> {
    let n = buf.len();
    let mut i = from;
    while i < n {
        let lt = memchr::memchr(b'<', &buf[i..])?;
        let p = i + lt;
        if p + 1 + sep.len() <= n && &buf[p + 1..p + 1 + sep.len()] == sep {
            let q = p + 1 + sep.len();
            match buf.get(q) {
                Some(b'>') => {
                    return Some(TagMatch {
                        start: p,
                        end: q + 1,
                        has_attrs: false,
                    });
                }
                Some(&b) if is_ws(b) => {
                    if let Some(end) = scan_attr_end(buf, q) {
                        return Some(TagMatch {
                            start: p,
                            end,
                            has_attrs: true,
                        });
                    }
                }
                _ => {}
            }
        }
        i = p + 1;
    }
    None
}

fn find_close_tag(buf: &[u8], from: usize, sep: &[u8]) -> Option<TagMatch> {
    let n = buf.len();
    let mut i = from;
    while i < n {
        let lt = memchr::memchr(b'<', &buf[i..])?;
        let p = i + lt;
        if p + 2 + sep.len() <= n
            && buf[p + 1] == b'/'
            && &buf[p + 2..p + 2 + sep.len()] == sep
        {
            let q = p + 2 + sep.len();
            match buf.get(q) {
                Some(b'>') => {
                    return Some(TagMatch {
                        start: p,
                        end: q + 1,
                        has_attrs: false,
                    });
                }
                Some(&b) if is_ws(b) => {
                    if let Some(r) = memchr::memchr(b'>', &buf[q..]) {
                        return Some(TagMatch {
                            start: p,
                            end: q + r + 1,
                            has_attrs: true,
                        });
                    }
                }
                _ => {}
            }
        }
        i = p + 1;
    }
    None
}
