"""Rypipe adapter scaling benchmark, crxml style.

Rows/s and MB/s across the adapter paths (read_xml / read_xml_par /
read_xml_stream / iter_xml_batches_par) at thread counts 1, 2, 4, 8, 12,
on three deterministic feeds (feeds.py): the flat 100k-item feed, the
CDATA 50k-item feed and a 128 MiB plain feed.

    uv run --group bench python benchmarks/bench_scaling.py [--quick]

Rows are best-of-N rounds; absolute numbers track the machine (CPU,
page-cache state, background load), the thread-count shape is the result.
"""

import argparse
import platform
import sys
import tempfile
import time
from datetime import date
from importlib.metadata import version
from pathlib import Path
from typing import Callable, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from feeds import cdata_feed, plain_feed, write_plain_feed  # noqa: E402

MB = 1024 * 1024
THREADS = (1, 2, 4, 8, 12)
AVG_ITEM_BYTES = 110  # PLAIN_ITEM_TEMPLATE is ~110 bytes
# Target size for the big feed; actual output is ~1.28x (the template is
# ~141 bytes), so 100 MiB lands on the ~128 MiB feed bench_rypipe.py
# produces with --feed-mb 100 and docs/benchmarks/adapter.md reports.
BIG_MIB = 100


def _cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine()


def make_feeds(quick: bool) -> Dict[str, Tuple[Path, int]]:
    """Write the three feeds to a temp dir; returns name -> (path, bytes)."""
    sizes = (
        {"plain": 100_000, "cdata": 50_000, "big_mib": BIG_MIB}
        if not quick
        else {"plain": 5_000, "cdata": 2_500, "big_mib": 8}
    )
    feeds: Dict[str, Tuple[Path, int]] = {}
    tmp = Path(tempfile.mkdtemp(prefix="ng-scaling-"))
    plain_path = tmp / "plain.xml"
    plain_path.write_bytes(plain_feed(sizes["plain"]))
    feeds[f"plain {sizes['plain']:,}"] = (plain_path, plain_path.stat().st_size)
    cdata_path = tmp / "cdata.xml"
    cdata_path.write_bytes(cdata_feed(sizes["cdata"]))
    feeds[f"cdata {sizes['cdata']:,}"] = (cdata_path, cdata_path.stat().st_size)
    big_path = tmp / "big.xml"
    with open(big_path, "wb") as f:
        n = max(1, (sizes["big_mib"] * MB) // AVG_ITEM_BYTES)
        written = write_plain_feed(f, n, block_items=50_000)
    feeds[f"plain {written / MB:,.0f} MiB"] = (big_path, written)
    return feeds


# --------------------------------------------------------------------------
# Paths: each takes a file path and returns rows processed
# --------------------------------------------------------------------------


def _read_xml(path: str) -> int:
    from xmlstreamer_ng import _xmlstreamer

    return _xmlstreamer.read_xml(path, separator_tag="item", use_mmap=True).num_rows


def _read_xml_par(threads: int) -> Callable[[str], int]:
    def run(path: str) -> int:
        from xmlstreamer_ng import _xmlstreamer

        return _xmlstreamer.read_xml_par(
            path, separator_tag="item", chunks=threads, use_mmap=True
        ).num_rows

    return run


def _read_xml_stream(path: str) -> int:
    from xmlstreamer_ng import _xmlstreamer

    return sum(
        b.num_rows
        for b in _xmlstreamer.read_xml_stream(path, separator_tag="item", memory="64MiB")
    )


def _iter_batches_par(threads: int) -> Callable[[str], int]:
    def run(path: str) -> int:
        from xmlstreamer_ng import _xmlstreamer

        return sum(
            b.num_rows
            for b in _xmlstreamer.iter_xml_batches_par(
                path,
                separator_tag="item",
                threads=threads,
                memory="64MiB",
                use_mmap=True,
            )
        )

    return run


def _paths() -> Dict[str, Callable[[str], int]]:
    paths: Dict[str, Callable[[str], int]] = {
        "read_xml": _read_xml,
        "read_xml_stream (64MiB)": _read_xml_stream,
    }
    for t in THREADS:
        paths[f"read_xml_par (chunks={t})"] = _read_xml_par(t)
    for t in THREADS:
        paths[f"iter_xml_batches_par (threads={t})"] = _iter_batches_par(t)
    return paths


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()

    print("# rypipe adapter scaling (crxml style)\n")
    print(
        f"Date: {date.today().isoformat()} | CPU: {_cpu_model()} | "
        f"Python {platform.python_version()} | "
        f"xmlstreamer_ng {version('xmlstreamer-ng')}, "
        f"pyarrow {version('pyarrow')}"
    )
    if args.quick:
        print("\nMode: --quick (smoke sizes; numbers are NOT representative)")

    feeds = make_feeds(args.quick)
    paths = _paths()
    rows: List[List[str]] = []
    for feed_name, (path, size) in feeds.items():
        for path_name, fn in paths.items():
            best = None
            n_rows = 0
            for _ in range(args.rounds):
                t0 = time.perf_counter()
                n_rows = fn(str(path))
                elapsed = time.perf_counter() - t0
                if best is None or elapsed < best:
                    best = elapsed
            rows.append([
                feed_name,
                path_name,
                f"{n_rows:,}",
                f"{best:.3f}",
                f"{n_rows / best:,.0f}",
                f"{size / MB / best:,.1f}",
            ])

    print("\n| feed | path | rows | seconds | rows/s | MB/s |")
    print("|---|---|---|---|---|---|")
    for row in rows:
        print("| " + " | ".join(row) + " |")


if __name__ == "__main__":
    main()
