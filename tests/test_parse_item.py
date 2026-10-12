import logging

import pytest

from xmlstreamer import ParsedItem, parse_item, to_nested


def test_flat_item():
    result = parse_item(
        b"<item><title>Atlas of Rivers</title><link>https://example.com/1</link></item>"
    )
    assert result == {"title": "Atlas of Rivers", "link": "https://example.com/1"}


def test_repeated_tags_get_numbered_keys():
    # Repeated sibling tags get numbered keys: cat, cat_1, cat_2.
    result = parse_item(b"<item><cat>a</cat><cat>b</cat><cat>c</cat></item>")
    assert (result["cat"], result["cat_1"], result["cat_2"]) == ("a", "b", "c")


def test_cdata_content_preserved():
    result = parse_item(b"<item><d><![CDATA[<b>Hello</b> & bye]]></d></item>")
    assert result["d"] == "<b>Hello</b> & bye"


def test_standard_entities_decoded():
    result = parse_item(b"<item><t>a &amp; b &lt;3</t></item>")
    assert result["t"] == "a & b <3"


def test_trailing_newlines_stripped_internal_kept():
    result = parse_item(b"<item><t>a\nb\n\n</t></item>")
    assert result["t"] == "a\nb"


def test_attributes_are_dropped():
    # Items are built from element text only: attributes are dropped.
    result = parse_item(b'<item><t lang="es">x</t></item>')
    assert result["t"] == "x"
    assert "lang" not in result


def test_malformed_item_returns_none():
    assert parse_item(b"<item><t>x</item>") is None


def test_leading_benign_doctype_parses():
    # A benign leading DOCTYPE (no entity declarations) is accepted.
    result = parse_item(b"<!DOCTYPE item><item><t>x</t></item>")
    assert result == {"t": "x"}


def test_leading_entity_declaration_returns_none():
    # Entity declarations (billion laughs seed) discard the item.
    item = b"<!DOCTYPE item [<!ENTITY e 'v'>]><item><d>&e;</d></item>"
    assert parse_item(item) is None


def test_external_system_entity_returns_none():
    item = (
        b'<!DOCTYPE item [<!ENTITY e SYSTEM "file:///etc/passwd">]>'
        b"<item><d>&e;</d></item>"
    )
    assert parse_item(item) is None


def test_mid_document_doctype_returns_none():
    # A mid-document DTD is malformed for any parser.
    item = b"<item><!DOCTYPE d [<!ENTITY e 'v'>]><d>x</d></item>"
    assert parse_item(item) is None


def test_undefined_entity_returns_none():
    # Undefined entities abort the item.
    assert parse_item(b"<item><d>a&nbsp;b</d></item>") is None


def test_discarded_item_logs_a_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="xmlstreamer"):
        assert parse_item(b"<item><d>a&nbsp;b</d></item>") is None
    assert "Discarding unparseable item" in caplog.text


def test_nested_child_value_preserved():
    # Path keys are "/"-joined (an XML name can never contain "/").
    # A parent emits its non-whitespace direct text.
    result = parse_item(b"<item><a>x<b>y</b>z</a></item>")
    assert result == {"a": "xz", "a/b": "y"}


def test_nested_paths_real_world_shape():
    result = parse_item(
        b"<item>"
        b"<title>Atlas</title>"
        b"<location><city>Aurora</city><country>AA</country></location>"
        b"</item>"
    )
    assert result == {
        "title": "Atlas",
        "location/city": "Aurora",
        "location/country": "AA",
    }


def test_nested_same_name_parent_child_no_collision():
    # A child with the same name as its parent must not collide.
    result = parse_item(
        b"<item><location>"
        b"<location>Northside</location><country>AA</country>"
        b"</location></item>"
    )
    assert result == {
        "location/location": "Northside",
        "location/country": "AA",
    }


def test_nested_depth_four_full_path():
    result = parse_item(
        b"<item><warehouse><address>"
        b"<locality>Delta</locality>"
        b"</address></warehouse></item>"
    )
    assert result == {"warehouse/address/locality": "Delta"}


def test_nested_repeated_siblings_numbered_by_path():
    result = parse_item(
        b"<item><locations>"
        b"<location>a</location><location>b</location>"
        b"</locations></item>"
    )
    assert result == {
        "locations/location": "a",
        "locations/location_1": "b",
    }


def test_nested_numbered_parent_propagates_to_children():
    result = parse_item(
        b"<item>"
        b"<group><v>1</v></group>"
        b"<group><v>2</v></group>"
        b"</item>"
    )
    assert result == {"group/v": "1", "group_1/v": "2"}


