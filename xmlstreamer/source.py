"""Pipeline-capable `rypipe` source for xmlstreamer feeds.

Follows the crxml formula: subclass `rypipe.Adapter`, implement `read`, and
users get the `|` pipeline, caching, and every sink for free. The parse runs
entirely in the Rust rypipe adapter (`xmlstreamer._xmlstreamer`).
"""

from __future__ import annotations

from typing import Any, Iterator, Optional

import pyarrow as pa

from rypipe import Adapter

from . import _xmlstreamer

__all__ = ["XmlSource"]

_MODES = ("auto", "columnar", "parallel", "stream", "parallel_streaming")


def _validate_separator_tag(separator_tag: Any) -> str:
    if not isinstance(separator_tag, str):
        raise TypeError("separator_tag must be a str")
    if not separator_tag or not _xmlstreamer.is_xml_name(
        separator_tag.encode("utf-8", "replace")
    ):
        raise ValueError(
            f"separator_tag {separator_tag!r} is not a name an XML tag can have"
        )
    return separator_tag


def _validate_engine(engine: Any) -> str:
    if not isinstance(engine, str):
        raise TypeError("engine must be a str")
    if engine not in _MODES:
        raise ValueError(
            f"engine must be one of {_MODES!r}, got {engine!r}"
        )
    return engine


def _from_batches(batches) -> pa.Table:
    """Materialize batches; an empty stream is an empty (zero-column) table,
    which `pa.Table.from_batches([])` refuses to build."""
    batches = list(batches)
    if not batches:
        return pa.table({})
    return pa.Table.from_batches(batches)


def _sized(
    batches: Iterator[pa.RecordBatch], batch_size: Optional[int]
) -> Iterator[pa.RecordBatch]:
    """Honor ``batch_size`` by slicing whatever the engine produced."""
    if batch_size is None:
        yield from batches
        return
    for batch in batches:
        offset = 0
        while offset < batch.num_rows:
            yield batch.slice(offset, batch_size)
            offset += batch_size


class XmlSource(Adapter):
    """A row source over an XML feed, one item per record.

    ``separator_tag`` names the record element; everything else follows the
    rypipe `Adapter` contract (``schema``, ``field_types``, ``drop_fields``,
    ``filter``, ``use_mmap``, ...).

    Unlike `StreamInterpreter`, the adapter does not run encoding detection:
    feeds must be UTF-8 (a leading BOM is allowed). Invalid bytes in text are
    replaced with U+FFFD; this path emits no warning for them.
    """

    __slots__ = ("_separator_tag", "_engine_mode", "_threads")

    def __init__(
        self,
        path,
        *,
        separator_tag: str = "item",
        engine: str = "columnar",
        threads: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        self._separator_tag = _validate_separator_tag(separator_tag)
        self._engine_mode = _validate_engine(engine)
        self._threads = threads
        super().__init__(path, **kwargs)

    def _resolve_mode(self, path: str, mode: str, threads: Optional[int]) -> str:
        if mode != "auto":
            return mode
        import os

        from rypipe import resolve_engine

        resolved = resolve_engine(
            file_size=os.path.getsize(path),
            threads=threads,
            schema=self._schema or None,
            has_parallel=True,
            has_columnar=True,
        )
        # rypipe's names are honored as-is; `read` maps streaming modes to
        # the parallel table reader, `iter_record_batches` to the streaming
        # one.
        return resolved

    def read(self, path: str, **kwargs: Any) -> pa.Table:
        mode = _validate_engine(kwargs.pop("engine", self._engine_mode))
        threads = kwargs.pop("threads", self._threads)
        chunks = kwargs.pop("chunks", None)
        memory = kwargs.pop("memory", None)
        kwargs.pop("batch_size", None)
        mode = self._resolve_mode(path, mode, threads)
        if mode in ("parallel", "parallel_streaming") or (
            mode == "columnar" and threads and threads > 1
        ):
            return _xmlstreamer.read_xml_par(
                str(path),
                separator_tag=self._separator_tag,
                chunks=chunks or threads or 8,
                **kwargs,
            )
        if mode in ("stream", "auto"):
            batches = _xmlstreamer.read_xml_stream(
                str(path),
                separator_tag=self._separator_tag,
                memory=memory if memory is not None else "64MiB",
                **kwargs,
            )
            return _from_batches(batches)
        return _xmlstreamer.read_xml(
            str(path), separator_tag=self._separator_tag, **kwargs
        )

    def _iter_record_batches_stream(
        self,
        memory: Any = "64MiB",
        batch_size: Optional[int] = None,
        **plan_overrides: Any,
    ) -> Iterator[pa.RecordBatch]:
        # Parallel streaming is the default when threads are requested; it
        # preserves file order and bounds parser memory. Without threads the
        # sequential bounded path is used.
        mode = _validate_engine(plan_overrides.pop("engine", self._engine_mode))
        threads = plan_overrides.pop("threads", self._threads)
        ordered = plan_overrides.pop("ordered", True)
        plan = self._build_plan_kwargs()
        if plan_overrides:
            plan.update(plan_overrides)
        mode = self._resolve_mode(str(self._path), mode, threads)
        if mode in ("parallel", "parallel_streaming") or (
            mode == "columnar" and threads and threads > 1
        ):
            yield from _sized(
                _xmlstreamer.iter_xml_batches_par(
                    str(self._path),
                    separator_tag=self._separator_tag,
                    threads=threads if threads else 8,
                    memory=memory,
                    ordered=ordered,
                    **plan,
                ),
                batch_size,
            )
            return
        yield from _sized(
            _xmlstreamer.read_xml_stream(
                str(self._path),
                separator_tag=self._separator_tag,
                memory=memory,
                **plan,
            ),
            batch_size,
        )
