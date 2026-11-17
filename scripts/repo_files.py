"""The repo's files for the gates: tracked, staged or untracked-but-not-ignored (so *.zip never shows)."""

import subprocess
from pathlib import Path

LOCKFILES = frozenset({"uv.lock", "pnpm-lock.yaml", "pubspec.lock"})


def repo_files(root: Path) -> list[Path]:
    """Return every non-ignored file under root that exists, relative to root, sorted."""
    out = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],  # noqa: S607
        check=True,
        capture_output=True,
    ).stdout.decode()
    names = sorted({name for name in out.split("\0") if name})
    return [Path(name) for name in names if (root / name).is_file()]
