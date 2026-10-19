"""Corpus benchmark: run the hand-authored valid/invalid feeds through the
same parsers as the synthetic harness.

    uv run --group bench python benchmarks/bench_corpus.py
    uv run --group bench python benchmarks/bench_corpus.py --corpus DIR

Rows are the median of N rounds (default 50: these feeds are tiny, so a
single scheduling hiccup is a large fraction of one round). The corpus is
deliberately small; use it to check that a change holds up on different XML
shapes, not to replace the large-feed numbers in ``bench_all.py``.
"""

import argparse
import os
import platform
import sys
import time
from datetime import date
from importlib.metadata import version
from io import BytesIO
from pathlib import Path
from typing import Callable, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus import VALID_DIR, load_corpus  # noqa: E402
from parsers import (  # noqa: E402
    consume_lxml,
    consume_stdlib,
    consume_xmlstreamer,
)
from stats import summarize  # noqa: E402

MIB = 1024 * 1024

PARSERS: Dict[str, Callable] = {
    "xmlstreamer-ng": consume_xmlstreamer,
    "lxml": consume_lxml,
    "stdlib ET": consume_stdlib,
}


def _run(consume: Callable, data: bytes) -> tuple[int, float]:
    counter = [0]

    def sink(record):
        counter[0] += 1

    t0 = time.perf_counter()
    consume(BytesIO(data), sink)
    return counter[0], time.perf_counter() - t0


def _cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--corpus", default=str(VALID_DIR),
        help=f"directory of *.xml files (default: {VALID_DIR})",
    )
    ap.add_argument("--rounds", type=int, default=50)
    ap.add_argument("--out", metavar="FILE")
    args = ap.parse_args()

    files = load_corpus(args.corpus)
    if not files:
        raise SystemExit(f"no *.xml files in {args.corpus}")
    display = os.path.relpath(args.corpus)

    lines = [
        "# corpus benchmark",
        "",
        f"Date: {date.today().isoformat()} | CPU: {_cpu_model()} | "
        f"Python {platform.python_version()} | "
        f"xmlstreamer_ng {version('xmlstreamer-ng')}, "
        f"lxml {version('lxml')}",
        "",
        f"Corpus: `{display}` ({len(files)} files). Median of "
        f"{args.rounds} rounds; spread is not shown because a trace "
        "fixture's runtime is dominated by fixed per-call overhead.",
        "",
        "| file | parser | items | median ms | best ms | p95 ms | "
        "items/s | MB/s |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for name, data in files:
        for parser_name, consume in PARSERS.items():
            times = []
            items = 0
            for _ in range(args.rounds):
                items, elapsed = _run(consume, data)
                times.append(elapsed)
            timing = summarize(times)
            lines.append(
                f"| {name} | {parser_name} | {items:,} | "
                f"{timing['median'] * 1000:.3f} | "
                f"{timing['best'] * 1000:.3f} | "
                f"{timing['p95'] * 1000:.3f} | "
                f"{items / timing['median']:,.0f} | "
                f"{len(data) / MIB / timing['median']:,.2f} |"
            )

    text = "\n".join(lines)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n")


if __name__ == "__main__":
    main()
