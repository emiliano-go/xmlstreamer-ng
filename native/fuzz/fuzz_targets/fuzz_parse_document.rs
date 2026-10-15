#![no_main]
//! Whole-document parse: exercises the per-item parser and its `unsafe`
//! UTF-8 borrows on arbitrary bytes. Any panic is a bug.
use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    let (parsed, collisions) = _xmlstreamer::fuzz_api::parse_document(data);
    // Collisions can only be reported for a document that parsed into fields.
    if collisions > 0 {
        assert!(parsed, "collisions reported for an unparsed document");
    }
});
