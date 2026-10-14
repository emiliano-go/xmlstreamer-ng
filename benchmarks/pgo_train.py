"""PGO training workload: drive every hot path, columnar and streaming.

Used by native/build_pgo.sh as the training step. The previous trainer only
exercised the columnar path, so the bounded streaming engine
(read_xml_stream / iter_xml_batches_par) collected little or no profile and
gained far less from PGO. This runs both feed shapes through every path once.

    python benchmarks/pgo_train.py [--mb 64]

Nothing here is a benchmark; it just feeds representative input to the
instrumented build.
"""

import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from feeds import cdata_feed, write_plain_feed  # noqa: E402

MB = 1024 * 1024


def train(mb: int) -> None:
    from xmlstreamer_ng import StreamInterpreter, _xmlstreamer

    tmp = Path(tempfile.mkdtemp(prefix="ng-pgo-"))
    plain = tmp / "plain.xml"
    with open(plain, "wb") as f:
        write_plain_feed(f, max(1, (mb * MB) // 110), block_items=50_000)
    cdata = tmp / "cdata.xml"
    cdata.write_bytes(cdata_feed(max(1, (mb * MB) // 470)))

    for path in (plain, cdata):
        sp = str(path)
        # rypipe columnar, whole file (mmap).
        _xmlstreamer.read_xml(sp, separator_tag="item", use_mmap=True)
        # Bounded streaming, single thread: the path PGO used to miss.
        sum(
            b.num_rows
            for b in _xmlstreamer.read_xml_stream(
                sp, separator_tag="item", memory="16MiB"
            )
        )
        # Parallel columnar and parallel streaming.
        _xmlstreamer.read_xml_par(sp, separator_tag="item", chunks=4, use_mmap=True)
        sum(
            b.num_rows
            for b in _xmlstreamer.iter_xml_batches_par(
                sp, separator_tag="item", threads=4, memory="16MiB", use_mmap=True
            )
        )
        # Per-item streaming engine.
        with open(path, "rb") as source:
            for _ in StreamInterpreter(source=source, separator_tag="item"):
                pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mb", type=int, default=64, help="feed size in MiB")
    args = ap.parse_args()
    train(args.mb)
    print("pgo training done")


if __name__ == "__main__":
    main()
