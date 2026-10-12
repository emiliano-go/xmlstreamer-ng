import gzip
import logging
import tempfile

import pytest
import requests

from feedlib import chunked

import chardet

from xmlstreamer import (
    ApiKeyAuth,
    BasicAuth,
    BearerAuth,
    DigestAuth,
    _build_http_auth,
    _build_http_headers,
    buffered_random_to_generator,
    decode_stream,
    is_gzip,
    read_stream_sample,
    resolve_sample_encoding,
    resolve_stream_encoding,
    stream_gzip_decompress,
)


UTF8_SAMPLE = "programación coração año".encode("utf-8")
LATIN1_SAMPLE = "programación región año".encode("latin-1")
UTF16_SAMPLE = "<books><book>programación</book></books>".encode("utf-16")


@pytest.mark.parametrize(
    ("detected", "sample", "expected"),
    [
        # Empty sample or no detection: passthrough.
        (None, b"", None),
        (None, LATIN1_SAMPLE, None),
        ("utf-8", UTF8_SAMPLE, None),
        ("ascii", b"plain ascii feed", None),
        # Valid utf-8 can never be overridden by chardet.
        ("MacRoman", UTF8_SAMPLE, None),
        ("windows-1252", UTF8_SAMPLE, None),
        ("ISO-8859-1", "melodía órbita".encode("utf-8"), None),
        # utf-8 cut mid-character at the sample edge is still utf-8.
        ("windows-1252", "año".encode("utf-8")[:-1], None),
        # Not valid utf-8: chardet decides.
        ("ISO-8859-1", LATIN1_SAMPLE, "ISO-8859-1"),
        ("windows-1252", LATIN1_SAMPLE, "windows-1252"),
        # UTF-16 (NUL-dense, BOM): transcode.
        ("UTF-16", UTF16_SAMPLE, "UTF-16"),
        # Codec unknown to Python: passthrough.
        ("NO-EXISTE-9000", LATIN1_SAMPLE, None),
    ],
)
def test_resolve_stream_encoding(detected, sample, expected):
    assert resolve_stream_encoding(detected, sample) == expected


def test_resolve_sample_encoding_never_runs_chardet_on_utf8(monkeypatch):
    # The common case must not pay the detector: valid utf-8 resolves
    # to passthrough before chardet is ever consulted.
    def boom(sample):
        raise AssertionError("chardet.detect ran for valid utf-8")

    monkeypatch.setattr(chardet, "detect", boom)
    assert resolve_sample_encoding(UTF8_SAMPLE) is None
    assert resolve_sample_encoding(b"plain ascii feed") is None
    assert resolve_sample_encoding(b"") is None


@pytest.mark.parametrize("sample", [LATIN1_SAMPLE, UTF16_SAMPLE])
def test_resolve_sample_encoding_matches_the_two_step_path(sample):
    # For non-utf-8 input the lazy path must decide exactly what the
    # detect-then-resolve path always decided.
    expected = resolve_stream_encoding(chardet.detect(sample)["encoding"], sample)
    assert resolve_sample_encoding(sample) == expected


def test_read_stream_sample_respects_chunk_granularity():
    assert read_stream_sample(chunked(b"abcdef", 2), sample_size=3) == b"abcd"


def test_read_stream_sample_short_stream():
    assert read_stream_sample(chunked(b"ab", 1), sample_size=100) == b"ab"


SAMPLE_XML = b"<feed>" + b"<item><t>data</t></item>" * 200 + b"</feed>"


@pytest.mark.parametrize("chunk_size", [1, 7, 1024, len(SAMPLE_XML)])
def test_stream_gzip_decompress_roundtrip(chunk_size):
    compressed = gzip.compress(SAMPLE_XML)
    result = b"".join(stream_gzip_decompress(chunked(compressed, chunk_size)))
    assert result == SAMPLE_XML


def test_stream_gzip_decompress_from_file_object():
    # File objects also work as input (duck typing).
    with tempfile.TemporaryFile() as f:
        f.write(gzip.compress(SAMPLE_XML))
        f.seek(0)
        assert b"".join(stream_gzip_decompress(f)) == SAMPLE_XML


@pytest.mark.parametrize("chunk_size", [1, 7, 1024])
def test_stream_gzip_decompress_multi_member(chunk_size):
    # Concatenated gzip members (pigz, log rotation) must all decompress.
    part1 = b"<feed><book><t>one</t></book>"
    part2 = b"<book><t>two</t></book></feed>"
    combined = gzip.compress(part1) + gzip.compress(part2)
    result = b"".join(stream_gzip_decompress(chunked(combined, chunk_size)))
    assert result == part1 + part2


def test_stream_gzip_decompress_three_members_in_one_chunk():
    combined = b"".join(gzip.compress(p) for p in (b"a", b"b", b"c"))
    result = b"".join(stream_gzip_decompress(chunked(combined, len(combined))))
    assert result == b"abc"


def test_stream_gzip_decompress_trailing_garbage_tolerated(caplog):
    data = gzip.compress(SAMPLE_XML) + b"NOT-GZIP-JUNK"
    with caplog.at_level(logging.WARNING, logger="xmlstreamer"):
        result = b"".join(stream_gzip_decompress(chunked(data, 64)))
    assert result == SAMPLE_XML
    # Leftovers after a complete member are expected, not damage.
    assert caplog.text == ""


