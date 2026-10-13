"""One consolidated comparison table: every engine on the same feed.

The common denominator is the plain synthetic feed from ``feeds.py`` at
~128 MiB (953,250 items by default): the Python per-item engines, the
columnar/parallel adapter paths and the native counters can all read it.

Rows: xmlstreamer-ng per-item (StreamInterpreter), XmlSource columnar,
XmlSource parallel (8 threads), XmlSource bounded parallel streaming,
xmlstreamer (original), lxml iterparse, stdlib ET iterparse, xmltodict,
plus the native parse+count references (quick-xml, simdxml, pugixml)
when their binaries exist.

Timing is best-of-N in this process. Peak RSS for the Python engines is
measured in a fresh ``--worker`` subprocess (VmHWM from
/proc/self/status, the same convention as bench_memory.py and
bench_rypipe.py). Peak RSS for the native counters comes from the
kernel: the binary is exec'd under ``os.wait4`` and its ``ru_maxrss``
is read from the rusage, so no /usr/bin/time dependency.

    python benchmarks/bench_all.py [--quick] [--rounds N] [--out FILE]
"""

import argparse
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from datetime import date
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from feeds import write_plain_feed  # noqa: E402

MB = 1024 * 1024
AVG_ITEM_BYTES = 110  # PLAIN_ITEM_TEMPLATE is ~110 bytes
DEFAULT_FEED_MB = 100  # -> 953,250 items, ~128 MiB on disk

HERE = Path(__file__).resolve().parent
BIN_DIR = HERE / "native" / "bin"
NATIVE_BINS = ("quick-xml", "simdxml", "pugixml")
# Native library versions, pinned by the lockfiles/native source the
# build script compiles (benchmarks/native/build_native.sh).
NATIVE_VERSIONS = {"quick-xml": "0.37.5", "simdxml": "0.2.1 (git)", "pugixml": "1.15"}


