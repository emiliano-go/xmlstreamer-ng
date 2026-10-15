"""Regression guard: split planning must stay linear in the input size.

A sectioned feed forces the section-aware split planner; an accidental
quadratic path (e.g. rescanning from every record) makes a few MiB take
minutes instead of milliseconds. This bounds the wall time generously so a
slow CI machine passes, but a super-linear planner does not.
"""

import time

from xmlstreamer_ng import _xmlstreamer

N_ITEMS = 4000
DESC = b"<desc><![CDATA[" + b"x" * 400 + b"]]></desc>"


def _big_cdata_feed(tmp_path):
    body = b"".join(
        b"<item><id>%d</id>" % i + DESC + b"</item>" for i in range(N_ITEMS)
    )
    path = tmp_path / "big_cdata.xml"
    path.write_bytes(b"<feed>" + body + b"</feed>")
    return str(path)


def test_large_sectioned_read_is_not_superlinear(tmp_path):
    path = _big_cdata_feed(tmp_path)
    base = _xmlstreamer.read_xml(path, separator_tag="item", use_mmap=True).num_rows
    assert base == N_ITEMS

    start = time.perf_counter()
    par = _xmlstreamer.read_xml_par(
        path, separator_tag="item", chunks=4, use_mmap=True
    ).num_rows
    stream = sum(
        batch.num_rows
        for batch in _xmlstreamer.read_xml_stream(
            path, separator_tag="item", memory="4MiB"
        )
    )
    elapsed = time.perf_counter() - start

    assert par == base
    assert stream == base
    assert elapsed < 15.0, f"split planning looks super-linear: {elapsed:.1f}s"
