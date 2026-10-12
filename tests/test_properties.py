"""Property-based tests: the library's core invariants verified over
generated inputs, not hand-picked examples. The generators build feeds
(and corruptions) around the `item` separator; every property runs the
real Tokenizer over in-memory chunks."""

from hypothesis import assume, given, settings, strategies as st

from feedlib import chunked

from xmlstreamer import Tokenizer, parse_item, to_nested

# Field tags: valid XML names that can never nest the separator.
TAGS = st.from_regex(r"[a-z][a-z0-9]{0,7}", fullmatch=True).filter(
    lambda t: t != "item"
)

# Values: printable text with no XML metacharacters and no ";", so an
# injected "&" can never complete into a valid entity reference.
VALUES = st.text(
    alphabet=st.characters(
        min_codepoint=0x20, max_codepoint=0x2FF,
        blacklist_characters='<>&;',
    ),
    max_size=20,
)

FIELDS = st.lists(st.tuples(TAGS, VALUES), min_size=1, max_size=6)
ITEMS = st.lists(FIELDS, min_size=1, max_size=6)


def render_item(fields) -> bytes:
    inner = "".join(f"<{t}>{v}</{t}>" for t, v in fields)
    return f"<item>{inner}</item>".encode()


def expected_flat(fields) -> dict:
    # Mirror of the public numbering rule for flat items: first
    # occurrence keeps the tag, repeats become tag_1, tag_2, ...
    out, seen = {}, {}
    for tag, value in fields:
        if tag in seen:
            seen[tag] += 1
            key = f"{tag}_{seen[tag]}"
        else:
            seen[tag] = 0
            key = tag
        out[key] = value
    return out


def drain(feed: bytes, buffer_size: int = 4096, chunk: int = 64) -> list:
    tokenizer = Tokenizer(
        feed_generator=chunked(feed, chunk),
        separator_tag="item",
        buffer_size=buffer_size,
    )
    out = []
    while (item := tokenizer.get_item()) is not None:
        out.append(item.parsed_content)
    return out


def emitted(feed: bytes, **kwargs) -> list:
    return [d for d in drain(feed, **kwargs) if d is not None]


def is_subsequence(sub: list, full: list) -> bool:
    it = iter(full)
    return all(any(x == y for y in it) for x in sub)


XML_TOKENS = st.sampled_from([
    b"<item>", b"</item>", b"<item />", b"<item a='1'>", b"<!--", b"-->",
    b"<![CDATA[", b"]]>", b"<a>", b"</a>", b"&", b"<", b">", b"<!",
])


@settings(max_examples=120, deadline=None)
@given(
    pieces=st.lists(
        st.one_of(st.binary(max_size=12), XML_TOKENS), max_size=25
    ),
    chunk=st.integers(min_value=1, max_value=97),
)
def test_arbitrary_bytes_never_crash_and_output_is_typed(pieces, chunk):
    feed = b"".join(pieces)
    for parsed in drain(feed, buffer_size=32, chunk=chunk):
        if parsed is not None:
            assert isinstance(parsed, dict)
            assert all(
                isinstance(k, str) and isinstance(v, str)
                for k, v in parsed.items()
            )


@settings(max_examples=100, deadline=None)
@given(items=ITEMS)
def test_wellformed_roundtrip(items):
    feed = b"<feed>" + b"".join(render_item(f) for f in items) + b"</feed>"
    assert emitted(feed) == [expected_flat(f) for f in items]


@settings(max_examples=100, deadline=None)
@given(
    items=st.lists(FIELDS, min_size=2, max_size=6),
    index=st.data(),
    poison=st.sampled_from([b"&", b"<"]),
)
def test_isolation_contained_corruption(items, index, poison):
    # Corrupting strictly inside one item's delimiters must drop exactly
    # that item and leave every neighbor byte-identical in the output.
    # CONTAINED is the precondition, not a detail: an injected "<" that
    # lands on "?" or "!" opens a section, and one that lands on the
    # separator's name opens an item. Neither is damage inside an item
    # any more - it is markup that never closes, and what a feed that
    # ends inside one means is a documented policy with its own tests
    # (test_tokenizer.py, "unterminated" and "read_as_text").
    i = index.draw(st.integers(0, len(items) - 1), label="victim")
    rendered = [render_item(f) for f in items]
    body = rendered[i][len(b"<item>"):-len(b"</item>")]
    cut = index.draw(st.integers(0, len(body)), label="cut")
    if poison == b"<":
        tail = body[cut:]
        assume(tail[:1] not in (b"?", b"!"))
        assume(not tail.startswith(b"item"))
    rendered[i] = b"<item>" + body[:cut] + poison + body[cut:] + b"</item>"
    feed = b"<feed>" + b"".join(rendered) + b"</feed>"
    expected = [expected_flat(f) for j, f in enumerate(items) if j != i]
    assert emitted(feed) == expected


@settings(max_examples=100, deadline=None)
@given(items=st.lists(FIELDS, min_size=2, max_size=6), index=st.data())
def test_structural_corruption_never_fabricates(items, index):
    # Even deleting an item delimiter (blast radius may reach a
    # neighbor) must never invent or mutate an emitted record.
    i = index.draw(st.integers(0, len(items) - 1), label="victim")
    which = index.draw(st.sampled_from(["open", "close"]), label="which")
    rendered = [render_item(f) for f in items]
    if which == "open":
        rendered[i] = rendered[i][len(b"<item>"):]
    else:
        rendered[i] = rendered[i][:-len(b"</item>")]
    feed = b"<feed>" + b"".join(rendered) + b"</feed>"
    expected = [expected_flat(f) for f in items]
    assert is_subsequence(emitted(feed), expected)


