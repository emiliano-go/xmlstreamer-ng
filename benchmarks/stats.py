"""Round summaries shared by the benchmark scripts.

Headline rates use the median so one fast (or throttled) round cannot
carry a parser. Best and p95 are kept alongside it for spread.
"""

import math
import statistics
from typing import Dict, Iterable


def summarize(times: Iterable[float]) -> Dict[str, float]:
    ordered = sorted(times)
    if not ordered:
        raise ValueError("summarize() needs at least one timing")
    median = statistics.median(ordered)
    p95_index = min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)
    return {
        "best": ordered[0],
        "median": median,
        "p95": ordered[p95_index],
        "spread": (ordered[-1] - ordered[0]) / median * 100.0 if median else 0.0,
    }
