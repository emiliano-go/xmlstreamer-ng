// Raw parse-throughput reference: index an XML feed with simdxml
// (structural indexing, SIMD-accelerated) and count <item> tags.
// No Python semantics, speed only.
//
// Usage: simdxml_counter <file.xml> [rounds]
// Prints: <items>\t<best_seconds>

use std::time::Instant;

fn count_items(path: &str) -> usize {
    let data = std::fs::read(path).expect("read input file");
    let mut index = simdxml::parse(&data).expect("parse XML");
    index.build_name_index();
    index.tags_by_name("item").len()
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let path = &args[1];
    let rounds: usize = args.get(2).map(|s| s.parse().unwrap()).unwrap_or(1);
    let mut best = f64::INFINITY;
    let mut items = 0usize;
    for _ in 0..rounds {
        let t0 = Instant::now();
        items = count_items(path);
        best = best.min(t0.elapsed().as_secs_f64());
    }
    println!("{items}\t{best:.6}");
}