def test_whitespace_only_parent_emits_no_key():
    result = parse_item(
        b"<item><location>\n  <city>Vega</city>\n</location></item>"
    )
    assert result == {"location/city": "Vega"}


def test_empty_item_wrapper_edge_preserved():
    # Childless item: the wrapper itself is a leaf and emits its key.
    assert parse_item(b"<item></item>") == {"item": ""}


def test_parsed_item_parse_content_wraps_in_item_tag():
    item = ParsedItem(content=b"<t>hello</t>")
    item.parse_content()
    assert item.parsed_content == {"t": "hello"}


def test_parsed_item_accepts_the_feeds_own_wrapper():
    # The tokenizer passes the separator's tag: bare-text items are
    # then keyed by the name the feed uses.
    item = ParsedItem(content=b"978-0-1")
    item.parse_content(b"<isbn>", b"</isbn>")
    assert item.parsed_content == {"isbn": "978-0-1"}


def test_to_nested_splits_paths():
    flat = {"title": "Atlas", "location/city": "Vega", "location/country": "AA"}
    assert to_nested(flat) == {
        "title": "Atlas",
        "location": {"city": "Vega", "country": "AA"},
    }


def test_to_nested_deep_paths():
    flat = {"warehouse/address/locality": "Delta"}
    assert to_nested(flat) == {
        "warehouse": {"address": {"locality": "Delta"}}
    }


def test_to_nested_numbered_siblings_stay_numbered():
    # No lists: mechanical re-shape, shape never depends on sibling count
    # (the classic xmltodict trap).
    flat = {"locations/location": "a", "locations/location_1": "b"}
    assert to_nested(flat) == {
        "locations": {"location": "a", "location_1": "b"}
    }


@pytest.mark.parametrize(
    "flat",
    [
        # Handler emits child before parent; cover both orders.
        {"a/b": "y", "a": "xz"},
        {"a": "xz", "a/b": "y"},
    ],
)
def test_to_nested_mixed_content_under_text_key(flat):
    assert to_nested(flat) == {"a": {"#text": "xz", "b": "y"}}


def test_to_nested_flat_item_passthrough():
    flat = {"title": "Atlas", "url": "https://example.com"}
    result = to_nested(flat)
    assert result == flat
    assert result is not flat


def test_to_nested_empty_wrapper_edge():
    assert to_nested({"item": ""}) == {"item": ""}


def test_to_nested_force_list_of_strings():
    flat = {"tags/tag": "a", "tags/tag_1": "b", "tags/tag_2": "c"}
    assert to_nested(flat, force_list={"tags/tag"}) == {
        "tags": {"tag": ["a", "b", "c"]}
    }


def test_to_nested_force_list_single_element_still_list():
    # The whole point of force_list: one element is still a list.
    flat = {"tags/tag": "a"}
    assert to_nested(flat, force_list={"tags/tag"}) == {"tags": {"tag": ["a"]}}


def test_to_nested_force_list_of_dicts():
    # A collection of elements with children becomes a list of dicts.
    flat = {
        "editions/edition/code": "AA",
        "editions/edition/name": "Alpha",
        "editions/edition_1/code": "BB",
        "editions/edition_1/name": "Beta",
    }
    assert to_nested(flat, force_list={"editions/edition"}) == {
        "editions": {
            "edition": [
                {"code": "AA", "name": "Alpha"},
                {"code": "BB", "name": "Beta"},
            ]
        }
    }


def test_to_nested_force_list_undeclared_paths_stay_numbered():
    flat = {
        "tags/tag": "a",
        "tags/tag_1": "b",
        "locations/location": "x",
        "locations/location_1": "y",
    }
    assert to_nested(flat, force_list={"tags/tag"}) == {
        "tags": {"tag": ["a", "b"]},
        "locations": {"location": "x", "location_1": "y"},
    }


def test_to_nested_force_list_per_numbered_parent_instance():
    # Declaring "group/v" makes v a list INSIDE each group instance.
    flat = {"group/v": "1", "group_1/v": "2"}
    assert to_nested(flat, force_list={"group/v"}) == {
        "group": {"v": ["1"]},
        "group_1": {"v": ["2"]},
    }


def test_to_nested_force_list_declared_ancestor_collapses_instances():
    # Declaring the repeated parent collapses instances into a dict list.
    flat = {"group/v": "1", "group_1/v": "2"}
    assert to_nested(flat, force_list={"group"}) == {
        "group": [{"v": "1"}, {"v": "2"}]
    }


