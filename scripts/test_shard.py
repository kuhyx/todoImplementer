#!/usr/bin/env python3
"""Print the test files of shard K of N, so `make test` runs as N calls each under 60 s (T2416).

Usage: test_shard.py K N (1 <= K <= N). Files are dealt largest first to the lightest shard, size standing
in for run time; each file lands in exactly one shard, so the N shards together run the whole suite once.
"""

from __future__ import annotations

import sys
from pathlib import Path

SHARD_VAR = "TODOIMPL_TEST_SHARD"  # k/N: the root conftest keeps shard k of N


def files(root: Path, shard: int, shards: int) -> list[str]:
    """Return the sorted repo-relative test files of `shard` (1-based) out of `shards`."""
    found = sorted(root.glob("tests/**/test_*.py"), key=lambda p: (-p.stat().st_size, str(p)))
    loads = [0] * shards
    picked: list[list[str]] = [[] for _ in range(shards)]
    for path in found:
        lightest = loads.index(min(loads))
        loads[lightest] += path.stat().st_size
        picked[lightest].append(str(path.relative_to(root)))
    return sorted(picked[shard - 1])


def main(argv: list[str]) -> int:
    """Print shard K of N, one file per line; 2 on bad arguments."""
    try:
        shard, shards = (int(a) for a in argv)
    except ValueError:
        print("usage: test_shard.py K N", file=sys.stderr)
        return 2
    if not 1 <= shard <= shards:
        print("usage: test_shard.py K N", file=sys.stderr)
        return 2
    print("\n".join(files(Path(), shard, shards)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