def test_stream_gzip_decompress_corrupt_member_warns(caplog):
    # Damage INSIDE a member truncates the feed: it must never pass as
    # the tolerated trailing garbage above.
    blob = bytearray(gzip.compress(SAMPLE_XML * 20))
    for offset in range(len(blob) // 2, len(blob) // 2 + 8):
        blob[offset] ^= 0xFF
    with caplog.at_level(logging.WARNING, logger="xmlstreamer"):
        b"".join(stream_gzip_decompress(chunked(bytes(blob), 64)))
    assert "corrupt" in caplog.text


@pytest.mark.parametrize("chunk_size", [1, 7, 64, 4096])
def test_stream_gzip_decompress_corrupt_header_warns(caplog, chunk_size):
    # A second member announces itself with the gzip magic and then
    # fails to decompress: broken member, not tolerated leftovers.
    good = gzip.compress(SAMPLE_XML)
    broken = bytearray(gzip.compress(SAMPLE_XML))
    for offset in range(2, 10):
        broken[offset] ^= 0xFF
    with caplog.at_level(logging.WARNING, logger="xmlstreamer"):
        result = b"".join(
            stream_gzip_decompress(chunked(good + bytes(broken), chunk_size))
        )
    assert result == SAMPLE_XML  # the healthy member still comes out
    assert "corrupt" in caplog.text


def test_stream_gzip_decompress_corrupt_after_complete_member_warns(caplog):
    # A second member that starts like gzip but is damaged is not
    # trailing garbage either.
    good = gzip.compress(SAMPLE_XML)
    broken = bytearray(gzip.compress(SAMPLE_XML * 20))
    for offset in range(len(broken) // 2, len(broken) // 2 + 8):
        broken[offset] ^= 0xFF
    with caplog.at_level(logging.WARNING, logger="xmlstreamer"):
        result = b"".join(
            stream_gzip_decompress(chunked(good + bytes(broken), 64))
        )
    assert result.startswith(SAMPLE_XML)
    assert "corrupt" in caplog.text


def test_stream_gzip_decompress_truncated_stream_warns(caplog):
    truncated = gzip.compress(SAMPLE_XML)[:-5]
    with caplog.at_level(logging.WARNING, logger="xmlstreamer"):
        result = b"".join(stream_gzip_decompress(chunked(truncated, 64)))
    assert result  # partial data still comes out
    assert "truncated" in caplog.text


def test_stream_gzip_decompress_complete_stream_does_not_warn(caplog):
    data = gzip.compress(SAMPLE_XML)
    with caplog.at_level(logging.WARNING, logger="xmlstreamer"):
        b"".join(stream_gzip_decompress(chunked(data, 64)))
    assert "truncated" not in caplog.text


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (gzip.compress(b"data"), True),
        (b"<xml/>", False),
        (b"", False),
    ],
)
def test_is_gzip(payload, expected):
    with tempfile.TemporaryFile() as f:
        f.write(payload)
        f.seek(3)  # arbitrary position: is_gzip must rewind on its own
        assert is_gzip(f) is expected
        assert f.tell() == 0


def test_buffered_random_to_generator_chunks():
    with tempfile.TemporaryFile() as f:
        f.write(b"0123456789")
        f.seek(0)
        chunks = list(buffered_random_to_generator(f, chunk_size=3))
    assert chunks == [b"012", b"345", b"678", b"9"]


@pytest.mark.parametrize("chunk_size", [1, 3, 16])
def test_decode_stream_utf16_to_utf8(chunk_size):
    # Odd sizes split UTF-16 code units: the incremental decoder must cope.
    text = "programación de una canción - piñata €"
    raw = text.encode("utf-16")
    result = b"".join(decode_stream(chunked(raw, chunk_size), "utf-16"))
    assert result.decode("utf-8") == text


def test_decode_stream_latin1_to_utf8():
    text = "programación región café"
    raw = text.encode("latin-1")
    result = b"".join(decode_stream(chunked(raw, 5), "ISO-8859-1"))
    assert result.decode("utf-8") == text


def test_decode_stream_invalid_bytes_replaced_not_raised():
    # 0x81 is undefined in cp1252: degrade to U+FFFD, do not blow up.
    raw = "año".encode("windows-1252") + b"\x81" + "fin".encode("windows-1252")
    result = b"".join(decode_stream(chunked(raw, 2), "windows-1252"))
    assert result.decode("utf-8") == "año�fin"


def test_build_http_auth_basic_tuple():
    assert _build_http_auth(BasicAuth("user", "pass")) == ("user", "pass")


def test_build_http_auth_digest():
    result = _build_http_auth(DigestAuth("user", "pass"))
    assert isinstance(result, requests.auth.HTTPDigestAuth)
    assert (result.username, result.password) == ("user", "pass")


@pytest.mark.parametrize(
    "auth",
    [None, BearerAuth("tok"), ApiKeyAuth(header="X-K", value="v")],
)
def test_build_http_auth_header_based_returns_none(auth):
    assert _build_http_auth(auth) is None


def test_build_http_headers_default():
    assert _build_http_headers("UA/1.0", None) == {"User-Agent": "UA/1.0"}


def test_build_http_headers_bearer():
    headers = _build_http_headers("UA/1.0", BearerAuth("tok123"))
    assert headers == {"User-Agent": "UA/1.0", "Authorization": "Bearer tok123"}


def test_build_http_headers_api_key():
    headers = _build_http_headers("UA/1.0", ApiKeyAuth(header="X-Api-Key", value="s3cr3t"))
    assert headers == {"User-Agent": "UA/1.0", "X-Api-Key": "s3cr3t"}
