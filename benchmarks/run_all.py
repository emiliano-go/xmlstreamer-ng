"""Run every benchmark and print the results as markdown tables.

    uv run --group bench python benchmarks/run_all.py [--quick]

--quick shrinks datasets and rounds to smoke-test the harness (CI).
"""

import argparse
import platform
import sys
from datetime import date
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bench_memory import run_memory
from bench_speed import run_speed
from gauntlet import CASES, GAUNTLET_PARSERS, run_gauntlet
from parsers import LABELS


def markdown_table(headers: List[str], rows: List[List[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)


def _cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine()


def _label(parser_key: str) -> str:
    return LABELS.get(parser_key, parser_key)


def _dist_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return version("xmlstreamer-ng")


def main() -> None:
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("--quick", action="store_true")
    args = arg_parser.parse_args()

    print("# xmlstreamer benchmarks\n")
    print(
        f"Date: {date.today().isoformat()} | CPU: {_cpu_model()} | "
        f"Python {platform.python_version()} | "
        f"xmlstreamer_ng {_dist_version('xmlstreamer-ng')}, "
        f"xmlstreamer (original) {version('xmlstreamer')}, "
        f"lxml {version('lxml')}, "
        f"xmltodict {version('xmltodict')}, chardet {version('chardet')}"
    )
    if args.quick:
        print("\nMode: --quick (smoke sizes; numbers are NOT representative)")

    print("\n## Speed (parse-only, same in-memory bytes, best of N)\n")
    speed_rows = []
    for r in run_speed(quick=args.quick):
        speed_rows.append([
            r["feed"], _label(r["parser"]), f"{r['items']:,}",
            f"{r['seconds']:.3f}", f"{r['rate']:,.0f}",
        ])
    print(markdown_table(
        ["feed", "parser", "items", "seconds", "items/s"], speed_rows
    ))

    print("\n## Peak memory (one subprocess per parser, RSS)\n")
    memory_rows = []
    for r in run_memory(quick=args.quick):
        feed_mb = r["feed_bytes"] / (1024 * 1024)
        label = (
            "(python + imports baseline)"
            if r["parser"] == "baseline" else _label(r["parser"])
        )
        memory_rows.append([
            label, f"{feed_mb:,.0f}", f"{r['peak_mb']:,.0f}",
            f"{r['items']:,}", f"{r['seconds']:.2f}",
        ])
    print(markdown_table(
        ["parser", "feed MB", "peak RSS MB", "items", "seconds"], memory_rows
    ))

    print("\n## Dirty-feed gauntlet (what each parser does to broken input)\n")
    gauntlet_rows = run_gauntlet()
    headers = ["case"] + list(GAUNTLET_PARSERS)
    print(markdown_table(headers, gauntlet_rows))
    notes = [c for c in CASES if c.note]
    if notes:
        print()
        for case in notes:
            print(f"- {case.name}: {case.note}")

    print("\n## Native references (raw parse throughput, speed only)\n")
    try:
        from native_bench import available_bins, run_native
    except ImportError:  # pragma: no cover - defensive
        available_bins = None
        run_native = None
    if available_bins is not None and available_bins():
        native_rows = []
        for r in run_native(quick=args.quick):
            native_rows.append([
                r["feed"], r["parser"], f"{r['items']:,}",
                f"{r['seconds']:.3f}", f"{r['rate']:,.0f}", f"{r['mbps']:,.1f}",
            ])
        print(markdown_table(
            ["feed", "parser", "items", "seconds", "items/s", "MB/s"],
            native_rows,
        ))
        print(
            "\nThese binaries fully parse the file and count <item> "
            "elements. They carry none of the Python layer semantics "
            "(encoding detection, recovery contract, Arrow "
            "materialization): an upper-bound ruler, not a like-for-like "
            "parser comparison. Build them with "
            "benchmarks/native/build_native.sh."
        )
    else:
        print(
            "skipped: native binaries not built "
            "(run benchmarks/native/build_native.sh to enable)"
        )


if __name__ == "__main__":
    main()
