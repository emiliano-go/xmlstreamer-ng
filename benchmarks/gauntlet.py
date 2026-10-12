"""Dirty-feed gauntlet: run each parser over small broken feeds and
classify the outcome automatically against the declared expectation.
The verdicts feed the honesty table: silent loss and silent corruption
are the failure modes this library exists to avoid."""

import dataclasses
import logging
from io import BytesIO
from typing import Any, Dict, List, Optional

from parsers import (
    consume_lxml,
    consume_stdlib,
    consume_xmlstreamer,
    consume_xmltodict,
)

GAUNTLET_PARSERS = {
    "xmlstreamer": consume_xmlstreamer,
    "lxml (recover)": consume_lxml,
    "stdlib ET": consume_stdlib,
    "xmltodict": consume_xmltodict,
}


@dataclasses.dataclass(slots=True)
class Case:
    name: str
    data: bytes
    # Items a parser SHOULD deliver: intact items only, never repaired
    # guesses. None marks the out-of-contract case (informative row).
    expected: Optional[List[Dict[str, Any]]]
    note: str = ""


CASES = [
    Case(
        name="healthy feed",
        data=b"<feed><item><t>a</t></item><item><t>b</t></item></feed>",
        expected=[{"t": "a"}, {"t": "b"}],
    ),
    Case(
        name="malformed item between healthy ones",
        data=(
            b"<feed><item><t>a</t></item><item><t>b</item>"
            b"<item><t>c</t></item></feed>"
        ),
        expected=[{"t": "a"}, {"t": "c"}],
        note="item b never closes its tag",
    ),
    Case(
        name="raw ampersand and raw < in text",
        data=(
            b"<feed><item><t>Salt & Pepper</t></item>"
            b"<item><u>pages < 300</u></item>"
            b"<item><t>clean</t></item></feed>"
        ),
        expected=[{"t": "clean"}],
        note="only the clean item is deliverable without guessing",
    ),
    Case(
        name="declaration lies: says iso-8859-1, bytes are utf-8",
        data=(
            b'<?xml version="1.0" encoding="iso-8859-1"?>\n'
            b"<feed><item><t>cora\xc3\xa7\xc3\xa3o</t></item></feed>"
        ),
        expected=[{"t": "cora\u00e7\u00e3o"}],
    ),
    Case(
        name="declaration lies: says utf-8, bytes are latin-1",
        data=(
            b'<?xml version="1.0" encoding="utf-8"?>\n<feed>'
            + b"<item><t>programaci\xf3n regi\xf3n caf\xe9</t></item>" * 5
            + b"</feed>"
        ),
        expected=(
            [{"t": "programaci\u00f3n regi\u00f3n caf\u00e9"}] * 5
        ),
    ),
    Case(
        name="CDATA with literal </item> plus commented-out item",
        data=(
            b"<feed><!-- template <item><t>fake</t></item> -->"
            b"<item><d><![CDATA[one </item> two]]></d></item></feed>"
        ),
        expected=[{"d": "one </item> two"}],
    ),
    Case(
        name="download truncated mid-item",
        data=(
            b"<feed><item><t>a</t></item><item><t>b</t></item>"
            b"<item><t>cor"
        ),
        expected=[{"t": "a"}, {"t": "b"}],
        note="the third item never arrived; inventing it is corruption",
    ),
    Case(
        name="nested separator (out of xmlstreamer's contract)",
        data=b"<feed><item><a>1</a><item><b>2</b></item></item></feed>",
        expected=None,
        note="xmlstreamer documents this as unsupported",
    ),
]


def _normalize(record: Any) -> Dict[str, Optional[str]]:
    return {str(k): (None if v is None else str(v)) for k, v in dict(record).items()}


class _WarningCounter(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.count = 0

    def emit(self, record):
        self.count += 1


def run_case(parser_name: str, consume, case: Case) -> str:
    """Run one parser over one case and return the verdict cell."""
    emitted: List[Any] = []
    counter = _WarningCounter()
    xs_logger = logging.getLogger("xmlstreamer")
    xs_logger.addHandler(counter)
    error: Optional[BaseException] = None
    try:
        consume(BytesIO(case.data), emitted.append)
    except Exception as exc:
        error = exc
    finally:
        xs_logger.removeHandler(counter)

    drops = sum(1 for record in emitted if record is None)
    delivered = [_normalize(r) for r in emitted if r is not None]

    if case.expected is None:
        # Informative row: report behavior without a verdict.
        if error is not None:
            return f"error ({type(error).__name__})"
        if drops and not delivered:
            return "unsupported (documented contract)"
        return f"parses it (emits {len(delivered)})"

    if error is not None:
        return (
            f"LOUD FAILURE: {type(error).__name__}, feed lost "
            f"(emitted {len(delivered)} of {len(case.expected)} first)"
        )
    if len(delivered) > len(case.expected):
        return (
            f"FABRICATES: emits {len(delivered)} where "
            f"{len(case.expected)} are real"
        )
    if delivered == case.expected:
        if drops:
            noise = "warning logged" if counter.count else "no warning"
            return f"OK: drops broken loudly ({noise})"
        return "OK"
    if len(delivered) < len(case.expected):
        missing = len(case.expected) - len(delivered)
        if drops:
            return f"drops {missing} recoverable item(s), warning logged"
        return f"SILENT LOSS: {missing} of {len(case.expected)} gone, no signal"
    for got, want in zip(delivered, case.expected):
        if got != want:
            return f"SILENT CORRUPTION: {got!r} instead of {want!r}"
    return "OK"


def run_gauntlet() -> List[List[str]]:
    """Rows: [case name, verdict per parser...] for markdown rendering."""
    rows = []
    for case in CASES:
        row = [case.name]
        for parser_name, consume in GAUNTLET_PARSERS.items():
            row.append(run_case(parser_name, consume, case))
        rows.append(row)
    return rows
