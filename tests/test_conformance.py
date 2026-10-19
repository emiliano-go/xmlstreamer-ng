"""Conformance against an independent parser (lxml) and against the
hand-authored benchmark corpus.

The library's record model is deliberately lossy: attributes are dropped,
repeated tags are numbered, and output is a flat ``{path: text}`` map, so
mixed text around child elements is attributed to the parent path. These
tests pin that documented shape and check it against lxml where the model
is lossless.
"""

from pathlib import Path

import pytest

from xmlstreamer_ng import StreamInterpreter, parse_item

CORPUS = Path(__file__).resolve().parent.parent / "benchmarks" / "corpus"


def load(name: str, kind: str = "valid") -> list:
    path = CORPUS / kind / name
    return list(StreamInterpreter(source=str(path), separator_tag="item"))


# --- lxml differential: flat items with no attributes or mixed content ---

FLAT_ITEMS = [
    {"a": "1", "b": "2"},
    {"a": "x &amp; y", "b": ""},
    {"a": "hello", "c": "world", "d": "!"},
    {"a": "repeat", "a_1": "second"},
    {"a": "unicode café 😀"},
]


def render(item: dict) -> bytes:
    # Rebuild XML from the numbered keys, undoing the numbering so lxml
    # sees the original document.
    inner = ""
    tags = {}
    for key in item:
        tag = key.split("_")[0] if "_" in key else key
        tags.setdefault(tag, 0)
        tags[tag] += 1
        inner += f"<{tag}>{item[key]}</{tag}>"
    return f"<item>{inner}</item>".encode()


def lxml_flat(item: dict) -> dict:
    from lxml import etree

    root = etree.fromstring(render(item))
    out, seen = {}, {}
    for child in root:
        tag = child.tag
        text = child.text or ""
        if tag in seen:
            seen[tag] += 1
            out[f"{tag}_{seen[tag]}"] = text
        else:
            seen[tag] = 0
            out[tag] = text
    return out


@pytest.mark.parametrize("item", FLAT_ITEMS)
def test_parse_item_matches_lxml_on_flat_items(item):
    pytest.importorskip("lxml")
    assert parse_item(render(item)) == lxml_flat(item)


# --- corpus fixtures: explicit expected records ---

VALID_EXPECTED = {
    "attributes.xml": [
        {"title": "A History of Bridges", "author": "A. Smith"},
        {"title": "Rivers of the World", "author": "B. Jones"},
    ],
    "bom_utf8.xml": [{"t": "coração"}],
    "charrefs.xml": [
        {"t": "a & b < c > d", "t_1": "café 😀"},
        {"t": "plain text"},
    ],
    "comments_pi.xml": [
        {"title": "A History of Bridges", "year": "1998"},
        {"title": "Rivers of the World"},
    ],
    "deep_nesting.xml": [
        {"a/b/c/d/e/f/g": "deep"},
        {"a/b/c": "shallow"},
    ],
    "encoding_latin1.xml": [{"t": "programación región café"}],
    "namespaces.xml": [
        {"b:title": "A History of Bridges", "b:author": "A. Smith",
         "b:year": "1998"},
        {"b:title": "Rivers of the World", "b:author": "B. Jones",
         "b:year": "2004"},
    ],
    "repeated_fields.xml": [
        {"cat": "a", "cat_1": "b", "cat_2": "c", "name": "first"},
        {"cat": "x", "name": "second", "name_1": "alias"},
    ],
}


@pytest.mark.parametrize("name,expected", sorted(VALID_EXPECTED.items()))
def test_valid_corpus_matches_expected(name, expected):
    assert load(name) == expected


def test_valid_corpus_covers_every_file():
    on_disk = {p.name for p in (CORPUS / "valid").glob("*.xml")}
    assert on_disk <= set(VALID_EXPECTED) | {"cdata_mixed.xml"}


def test_mixed_content_is_flattened_by_design():
    # Documented lossy case: text around children lands on the parent
    # path and the child text on the child path, in document order.
    assert load("cdata_mixed.xml") == [
        {
            "title": "A History of Bridges",
            "desc": "A survey of <b>bridge</b> engineering & construction.",
            "topics": "masonry, steel",
        },
        {
            "title": "Rivers of the World",
            "desc/b": "mixed",
            "desc/i": "inline",
            "desc": "Plain  content with  markup.",
        },
    ]


# --- dirty corpus: documented recovery, no crash ---

DIRTY_EXPECTED = {
    "lying_encoding.xml": [{"t": "programación región café"}],
    "nested_separator.xml": [],
    "raw_amp.xml": [{"t": "clean"}],
    "stray_lt.xml": [{"t": "clean"}],
    "truncated.xml": [{"t": "a"}, {"t": "b"}],
    "unclosed_item.xml": [{"t": "a"}, {"t": "c"}],
    "unterminated_cdata.xml": [{"t": "a"}],
    "unterminated_comment.xml": [{"t": "a"}],
}


@pytest.mark.parametrize("name,expected", sorted(DIRTY_EXPECTED.items()))
def test_dirty_corpus_recovers_without_crashing(name, expected):
    assert load(name, kind="dirty") == expected


def test_dirty_corpus_covers_every_file():
    on_disk = {p.name for p in (CORPUS / "dirty").glob("*.xml")}
    assert on_disk == set(DIRTY_EXPECTED)
