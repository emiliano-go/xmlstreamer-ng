// Raw parse-throughput reference: fully parse an XML feed with quick-xml
// and count the closing </item> tags. No Python semantics, speed only.
//
// Usage: quick_xml_counter <file.xml> [rounds]
// Prints: <items>\t<best_seconds>

use std::time::Instant;

use quick_xml::events::Event;
use quick_xml::reader::Reader;

fn count_items(path: &str) -> usize {
    let mut reader = Reader::from_file(path)
        .expect("open input file");
    reader.config_mut().trim_text(true);
    let mut buf = Vec::with_capacity(64 * 1024);
    let mut count = 0usize;
    loop {
        match reader.read_event_into(&mut buf) {
            Ok(Event::End(e)) => {
                if e.name().as_ref() == b"item" {
                    count += 1;
                }
            }
            Ok(Event::Eof) => break,
            Err(e) => panic!("parse error at {}: {e}", reader.error_position()),
            _ => {}
        }
        buf.clear();
    }
    count
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
