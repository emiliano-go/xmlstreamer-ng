"""Regression tests: drops in the columnar/parallel paths are loud and counted.

The streaming engine logs every discarded item and exposes counters; these
tests pin the same contract for `read_xml`, `read_xml_par`,
`read_xml_stream`, and `iter_xml_batches_par`, and confirm the streaming
path already met it.
"""

import logging

import pytest

from xmlstreamer_ng import StreamInterpreter, _xmlstreamer

# One malformed item between healthy ones: <t> never closes.
BROKEN_MIDDLE = (
    b"<feed>"
    b"<item><t>one</t></item>"
    b"<item><t>two</item>"
    b"<item><t>three</t></item>"
    b"</feed>"
)

# A comment that never closes, before later healthy items.
UNCLOSED_COMMENT = (
    b"<feed>"
    b"<item><t>one</t></item>"
    b"<!-- never closed"
    b"<item><t>two</t></item>"
    b"</feed>"
)

# A row boundary whose closing delimiter carries junk.
JUNK_CLOSE = (
    b"<feed>"
    b"<item><t>one</t></item junk>"
    b"<item><t>two</t></item>"
    b"</feed>"
)

COLUMNAR_READS = (
    _xmlstreamer.read_xml,
    _xmlstreamer.read_xml_par,
    _xmlstreamer.read_xml_stream,
    _xmlstreamer.iter_xml_batches_par,
)

_IDS = [f.__name__ for f in COLUMNAR_READS]


def _read_all(reader, path):
    if reader is _xmlstreamer.iter_xml_batches_par:
        return sum(b.num_rows for b in reader(str(path), threads=2))
    if reader is _xmlstreamer.read_xml_par:
        return reader(str(path), chunks=2).num_rows
    if reader is _xmlstreamer.read_xml_stream:
        return sum(b.num_rows for b in reader(str(path)))
    return reader(str(path)).num_rows


@pytest.fixture(name="feed_path")
def _feed_path(tmp_path):
    def write(data: bytes):
        path = tmp_path / "feed.xml"
        path.write_bytes(data)
        return path

    return write


def _diag():
    return _xmlstreamer.last_read_diagnostics()


@pytest.mark.parametrize("reader", COLUMNAR_READS, ids=_IDS)
def test_malformed_middle_item_is_loud_and_counted(reader, feed_path, caplog):
    path = feed_path(BROKEN_MIDDLE)
    with caplog.at_level(logging.WARNING, logger="xmlstreamer_ng"):
        rows = _read_all(reader, path)
    assert rows == 2, "the good items on both sides must survive"
    assert any(
        "Discarding unparseable item" in r.message for r in caplog.records
    ), "the drop must be logged, the way the streaming path logs it"
    diag = _diag()
    assert diag is not None and diag["malformed_items"] >= 1
    assert diag["unterminated_sections"] == 0


@pytest.mark.parametrize("reader", COLUMNAR_READS, ids=_IDS)
def test_unterminated_section_is_loud_and_counted(reader, feed_path, caplog):
    path = feed_path(UNCLOSED_COMMENT)
    with caplog.at_level(logging.WARNING, logger="xmlstreamer_ng"):
        rows = _read_all(reader, path)
    assert rows == 1, "only the item before the unterminated comment survives"
    assert any(
        "Unterminated section" in r.message and "discarding" in r.message
        for r in caplog.records
    ), "the discarded tail must be reported, not dropped silently"
    diag = _diag()
    assert diag is not None
    assert diag["unterminated_sections"] >= 1
    assert diag["discarded_bytes"] > 0


@pytest.mark.parametrize("reader", COLUMNAR_READS, ids=_IDS)
def test_malformed_closing_delimiter_is_counted(reader, feed_path, caplog):
    path = feed_path(JUNK_CLOSE)
    with caplog.at_level(logging.WARNING, logger="xmlstreamer_ng"):
        rows = _read_all(reader, path)
    assert rows == 2, "the junky close still ends the row, as before"
    diag = _diag()
    assert diag is not None and diag["malformed_closing_tags"] >= 1


@pytest.mark.parametrize("reader", COLUMNAR_READS, ids=_IDS)
def test_clean_feed_is_silent_and_empty_counted(reader, feed_path, caplog):
    path = feed_path(
        b"<feed><item><t>one</t></item><item><t>two</t></item></feed>"
    )
    with caplog.at_level(logging.WARNING, logger="xmlstreamer_ng"):
        rows = _read_all(reader, path)
    assert rows == 2
    assert not [r for r in caplog.records if r.name == "xmlstreamer_ng"]
    assert _diag() is None


def test_streaming_path_already_reports_both(feed_path, caplog):
    """The streaming engine must keep its contract: loud on both bugs."""
    malformed = feed_path(BROKEN_MIDDLE)
    with caplog.at_level(logging.WARNING, logger="xmlstreamer_ng"):
        list(
            StreamInterpreter(source=str(malformed), separator_tag="item")
        )
    assert any("Discarding unparseable item" in r.message for r in caplog.records)

    caplog.clear()
    unterminated = feed_path(UNCLOSED_COMMENT)
    with caplog.at_level(logging.WARNING, logger="xmlstreamer_ng"):
        rows = list(
            StreamInterpreter(source=str(unterminated), separator_tag="item")
        )
    assert any(
        "never closed" in r.message or "Unterminated" in r.message
        for r in caplog.records
    ), "streaming must report the unterminated section too"
    # The streaming default discards the tail but says so loudly; whatever
    # rows it delivers are well-formed.
    assert all(isinstance(row, dict) for row in rows)
