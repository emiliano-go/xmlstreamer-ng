//! Byte-scanning helpers shared by the rypipe `Splitter` and `RecordParser`.
//!
//! These locate the separator tags lexically and skip markup sections
//! (comments, CDATA, processing instructions, DOCTYPE declarations) so a
//! separator written inside one is never mistaken for a record boundary.

/// What `section_end` found at a position.
pub enum Section {
    /// Not a section opener.
    No,
    /// A section opener that does not close in these bytes.
    Unterminated,
    /// A complete section; the index just past it.
    End(usize),
}

/// Python's bytes `\s` set, which is what the scanner's tag patterns use.
#[inline]
pub fn is_ws(b: u8) -> bool {
    matches!(b, b' ' | b'\t' | b'\r' | b'\n' | b'\x0b' | b'\x0c')
}

#[inline]
pub fn find_seq(bytes: &[u8], from: usize, seq: &[u8]) -> Option<usize> {
    if from > bytes.len() {
        return None;
    }
    memchr::memmem::find(&bytes[from..], seq).map(|r| from + r)
}

/// Walk a `<!DOCTYPE …>` declaration, from `start` (at `<!DOCTYPE`) to just
/// past its closing `>`. Quotes hide `>`, brackets nest the internal subset,
/// and comments/instructions inside the subset are skipped.
fn skip_doctype(bytes: &[u8], start: usize) -> Option<usize> {
    let n = bytes.len();
    let mut i = start + 9;
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
            i = find_seq(bytes, i + 4, b"-->")? + 3;
            continue;
        }
        if bytes[i..].starts_with(b"<?") {
            i = find_seq(bytes, i + 2, b"?>")? + 2;
            continue;
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

/// Classify the markup section opening at `start` (comments, CDATA, PIs,
/// DOCTYPE declarations).
pub fn section_end(bytes: &[u8], start: usize) -> Section {
    // Almost every `<` is an ordinary start tag: bail on the second byte
    // before the four full prefix compares are reached.
    match bytes.get(start + 1) {
        Some(b'!') => {}
        Some(b'?') => {
            return match find_seq(bytes, start + 2, b"?>") {
                Some(end) => Section::End(end + 2),
                None => Section::Unterminated,
            };
        }
        _ => return Section::No,
    }
    let rest = match bytes.get(start..) {
        Some(r) => r,
        None => return Section::No,
    };
    if rest.starts_with(b"<!--") {
        return match find_seq(bytes, start + 4, b"-->") {
            Some(end) => Section::End(end + 3),
            None => Section::Unterminated,
        };
    }
    if rest.starts_with(b"<![CDATA[") {
        return match find_seq(bytes, start + 9, b"]]>") {
            Some(end) => Section::End(end + 3),
            None => Section::Unterminated,
        };
    }
    if rest.starts_with(b"<!DOCTYPE") {
        return match skip_doctype(bytes, start) {
            Some(end) => Section::End(end),
            None => Section::Unterminated,
        };
    }
    Section::No
}

/// End (exclusive) of the tag whose content starts at `from` (the byte after
/// `<`): the position just past the `>` that closes it, skipping `>` inside
/// quotes. `None` when it does not close in these bytes.
fn find_tag_end(bytes: &[u8], from: usize) -> Option<usize> {
    let n = bytes.len();
    let mut i = from;
    while i < n {
        match bytes[i] {
            b'>' => return Some(i + 1),
            b'"' | b'\'' => {
                let close = rypipe_core::scan::find(bytes, i + 1, bytes[i])?;
                i = close + 1;
            }
            _ => i += 1,
        }
    }
    None
}

/// Find the next opening separator tag at or after `from`.
///
/// Returns `(start_of_tag, position_after_the_open_tag)`. Sections are skipped
/// whole; a section that does not close in these bytes stops the search
/// (`None`): nothing after it can be trusted as a record boundary.
pub fn find_open_sep(bytes: &[u8], from: usize, sep: &[u8]) -> Option<(usize, usize)> {
    let n = bytes.len();
    let mut i = from;
    while i < n {
        let p = rypipe_core::scan::find(bytes, i, b'<')?;
        match section_end(bytes, p) {
            Section::End(end) => {
                i = end;
                continue;
            }
            Section::Unterminated => return None,
            Section::No => {}
        }
        if p + 1 + sep.len() <= n && &bytes[p + 1..p + 1 + sep.len()] == sep {
            let q = p + 1 + sep.len();
            match bytes.get(q) {
                Some(b'>') => return Some((p, q + 1)),
                Some(&b) if is_ws(b) => {
                    if let Some(end) = find_tag_end(bytes, q) {
                        return Some((p, end));
                    }
                    // The opening tag never closes: a malformed delimiter,
                    // not a boundary. Resync the way the streaming scanner
                    // does and keep looking for the next one.
                }
                _ => {}
            }
        }
        i = p + 1;
    }
    None
}

/// Find the next `</sep>` at or after `from`, skipping sections.
///
/// Returns `(start_of_close_tag, position_after_it)`.
pub fn find_close_sep(bytes: &[u8], from: usize, sep: &[u8]) -> Option<(usize, usize)> {
    let n = bytes.len();
    let mut i = from;
    while i < n {
        let p = rypipe_core::scan::find(bytes, i, b'<')?;
        match section_end(bytes, p) {
            Section::End(end) => {
                i = end;
                continue;
            }
            Section::Unterminated => return None,
            Section::No => {}
        }
        if p + 2 + sep.len() <= n
            && bytes[p + 1] == b'/'
            && &bytes[p + 2..p + 2 + sep.len()] == sep
        {
            let q = p + 2 + sep.len();
            if let Some(gt) = rypipe_core::scan::find(bytes, q, b'>') {
                return Some((p, gt + 1));
            }
            return None;
        }
        i = p + 1;
    }
    None
}

/// Skip the element named `tag` whose opening tag ends at `after_open`,
/// returning the index just past its matching close tag.
///
/// Nested same-name elements are depth-counted; sections and quoted attribute
/// values are skipped. `None` when the element does not close in these bytes.
pub fn skip_element(bytes: &[u8], after_open: usize, tag: &[u8]) -> Option<usize> {
    let n = bytes.len();
    let mut depth = 1usize;
    let mut i = after_open;
    while i < n {
        let p = rypipe_core::scan::find(bytes, i, b'<')?;
        match section_end(bytes, p) {
            Section::End(end) => {
                i = end;
                continue;
            }
            Section::Unterminated => return None,
            Section::No => {}
        }
        if bytes.get(p + 1) == Some(&b'/') {
            let q = p + 2;
            if q + tag.len() <= n && &bytes[q..q + tag.len()] == tag {
                let z = q + tag.len();
                if matches!(bytes.get(z), Some(b'>') | Some(b' ') | Some(b'\t') | Some(b'\n') | Some(b'\r'))
                {
                    depth -= 1;
                    let end = find_tag_end(bytes, p + 1)?;
                    if depth == 0 {
                        return Some(end);
                    }
                    i = end;
                    continue;
                }
            }
        } else if p + 1 + tag.len() <= n && &bytes[p + 1..p + 1 + tag.len()] == tag {
            let z = p + 1 + tag.len();
            match bytes.get(z) {
                Some(b'>') => {
                    depth += 1;
                    i = z + 1;
                    continue;
                }
                Some(&b) if is_ws(b) => {
                    let end = find_tag_end(bytes, p + 1)?;
                    if !is_self_closing(&bytes[p..end]) {
                        depth += 1;
                    }
                    i = end;
                    continue;
                }
                _ => {}
            }
        }
        i = p + 1;
    }
    None
}

/// Whether an opening separator tag (`<sep ...>`) is self-closing (`<sep/>`).
#[inline]
pub fn is_self_closing(open_tag: &[u8]) -> bool {
    let mut end = open_tag.len().saturating_sub(1); // the closing ">"
    while end > 0 && is_ws(open_tag[end - 1]) {
        end -= 1;
    }
    end > 0 && open_tag[end - 1] == b'/'
}
