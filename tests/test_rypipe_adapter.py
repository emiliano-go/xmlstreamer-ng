"""The rypipe adapter must agree with the legacy streaming parser.

The adapter is a second engine over the same contract; these tests pin the
`{path: text}` output (flat keys, numbering, sections, empty/malformed items)
against `Tokenizer`, for the columnar, parallel and bounded-streaming paths.
"""

import pyarrow as pa
import pytest
import rypipe

from feedlib import build_feed, chunked

from xmlstreamer import Tokenizer, XmlSource, col
from xmlstreamer import _xmlstreamer

# (name, feed, separator_tag, expected) — expected mirrors legacy behaviour.
CASES = [
    (
        "flat",
        b"<feed><item><t>a</t><n>1</n></item><item><t>b</t><n>2</n></item></feed>",
        "item",
        [{"t": "a", "n": "1"}, {"t": "b", "n": "2"}],
    ),
    (
        "repeated_siblings",
        b"<item><cat>a</cat><cat>b</cat><cat>c</cat></item>",
        "item",
        [{"cat": "a", "cat_1": "b", "cat_2": "c"}],
    ),
    (
        "nested_paths",
        b"<item><title>A</title><location><city>V</city>"
        b"<country>AA</country></location></item>",
        "item",
        [{"title": "A", "location/city": "V", "location/country": "AA"}],
    ),
    (
        "numbered_parent",
        b"<item><group><v>1</v></group><group><v>2</v></group></item>",
        "item",
        [{"group/v": "1", "group_1/v": "2"}],
    ),
    ("mixed_content", b"<item><a>x<b>y</b>z</a></item>", "item", [{"a/b": "y", "a": "xz"}]),
    (
        "cdata",
        b"<item><d><![CDATA[<b>Hi</b> & bye]]></d></item>",
        "item",
        [{"d": "<b>Hi</b> & bye"}],
    ),
    ("entities", b"<item><t>a &amp; b &lt;3</t></item>", "item", [{"t": "a & b <3"}]),
    ("separator_attrs", b'<feed><item id="7"><t>x</t></item></feed>', "item", [{"t": "x"}]),
    (
        "comment_ghost",
        b"<feed><!-- <item><t>fake</t></item> --><item><t>real</t></item></feed>",
        "item",
        [{"t": "real"}],
    ),
    (
        "cdata_ghost",
        b"<feed><![CDATA[<item><t>fake</t></item>]]><item><t>real</t></item></feed>",
        "item",
        [{"t": "real"}],
    ),
    (
        "malformed_item_between",
        b"<feed><item><t>a</t></item><item><t>b</item>"
        b"<item><t>c</t></item></feed>",
        "item",
        [{"t": "a"}, {"t": "c"}],
    ),
    (
        "empty_items",
        b"<feed><item/><item>   </item><item><t>real</t></item></feed>",
        "item",
        [{"t": "real"}],
    ),
    (
        "bare_text_items",
        b"<catalog><isbn>978-0</isbn><isbn>978-1</isbn></catalog>",
        "isbn",
        [{"isbn": "978-0"}, {"isbn": "978-1"}],
    ),
    (
        "key_collision",
        b"<item><x>a</x><x_1>natural</x_1><x>repeat</x></item>",
        "item",
        [{"x": "a", "x_1": "natural", "x_2": "repeat"}],
    ),
]


def legacy_items(feed: bytes, separator_tag: str) -> list:
    tokenizer = Tokenizer(
        feed_generator=chunked(feed, 7),
        separator_tag=separator_tag,
        buffer_size=64,
    )
    out = []
    while (item := tokenizer.get_item()) is not None:
        if item.parsed_content is not None:
            out.append(item.parsed_content)
    return out


def _write(tmp_path, feed: bytes) -> str:
    path = tmp_path / "feed.xml"
    path.write_bytes(feed)
    return str(path)


@pytest.mark.parametrize("name,feed,sep,expected", CASES, ids=[c[0] for c in CASES])
def test_columnar_matches_legacy(tmp_path, name, feed, sep, expected):
    table = _xmlstreamer.read_xml(_write(tmp_path, feed), separator_tag=sep)
    assert table.to_pylist() == expected
    assert table.to_pylist() == legacy_items(feed, sep)


@pytest.mark.parametrize("name,feed,sep,expected", CASES, ids=[c[0] for c in CASES])
def test_parallel_matches_legacy(tmp_path, name, feed, sep, expected):
    table = _xmlstreamer.read_xml_par(
        _write(tmp_path, feed), separator_tag=sep, chunks=4
    )
    assert table.to_pylist() == expected