@settings(max_examples=100, deadline=None)
@given(
    items=ITEMS,
    cuts=st.lists(st.integers(min_value=0, max_value=10_000), max_size=12),
)
def test_chunking_and_buffer_invariance(items, cuts):
    # The same bytes must yield the same items regardless of how the
    # stream is fragmented or how small the buffer is; twice over for
    # determinism. This is the cursor/seek edge-case hunter.
    feed = b"<feed>" + b"".join(render_item(f) for f in items) + b"</feed>"
    points = sorted({min(c, len(feed)) for c in cuts})
    fragments = []
    prev = 0
    for p in points + [len(feed)]:
        fragments.append(feed[prev:p])
        prev = p

    def fragmented():
        yield from fragments

    reference = emitted(feed, buffer_size=4096, chunk=len(feed) or 1)
    tokenizer = Tokenizer(
        feed_generator=fragmented(), separator_tag="item", buffer_size=16
    )
    ragged = []
    while (item := tokenizer.get_item()) is not None:
        if item.parsed_content is not None:
            ragged.append(item.parsed_content)
    again = emitted(feed, buffer_size=16, chunk=7)
    assert ragged == reference == again


@settings(max_examples=150, deadline=None)
@given(blob=st.binary(max_size=300))
def test_parse_item_is_total(blob):
    result = parse_item(blob)
    assert result is None or (
        isinstance(result, dict)
        and all(
            isinstance(k, str) and isinstance(v, str)
            for k, v in result.items()
        )
    )


@settings(max_examples=100, deadline=None)
@given(
    flat=st.dictionaries(
        st.text(
            alphabet=st.characters(
                min_codepoint=0x30, max_codepoint=0x7A,
                whitelist_characters="/_",
            ),
            min_size=1, max_size=12,
        ),
        VALUES,
        max_size=8,
    ),
    force_list=st.one_of(
        st.none(), st.just(True), st.sets(st.text(max_size=8), max_size=3)
    ),
)
def test_to_nested_is_total_and_deterministic(flat, force_list):
    first = to_nested(flat, force_list)
    second = to_nested(flat, force_list)
    assert first == second
    assert isinstance(first, dict)


# --- Markup sections: their content is never a record --- #

SECTION_WRAPPERS = st.sampled_from([
    (b"<!--", b"-->"),
    (b"<![CDATA[", b"]]>"),
    (b"<?pi ", b" ?>"),
    (b'<!DOCTYPE feed [<!ENTITY ghost "', b'">]>'),
])

# Ghost content has to be well-formed markup: a quote inside the entity
# value would end the DOCTYPE early, and what a MALFORMED section means
# is the caller's policy (Sections.on_limit), not an invariant.
GHOST_VALUES = st.text(
    alphabet=st.characters(
        min_codepoint=0x20, max_codepoint=0x2FF,
        blacklist_characters='<>&;"\'',
    ),
    max_size=20,
)
GHOST_ITEMS = st.lists(
    st.lists(st.tuples(TAGS, GHOST_VALUES), min_size=1, max_size=4),
    min_size=1, max_size=4,
)


@settings(max_examples=120, deadline=None)
@given(
    items=ITEMS,
    ghosts=GHOST_ITEMS,
    wrapper=SECTION_WRAPPERS,
    chunk=st.integers(min_value=1, max_value=64),
    where=st.data(),
)
def test_items_inside_markup_sections_are_never_emitted(
    items, ghosts, wrapper, chunk, where
):
    # Comments, CDATA, processing instructions and DOCTYPE subsets are
    # markup: whatever they contain is not a record, at any chunking.
    opener, closer = wrapper
    block = opener + b"".join(render_item(f) for f in ghosts) + closer
    cut = where.draw(st.integers(0, len(items)), label="where")
    rendered = [render_item(f) for f in items]
    feed = (
        b"<feed>" + b"".join(rendered[:cut]) + block
        + b"".join(rendered[cut:]) + b"</feed>"
    )
    assert emitted(feed, chunk=chunk) == [expected_flat(f) for f in items]


# Attribute values may hold ">": only "<" and "&" are illegal there.
ATTR_VALUES = st.text(
    alphabet=st.characters(
        min_codepoint=0x20, max_codepoint=0x7E,
        blacklist_characters='<&"',
    ),
    max_size=15,
)


@settings(max_examples=120, deadline=None)
@given(
    items=ITEMS,
    attr=ATTR_VALUES,
    chunk=st.integers(min_value=1, max_value=64),
)
def test_separator_attributes_never_change_the_items(items, attr, chunk):
    plain = b"<feed>" + b"".join(render_item(f) for f in items) + b"</feed>"
    decorated = b"<feed>" + b"".join(
        b'<item note="' + attr.encode() + b'">' + render_item(f)[len(b"<item>"):]
        for f in items
    ) + b"</feed>"
    assert emitted(decorated, chunk=chunk) == emitted(plain, chunk=chunk)
