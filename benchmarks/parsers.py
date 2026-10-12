"""One adapter per parser, all with the same shape: consume a binary
file-like object and call sink(record) per item, in each library's best
streaming idiom. Third-party imports are lazy so the xmlstreamer column
works without the bench dependency group."""

from typing import Any, BinaryIO, Callable

SinkT = Callable[[Any], Any]

CHUNK_SIZE = 64 * 1024


def _chunks(source: BinaryIO, size: int = CHUNK_SIZE):
    while True:
        block = source.read(size)
        if not block:
            return
        yield block


def consume_xmlstreamer(source: BinaryIO, sink: SinkT) -> None:
    """Full local pipeline: encoding detection + tokenizer + per-item
    expat. Discarded (malformed) items reach the sink as None."""
    from xmlstreamer import Tokenizer, decode_stream, resolve_sample_encoding

    sample = source.read(CHUNK_SIZE)
    encoding = resolve_sample_encoding(sample)

    def replayed():
        if sample:
            yield sample
        yield from _chunks(source)

    feed = decode_stream(replayed(), encoding) if encoding else replayed()
    tokenizer = Tokenizer(
        feed_generator=feed, separator_tag="item", buffer_size=128 * 1024
    )
    while True:
        item = tokenizer.get_item()
        if item is None:
            return
        sink(item.parsed_content)


def consume_lxml(source: BinaryIO, sink: SinkT) -> None:
    """lxml.etree.iterparse(recover=True) with the documented cleanup
    idiom, so processed elements do not accumulate."""
    from lxml import etree

    for _, element in etree.iterparse(
        source, events=("end",), tag="item", recover=True
    ):
        sink({child.tag: child.text for child in element})
        element.clear(keep_tail=True)
        while element.getprevious() is not None:
            del element.getparent()[0]


def consume_stdlib(source: BinaryIO, sink: SinkT) -> None:
    """xml.etree.ElementTree.iterparse with root.clear() per item, the
    stdlib memory idiom. No recovery mode exists: dirty XML raises."""
    import xml.etree.ElementTree as ElementTree

    iterator = ElementTree.iterparse(source, events=("start", "end"))
    _, root = next(iterator)
    for event, element in iterator:
        if event == "end" and element.tag == "item":
            sink({child.tag: child.text for child in element})
            root.clear()


def consume_xmltodict(source: BinaryIO, sink: SinkT) -> None:
    """xmltodict.parse() as commonly used: the whole document becomes
    one dict in memory, then items are walked."""
    import xmltodict

    document = xmltodict.parse(source)
    root = next(iter(document.values()), None) if document else None
    items = (root or {}).get("item", [])
    if isinstance(items, dict):
        items = [items]
    for item in items:
        sink(item)


def consume_xmltodict_stream(source: BinaryIO, sink: SinkT) -> None:
    """xmltodict streaming mode (item_depth + item_callback), its own
    answer to large documents."""
    import xmltodict

    def callback(_path, item):
        sink(item)
        return True

    xmltodict.parse(source, item_depth=2, item_callback=callback)


# Short keys double as CLI arguments for the memory workers.
PARSERS = {
    "xmlstreamer": consume_xmlstreamer,
    "lxml": consume_lxml,
    "stdlib": consume_stdlib,
    "xmltodict": consume_xmltodict,
    "xmltodict-stream": consume_xmltodict_stream,
}

LABELS = {
    "xmlstreamer": "xmlstreamer",
    "lxml": "lxml iterparse (recover=True)",
    "stdlib": "stdlib ElementTree iterparse",
    "xmltodict": "xmltodict",
    "xmltodict-stream": "xmltodict (streaming mode)",
}
