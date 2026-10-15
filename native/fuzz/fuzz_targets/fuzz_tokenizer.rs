#![no_main]
//! Streaming tokenizer: drives the resumable scanner over arbitrary bytes.
//! Any panic is a bug.
use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    let _items = _xmlstreamer::fuzz_api::tokenizer_rows(data);
});
