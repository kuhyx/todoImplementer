"""Gate: no file in the repo is longer than the line cap (lockfiles are exempt by name)."""

import sys
from pathlib import Path

from repo_files import LOCKFILES, repo_files

CAP = 250


def line_count(path: Path) -> int:
    """Return the number of lines in a text file, 0 for a binary one."""
    data = path.read_bytes()
    if b"\0" in data:
        return 0
    return data.count(b"\n") + (0 if data.endswith(b"\n") or not data else 1)


def over_cap(root: Path, cap: int = CAP) -> list[tuple[str, int]]:
    """Return (path, lines) for every file past the cap."""
    found = [(str(rel), line_count(root / rel)) for rel in repo_files(root) if rel.name not in LOCKFILES]
    return [(name, lines) for name, lines in found if lines > cap]


def main(argv: list[str]) -> int:
    """Print the offenders; exit 1 when there are any."""
    root = Path(argv[0]) if argv else Path.cwd()
    bad = over_cap(root)
    for name, lines in bad:
        print(f"{name}: {lines} lines (cap {CAP}); split it by concern")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
