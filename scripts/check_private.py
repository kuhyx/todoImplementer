"""Gate: no repo file, path or commit message contains a value from the private denylist.

The denylist lives outside the repo (default ~/.config/todoImplementer/private-denylist.txt, override with
TODOIMPL_PRIVATE_DENYLIST). A line is a literal substring, or "re:<regex>"; "#" starts a comment. Matching is
case-insensitive. A missing or empty denylist fails closed: an unchecked repo is not a clean repo.

Usage: check_private.py [--root DIR] [--message TEXT | --message-file FILE]
"""

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from repo_files import repo_files

ENV_VAR = "TODOIMPL_PRIVATE_DENYLIST"
DEFAULT_PATH = Path("~/.config/todoImplementer/private-denylist.txt")


@dataclass(frozen=True)
class Hit:
    """One denylisted value found at a place (a file path, "path:line" or the commit message)."""

    where: str
    pattern: str


def denylist_path() -> Path:
    """Return the denylist file: the env override, else the default under HOME."""
    return Path(os.environ.get(ENV_VAR) or DEFAULT_PATH).expanduser()


def load_patterns(path: Path) -> list[re.Pattern[str]]:
    """Compile the denylist; raise ValueError when it is missing or holds no pattern."""
    if not path.is_file():
        msg = f"denylist not found at {path}"
        raise ValueError(msg)
    patterns: list[re.Pattern[str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        source = line[3:] if line.startswith("re:") else re.escape(line)
        patterns.append(re.compile(source, re.IGNORECASE))
    if not patterns:
        msg = f"denylist at {path} is empty"
        raise ValueError(msg)
    return patterns


def scan_text(where: str, text: str, patterns: list[re.Pattern[str]]) -> list[Hit]:
    """Return a Hit per (line, pattern) match; `where` names the file ("path:line") or message."""
    hits: list[Hit] = []
    for number, line in enumerate(text.splitlines(), start=1):
        hits.extend(Hit(f"{where}:{number}", p.pattern) for p in patterns if p.search(line))
    return hits


def scan_repo(root: Path, patterns: list[re.Pattern[str]]) -> list[Hit]:
    """Scan every repo file's path and text content."""
    hits: list[Hit] = []
    for rel in repo_files(root):
        hits.extend(Hit(str(rel), p.pattern) for p in patterns if p.search(str(rel)))
        data = (root / rel).read_bytes()
        if b"\0" not in data:
            hits.extend(scan_text(str(rel), data.decode("utf-8", errors="replace"), patterns))
    return hits


def main(argv: list[str]) -> int:
    """Exit 0 clean, 1 on a hit, 2 when the denylist cannot be used."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--message")
    parser.add_argument("--message-file", type=Path)
    args = parser.parse_args(argv)
    try:
        patterns = load_patterns(denylist_path())
    except ValueError as error:
        print(f"check_private: {error}", file=sys.stderr)
        return 2
    hits = scan_repo(args.root, patterns)
    message = args.message
    if args.message_file:
        message = args.message_file.read_text(encoding="utf-8")
    if message:
        hits += scan_text("commit-message", message, patterns)
    for hit in hits:
        print(f"private value at {hit.where} (pattern {hit.pattern})")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