@pytest.mark.parametrize("name,feed,sep,expected", CASES, ids=[c[0] for c in CASES])
def test_streaming_matches_legacy(tmp_path, name, feed, sep, expected):
    batches = _xmlstreamer.read_xml_stream(
        _write(tmp_path, feed), separator_tag=sep, memory="1MiB"
    )
    rows = [row for batch in batches for row in batch.to_pylist()]
    assert rows == expected


DOCTYPE_CASES = [
    # benign declaration
    b"<!DOCTYPE feed><feed><item><t>real</t></item></feed>",
    # internal subset with a ghost <item> inside a quoted entity value
    b'<!DOCTYPE feed [<!ENTITY ghost "<item><t>x</t></item>">]>'
    b"<feed><item><t>real</t></item></feed>",
    # ]> inside a quoted entity value does not end the declaration
    b'<!DOCTYPE feed [<!ENTITY x "]> <item><t>ghost</t></item>">]>'
    b"<feed><item><t>real</t></item></feed>",
    # > inside a quoted system id
    b'<!DOCTYPE feed SYSTEM "weird>name.dtd">'
    b"<feed><item><t>real</t></item></feed>",
    # nested brackets and a second entity
    b'<!DOCTYPE feed [<!ENTITY x "[nested]"> <!ENTITY y "z">]>'
    b"<feed><item><t>real</t></item></feed>",
]


@pytest.mark.parametrize("feed", DOCTYPE_CASES)
def test_doctype_is_not_a_record(tmp_path, feed):
    expected = [{"t": "real"}]
    path = _write(tmp_path, feed)
    assert legacy_items(feed, "item") == expected
    assert _xmlstreamer.read_xml(path, separator_tag="item").to_pylist() == expected
    assert (
        _xmlstreamer.read_xml_par(path, separator_tag="item", chunks=2).to_pylist()
        == expected
    )
    assert [
        row
        for batch in _xmlstreamer.read_xml_stream(
            path, separator_tag="item", memory="1MiB"
        )
        for row in batch.to_pylist()
    ] == expected


def test_order_is_preserved_over_many_items(tmp_path):
    feed = build_feed([{"n": str(i)} for i in range(5000)])
    expected = [{"n": str(i)} for i in range(5000)]
    path = _write(tmp_path, feed)
    assert _xmlstreamer.read_xml(path, separator_tag="item").to_pylist() == expected
    assert (
        _xmlstreamer.read_xml_par(path, separator_tag="item", chunks=8).to_pylist()
        == expected
    )


def test_rypipe_read_registration(tmp_path):
    feed = build_feed([{"t": "a"}, {"t": "b"}])
    table = rypipe.read(_write(tmp_path, feed), separator_tag="item")
    assert isinstance(table, pa.Table)
    assert table.to_pylist() == [{"t": "a"}, {"t": "b"}]


def test_source_pipeline_and_sinks(tmp_path):
    feed = build_feed([{"t": "a", "n": "1"}, {"t": "b", "n": "2"}, {"t": "c", "n": "3"}])
    source = XmlSource(_write(tmp_path, feed), separator_tag="item")
    result = (source | rypipe.CastTypes({"n": int}) | rypipe.FilterRows(col("n") > 1)).to_arrow()
    assert result.to_pylist() == [{"t": "b", "n": 2}, {"t": "c", "n": 3}]
    assert result.schema.field("n").type == pa.int64()


def test_source_engine_dispatch(tmp_path):
    feed = build_feed([{"n": str(i)} for i in range(100)])
    path = _write(tmp_path, feed)
    expected = [{"n": str(i)} for i in range(100)]
    for kwargs in (
        {"engine": "columnar"},
        {"engine": "parallel", "threads": 2},
        {"engine": "auto", "threads": 4},
        {"threads": 3},
    ):
        source = XmlSource(path, separator_tag="item", **kwargs)
        assert source.to_arrow().to_pylist() == expected


def test_source_streaming_iter_record_batches(tmp_path):
    feed = build_feed([{"n": str(i)} for i in range(2000)])
    source = XmlSource(_write(tmp_path, feed), separator_tag="item")
    total = sum(batch.num_rows for batch in source.iter_record_batches(memory="64KiB"))
    assert total == 2000