def make_feed(path: str, target_mb: int) -> int:
    """Write a plain feed of roughly ``target_mb`` megabytes; returns bytes."""
    n_items = max(1, (target_mb * MB) // AVG_ITEM_BYTES)
    with open(path, "wb") as f:
        written = write_plain_feed(f, n_items, block_items=50_000)
    return written


# ---------------------------------------------------------------------------
# Engines: each takes a path and returns the item count it processed.
# ---------------------------------------------------------------------------


def _ng_per_item(path: str) -> int:
    from xmlstreamer_ng import StreamInterpreter

    with open(path, "rb") as source:
        return sum(
            1
            for _ in StreamInterpreter(source=source, separator_tag="item")
        )


def _ng_columnar(path: str) -> int:
    from xmlstreamer_ng import _xmlstreamer

    return _xmlstreamer.read_xml(path, separator_tag="item", use_mmap=True).num_rows


def _ng_parallel8(path: str) -> int:
    from xmlstreamer_ng import _xmlstreamer

    return _xmlstreamer.read_xml_par(
        path, separator_tag="item", chunks=8, use_mmap=True
    ).num_rows


def _ng_par_stream8(path: str) -> int:
    from xmlstreamer_ng import _xmlstreamer

    return sum(
        b.num_rows
        for b in _xmlstreamer.iter_xml_batches_par(
            path, separator_tag="item", threads=8, memory="64MiB", use_mmap=True
        )
    )


def _xmlstreamer_original(path: str) -> int:
    from xmlstreamer import StreamInterpreter

    count = 0
    with open(path, "rb") as source:
        for _ in StreamInterpreter(source=source, separator_tag="item"):
            count += 1
    return count


def _lxml(path: str) -> int:
    from lxml import etree

    count = 0
    with open(path, "rb") as source:
        for _, element in etree.iterparse(
            source, events=("end",), tag="item", recover=True
        ):
            count += 1
            element.clear(keep_tail=True)
            while element.getprevious() is not None:
                del element.getparent()[0]
    return count


def _stdlib(path: str) -> int:
    import xml.etree.ElementTree as ElementTree

    count = 0
    with open(path, "rb") as source:
        iterator = ElementTree.iterparse(source, events=("start", "end"))
        _, root = next(iterator)
        for event, element in iterator:
            if event == "end" and element.tag == "item":
                count += 1
                root.clear()
    return count


def _xmltodict(path: str) -> int:
    import xmltodict

    with open(path, "rb") as source:
        document = xmltodict.parse(source)
    root = next(iter(document.values()), None) if document else None
    items = (root or {}).get("item", [])
    if isinstance(items, dict):
        items = [items]
    return len(items)


# name -> (callable, threads, note)
ENGINES: Dict[str, Tuple[Callable[[str], int], int, str]] = {
    "xmlstreamer-ng per-item": (_ng_per_item, 1, "per-item dicts"),
    "XmlSource columnar": (_ng_columnar, 1, "Arrow batches"),
    "XmlSource parallel (8 threads)": (_ng_parallel8, 8, "Arrow batches, 8 threads"),
    "XmlSource bounded parallel streaming": (
        _ng_par_stream8, 8, "bounded batches, 8 threads",
    ),
    "xmlstreamer (original)": (_xmlstreamer_original, 1, "per-item dicts"),
    "lxml iterparse": (_lxml, 1, "iterparse + clear()"),
    "stdlib ET iterparse": (_stdlib, 1, "iterparse + root.clear()"),
    "xmltodict": (_xmltodict, 1, "whole-document dict"),
}

ROWS_ORDER = list(ENGINES) + list(NATIVE_BINS)


def _peak_rss_mb() -> float:
    """Own peak RSS (VmHWM restarts at exec(); ru_maxrss does not)."""
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmHWM:"):
                return int(line.split()[1]) / 1024
    except OSError:
        pass
    import resource

    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def worker(engine: str, path: str) -> None:
    fn = ENGINES[engine][0]
    t0 = time.perf_counter()
    items = fn(path)
    print(json.dumps({
        "items": items,
        "seconds": time.perf_counter() - t0,
        "peak_mb": _peak_rss_mb(),
    }))


def available_native_bins() -> Dict[str, Path]:
    found = {}
    for name in NATIVE_BINS:
        exe = BIN_DIR / f"{name.replace('-', '_')}_counter"
        if exe.exists():
            found[name] = exe
    return found


def _run_native(exe: Path, path: str, rounds: int) -> Tuple[int, float]:
    """Best of two invocations; the binary self-times best-of-N internally."""
    best = None
    items = 0
    for _ in range(2):
        out = subprocess.run(
            [str(exe), str(path), str(rounds)],
            capture_output=True, text=True, check=True,
        )
        n, secs = out.stdout.strip().split("\t")
        items = int(n)
        if best is None or float(secs) < best:
            best = float(secs)
    return items, best


def _run_native_rss(exe: Path, path: str, rounds: int) -> float:
    """Peak RSS of the native counter via os.wait4 rusage (ru_maxrss).

    Avoids a /usr/bin/time dependency; the child is exec'd directly.
    """
    import warnings

    with warnings.catch_warnings():
        # fork in a process that has imported thread-using libs (pyarrow);
        # the child only exec()s, it never touches locks.
        warnings.simplefilter("ignore", DeprecationWarning)
        pid = os.fork()
    if pid == 0:  # child
        try:
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, 1)
            os.execv(str(exe), [str(exe), str(path), str(rounds)])
        finally:
            os._exit(127)
    _, status, rusage = os.wait4(pid, 0)
    if not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
        raise RuntimeError(f"native counter failed: {exe}")
    return rusage.ru_maxrss / 1024


def _cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine()


def _dist_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return version("xmlstreamer-ng")


def _fmt_rate(rate: float) -> str:
    if rate >= 1_000_000:
        return f"{rate / 1_000_000:.1f}M"
    if rate >= 1_000:
        return f"{rate / 1_000:.0f}k"
    return f"{rate:.0f}"


