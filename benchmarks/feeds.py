"""Deterministic synthetic feeds shared by every benchmark: same call,
same bytes, no randomness. Nothing here comes from real feeds."""

from typing import BinaryIO

PLAIN_ITEM_TEMPLATE = (
    b"<item><id>%d</id><title>A History of Bridges</title>"
    b"<author>A. Smith</author><publisher>Example Press</publisher>"
    b"<year>1998</year></item>"
)

_CDATA_DESC = (
    b"A survey of <b>bridge</b> engineering &amp; construction. " * 6
)

CDATA_ITEM_TEMPLATE = (
    b"<item><id>%d</id><title>A History of Bridges</title>"
    b"<desc><![CDATA[" + _CDATA_DESC + b"]]></desc>"
    b"<topics><![CDATA[masonry, steel]]></topics>"
    b"<shelf>B2</shelf></item>"
)


def plain_feed(n_items: int) -> bytes:
    """Flat feed: n five-field items, one varying field (id)."""
    body = b"".join(PLAIN_ITEM_TEMPLATE % i for i in range(n_items))
    return b"<feed>" + body + b"</feed>"


def cdata_feed(n_items: int) -> bytes:
    """CDATA-heavy feed: two CDATA sections per item."""
    body = b"".join(CDATA_ITEM_TEMPLATE % i for i in range(n_items))
    return b"<feed>" + body + b"</feed>"


def write_plain_feed(f: BinaryIO, n_items: int, block_items: int = 10_000) -> int:
    """Stream a big plain feed to an open binary file in blocks, so the
    generator itself never holds the whole feed. Returns bytes written."""
    written = f.write(b"<feed>")
    for start in range(0, n_items, block_items):
        stop = min(start + block_items, n_items)
        written += f.write(
            b"".join(PLAIN_ITEM_TEMPLATE % i for i in range(start, stop))
        )
    written += f.write(b"</feed>")
    f.flush()
    return written
