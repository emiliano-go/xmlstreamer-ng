"""Run every benchmark and print the results as markdown tables.

    uv run --group bench python benchmarks/run_all.py [--quick]

--quick shrinks datasets and rounds to smoke-test the harness (CI).
"""

import argparse
import platform
import sys
from datetime import date
from importlib.metadata import version
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


def main() -> None:
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("--quick", action="store_true")
    args = arg_parser.parse_args()

    print("# xmlstreamer benchmarks\n")
    print(
        f"Date: {date.today().isoformat()} | CPU: {_cpu_model()} | "
        f"Python {platform.python_version()} | "
        f"xmlstreamer {version('xmlstreamer')}, lxml {version('lxml')}, "
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


if __name__ == "__main__":
    main()
