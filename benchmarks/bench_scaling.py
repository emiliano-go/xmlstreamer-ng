"""Rypipe adapter scaling benchmark, crxml style.

Rows/s and MB/s across the adapter paths (read_xml / read_xml_par /
read_xml_stream / iter_xml_batches_par) at thread counts 1, 2, 4, 8, 12,
on three deterministic feeds (feeds.py): the flat 100k-item feed, the
CDATA 50k-item feed and a 128 MiB plain feed.

    uv run --group bench python benchmarks/bench_scaling.py [--quick]

Rows are the median of N rounds (best and p95 reported too); absolute
numbers track the machine (CPU, page-cache state, background load), the
thread-count shape is the result.
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

from feeds import (  # noqa: E402
    cdata_feed,
    plain_feed,
    write_plain_feed_mb,
)
from stats import summarize  # noqa: E402

MB = 1024 * 1024
THREADS = (1, 2, 4, 8, 12)
BIG_MIB = 128


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
        _, written = write_plain_feed_mb(f, sizes["big_mib"], block_items=50_000)
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
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--out", metavar="FILE")
    args = ap.parse_args()

    lines = [
        "# rypipe adapter scaling (crxml style)",
        "",
        f"Date: {date.today().isoformat()} | CPU: {_cpu_model()} | "
        f"Python {platform.python_version()} | "
        f"xmlstreamer_ng {version('xmlstreamer-ng')}, "
        f"pyarrow {version('pyarrow')}",
    ]
    if args.quick:
        lines.append(
            "\nMode: --quick (smoke sizes; numbers are NOT representative)"
        )

    feeds = make_feeds(args.quick)
    paths = _paths()
    rows: List[List[str]] = []
    for feed_name, (path, size) in feeds.items():
        for path_name, fn in paths.items():
            times = []
            n_rows = 0
            for _ in range(args.rounds):
                t0 = time.perf_counter()
                n_rows = fn(str(path))
                times.append(time.perf_counter() - t0)
            timing = summarize(times)
            rows.append([
                feed_name,
                path_name,
                f"{n_rows:,}",
                f"{timing['median']:.3f}",
                f"{timing['best']:.3f}",
                f"{timing['p95']:.3f}",
                f"{timing['spread']:.1f}%",
                f"{n_rows / timing['median']:,.0f}",
                f"{size / MB / timing['median']:,.1f}",
            ])

    lines.append(
        "\n| feed | path | rows | median s | best s | p95 s | spread | "
        "rows/s (median) | MB/s |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    text = "\n".join(lines)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n")


if __name__ == "__main__":
    main()
