"""Deterministic synthetic feeds shared by every benchmark: same call,
same bytes, no randomness. Nothing here comes from real feeds."""

from typing import BinaryIO

MIB = 1024 * 1024

# The template is 136 bytes plus the digits of the id; at ~1M items the
# mean is ~140.9 bytes. Keep one constant so every benchmark asks for the
# same feed size instead of repeating (and drifting from) this number.
PLAIN_ITEM_BYTES = 141

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


def plain_item_count(target_mib: int) -> int:
    """Approximate item count for a plain feed of ``target_mib`` MiB."""
    return max(1, (target_mib * MIB) // PLAIN_ITEM_BYTES)


def write_plain_feed_mb(
    f: BinaryIO, target_mib: int = 128, block_items: int = 10_000
) -> tuple[int, int]:
    """Write a plain feed of roughly ``target_mib`` MiB.

    Returns ``(n_items, bytes_written)``; the actual size lands within
    ~1% of the target because the per-item byte count grows with the id
    digits.
    """
    n_items = plain_item_count(target_mib)
    written = write_plain_feed(f, n_items, block_items=block_items)
    return n_items, written
