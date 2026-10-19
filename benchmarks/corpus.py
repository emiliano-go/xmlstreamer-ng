"""Loader for the hand-authored benchmark corpus (see corpus/README.md)."""

from pathlib import Path
from typing import List, Tuple

HERE = Path(__file__).resolve().parent
VALID_DIR = HERE / "corpus" / "valid"
DIRTY_DIR = HERE / "corpus" / "dirty"


def load_corpus(directory: Path | str) -> List[Tuple[str, bytes]]:
    """Return ``(filename, bytes)`` for every ``*.xml`` file, sorted."""
    return [
        (path.name, path.read_bytes())
        for path in sorted(Path(directory).glob("*.xml"))
    ]
