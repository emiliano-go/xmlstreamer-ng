"""Peak memory per parser over a big on-disk feed. Each parser runs in
its own subprocess so ru_maxrss reflects that parser alone; the parent
only orchestrates. RSS is the honest metric here: tracemalloc cannot
see lxml/expat C allocations."""

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List

FULL_ITEMS = 900_000  # ~121 MB feed
QUICK_ITEMS = 40_000


def _peak_rss_kb() -> int:
    """Own peak RSS. VmHWM restarts at exec(); ru_maxrss does NOT (it
    inherits the forking parent's peak on Linux), so prefer VmHWM."""
    try:
        with open("/proc/self/status") as status:
            for line in status:
                if line.startswith("VmHWM:"):
                    return int(line.split()[1])
    except OSError:
        pass
    import resource

    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss


def _worker(parser_key: str, path: str) -> None:
    from parsers import PARSERS

    counter = [0]

    def sink(record):
        counter[0] += 1

    t0 = time.perf_counter()
    if parser_key != "baseline":
        with open(path, "rb") as source:
            PARSERS[parser_key](source, sink)
    elapsed = time.perf_counter() - t0
    print(json.dumps({
        "maxrss_kb": _peak_rss_kb(),
        "items": counter[0],
        "seconds": elapsed,
    }))


def run_memory(quick: bool = False) -> List[Dict]:
    from feeds import write_plain_feed

    n_items = QUICK_ITEMS if quick else FULL_ITEMS
    results = []
    with tempfile.NamedTemporaryFile(suffix=".xml") as feed_file:
        feed_bytes = write_plain_feed(feed_file, n_items)
        parser_keys = [
            "baseline", "xmlstreamer", "lxml", "stdlib",
            "xmltodict-stream", "xmltodict",
        ]
        for parser_key in parser_keys:
            proc = subprocess.run(
                [
                    sys.executable, str(Path(__file__).resolve()),
                    "--worker", parser_key, feed_file.name,
                ],
                capture_output=True, text=True, check=True,
            )
            stats = json.loads(proc.stdout)
            results.append({
                "parser": parser_key,
                "feed_bytes": feed_bytes,
                "peak_mb": stats["maxrss_kb"] / 1024,
                "items": stats["items"],
                "seconds": stats["seconds"],
            })
    return results


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--worker":
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        _worker(sys.argv[2], sys.argv[3])
    else:
        raise SystemExit("run via run_all.py, or: --worker <parser> <path>")
