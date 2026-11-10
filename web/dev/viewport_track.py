"""R1 step for the umbrella tracking view: the run page, an expanded row, and the link on the board card."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cdp_driver import Cdp, goto, probe

UMBRELLA = "2d0704cd-0"
OPEN_ROW = "2d0704cd-2"
TOUCH = 44  # CSS px; checked on phones only (the 4K layout is zoomed 2x)

SMALL = """(() => [...document.querySelectorAll('.t-kid-main, .t-link, .track-link, [data-close]')]
  .map(e => [e.className, e.getBoundingClientRect()])
  .filter(([, r]) => r.width > 0 && (r.width < %d || r.height < %d))
  .map(([c, r]) => c + ' ' + Math.round(r.width) + 'x' + Math.round(r.height)))()"""


def step_track(cdp: Cdp, url: str, out: Path, tag: str) -> dict[str, Any]:
    """Load the run at `#umbrella=<id>`, open one row, then look at the card link on the board."""
    goto(cdp, f"{url}#umbrella={UMBRELLA}", 2.4)
    cdp.shot(out / f"{tag}-track.png")
    selectors = [".t-head", ".t-bar", ".t-stats", ".t-strip", ".t-kid", ".t-kid-main", "[data-close]"]
    result = probe(cdp, selectors)
    problems = list(result["problems"])
    if cdp.size is not None and cdp.size[0] < 720:
        small = cdp.js(SMALL % (TOUCH, TOUCH))
        problems += [f"touch target under {TOUCH}px: {s}" for s in small]
    cdp.js(f"document.querySelector('[data-id=\"{OPEN_ROW}\"] .t-kid-main').click()")
    cdp.js("document.querySelector('.t-group-main')?.click()")
    cdp.shot(out / f"{tag}-track-open.png")
    detail = cdp.js(f"document.querySelector('[data-id=\"{OPEN_ROW}\"] .t-detail')?.innerText ?? null")
    if not detail:
        problems.append("the expanded row shows no issue")
    goto(cdp, f"{url}#col=running", 2.4)
    cdp.shot(out / f"{tag}-track-card.png")
    problems += probe(cdp, ["a.card-track"])["problems"]
    return {"problems": problems, "detail": detail}
