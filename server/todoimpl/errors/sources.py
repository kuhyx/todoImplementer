"""Where app errors come from: settings.json `error_sources`, the app-errors folder, and each source's hooks.

A source is one file plus an adapter (`adapters.py`) and two optional argv hooks: `resolve` closes an error
at its origin once the fix is deployed, `build` prints the build number that contains a pushed commit. In an
argv, `{signature}`, `{repo_dir}` and `{commit}` are replaced; a leading `~` is the home directory.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from todoimpl.credits import setting

from . import adapters
from .adapters import SourceError

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from .record import AppError

log = logging.getLogger("todoimpl.errors")
KEY = "error_sources"
HOOK_TIMEOUT = 120.0
ADAPTERS = ("kartka", "contract")


@dataclass(frozen=True)
class Source:
    """One error file and what to run for it; `repo` is empty for a contract file (its records name it)."""

    app: str
    repo: str
    adapter: str
    path: Path
    resolve: tuple[str, ...] = ()
    build: tuple[str, ...] = ()


def state_base() -> Path:
    """`$TODOIMPL_ERROR_STATE_ROOT`, else ~/.local/state: where apps keep their error state."""
    given = os.environ.get("TODOIMPL_ERROR_STATE_ROOT")
    return Path(given) if given else Path.home() / ".local" / "state"


def _home(text: str) -> str:
    return str(Path.home() / text[2:]) if text.startswith("~/") else text


def _kartka_default() -> Source:
    tool = Path.home() / "src" / "kartka" / "tools" / "errors" / "run.sh"
    count = ("git", "-C", "{repo_dir}", "rev-list", "--count", "{commit}")  # versionCode = the commit count
    return Source(
        "kartka", "kuhyx/kartka", "kartka", state_base() / "kartka-errors" / "state.json",
        (str(tool), "resolve", "{signature}"), count,
    )  # fmt: skip


def _argv(raw: object) -> tuple[str, ...] | None:
    if raw is None:
        return ()
    ok = isinstance(raw, list) and all(isinstance(part, str) for part in raw)
    return tuple(_home(part) for part in raw) if ok and isinstance(raw, list) else None


def _entry(raw: object) -> Source | None:
    """Return the Source an `error_sources` entry describes, None when it is not one (see the contract)."""
    if not isinstance(raw, dict):
        return None
    fields: dict[str, Any] = raw
    app, repo, kind, path = (fields.get(name) for name in ("app", "repo", "adapter", "path"))
    resolve, build = _argv(fields.get("resolve")), _argv(fields.get("build"))
    if not all(isinstance(v, str) and v for v in (app, repo, path)) or kind not in ADAPTERS:
        return None
    if resolve is None or build is None:
        return None
    return Source(str(app), str(repo), str(kind), Path(_home(str(path))), resolve, build)


def configured() -> list[Source]:
    """Return the sources: settings.json `error_sources` (default: kartka), then every file in app-errors/."""
    raw = setting.read().get(KEY)
    listed = [_kartka_default()] if not isinstance(raw, list) else [s for e in raw if (s := _entry(e))]
    known = {source.path for source in listed}
    folder = state_base() / "app-errors"
    files = sorted(folder.glob("*.json")) if folder.is_dir() else []
    return listed + [Source(f.stem, "", "contract", f) for f in files if f not in known]


def read(source: Source) -> list[AppError]:
    """Return the source's records; SourceError when its file is missing or in the wrong shape."""
    if source.adapter == "kartka":
        return adapters.kartka(source.path, source.app, source.repo)
    return adapters.contract(source.path)


def records(found: Iterable[Source]) -> list[tuple[Source, AppError]]:
    """Return (source, record) for every readable source; a broken one is logged and skipped."""
    out: list[tuple[Source, AppError]] = []
    for source in found:
        try:
            out += [(source, record) for record in read(source)]
        except SourceError as exc:
            log.warning("error source %s skipped: %s", source.app, exc)
    return out


def _run(template: Sequence[str], **fields: str) -> subprocess.CompletedProcess[str] | None:
    """Run an argv hook (no shell); None when the tool is missing or runs too long."""
    try:
        argv = [part.format(**fields) for part in template]
        return subprocess.run(  # noqa: S603 - argv from kuhy's own settings, never a shell
            argv, capture_output=True, text=True, timeout=HOOK_TIMEOUT, check=False
        )
    except (OSError, subprocess.SubprocessError, LookupError, ValueError) as exc:
        log.warning("hook %s failed: %s", template[0], exc)  # a bad placeholder is a KeyError or ValueError
        return None


def resolve(source: Source, signature: str) -> bool:
    """Close the error at its origin; True when there is nothing to call or the hook exits 0."""
    if not source.resolve:
        return True
    done = _run(source.resolve, signature=signature)
    return done is not None and done.returncode == 0


def build_of(source: Source, repo_dir: Path, commit: str) -> int:
    """Return the build number the hook prints for `commit`; 0 when unknown (no hook, failure, no number)."""
    if not source.build:
        return 0
    done = _run(source.build, repo_dir=str(repo_dir), commit=commit)
    out = done.stdout.strip() if done is not None and done.returncode == 0 else ""
    return int(out) if out.isdigit() else 0
