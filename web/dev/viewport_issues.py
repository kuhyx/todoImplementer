"""Viewport step of the issues page (served at /issues#task=<id>): table, then a phase filter and a header sort.

Run through viewport_check.py (--steps issues --url 'http://127.0.0.1:PORT/issues#task=<id>').
Reads only; the page has no mutating control.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from cdp_driver import Cdp, goto, probe

LETTERS = "/[A-Za-z]{3,}/.test(el.textContent)"


def step_issues(cdp: Cdp, url: str, out: Path, tag: str) -> dict[str, Any]:
    goto(cdp, url, 2.0)
    cdp.shot(out / f"{tag}-issues.png")
    ms = cdp.js(
        "(async () => { const t = performance.now(); const id = new URLSearchParams(location.hash.slice(1)).get('task');"
        " await (await fetch(`/api/task/${id}/issues`, { cache: 'no-store' })).text(); return performance.now() - t; })()"
    )
    # One full redraw of toolbar and table (a chip click renders synchronously).
    render_ms = cdp.js(
        "(() => { const t = performance.now(); document.querySelector('.states [data-state=all]').click();"
        " return performance.now() - t; })()"
    )
    result = probe(cdp, [".toolbar", "input[type=search]", "th[data-key=ts] button", "a.raw-link", "a.back"])
    rows = cdp.js("document.querySelectorAll('tbody tr').length")
    words = cdp.js(
        "(() => { const head = document.querySelector('thead'); const states = document.querySelector('.states');"
        f" return [head, states].filter((el) => {LETTERS}).length; }})()"
    )
    clipped = cdp.js(
        "[...document.querySelectorAll('.col-symptom .prose, .col-action .prose')]"
        ".filter((el) => el.scrollWidth > el.clientWidth + 1).length"
    )
    if not rows:
        result["problems"].append("no rows")
    if words:
        result["problems"].append("table header or state chips carry words")
    if clipped:
        result["problems"].append(f"{clipped} symptom/action cells clip their text")
    cdp.js("document.querySelector('[data-key=phase] .value-chip').click()")
    cdp.js("document.querySelector('th[data-key=child] button')?.click()")
    time.sleep(0.4)
    cdp.shot(out / f"{tag}-issues-filtered.png")
    filtered = cdp.js("document.querySelectorAll('tbody tr').length")
    hash_ = str(cdp.js("location.hash"))
    if "phase=" not in hash_:
        result["problems"].append(f"phase filter not in the hash: {hash_}")
    if not 0 < filtered < rows:
        result["problems"].append(f"phase filter kept {filtered} of {rows} rows")
    return {
        **result,
        "rows": rows,
        "filtered": filtered,
        "fetch_ms": round(float(ms), 1),
        "render_ms": round(float(render_ms), 1),
        "hash": hash_,
    }
