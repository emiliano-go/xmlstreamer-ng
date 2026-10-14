"""Split planning must never cut inside a markup section.

The parallel/streaming paths slice the file at planned record boundaries; a
boundary inside a comment, CDATA, PI or DOCTYPE would split a record. These
cases pin that every path yields exactly the rows the single-pass `read_xml`
does, including sections longer than a chunk and a literal ``<item>`` written
inside CDATA (a boundary lookalike).
"""

import pyarrow as pa
import pytest

from xmlstreamer_ng import _xmlstreamer


def _feed(tmp_path, name, body):
    path = tmp_path / f"{name}.xml"
    path.write_bytes(b"<feed>" + body + b"</feed>")
    return str(path)


def _values(table):
    if table is None:
        return None
    return {c: table.column(c).to_pylist() for c in table.column_names}


def _base(path):
    return _values(_xmlstreamer.read_xml(path, separator_tag="item", use_mmap=True))


def _parallel(path, chunks):
    return _values(
        _xmlstreamer.read_xml_par(
            path, separator_tag="item", chunks=chunks, use_mmap=True
        )
    )


def _stream(path, memory):
    batches = list(
        _xmlstreamer.read_xml_stream(path, separator_tag="item", memory=memory)
    )
    table = pa.Table.from_batches(batches) if batches else None
    return _values(table)


LONG = b"<desc><![CDATA[" + b"x" * (3 << 20) + b"]]></desc>"

FEEDS = {
    "plain": b"".join(b"<item><id>%d</id><t>v</t></item>" % i for i in range(2000)),
    "cdata": b"".join(
        b"<item><id>%d</id><desc><![CDATA[a<b>&amp;c]]></desc></item>" % i
        for i in range(2000)
    ),
    "long_cdata": b"".join(
        b"<item><id>%d</id>" % i + LONG + b"</item>" for i in range(4)
    ),
    "literal_item_in_cdata": b"".join(
        b"<item><id>%d</id><desc><![CDATA[literal <item> here]]></desc></item>" % i
        for i in range(500)
    ),
    "comment": b"".join(
        b"<item><id>%d</id><!-- c --><t>x</t></item>" % i for i in range(500)
    ),
    "malformed_close": b"".join(
        b"<item><id>%d</id></item junk><item><id>%d</id></item>" % (i, i)
        for i in range(300)
    ),
    "attributes": b"".join(b'<item a="1"><id>%d</id></item>' % i for i in range(1000)),
}


@pytest.mark.parametrize("name", list(FEEDS))
def test_split_paths_agree_with_single_pass(tmp_path, name):
    path = _feed(tmp_path, name, FEEDS[name])
    base = _base(path)
    for chunks in (2, 4, 8, 16):
        assert _parallel(path, chunks) == base, f"{name} chunks={chunks}"
    for memory in ("1MiB", "16MiB", "64MiB"):
        assert _stream(path, memory) == base, f"{name} stream {memory}"