def test_parallel_streaming_preserves_order_and_matches(tmp_path):
    feed = build_feed([{"n": str(i)} for i in range(5000)])
    path = _write(tmp_path, feed)
    expected = [{"n": str(i)} for i in range(5000)]

    sequential = [
        row
        for batch in _xmlstreamer.read_xml_stream(
            path, separator_tag="item", memory="64KiB"
        )
        for row in batch.to_pylist()
    ]
    parallel = [
        row
        for batch in _xmlstreamer.iter_xml_batches_par(
            path, separator_tag="item", threads=4, memory="1MiB"
        )
        for row in batch.to_pylist()
    ]
    assert sequential == expected
    assert parallel == expected


def test_parallel_streaming_autodiscovers_columns(tmp_path):
    # No schema: the parallel streaming executor runs a locate-only discovery
    # pass, then the parser must still record every field name.
    feed = (
        b"<feed>"
        + b"<item><a>1</a></item>" * 50
        + b"<item><a>2</a><b>late</b></item>"
        + b"</feed>"
    )
    path = _write(tmp_path, feed)
    rows = [
        row
        for batch in _xmlstreamer.iter_xml_batches_par(
            path, separator_tag="item", threads=2, memory="1MiB"
        )
        for row in batch.to_pylist()
    ]
    assert rows[-1]["b"] == "late"
    assert len(rows) == 51


def test_source_parallel_streaming_via_iter_record_batches(tmp_path):
    feed = build_feed([{"n": str(i)} for i in range(2000)])
    source = XmlSource(_write(tmp_path, feed), separator_tag="item")
    rows = [
        row
        for batch in source.iter_record_batches(memory="1MiB", threads=4)
        for row in batch.to_pylist()
    ]
    assert rows == [{"n": str(i)} for i in range(2000)]


_NESTED_FEED = (
    b"<item><title>A</title><location><city>V</city>"
    b"<country>AA</country></location></item>"
)


@pytest.mark.parametrize(
    "schema,expected",
    [
        (["title"], [{"title": "A"}]),
        (["location/city"], [{"location/city": "V"}]),
        (["title", "location/city"], [{"title": "A", "location/city": "V"}]),
        (
            ["location/country"],
            [{"location/country": "AA"}],
        ),
    ],
)
def test_schema_projection_skips_unwanted_subtrees(tmp_path, schema, expected):
    path = _write(tmp_path, _NESTED_FEED)
    # columnar and parallel
    assert _xmlstreamer.read_xml(
        path, separator_tag="item", schema=schema
    ).to_pylist() == expected
    assert _xmlstreamer.read_xml_par(
        path, separator_tag="item", schema=schema, chunks=2
    ).to_pylist() == expected


def test_schema_projection_numbered_parents_kept(tmp_path):
    feed = (
        b"<item><group><v>1</v></group><group><v>2</v></group></item>"
    )
    table = _xmlstreamer.read_xml(
        _write(tmp_path, feed), separator_tag="item", schema=["group/v"]
    )
    assert table.to_pylist() == [{"group/v": "1"}]


def test_field_types_emit_typed_values(tmp_path):
    feed = (
        b"<feed><item><id>1</id><year>1998</year></item>"
        b"<item><id>2</id><year>2000</year></item></feed>"
    )
    table = _xmlstreamer.read_xml(
        _write(tmp_path, feed),
        separator_tag="item",
        field_types={"id": "int64", "year": "int64"},
    )
    assert table.schema.field("id").type == pa.int64()
    assert table.schema.field("year").type == pa.int64()
    assert table.to_pylist() == [{"id": 1, "year": 1998}, {"id": 2, "year": 2000}]


def test_untyped_values_stay_strings(tmp_path):
    feed = b"<feed><item><id>1</id></item></feed>"
    table = _xmlstreamer.read_xml(_write(tmp_path, feed), separator_tag="item")
    assert table.schema.field("id").type == pa.string()
    assert table.to_pylist() == [{"id": "1"}]


def test_field_types_unparseable_value_is_null(tmp_path):
    feed = b"<feed><item><id>1</id><year>not-a-year</year></item></feed>"
    table = _xmlstreamer.read_xml(
        _write(tmp_path, feed),
        separator_tag="item",
        field_types={"id": "int64", "year": "int64"},
    )
    assert table.to_pylist() == [{"id": 1, "year": None}]


@pytest.mark.parametrize("name,feed,sep,expected", CASES, ids=[c[0] for c in CASES])
def test_fast_validation_matches_strict_on_wellformed(
    tmp_path, name, feed, sep, expected
):
    table = _xmlstreamer.read_xml(
        _write(tmp_path, feed), separator_tag=sep, validate="fast"
    )
    assert table.to_pylist() == expected


