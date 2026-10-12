"""Builders for the synthetic XML feeds used across the test suite."""

from typing import Generator


def build_feed(items: list[dict[str, str]], encoding: str = "utf-8") -> bytes:
    """Flat RSS-like document: a <feed> wrapping one <item> per dict."""
    parts = ['<?xml version="1.0"?>', "<feed>"]
    for item in items:
        parts.append("<item>")
        for tag, text in item.items():
            parts.append(f"<{tag}>{text}</{tag}>")
        parts.append("</item>")
    parts.append("</feed>")
    return "".join(parts).encode(encoding)


def chunked(data: bytes, size: int) -> Generator[bytes, None, None]:
    """Yield `data` in chunks of `size` bytes.

    A real generator function: Tokenizer's construction validator expects
    a Generator, so plain iterators (e.g. iter([...])) are not a
    substitute.
    """
    for i in range(0, len(data), size):
        yield data[i:i + size]


def drain(tokenizer, limit: int = 200) -> list:
    """Pull items until the tokenizer reports EOF.

    Hard cap so a run that never terminates fails fast instead of
    hanging.
    """
    out = []
    for _ in range(limit):
        item = tokenizer.get_item()
        if item is None:
            return out
        out.append(item)
    raise AssertionError("Tokenizer did not reach EOF within limit")
