"""Sinks re-exported from `rypipe` (crxml formula)."""

from rypipe.sinks import (  # noqa: F401
    collect,
    to_arrow,
    to_csv,
    to_pandas,
    to_parquet,
    to_polars,
)

__all__ = [
    "collect",
    "to_arrow",
    "to_csv",
    "to_pandas",
    "to_parquet",
    "to_polars",
]