def test_validate_rejects_unknown_mode(tmp_path):
    path = _write(tmp_path, b"<feed><item><t>x</t></item></feed>")
    with pytest.raises(ValueError):
        _xmlstreamer.read_xml(path, separator_tag="item", validate="bogus")


def test_min_chunk_bytes_knob_is_accepted(tmp_path):
    feed = build_feed([{"n": str(i)} for i in range(1000)])
    path = _write(tmp_path, feed)
    assert _xmlstreamer.read_xml(
        path, separator_tag="item", min_chunk_bytes=64 * 1024
    ).num_rows == 1000
    assert _xmlstreamer.read_xml_par(
        path, separator_tag="item", chunks=4, min_chunk_bytes=64 * 1024
    ).num_rows == 1000


def test_projection_drop_fields(tmp_path):
    feed = build_feed([{"t": "a", "n": "1"}, {"t": "b", "n": "2"}])
    table = _xmlstreamer.read_xml(
        _write(tmp_path, feed), separator_tag="item", drop_fields=["n"]
    )
    assert table.column_names == ["t"]


@pytest.mark.parametrize(
    "feed,sep,drops,expected",
    [
        # depth-1 leaf dropped
        (
            b"<feed><item><t>a</t><n>1</n></item><item><t>b</t><n>2</n></item></feed>",
            "item",
            ["n"],
            [{"t": "a"}, {"t": "b"}],
        ),
        # nested path dropped
        (
            b"<item><title>A</title><location><city>V</city>"
            b"<country>AA</country></location></item>",
            "item",
            ["location/city"],
            [{"title": "A", "location/country": "AA"}],
        ),
        # repeated siblings: dropping the first must NOT shift numbering
        (
            b"<item><cat>a</cat><cat>b</cat><cat>c</cat></item>",
            "item",
            ["cat"],
            [{"cat_1": "b", "cat_2": "c"}],
        ),
        # literal numbered key + repeats under a drop
        (
            b"<item><x>a</x><x_1>natural</x_1><x>repeat</x></item>",
            "item",
            ["x"],
            [{"x_1": "natural", "x_2": "repeat"}],
        ),
    ],
)
def test_projection_matches_legacy(tmp_path, feed, sep, drops, expected):
    table = _xmlstreamer.read_xml(
        _write(tmp_path, feed), separator_tag=sep, drop_fields=drops
    )
    assert table.to_pylist() == expected


# --- regressions: chunk/section correctness across every engine --- #

DAMAGED_CASES = [
    # junk in the closing tag still delivers the item (scanner contract)
    (
        b"<feed><item><t>a</t></item junk><item><t>b</t></item></feed>",
        [{"t": "a"}, {"t": "b"}],
    ),
    # an opening quote that never closes must not swallow later items
    (
        b'<feed><item note="never><t>a</t></item><item><t>b</t></item></feed>',
        [{"t": "b"}],
    ),
    # invalid utf-8 is replaced, like the streaming parser
    (b"<feed><item><t>a\xffb</t></item></feed>", [{"t": "a\ufffdb"}]),
    # a leading BOM is not document content
    (b"\xef\xbb\xbf<feed><item><t>a</t></item></feed>", [{"t": "a"}]),
    # CRLF is normalized (XML 1.0 §2.11)
    (b"<feed><item><t>a\r\nb</t></item></feed>", [{"t": "a\nb"}]),
]


@pytest.mark.parametrize("feed,expected", DAMAGED_CASES, ids=range(len(DAMAGED_CASES)))
def test_damaged_feeds_agree_across_engines(tmp_path, feed, expected):
    path = _write(tmp_path, feed)
    assert _xmlstreamer.read_xml(path, separator_tag="item").to_pylist() == expected
    assert (
        _xmlstreamer.read_xml_par(path, separator_tag="item", chunks=4).to_pylist()
        == expected
    )
    assert [
        row
        for batch in _xmlstreamer.read_xml_stream(
            path, separator_tag="item", memory="64KiB"
        )
        for row in batch.to_pylist()
    ] == expected
    assert [
        row
        for batch in _xmlstreamer.iter_xml_batches_par(
            path, separator_tag="item", threads=4, memory="64KiB"
        )
        for row in batch.to_pylist()
    ] == expected


def test_doctype_ghost_at_every_chunk_count(tmp_path):
    feed = (
        b'<!DOCTYPE feed [<!ENTITY ghost "<item><t>x</t></item>">]>'
        b"<feed><item><t>real</t></item></feed>"
    )
    path = _write(tmp_path, feed)
    for chunks in (2, 3, 4, 8):
        assert (
            _xmlstreamer.read_xml_par(
                path, separator_tag="item", chunks=chunks
            ).to_pylist()
            == [{"t": "real"}]
        )


