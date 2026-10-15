"""Hard caps for hostile or endless feeds: max_bytes / max_items."""

import io
import logging

import pytest

from xmlstreamer_ng import StreamInterpreter

FEED = b"<feed>" + b"".join(
    b"<item><id>%d</id></item>" % i for i in range(10)
) + b"</feed>"


def _source() -> io.BytesIO:
    return io.BytesIO(FEED)


def test_no_cap_delivers_all():
    assert len(list(StreamInterpreter(source=_source(), separator_tag="item"))) == 10


def test_max_items_stops_early(caplog):
    with caplog.at_level(logging.WARNING, logger="xmlstreamer_ng"):
        items = list(
            StreamInterpreter(source=_source(), separator_tag="item", max_items=3)
        )
    assert len(items) == 3
    assert any("max_items" in record.getMessage() for record in caplog.records)


def test_max_bytes_stops_early(caplog):
    with caplog.at_level(logging.WARNING, logger="xmlstreamer_ng"):
        items = list(
            StreamInterpreter(source=_source(), separator_tag="item", max_bytes=90)
        )
    assert 0 < len(items) < 10
    assert any("max_bytes" in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize("value", [0, -1])
def test_max_caps_must_be_positive(value):
    with pytest.raises(ValueError):
        StreamInterpreter(source=_source(), separator_tag="item", max_items=value)
    with pytest.raises(ValueError):
        StreamInterpreter(source=_source(), separator_tag="item", max_bytes=value)


@pytest.mark.parametrize("value", [True, 1.5, "10"])
def test_max_caps_must_be_int(value):
    with pytest.raises(TypeError):
        StreamInterpreter(source=_source(), separator_tag="item", max_items=value)
    with pytest.raises(TypeError):
        StreamInterpreter(source=_source(), separator_tag="item", max_bytes=value)
