"""Native parse-throughput references (quick-xml, simdxml, pugixml).

Speed-only: these binaries fully parse a feed file and count <item>
elements. They carry none of the Python layer semantics (encoding
detection, recovery contract, Arrow materialization), so treat them as
an upper-bound ruler, not as like-for-like parser comparisons.

Binaries are built by benchmarks/native/build_native.sh into
benchmarks/native/bin/; this module skips gracefully when they are
missing.

    python benchmarks/native_bench.py            # human table
"""

import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from feeds import (  # noqa: E402
    cdata_feed,
    plain_feed,
    write_plain_feed_mb,
)

MB = 1024 * 1024
BIG_MIB = 128  # same 128 MiB feed the other harnesses use

HERE = Path(__file__).resolve().parent
BIN_DIR = HERE / "native" / "bin"

BINS = ("quick-xml", "simdxml", "pugixml")


def available_bins() -> Dict[str, Path]:
    found = {}
    for name in BINS:
        exe = BIN_DIR / f"{name.replace('-', '_')}_counter"
        if exe.exists():
            found[name] = exe
    return found


def make_feeds(quick: bool) -> Dict[str, Tuple[Path, int]]:
    """The same feeds the rest of the harness uses, written to a temp dir."""
    sizes = (
        {"plain": 100_000, "cdata": 50_000, "big_mib": BIG_MIB}
        if not quick
        else {"plain": 2_000, "cdata": 1_000, "big_mib": 8}
    )
    feeds: Dict[str, Tuple[Path, int]] = {}
    tmp = Path(tempfile.mkdtemp(prefix="ng-native-"))
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


def run_native(
    quick: bool = False, rounds: int = 3, bins: Optional[Dict[str, Path]] = None
) -> List[dict]:
    bins = bins if bins is not None else available_bins()
    results = []
    feeds = make_feeds(quick)
    for feed_name, (path, size) in feeds.items():
        for name, exe in bins.items():
            # The binary self-times best-of-N internally; run it twice and
            # keep the best so page-cache state cannot skew a single shot.
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
            results.append({
                "feed": feed_name, "parser": name, "items": items,
                "seconds": best, "rate": items / best,
                "mbps": size / MB / best, "feed_bytes": size,
            })
    return results


def main() -> None:
    bins = available_bins()
    if not bins:
        print(
            "native binaries not built; run benchmarks/native/build_native.sh",
            file=sys.stderr,
        )
        sys.exit(1)
    print(
        "| feed | parser | items | best seconds | items/s | MB/s |",
        "|---|---|---|---|---|---|",
        sep="\n",
    )
    for r in run_native(bins=bins):
        print(
            f"| {r['feed']} | {r['parser']} | {r['items']:,} | "
            f"{r['seconds']:.3f} | {r['rate']:,.0f} | {r['mbps']:,.1f} |"
        )


if __name__ == "__main__":
    main()