def test_section_longer_than_skip_window_is_not_split(tmp_path):
    feed = (
        b"<feed><![CDATA["
        + b"y" * 100_000
        + b"<item><t>ghost</t></item>"
        + b"y" * 100_000
        + b"]]><item><t>real</t></item></feed>"
    )
    path = _write(tmp_path, feed)
    assert (
        _xmlstreamer.read_xml_par(path, separator_tag="item", chunks=4).to_pylist()
        == [{"t": "real"}]
    )
    assert [
        row
        for batch in _xmlstreamer.iter_xml_batches_par(
            path, separator_tag="item", threads=4, memory="1MiB"
        )
        for row in batch.to_pylist()
    ] == [{"t": "real"}]


# --- regressions: projection / validation semantics --- #


def test_field_mapping_with_schema_keeps_the_mapped_subtree(tmp_path):
    feed = b"<feed><item><t>a</t><n>1</n></item></feed>"
    table = _xmlstreamer.read_xml(
        _write(tmp_path, feed),
        separator_tag="item",
        field_mapping={"t": "title"},
        schema=["title"],
    )
    assert table.to_pylist() == [{"title": "a"}]


def test_projection_keeps_empty_rows(tmp_path):
    feed = b"<feed><item><t>a</t></item><item><n>1</n></item></feed>"
    table = _xmlstreamer.read_xml(
        _write(tmp_path, feed), separator_tag="item", schema=["t"]
    )
    assert table.num_rows == 2
    assert table.to_pylist() == [{"t": "a"}, {"t": None}]


def test_empty_schema_means_no_projection(tmp_path):
    feed = b"<feed><item><t>a</t></item></feed>"
    table = _xmlstreamer.read_xml(
        _write(tmp_path, feed), separator_tag="item", schema=[]
    )
    assert table.to_pylist() == [{"t": "a"}]


@pytest.mark.parametrize(
    "feed,expected",
    [
        # strict validation reaches into a skipped subtree
        (b"<feed><item><t>a</t><n>&bogus;</n></item></feed>", []),
        (b"<feed><item><t>a</t><n>\x01</n></item></feed>", []),
        (
            b"<feed><item><t>a</t><junk><item><t>b</t></junk></item>"
            b"<item><t>c</t></item></feed>",
            [{"t": "c"}],
        ),
    ],
    ids=["undefined_entity", "control_char", "crossing_subtree"],
)
def test_strict_projection_validates_skipped_content(tmp_path, feed, expected):
    table = _xmlstreamer.read_xml(
        _write(tmp_path, feed), separator_tag="item", schema=["t"]
    )
    assert table.to_pylist() == expected


def test_engine_and_separator_are_validated(tmp_path):
    path = _write(tmp_path, b"<feed><item><t>x</t></item></feed>")
    with pytest.raises(ValueError):
        XmlSource(path, engine="bogus")
    with pytest.raises(ValueError):
        XmlSource(path, separator_tag="not a name")
    with pytest.raises(ValueError):
        _xmlstreamer.read_xml(path, separator_tag="")


def test_source_threads_reach_the_streaming_reader(tmp_path, monkeypatch):
    import xmlstreamer.source as source_module

    feed = build_feed([{"n": str(i)} for i in range(500)])
    path = _write(tmp_path, feed)
    calls = []
    real = source_module._xmlstreamer

    class Spy:
        def __getattr__(self, name):
            def call(*args, **kwargs):
                calls.append(name)
                return getattr(real, name)(*args, **kwargs)

            return call

    monkeypatch.setattr(source_module, "_xmlstreamer", Spy())
    rows = [
        row
        for batch in XmlSource(path, threads=4).iter_record_batches(memory="64KiB")
        for row in batch.to_pylist()
    ]
    assert calls == ["iter_xml_batches_par"] or "iter_xml_batches_par" in calls
    assert rows == [{"n": str(i)} for i in range(500)]


def test_rypipe_read_stream_par_and_batches(tmp_path):
    feed = build_feed([{"t": "a"}, {"t": "b"}])
    path = _write(tmp_path, feed)
    assert rypipe.read_stream(path, format="xmlstreamer", memory="1MiB").to_pylist() == [
        {"t": "a"},
        {"t": "b"},
    ]
    assert rypipe.read_par(path, format="xmlstreamer", chunks=2).num_rows == 2
    batches = list(
        rypipe.read_batches(path, format="xmlstreamer", batch_size=1)
    )
    assert [batch.num_rows for batch in batches] == [1, 1]

