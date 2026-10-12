"""The benchmark harness pieces that run without the bench dependency
group: feed generators and the xmlstreamer column of the gauntlet."""

import sys
from io import BytesIO
from pathlib import Path

# Benchmark modules live outside the package on purpose.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "benchmarks"))

from feeds import cdata_feed, plain_feed, write_plain_feed
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


def test_gauntlet_xmlstreamer_column_is_all_green():
    # Every verdict cell for xmlstreamer must be OK (possibly with a
    # loud drop) or the documented out-of-contract rejection.
    for case in CASES:
        verdict = run_case("xmlstreamer", consume_xmlstreamer, case)
        if case.expected is None:
            assert verdict == "unsupported (documented contract)", (
                case.name, verdict
            )
        else:
            assert verdict.startswith("OK"), (case.name, verdict)
            assert "no warning" not in verdict, (case.name, verdict)
