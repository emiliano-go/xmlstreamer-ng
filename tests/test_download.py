import io
import urllib.request
from urllib.parse import unquote, urlparse

import pytest
import requests

from feedlib import build_feed

from xmlstreamer import (
    USER_AGENT,
    BasicAuth,
    Transport,
    UnsupportedSchemeError,
    XMLStreamerError,
    download_file,
)


class _RecordingOpener:
    """Replaces the urllib opener to capture FTP calls without network."""

    def __init__(self, record):
        self._record = record

    def open(self, url, timeout=None):
        self._record.append((url, timeout))
        return io.BytesIO(b"<feed></feed>")


@pytest.fixture()
def ftp_opened(monkeypatch):
    opened = []
    monkeypatch.setattr(
        urllib.request, "build_opener", lambda *handlers: _RecordingOpener(opened)
    )
    return opened


def test_http_download_and_user_agent(http_server):
    body = build_feed([{"t": "x"}])
    url = http_server.serve("/feed.xml", body)
    f = download_file(url, Transport())
    try:
        f.seek(0)
        assert f.read() == body
        assert http_server.last_headers()["user-agent"] == USER_AGENT
    finally:
        f.close()


def test_unknown_scheme_raises():
    with pytest.raises(UnsupportedSchemeError, match="gopher"):
        download_file("gopher://example.com/feed", Transport())


@pytest.mark.parametrize("caught", [XMLStreamerError, ValueError])
def test_unknown_scheme_is_catchable_as_family_and_value_error(caught):
    with pytest.raises(caught):
        download_file("gopher://example.com/feed", Transport())


def test_unknown_scheme_message_does_not_leak_the_url():
    # A URL can carry credentials: the message names the scheme only.
    with pytest.raises(UnsupportedSchemeError) as excinfo:
        download_file("gopher://example.com/feed?api_key=s3cr3t", Transport())
    assert "s3cr3t" not in str(excinfo.value)


def test_ftp_url_without_auth_passes_through(ftp_opened):
    f = download_file("ftp://ftp.example.com/feed.xml", Transport())
    try:
        assert ftp_opened == [("ftp://ftp.example.com/feed.xml", 300)]
        f.seek(0)
        assert f.read() == b"<feed></feed>"
    finally:
        f.close()


def test_ftp_basic_auth_in_netloc(ftp_opened):
    download_file(
        "ftp://ftp.example.com:2121/feed.xml",
        Transport(auth=BasicAuth("user", "sec4et")),
    ).close()
    assert ftp_opened == [
        ("ftp://user:sec4et@ftp.example.com:2121/feed.xml", 300)
    ]


def test_ftp_timeout_uses_read_component(ftp_opened):
    download_file(
        "ftp://ftp.example.com/feed.xml",
        Transport(timeout=(5, 42)),
    ).close()
    assert ftp_opened[0][1] == 42


def test_http_read_timeout_raises_on_stalled_server(http_server):
    url = http_server.serve("/stalled.xml", b"<feed></feed>", delay=2.0)
    with pytest.raises(requests.exceptions.Timeout):
        download_file(url, Transport(timeout=(5, 0.3)))


def test_ftp_auth_with_reserved_chars(ftp_opened):
    download_file(
        "ftp://ftp.example.com/feed.xml",
        Transport(auth=BasicAuth("user", "p/ss@w:rd")),
    ).close()
    parsed = urlparse(ftp_opened[0][0])
    assert parsed.hostname == "ftp.example.com"
    assert unquote(parsed.username) == "user"
    assert unquote(parsed.password) == "p/ss@w:rd"
