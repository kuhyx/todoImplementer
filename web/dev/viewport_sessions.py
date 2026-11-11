"""Viewport steps of the sessions page (served at /sessions): list, then expanded row + selection + sort.

Run through viewport_check.py (--steps sessions,sessions-detail --url http://127.0.0.1:PORT/sessions).
Reads only: it opens, expands, selects and sorts; it never clicks an action button.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from cdp_driver import Cdp, goto, probe

LETTERS = "/[A-Za-z]{3,}/.test(el.textContent)"


def step_sessions(cdp: Cdp, url: str, out: Path, tag: str) -> dict[str, Any]:
    goto(cdp, url, 2.5)
    cdp.shot(out / f"{tag}-sessions.png")
    result = probe(
        cdp,
        [".toolbar", "input[type=search]", ".main", "th[data-key=group] button", "tr[data-id] .title-btn"],
    )
    rows = cdp.js("document.querySelectorAll('tr[data-id]').length")
    words = cdp.js(
        "(() => { const bar = document.querySelector('.toolbar').cloneNode(true);"
        " bar.querySelector('select').remove();"
        f" const head = document.querySelector('thead'); return [bar, head].filter((el) => {LETTERS}).length; }})()"
    )
    phone = cdp.size is not None and cdp.size[0] <= 700
    terminal = cdp.js(
        "(() => { const b = document.querySelector('tr[data-id] .desktop-only');"
        " return b ? getComputedStyle(b).display : 'missing'; })()"
    )
    copy = cdp.js("document.querySelector('tr[data-id] button[aria-label^=\"copy\"]')?.offsetParent !== null")
    if not rows:
        result["problems"].append("no rows")
    if words:
        result["problems"].append("toolbar or header carries words")
    if phone and terminal != "none":
        result["problems"].append(f"terminal button visible on a phone: {terminal}")
    if not phone and terminal == "none":
        result["problems"].append("terminal button hidden on the desktop")
    if not copy:
        result["problems"].append("copy button not visible")
    return {**result, "rows": rows, "terminal": terminal}


def step_detail(cdp: Cdp, url: str, out: Path, tag: str) -> dict[str, Any]:
    goto(cdp, url, 2.5)
    cdp.js("document.querySelector('tr[data-id] .title-btn').click()")
    time.sleep(0.3)
    cdp.js(
        "document.querySelectorAll('tr[data-id] input[type=checkbox]').forEach((box, i) => i < 2 && box.click())"
    )
    time.sleep(0.3)
    cdp.js("document.querySelector('th[data-key=age] button').click()")
    time.sleep(0.4)
    cdp.shot(out / f"{tag}-sessions-detail.png")
    # The detail of a long reply is taller than a phone: it scrolls inside .main, so it is only checked to exist.
    result = probe(cdp, [".bulk-bar", "th[data-key=age][aria-sort=ascending]"])
    if not cdp.js("document.querySelector('.detail-row .detail') !== null"):
        result["problems"].append("expanded row has no detail")
    sorted_hash = cdp.js("location.hash")
    if "t.s.sort=age" not in str(sorted_hash):
        result["problems"].append(f"sort not in the hash: {sorted_hash}")
    return {**result, "hash": sorted_hash}
