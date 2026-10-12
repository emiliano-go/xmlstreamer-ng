"""Registration of xmlstreamer as a `rypipe` adapter.

Importing this module (which `xmlstreamer/__init__.py` does) makes
``rypipe.read("feed.xml", separator_tag="item")`` work.
"""

from __future__ import annotations

from typing import Any, Iterator, Optional

import pyarrow as pa

from . import _xmlstreamer
from .source import _from_batches, _sized, _validate_engine, _validate_separator_tag

__all__ = ["XmlAdapter"]


class XmlAdapter:
    """Plain adapter object registered with rypipe."""

    def read(self, path: str, **kwargs: Any) -> pa.Table:
        _validate_separator_tag(kwargs.get("separator_tag", "item"))
        engine = kwargs.pop("engine", None)
        memory = kwargs.pop("memory", None)
        threads = kwargs.pop("threads", None)
        chunks = kwargs.pop("chunks", None)
        kwargs.pop("batch_size", None)
        if engine is not None:
            engine = _validate_engine(engine)
        mode = engine or "columnar"
        if mode in ("parallel", "parallel_streaming"):
            return _xmlstreamer.read_xml_par(
                str(path), chunks=chunks or threads or 8, **kwargs
            )
        if mode in ("stream", "auto") or memory is not None:
            batches = _xmlstreamer.read_xml_stream(
                str(path),
                memory=memory if memory is not None else "64MiB",
                **kwargs,
            )
            return _from_batches(batches)
        if threads and threads > 1 or (chunks and chunks > 1):
            return _xmlstreamer.read_xml_par(
                str(path), chunks=chunks or threads or 8, **kwargs
            )
        return _xmlstreamer.read_xml(str(path), **kwargs)

    def iter_record_batches(
        self,
        path: str,
        memory: Any = "64MiB",
        batch_size: Optional[int] = None,
        **kwargs: Any,
    ) -> Iterator[pa.RecordBatch]:
        _validate_separator_tag(kwargs.get("separator_tag", "item"))
        engine = kwargs.pop("engine", None)
        threads = kwargs.pop("threads", None)
        ordered = kwargs.pop("ordered", True)
        if engine is not None and _validate_engine(engine) == "stream":
            threads = None  # an explicit sequential stream ignores threads
        if threads and threads > 1:
            batches: Iterator[pa.RecordBatch] = _xmlstreamer.iter_xml_batches_par(
                str(path),
                threads=threads,
                memory=memory,
                ordered=ordered,
                **kwargs,
            )
        else:
            batches = _xmlstreamer.read_xml_stream(
                str(path), memory=memory, **kwargs
            )
        yield from _sized(batches, batch_size)


def _register() -> None:
    try:
        import rypipe
    except Exception:  # pragma: no cover - rypipe is a hard dependency
        return
    rypipe.register_adapter("xmlstreamer", XmlAdapter(), extensions=[".xml"])


_register()
