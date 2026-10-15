#![no_main]
//! Columnar read: the single-engine path must agree with the bounded spilling
//! path on the same bytes (the `SpillSink` only re-batches, never drops).
use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    let (single, streamed) = _xmlstreamer::fuzz_api::columnar_rows(data);
    // usize::MAX marks a path that returned an error; compare only when both
    // succeeded.
    if single != usize::MAX && streamed != usize::MAX {
        assert_eq!(single, streamed, "spill path diverged from the single engine");
    }
});
