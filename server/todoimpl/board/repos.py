"""Where a note's repo is checked out: the one rule the board's repo check and the runner's repo_dir share.

Order (T2079, DOCS-landing.md "Where a repo lives"): the override file, `<src>/<name>`, then a cached map from
origin remote to checkout built over a few likely roots, else `<src>/<name>` (which Start then clones).
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

OWNER = "kuhyx"  # this owner (or a bare name) runs from `<src>/<name>` whatever its origin
REFRESH_S = 600.0  # the origin map is rebuilt at most this often, and on any miss
_clock = time.monotonic
_MAPS: dict[tuple[Path, tuple[Path, ...], tuple[Path, ...]], tuple[float, dict[str, Path]]] = {}
_ORIGIN = re.compile(r'\[remote "origin"\][^\[]*?^\s*url\s*=\s*(\S+)', re.MULTILINE)
_SLUG = re.compile(r"[/:]([^/:\s]+)/([^/\s]+?)(?:\.git)?/?$")
# A hosted remote only (https/ssh URL or scp-like `git@host:`): a local bare path names no owner.
_HOSTED = re.compile(r"(?:[a-z+]+://(?:[^@/\s]+@)?[^/\s]+/|[^@/\s]+@[^:/\s]+:)([^/\s]+)/([^/\s]+?)/?$")
_CANON: dict[tuple[object, ...], tuple[float, str]] = {}
_ENV = ("TODOIMPL_SRC", "TODOIMPL_REPO_ROOTS", "TODOIMPL_REPO_PATHS")  # what repo_path reads


def _origin_url(clone: Path) -> str | None:
    """Return the clone's origin URL without a `.git` suffix, or None when it has none."""
    try:
        config = (clone / ".git" / "config").read_text(encoding="utf-8")
    except OSError, UnicodeDecodeError:
        return None
    found = _ORIGIN.search(config)
    return None if found is None else found.group(1).removesuffix(".git")


def _slug(clone: Path) -> str | None:
    """Return the clone's origin as lower-case `owner/name` (https or ssh), else None."""
    url = _origin_url(clone)
    found = None if url is None else _SLUG.search(url)
    return None if found is None else f"{found.group(1)}/{found.group(2)}".lower()


def _origin_matches(clone: Path, repo: str) -> bool:
    """Say whether the clone's origin is `repo` (`owner/name`, case-blind)."""
    return _slug(clone) == repo.lower()


def _roots(base: Path) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    """Return (checkouts that may themselves be a repo, directories whose children may be repos).

    $TODOIMPL_REPO_ROOTS (os.pathsep list) replaces the defaults; the src root is always searched.
    """
    given = os.environ.get("TODOIMPL_REPO_ROOTS")
    if given is not None:
        roots = tuple(Path(part) for part in given.split(os.pathsep) if part)
        return roots, (base, *roots)
    home = Path.home()
    return (home / ".claude", home / "praca_magisterska"), (
        base,
        base / "testsAndMisc",
        home / "praca_magisterska",
    )


def _build(base: Path) -> dict[str, Path]:
    """Scan the roots, one level deep, for git checkouts; the first checkout of an origin wins."""
    singles, containers = _roots(base)
    found: dict[str, Path] = {}
    for container in containers:
        try:
            children = sorted(p for p in container.iterdir() if p.is_dir())
        except OSError:
            continue
        for child in children:
            if (slug := _slug(child)) is not None:
                found.setdefault(slug, child)
    for single in singles:
        if (slug := _slug(single)) is not None:
            found.setdefault(slug, single)
    return found


def _lookup(base: Path, repo: str) -> Path | None:
    """Return the checkout of `owner/name` from the cached map; a miss or a stale map rebuilds it first."""
    key = (base, *_roots(base))
    now = _clock()
    cached = _MAPS.get(key)
    if cached is not None and now - cached[0] < REFRESH_S:
        hit = cached[1].get(repo.lower())
        if hit is not None and (hit / ".git").exists():
            return hit
    found = _build(base)
    _MAPS[key] = (now, found)
    return found.get(repo.lower())


def _pinned(repo: str) -> Path | None:
    """Return the directory the override file maps `repo` to (`{"owner/name": "/abs"}`), if it is one."""
    given = os.environ.get("TODOIMPL_REPO_PATHS")
    path = Path(given) if given else Path.home() / ".config" / "todoImplementer" / "repo-paths.json"
    try:
        table = json.loads(path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None
    where = table.get(repo) if isinstance(table, dict) else None
    pinned = Path(where).expanduser() if isinstance(where, str) else None
    return pinned if pinned is not None and pinned.is_dir() else None


def repo_path(repo: str, src_root: Path | None = None) -> Path:
    """Return the checkout of `owner/name` (a bare name is `kuhyx/<name>`).

    Order: the override file, `<src root>/<name>` (unless its origin is some other repo, T1839), then the
    checkout whose origin is that repo in ~/src/*, ~/.claude, ~/praca_magisterska, ~/src/testsAndMisc/*
    (T2079). The root defaults to $TODOIMPL_SRC, ~/src. No checkout at all still yields `<root>/<name>`,
    where Start clones.
    """
    base = src_root or Path(os.environ.get("TODOIMPL_SRC") or Path.home() / "src")
    direct = base / repo.rpartition("/")[2]
    full = repo if "/" in repo else f"{OWNER}/{repo}"
    if (pinned := _pinned(full)) is not None:
        return pinned
    if direct.exists() and ("/" not in repo or _origin_url(direct) is None or _origin_matches(direct, repo)):
        return direct
    return _lookup(base, full) or direct


def _origin_name(clone: Path) -> str | None:
    """Return the clone's origin as `owner/name` in the URL's own case; a local-path origin has none."""
    url = _origin_url(clone)
    found = None if url is None else _HOSTED.match(url)
    return None if found is None else f"{found.group(1)}/{found.group(2)}"


def canonical(repo: str, src_root: Path | None = None) -> str:
    """Return the real `owner/name` of a repo: the origin of the checkout it runs in (T2272).

    A name guessed from a folder (`kuhyx/cleanup-plate` for ~/src/cleanup-plate, whose origin is
    `Sepci0/cleanup-plate`) and every case spelling collapse onto that origin. A repo with no checkout, or
    whose checkout has no hosted origin, keeps its name. Answers are kept for REFRESH_S.
    """
    key = (repo, src_root, Path.home(), *(os.environ.get(name) for name in _ENV))
    now = _clock()
    cached = _CANON.get(key)
    if cached is not None and now - cached[0] < REFRESH_S:
        return cached[1]
    path = repo_path(repo, src_root)
    real = (_origin_name(path) if is_clone_of(path, repo) else None) or repo
    _CANON[key] = (now, real)
    return real


def is_clone_of(path: Path, repo: str) -> bool:
    """Say whether `path` is a git clone that `repo` may run in.

    A kuhyx/ repo or a bare name needs only the clone (T202); a foreign owner needs its origin to be that
    `owner/name`, so a same-named clone of another repo never takes its place (T2000).
    """
    owner = repo.rpartition("/")[0]
    return (path / ".git").exists() and (owner in ("", OWNER) or _origin_matches(path, repo))
