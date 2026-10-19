"""The benchmark harness pieces that run without the bench dependency
group: feed generators and the xmlstreamer column of the gauntlet."""

import sys
from io import BytesIO
from pathlib import Path

# Benchmark modules live outside the package on purpose.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "benchmarks"))

from feeds import (
    MIB,
    cdata_feed,
    plain_feed,
    plain_item_count,
    write_plain_feed,
    write_plain_feed_mb,
)
from gauntlet import CASES, run_case
from parsers import consume_xmlstreamer


def test_feeds_are_deterministic():
    assert plain_feed(50) == plain_feed(50)
    assert cdata_feed(50) == cdata_feed(50)


def test_write_plain_feed_matches_in_memory_builder():
    buffer = BytesIO()
    written = write_plain_feed(buffer, 1000, block_items=64)
    assert buffer.getvalue() == plain_feed(1000)
    assert written == len(buffer.getvalue())


def test_write_plain_feed_mb_hits_target_and_matches_items():
    buffer = BytesIO()
    n_items, written = write_plain_feed_mb(buffer, target_mib=1)
    data = buffer.getvalue()
    assert n_items == plain_item_count(1)
    assert written == len(data)
    # The byte estimate is intentionally approximate; the real size lands
    # within 2% of the target.
    assert abs(len(data) - MIB) / MIB < 0.02
    assert data.count(b"<item>") == n_items


def test_gauntlet_xmlstreamer_column_is_all_green():
    # Every verdict cell for xmlstreamer must be OK (possibly with a
    # loud drop) or the documented out-of-contract rejection.
    for case in CASES:
        verdict = run_case("xmlstreamer_ng", consume_xmlstreamer, case)
        if case.expected is None:
            assert verdict == "unsupported (documented contract)", (
                case.name, verdict
            )
        else:
            assert verdict.startswith("OK"), (case.name, verdict)
            assert "no warning" not in verdict, (case.name, verdict)
