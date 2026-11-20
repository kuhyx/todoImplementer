"""web/dist file serving; every served .html gets the CSRF token and build id injected as meta tags."""

from __future__ import annotations

import html
import mimetypes
import re
from pathlib import Path
from urllib.parse import unquote

from .reply import Reply

IMMUTABLE = "public, max-age=31536000, immutable"


class StaticSite:
    """Serve files strictly inside root; unknown or escaping paths give None."""

    def __init__(self, root: Path, token: str, build: str, build_name: str | None = None) -> None:
        """Serve root; every .html page is stamped with token, build and its name (the build when none)."""
        self.root = root.resolve()
        self.token = token
        self.build = build
        self.build_name = build_name or build

    def _index(self, page: str, *, local: bool) -> str:
        """Stamp the csrf token and build id: fill a shipped placeholder tag in place, else insert one.

        A local request also gets the `todoimpl-local` flag; a public one has any flag the page ships removed.
        """
        missing = ""
        stamps = [
            ("todoimpl-csrf", self.token),
            ("todoimpl-build", self.build),
            ("todoimpl-build-name", self.build_name),
        ]
        if local:
            stamps.append(("todoimpl-local", "1"))
        else:
            page = re.sub(r'<meta\s+name="todoimpl-local"[^>]*>', "", page)
        for name, value in stamps:
            tag = f'<meta name="{name}" content="{html.escape(value)}">'
            found = re.search(rf'<meta\s+name="{name}"[^>]*>', page)
            if found:
                page = page[: found.start()] + tag + page[found.end() :]
            else:
                missing += tag
        if not missing:
            return page
        if "</head>" in page:
            return page.replace("</head>", f"{missing}</head>", 1)
        return missing + page

    def serve(self, url_path: str, *, local: bool = False) -> Reply | None:
        """Return the file for url_path, or None when it is missing or outside the root.

        `local` says the request came from the PC (loopback Host); only then does a page carry the local flag.
        """
        rel = unquote(url_path).lstrip("/") or "index.html"
        if "\x00" in rel:
            return None
        target = (self.root / rel).resolve()
        if target.is_dir():  # Astro emits sub-pages as <page>/index.html
            target /= "index.html"
        if not target.is_relative_to(self.root) or not target.is_file():
            return None
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/"):
            ctype += "; charset=utf-8"
        if target.suffix == ".html":
            body = self._index(target.read_text(encoding="utf-8"), local=local).encode()
            return Reply(200, body, ctype, (("Cache-Control", "no-store"),))
        cache = IMMUTABLE if rel.startswith("_astro/") else "no-cache"
        return Reply(200, target.read_bytes(), ctype, (("Cache-Control", cache),))
