"""Gate: every regression row has a test tagged with its id, and every test tag has a row.

Rows live in tests/regressions/*.md as `| T12 | what went wrong | test |`. A pytest test carries the tag as
`def test_t12_...`; a vitest title carries `[T12]`.
"""

import re
import sys
from pathlib import Path

from repo_files import repo_files

ROW = re.compile(r"^\|\s*(T\d+)\s*\|", re.MULTILINE)
PY_TAG = re.compile(r"^\s*def test_(t\d+)_", re.MULTILINE)
TS_TAG = re.compile(r"\[(T\d+)\]")


def row_ids(root: Path) -> set[str]:
    """Return the ids of every row under tests/regressions/."""
    ids: set[str] = set()
    for rel in repo_files(root):
        if rel.parts[:2] == ("tests", "regressions") and rel.suffix == ".md":
            ids |= set(ROW.findall((root / rel).read_text(encoding="utf-8")))
    return ids


def test_tags(root: Path) -> set[str]:
    """Return the ids that tests/**/*.py and web/**/*.test.ts name in a test title."""
    tags: set[str] = set()
    for rel in repo_files(root):
        text_file = root / rel
        if rel.parts[0] == "tests" and rel.suffix == ".py":
            tags |= {tag.upper() for tag in PY_TAG.findall(text_file.read_text(encoding="utf-8"))}
        elif rel.parts[0] == "web" and rel.name.endswith((".test.ts", ".test.tsx")):
            tags |= set(TS_TAG.findall(text_file.read_text(encoding="utf-8")))
    return tags


def problems(root: Path) -> list[str]:
    """Return one line per row without a test and per tag without a row."""
    rows, tags = row_ids(root), test_tags(root)
    return [f"{rid}: row has no test" for rid in sorted(rows - tags)] + [
        f"{rid}: test has no row" for rid in sorted(tags - rows)
    ]


def main(argv: list[str]) -> int:
    """Print the problems; exit 1 when there are any."""
    found = problems(Path(argv[0]) if argv else Path.cwd())
    for line in found:
        print(line)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
