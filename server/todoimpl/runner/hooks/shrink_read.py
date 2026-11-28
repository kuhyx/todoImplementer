"""PreToolUse hook on `Read`: an image over 1000 px is read as a shrunk copy (silent, fails open).

Images cost tokens by pixel area, and a board session re-sends every one it read. The hook shrinks a copy
(never the original) to a longest edge of 1000 px in a cache file and rewrites the Read's `file_path` to it
with `hookSpecificOutput.updatedInput`. On any error it prints nothing and exits 0, so the original file is
read. Stdlib plus the `magick` CLI; the board runs it as `python shrink_read.py`.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MAX_EDGE = 1000
SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
CACHE_VAR = "TODOIMPL_SHRINK_DIR"
TIMEOUT_S = 20


def cache_dir() -> Path:
    """Return the cache dir: `$TODOIMPL_SHRINK_DIR`, else `shrink` in the run root (`$TODOIMPL_HOME`)."""
    if given := os.environ.get(CACHE_VAR):
        return Path(given)
    home = os.environ.get("TODOIMPL_HOME")  # board/state.py `run_root`; this hook imports nothing of todoimpl
    return (Path(home) if home else Path.home() / ".cache" / "todoImplementer") / "shrink"


def longest_edge(magick: str, src: Path) -> int:
    """Return the longest edge of the image in pixels (first frame)."""
    out = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [magick, "identify", "-format", "%w %h", f"{src}[0]"],
        capture_output=True,
        text=True,
        check=True,
        timeout=TIMEOUT_S,
    )
    return max(int(n) for n in out.stdout.split())


def shrunk_copy(src: Path) -> Path | None:
    """Return the cached copy of `src` at <= MAX_EDGE px (per path and mtime); None = read the original."""
    if src.suffix.lower() not in SUFFIXES or not src.is_file():
        return None
    magick = shutil.which("magick")
    if magick is None:
        return None
    stat = src.stat()
    key = hashlib.sha1(f"{src.resolve()}\0{stat.st_mtime_ns}\0{stat.st_size}".encode()).hexdigest()[:20]  # noqa: S324
    dest = cache_dir() / f"{key}{src.suffix.lower()}"
    if dest.is_file():
        return dest
    if longest_edge(magick, src) <= MAX_EDGE:
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=dest.parent, suffix=dest.suffix, delete=False) as tmp:
        part = Path(tmp.name)
    try:
        resize = f"{MAX_EDGE}x{MAX_EDGE}>"
        subprocess.run(  # noqa: S603 - fixed argv, no shell
            [magick, f"{src}[0]", "-resize", resize, str(part)],
            capture_output=True,
            check=True,
            timeout=TIMEOUT_S,
        )
        part.replace(dest)
    finally:
        part.unlink(missing_ok=True)
    return dest


def main() -> int:
    """Read the hook input on stdin; print the `updatedInput` JSON when the Read is redirected."""
    try:
        data = json.load(sys.stdin)
        tool_input = dict(data["tool_input"])
        copy = shrunk_copy(Path(str(tool_input["file_path"])))
        if copy is not None:
            tool_input["file_path"] = str(copy)
            out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "updatedInput": tool_input}}
            sys.stdout.write(json.dumps(out))
    except Exception:  # noqa: BLE001 - fail open: the original file is read
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
