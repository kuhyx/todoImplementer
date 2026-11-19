"""The pages a Needs-you ask tells kuhy to open: absolute links, and routes with no host (T2135).

"Open /logo-lab" is no ask kuhy can follow: he needs the full URL on the card, or better the content in the
task itself (DOCS-asks.md). `scan` reads the ask text and the run's last reply, deterministically:

- an absolute http(s) URL in the ask is a link;
- a route named after a cue verb (`open /logo-lab`, `preview them on /logo-lab`) is resolved against the first
  own-host URL (loopback or `*.duckdns.org`) in the ask or reply, else it is `bare`: not concrete;
- file paths (`/home/...`, `/run/...`, `~/src/...`, `scripts/x.sh`) are never routes.

Nothing records a per-repo base URL, so an unresolved route is flagged and the runner sends the session back
(`runner/linknudge.py`) instead of guessing a host.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

MAX_LINKS = 5
OWN_SUFFIX = ".duckdns.org"
LOOPBACK = ("127.0.0.1", "localhost", "::1")
# System directories (and the server's own /api): a path under one is a file or an endpoint, not a page.
SYSTEM_ROOTS = frozenset(
    {"api", "bin", "boot", "dev", "etc", "home", "lib", "lib64", "mnt", "opt", "proc", "root", "run"}
    | {"sbin", "srv", "sys", "tmp", "usr", "var"}
)
FILE_EXT = frozenset(
    {"py", "pyc", "ts", "tsx", "js", "mjs", "cjs", "md", "json", "sh", "yml", "yaml", "toml", "txt", "log"}
    | {"lock", "cfg", "ini", "conf", "dart", "go", "rs", "c", "h", "cpp", "png", "jpg", "zip"}
)
URL = re.compile(r"https?://[^\s<>\"'`]+")
CUE = r"\b(?:open|visit|preview|see|view|browse|go to|navigate to|look at|check|load|try)\b"
ROUTE = re.compile(
    rf"{CUE}(?:\s+[\w'-]+){{0,3}}?\s+[`'\"(]*(/[A-Za-z][\w.~%-]*(?:/[\w.~%-]*)*)", re.IGNORECASE
)
TRAIL = ".,;:!?)]}"


@dataclass(frozen=True)
class Found:
    """`urls`: absolute links to show; `bare`: routes that name a page but have no host to open on."""

    urls: tuple[str, ...] = ()
    bare: tuple[str, ...] = ()


def _urls(text: str) -> list[str]:
    return [u.rstrip(TRAIL) for u in URL.findall(text)]


def _routes(text: str) -> list[str]:
    """Return the routes a cue verb points at; file paths are left out."""
    out: list[str] = []
    for found in ROUTE.finditer(text):
        path = found.group(1).rstrip(TRAIL)
        first = path[1:].split("/", 1)[0]
        last = path.rsplit("/", 1)[-1]
        ext = last.rsplit(".", 1)[-1].lower() if "." in last else ""
        if first.lower() not in SYSTEM_ROOTS and ext not in FILE_EXT and path not in out:
            out.append(path)
    return out


def _origin(urls: list[str]) -> str | None:
    """Return `scheme://host[:port]` of the first loopback or own-domain URL, else None."""
    for url in urls:
        parts = urlsplit(url)
        host = parts.hostname or ""
        if host in LOOPBACK or host.endswith(OWN_SUFFIX):
            return f"{parts.scheme}://{parts.netloc}"
    return None


def scan(ask: str, reply: str = "") -> Found:
    """Return the links of the ask and the routes of the ask or reply that have no host to open them on."""
    mine = _urls(ask)
    origin = _origin(mine + _urls(reply))
    urls = list(dict.fromkeys(mine))
    bare: list[str] = []
    for route in dict.fromkeys(_routes(ask) + _routes(reply)):
        if origin is None:
            bare.append(route)
        elif (full := origin + route) not in urls:
            urls.append(full)
    return Found(tuple(urls[:MAX_LINKS]), tuple(bare))
