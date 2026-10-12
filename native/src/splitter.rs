//! `rypipe_core::Splitter` for xmlstreamer feeds.

use rypipe_core::decoder::{plan_chunk_count_with, SplitMode, MIN_CHUNK_BYTES};
use rypipe_core::Splitter;

use crate::scan;

/// Finds separator-tag boundaries, skipping markup sections.
#[derive(Clone)]
pub struct XmlSplitter {
    sep: Vec<u8>,
    open_pattern: Vec<u8>,
}

impl XmlSplitter {
    pub fn new(separator_tag: &str) -> Self {
        let sep = separator_tag.as_bytes().to_vec();
        let mut open_pattern = Vec::with_capacity(sep.len() + 1);
        open_pattern.push(b'<');
        open_pattern.extend_from_slice(&sep);
        Self { sep, open_pattern }
    }

    /// Section-aware split planning: walk the whole input forward with the
    /// same scanner the parser uses and collect true record starts, then cut
    /// at the starts nearest the nominal offsets. A split therefore never
    /// lands inside a comment, CDATA, PI, DOCTYPE (however long) or a quoted
    /// attribute value, which the backward `SkipRegionFinder` heuristic
    /// cannot guarantee.
    fn split_points(
        &self,
        bytes: &[u8],
        max_chunks: usize,
        min_chunk_bytes: usize,
    ) -> Vec<usize> {
        if max_chunks <= 1 || bytes.is_empty() {
            return vec![0, bytes.len()];
        }
        let n = plan_chunk_count_with(
            bytes.len(),
            max_chunks,
            SplitMode::Parallel,
            min_chunk_bytes.max(1),
        );
        if n <= 1 {
            return vec![0, bytes.len()];
        }
        // No section can exist without `<!` (comment/CDATA/DOCTYPE) or `<?`
        // (PI), so the cheap per-offset scan is exact. This keeps the common
        // section-free feed on the fast planning path.
        if memchr::memmem::find(bytes, b"<!").is_none()
            && memchr::memmem::find(bytes, b"<?").is_none()
        {
            return self.offset_points(bytes, n);
        }
        let len = bytes.len();
        let mut points = Vec::with_capacity(n + 1);
        points.push(0);
        let mut k = 1usize;
        let mut i = 0usize;
        while k < n {
            let Some((start, after_open)) = scan::find_open_sep(bytes, i, &self.sep) else {
                break;
            };
            if !scan::is_self_closing(&bytes[start..after_open]) {
                while k < n && len / n * k <= start {
                    if points.last() != Some(&start) {
                        points.push(start);
                    }
                    k += 1;
                }
            }
            i = after_open;
        }
        if points.last() != Some(&len) {
            points.push(len);
        }
        points
    }

    /// Plan cuts by probing each nominal offset, the way rypipe's default
    /// planner does. Only valid when the input holds no markup sections.
    fn offset_points(&self, bytes: &[u8], n: usize) -> Vec<usize> {
        let len = bytes.len();
        let mut points = vec![0usize];
        for k in 1..n {
            let approx = len / n * k;
            if let Some(pos) = self.next_record_start(bytes, approx) {
                if points.last() != Some(&pos) {
                    points.push(pos);
                }
            }
        }
        if points.last() != Some(&len) {
            points.push(len);
        }
        points.sort_unstable();
        points.dedup();
        points
    }
}

impl Splitter for XmlSplitter {
    fn next_record_start(&self, bytes: &[u8], from: usize) -> Option<usize> {
        let mut i = from;
        while i < bytes.len() {
            let (start, after_open) = scan::find_open_sep(bytes, i, &self.sep)?;
            // Self-closing separators carry no content: the next record is
            // the one after them.
            if scan::is_self_closing(&bytes[start..after_open]) {
                i = after_open;
                continue;
            }
            return Some(start);
        }
        None
    }

    fn estimate_bytes_per_row(&self, sample: &[u8]) -> usize {
        let count = memchr::memmem::find_iter(sample, &self.open_pattern)
            .count()
            .max(1);
        (sample.len() / count).max(1)
    }

    fn find_split_points(&self, bytes: &[u8], max_chunks: usize) -> Vec<usize> {
        self.split_points(bytes, max_chunks, MIN_CHUNK_BYTES)
    }

    fn find_split_points_with(
        &self,
        bytes: &[u8],
        max_chunks: usize,
        min_chunk_bytes: usize,
    ) -> Vec<usize> {
        self.split_points(bytes, max_chunks, min_chunk_bytes)
    }
}
