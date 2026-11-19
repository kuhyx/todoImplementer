"""Gate: every regression row has a test tagged with its id, every tag has a row, and no id repeats.

Rows live in tests/regressions/*.md as `| T12 | what went wrong | test |`. A pytest test carries the tag as
`def test_t12_...`; a vitest or Flutter test title (`app/**/*_test.dart`) carries `[T12]`.
"""

import re
import sys
from pathlib import Path

from repo_files import repo_files

ROW = re.compile(r"^\|\s*(T\d+)\s*\|", re.MULTILINE)
PY_TAG = re.compile(r"^\s*def test_(t\d+)_", re.MULTILINE)
TS_TAG = re.compile(r"\[(T\d+)\]")


def row_files(root: Path) -> dict[str, list[str]]:
    """Return, per row id under tests/regressions/, the file of each row that has it."""
    files: dict[str, list[str]] = {}
    for rel in repo_files(root):
        if rel.parts[:2] == ("tests", "regressions") and rel.suffix == ".md":
            for rid in ROW.findall((root / rel).read_text(encoding="utf-8")):
                files.setdefault(rid, []).append(rel.as_posix())
    return files


def test_tags(root: Path) -> set[str]:
    """Return the ids that tests/**/*.py, web/**/*.test.ts and app/**/*_test.dart name in a test title."""
    tags: set[str] = set()
    for rel in repo_files(root):
        text_file = root / rel
        if rel.parts[0] == "tests" and rel.suffix == ".py":
            tags |= {tag.upper() for tag in PY_TAG.findall(text_file.read_text(encoding="utf-8"))}
        elif (rel.parts[0] == "web" and rel.name.endswith((".test.ts", ".test.tsx"))) or (
            rel.parts[0] == "app" and rel.name.endswith("_test.dart")
        ):
            tags |= set(TS_TAG.findall(text_file.read_text(encoding="utf-8")))
    return tags


def problems(root: Path) -> list[str]:
    """Return one line per repeated id, per row without a test and per tag without a row."""
    files, tags = row_files(root), test_tags(root)
    rows = set(files)
    repeated = [
        f"{rid}: row repeated in {', '.join(sorted(where))}"
        for rid, where in sorted(files.items())
        if len(where) > 1
    ]
    return (
        repeated
        + [f"{rid}: row has no test" for rid in sorted(rows - tags)]
        + [f"{rid}: test has no row" for rid in sorted(tags - rows)]
    )


def main(argv: list[str]) -> int:
    """Print the problems; exit 1 when there are any."""
    found = problems(Path(argv[0]) if argv else Path.cwd())
    for line in found:
        print(line)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
