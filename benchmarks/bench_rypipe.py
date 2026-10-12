"""Aggressive file-level benchmarks for the rypipe adapter.

Measures the legacy per-item engine against the rypipe columnar, parallel and
bounded-streaming paths on large, deterministic feeds.

    uv run --group bench python benchmarks/bench_rypipe.py --feed-mb 100

Rows are best-of-N; peak RSS is measured in a fresh subprocess
(``--worker <engine>``) from ``/proc/self/status``.
"""

import argparse
import os
import resource
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

from feeds import write_plain_feed  # noqa: E402

MB = 1024 * 1024
AVG_ITEM_BYTES = 110  # PLAIN_ITEM_TEMPLATE is ~110 bytes


def make_feed(path: str, target_mb: int) -> int:
    """Write a plain feed of roughly ``target_mb`` megabytes; returns bytes."""
    n_items = max(1, (target_mb * MB) // AVG_ITEM_BYTES)
    with open(path, "wb") as f:
        written = write_plain_feed(f, n_items, block_items=50_000)
    return written


# --------------------------------------------------------------------------
# Engines: each takes (path, data) and returns (items_processed, seconds)
# --------------------------------------------------------------------------


def _legacy(path: str, data: bytes) -> int:
    from io import BytesIO

    from parsers import consume_xmlstreamer

    count = [0]

    def sink(record):
        count[0] += 1

    consume_xmlstreamer(BytesIO(data), sink)
    return count[0]


def _columnar(path: str) -> int:
    from xmlstreamer import _xmlstreamer

    return _xmlstreamer.read_xml(path, separator_tag="item", use_mmap=True).num_rows


def _parallel(chunks: int) -> Callable[[str], int]:
    def run(path: str) -> int:
        from xmlstreamer import _xmlstreamer

        return _xmlstreamer.read_xml_par(
            path, separator_tag="item", chunks=chunks, use_mmap=True
        ).num_rows

    return run


def _stream(memory: str) -> Callable[[str], int]:
    def run(path: str) -> int:
        from xmlstreamer import _xmlstreamer

        return sum(
            b.num_rows
            for b in _xmlstreamer.read_xml_stream(
                path, separator_tag="item", memory=memory
            )
        )

    return run


def _par_stream(threads: int, memory: str = "64MiB") -> Callable[[str], int]:
    def run(path: str) -> int:
        from xmlstreamer import _xmlstreamer

        return sum(
            b.num_rows
            for b in _xmlstreamer.iter_xml_batches_par(
                path,
                separator_tag="item",
                threads=threads,
                memory=memory,
                use_mmap=True,
            )
        )

    return run


def _projection(path: str) -> int:
    from xmlstreamer import _xmlstreamer

    return _xmlstreamer.read_xml(
        path,
        separator_tag="item",
        use_mmap=True,
        drop_fields=["title", "author", "publisher", "year"],
    ).num_rows


# A declared schema acts as a projection: only these columns are wanted, so
# the parser skips scanning the rest (the documented +80% projection win).
_PROJ_SCHEMA = ["id"]


def _stdlib(path: str) -> int:
    import xml.etree.ElementTree as ET

    count = 0
    iterator = ET.iterparse(open(path, "rb"), events=("start", "end"))
    _, root = next(iterator)
    for event, element in iterator:
        if event == "end" and element.tag == "item":
            count += 1
            root.clear()
    return count


def _lxml(path: str) -> int:
    from lxml import etree

    count = 0
    for _, element in etree.iterparse(
        open(path, "rb"), events=("end",), tag="item", recover=True
    ):
        count += 1
        element.clear(keep_tail=True)
        while element.getprevious() is not None:
            del element.getparent()[0]
    return count


def _columnar_proj(path: str) -> int:
    from xmlstreamer import _xmlstreamer

    return _xmlstreamer.read_xml(
        path,
        separator_tag="item",
        use_mmap=True,
        schema=_PROJ_SCHEMA,
    ).num_rows


def _par_proj(chunks: int) -> Callable[[str], int]:
    def run(path: str) -> int:
        from xmlstreamer import _xmlstreamer

        return _xmlstreamer.read_xml_par(
            path,
            separator_tag="item",
            chunks=chunks,
            use_mmap=True,
            schema=_PROJ_SCHEMA,
        ).num_rows

    return run


ENGINES: Dict[str, Callable] = {
    "legacy (per-item)": _legacy,  # special: needs the whole buffer
    "rypipe columnar": _columnar,
    "rypipe par4": _parallel(4),
    "rypipe par8": _parallel(8),
    "rypipe par12": _parallel(12),
    "rypipe stream64": _stream("64MiB"),
    "rypipe par-stream8": _par_stream(8),
    "rypipe columnar drop4": _projection,
    "rypipe columnar proj1": _columnar_proj,
    "rypipe par8 proj1": _par_proj(8),
    "stdlib ET iterparse": _stdlib,
    "lxml iterparse (recover)": _lxml,
}


def _run_one(name: str, fn, path: str, data: bytes) -> float:
    t0 = time.perf_counter()
    if name.startswith("legacy"):
        fn(path, data)
    else:
        fn(path)
    return time.perf_counter() - t0


def peak_rss_mb() -> float:
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmHWM:"):
                return int(line.split()[1]) / 1024
    except OSError:
        pass
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def worker(engine: str, path: str) -> None:
    fn = ENGINES[engine]
    if engine.startswith("legacy"):
        data = Path(path).read_bytes()
        n = fn(path, data)
    else:
        n = fn(path)
    print(f"{engine}\t{n}\t{peak_rss_mb():.1f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--feed-mb", type=int, default=100)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--worker", nargs=2, metavar=("ENGINE", "PATH"))
    args = ap.parse_args()

    if args.worker:
        worker(args.worker[0], args.worker[1])
        return

    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
        path = f.name
    try:
        size = make_feed(path, args.feed_mb)
        data = Path(path).read_bytes()
        print(
            f"# rypipe adapter benchmark\n\nfeed: {path} "
            f"({size / MB:.1f} MiB)\n\n"
            "| engine | items | seconds | items/s | MB/s | peak RSS MB |"
        )
        print("|---|---|---|---|---|---|")

        for name, fn in ENGINES.items():
            best = None
            items = 0
            for _ in range(args.rounds):
                elapsed = _run_one(name, fn, path, data)
                if best is None or elapsed < best:
                    best = elapsed
            # item count from a single clean run
            if name.startswith("legacy"):
                items = fn(path, data)
            else:
                items = fn(path)
            rss = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--worker",
                    name,
                    path,
                ],
                capture_output=True,
                text=True,
            )
            peak = "?"
            if rss.returncode == 0 and rss.stdout.strip():
                peak = rss.stdout.strip().split("\t")[-1]
            print(
                f"| {name} | {items:,} | {best:.3f} | {items / best:,.0f} "
                f"| {size / MB / best:,.1f} | {peak} |"
            )
    finally:
        if not args.keep:
            os.unlink(path)


if __name__ == "__main__":
    main()
