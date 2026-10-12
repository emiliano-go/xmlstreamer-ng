"""Parse-only throughput: every parser gets the same in-memory bytes,
best of N rounds. One extra non-comparative row measures xmlstreamer's
full pipeline over HTTP loopback (download + encoding detection)."""

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from typing import Dict, List

from feeds import cdata_feed, plain_feed
from parsers import PARSERS

FULL_SIZES = {"plain": 100_000, "cdata": 50_000}
QUICK_SIZES = {"plain": 2_000, "cdata": 1_000}


def _one_run(consume, data: bytes) -> float:
    source = BytesIO(data)
    counter = [0]

    def sink(record):
        counter[0] += 1

    t0 = time.perf_counter()
    consume(source, sink)
    return time.perf_counter() - t0


def run_speed(quick: bool = False) -> List[Dict]:
    sizes = QUICK_SIZES if quick else FULL_SIZES
    rounds = 2 if quick else 7
    datasets = {
        "plain": plain_feed(sizes["plain"]),
        "cdata": cdata_feed(sizes["cdata"]),
    }
    results = []
    parser_list = list(PARSERS.items())
    for feed_name, data in datasets.items():
        # Interleave parsers within each round AND rotate who goes first:
        # with monotonic thermal throttling, a fixed order systematically
        # favors whoever runs first in the coldest round.
        best: Dict[str, float] = {}
        for round_number in range(rounds):
            shift = round_number % len(parser_list)
            for parser_key, consume in (
                parser_list[shift:] + parser_list[:shift]
            ):
                elapsed = _one_run(consume, data)
                if parser_key not in best or elapsed < best[parser_key]:
                    best[parser_key] = elapsed
        for parser_key in PARSERS:
            results.append({
                "feed": feed_name,
                "parser": parser_key,
                "items": sizes[feed_name],
                "seconds": best[parser_key],
                "rate": sizes[feed_name] / best[parser_key],
            })
    results.append(_end_to_end(datasets["plain"], sizes["plain"], rounds))
    return results


class _FeedHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = self.server.feed_body
        self.send_response(200)
        self.send_header("Content-Type", "application/xml")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def _end_to_end(data: bytes, n_items: int, rounds: int) -> Dict:
    """StreamInterpreter over HTTP loopback: the whole real pipeline.
    Informative row, not comparable with the parse-only numbers."""
    from xmlstreamer import StreamInterpreter, Transport

    server = ThreadingHTTPServer(("127.0.0.1", 0), _FeedHandler)
    server.feed_body = data
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        interpreter = StreamInterpreter(
            url=f"http://{host}:{port}/feed.xml",
            separator_tag="item",
            transport=Transport(download_mode="stream"),
        )
        best = None
        for _ in range(rounds):
            t0 = time.perf_counter()
            count = sum(1 for _ in interpreter)
            elapsed = time.perf_counter() - t0
            assert count == n_items, f"{count} != {n_items}"
            if best is None or elapsed < best:
                best = elapsed
    finally:
        server.shutdown()
        server.server_close()
    return {
        "feed": "plain",
        "parser": "xmlstreamer end-to-end (HTTP)",
        "items": n_items,
        "seconds": best,
        "rate": n_items / best,
    }