def run_all(
    feed_mb: int, rounds: int, quick: bool
) -> Tuple[List[dict], Dict[str, str]]:
    """Returns (rows, extras); extras carries skip notes for absent natives."""
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
        path = f.name
    extras: Dict[str, str] = {}
    rows: List[dict] = []
    try:
        size = make_feed(path, 8 if quick else feed_mb)
        feed_miB = size / MB

        for name, (fn, threads, note) in ENGINES.items():
            best = None
            for _ in range(rounds):
                t0 = time.perf_counter()
                items = fn(path)
                elapsed = time.perf_counter() - t0
                if best is None or elapsed < best:
                    best = elapsed
            proc = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()),
                 "--worker", name, path],
                capture_output=True, text=True, check=True,
            )
            stats = json.loads(proc.stdout)
            rows.append({
                "engine": name, "items": items, "seconds": best,
                "items_s": items / best, "mbps": feed_miB / best,
                "rss_mb": stats["peak_mb"], "threads": threads, "note": note,
            })

        bins = available_native_bins()
        for name in NATIVE_BINS:
            exe = bins.get(name)
            if exe is None:
                extras[name] = (
                    "binary not built (run benchmarks/native/build_native.sh); "
                    "row omitted"
                )
                continue
            items, secs = _run_native(exe, path, rounds)
            rss = _run_native_rss(exe, path, rounds)
            rows.append({
                "engine": f"{name} {NATIVE_VERSIONS[name]}", "items": items,
                "seconds": secs, "items_s": items / secs,
                "mbps": feed_miB / secs, "rss_mb": rss, "threads": 1,
                "note": "parse+count only, no data",
            })
    finally:
        os.unlink(path)
    return rows, extras


def render_markdown(rows: List[dict], extras: Dict[str, str], feed_mb: int) -> str:
    items = rows[0]["items"] if rows else 0
    lines = [
        f"Common feed: synthetic plain feed (`feeds.py`), "
        f"{feed_mb} MiB target, {items:,} items. Best of N rounds.",
        "",
        f"Date: {date.today().isoformat()} | CPU: {_cpu_model()} | "
        f"Python {platform.python_version()} | "
        f"xmlstreamer-ng {_dist_version('xmlstreamer-ng')}, "
        f"xmlstreamer (original) {_dist_version('xmlstreamer')}, "
        f"lxml {_dist_version('lxml')}, "
        f"xmltodict {_dist_version('xmltodict')}, "
        f"pyarrow {_dist_version('pyarrow')}; "
        + ", ".join(f"{n} {v}" for n, v in NATIVE_VERSIONS.items()),
        "",
        "| engine | items/s | MB/s | peak RSS MB | threads | API/notes |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['engine']} | {_fmt_rate(r['items_s'])} | "
            f"{r['mbps']:.1f} | {r['rss_mb']:.0f} | {r['threads']} | "
            f"{r['note']} |"
        )
    if extras:
        lines.append("")
        for name, note in extras.items():
            lines.append(f"- {name}: {note}.")
    lines.append(
        "\nNative rows are speed-only references (parse and count, no "
        "encoding detection, recovery contract, or data materialization)."
    )
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) >= 4 and sys.argv[1] == "--worker":
        worker(sys.argv[2], sys.argv[3])
        return

    ap = argparse.ArgumentParser()
    ap.add_argument("--feed-mb", type=int, default=DEFAULT_FEED_MB)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--quick", action="store_true",
                    help="tiny feed; smoke-test only")
    ap.add_argument("--out", metavar="FILE",
                    help="also write the markdown table to FILE")
    args = ap.parse_args()

    feed_mb = 8 if args.quick else args.feed_mb
    rows, extras = run_all(args.feed_mb, 2 if args.quick else args.rounds,
                           args.quick)
    md = render_markdown(rows, extras, feed_mb)
    print(md)
    if args.out:
        Path(args.out).write_text(md + "\n")


if __name__ == "__main__":
    main()