def test_to_nested_force_list_genuine_digit_tag_not_confused():
    # A real digit-ending tag (address1) cannot even match the _N pattern.
    flat = {"address1": "Calle 123"}
    assert to_nested(flat, force_list={"address"}) == {"address1": "Calle 123"}


def test_to_nested_force_list_genuine_underscore_tag_not_confused():
    # Real address_1 tag with no bare "address" sibling: not the
    # library's numbering.
    flat = {"address_1": "Calle 123"}
    assert to_nested(flat, force_list={"address"}) == {"address_1": "Calle 123"}


def test_to_nested_force_list_true_everything_is_a_list():
    # Total uniformity: every path is a collection, numbering collapses,
    # single fields become one-element lists.
    flat = {
        "title": "Atlas",
        "location/city": "Aurora",
        "editions/edition/code": "AA",
        "editions/edition_1/code": "BB",
    }
    assert to_nested(flat, force_list=True) == {
        "title": ["Atlas"],
        "location": [{"city": ["Aurora"]}],
        "editions": [
            {"edition": [{"code": ["AA"]}, {"code": ["BB"]}]}
        ],
    }


def test_to_nested_force_list_true_numbered_leaves_merge():
    flat = {"cat": "a", "cat_1": "b", "cat_2": "c"}
    assert to_nested(flat, force_list=True) == {"cat": ["a", "b", "c"]}


def test_to_nested_force_list_true_empty_wrapper():
    assert to_nested({"item": ""}, force_list=True) == {"item": [""]}


def test_to_nested_force_list_accepts_lone_string():
    # A lone string is one path, not an iterable of characters.
    flat = {"tags/tag": "a", "tags/tag_1": "b"}
    assert to_nested(flat, force_list="tags/tag") == {
        "tags": {"tag": ["a", "b"]}
    }


def test_field_named_item_keeps_bare_key():
    # The invisible root wrapper must not consume the numbering slot of a
    # real depth-1 field named "item".
    result = parse_item(b"<item><item>a</item><t>x</t></item>")
    assert result == {"item": "a", "t": "x"}


def test_to_nested_force_list_true_mixed_content():
    # Handler order (child closes first): parent text lands under #text.
    flat = {"a/b": "y", "a": "xz"}
    assert to_nested(flat, force_list=True) == {
        "a": [{"b": ["y"], "#text": "xz"}]
    }


def test_natural_underscore_key_does_not_lose_the_sibling(caplog):
    # A field literally named "x_1" collides with the numbering rule
    # for a repeated <x>. Neither value may vanish in silence.
    with caplog.at_level(logging.WARNING, logger="xmlstreamer"):
        parsed = parse_item(
            b"<item><x>a</x><x_1>natural</x_1><x>repeat</x></item>"
        )
    assert sorted(parsed.values()) == ["a", "natural", "repeat"]
    assert "collision" in caplog.text.lower()


def test_numbering_without_collisions_is_unchanged(caplog):
    with caplog.at_level(logging.WARNING, logger="xmlstreamer"):
        parsed = parse_item(b"<item><x>a</x><x>b</x><x>c</x></item>")
    assert parsed == {"x": "a", "x_1": "b", "x_2": "c"}
    assert caplog.text == ""


def test_crlf_and_cr_are_normalized():
    # XML 1.0 §2.11: literal line ends normalize to "\n" before parsing.
    assert parse_item(b"<item><t>a\r\nb</t></item>") == {"t": "a\nb"}
    assert parse_item(b"<item><t>a\rb</t></item>") == {"t": "a\nb"}
    assert parse_item(b"<item><t>trailing\r\n</t></item>") == {"t": "trailing"}


def test_character_references_are_exempt_from_newline_normalization():
    assert parse_item(b"<item><t>a&#13;b</t></item>") == {"t": "a\rb"}


def test_leading_bom_is_ignored():
    assert parse_item(b"\xef\xbb\xbf<item><t>x</t></item>") == {"t": "x"}


@pytest.mark.parametrize(
    "doc",
    [
        b"<item><t>x]]>y</t></item>",
        b"<item><!-- a -- b --><t>x</t></item>",
        b"<item><?xml version='1.0'?><t>x</t></item>",
        b"<item><?1pi x?><t>x</t></item>",
        b"<item><t a='&bogus;'>x</t></item>",
    ],
)
def test_malformed_constructs_drop_the_item(doc):
    assert parse_item(doc) is None
