"""R1 `questions` step: the question flow shows ONLY ONE big question, its box and OK, and every control stays on screen.

Asserts, per viewport, on the dev mock's real-shaped ask cards (web/src/test/fixture-ask.ts):
 - the drawer shows no tab strip (only a "Details" toggle), the answer box is focused, prefilled and inside the viewport;
 - exactly one question card, no Send-to-Claude box; Back and OK are inside the viewport and topmost; the progress
   reads "1 / 5" and moves to "2 / 5" on OK;
 - "All questions" lists every box and keeps "Accept all" inside the viewport;
 - 9 questions step to "9 / 9" with OK reachable; the free-text question still has its box.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cdp_driver import Cdp, goto, probe

ASK = "f1a1b2c3-0"
ASK9 = "f2a1b2c3-0"
FREE = "f3a1b2c3-0"
URL = "http://127.0.0.1:4399/#task="

METRICS = """(() => {
  const q = (s) => document.querySelector(s);
  const vis = (e) => !!e && e.getBoundingClientRect().width > 0 && getComputedStyle(e).display !== 'none';
  const box = q('textarea[name]');
  const r = box ? box.getBoundingClientRect() : null;
  const scroll = q('.drawer-scroll');
  const toggle = q('[data-details]');
  return {
    label: (q('.ask-page') || {}).innerText || '',
    focused: !!box && document.activeElement === box,
    boxInside: !!r && r.width > 0 && r.bottom <= innerHeight && r.right <= innerWidth,
    boxChars: box ? box.value.length : 0,
    boxes: document.querySelectorAll('.ask textarea').length,
    cards: document.querySelectorAll('.ask .ask-card').length,
    sendBox: vis(q('.drawer-send')),
    titlepx: parseFloat(getComputedStyle(q('.ask-title') || document.body).fontSize),
    tabsVisible: vis(q('.dtabs')),
    toggleVisible: vis(toggle),
    scrollOver: scroll ? scroll.scrollHeight - scroll.clientHeight : null,
    accept: (q('[data-ask=accept]') || {}).innerText || '',
    badText: /\\[object Object\\]|\\bundefined\\b|\\bNaN\\b/.test(document.body.innerText),
  };
})()"""


def read(cdp: Cdp) -> dict[str, Any]:
    return dict(cdp.js(METRICS))


def click(cdp: Cdp, selector: str) -> None:
    cdp.js(f"document.querySelector({selector!r}).click()")


def common(m: dict[str, Any], where: str) -> list[str]:
    problems = []
    if m["tabsVisible"] or not m["toggleVisible"]:
        problems.append(
            f"{where}: tabs {m['tabsVisible']} / Details toggle {m['toggleVisible']} (want only the toggle)"
        )
    if m["sendBox"]:
        problems.append(f"{where}: the Send to Claude box is visible")
    if m["scrollOver"] is None or m["scrollOver"] > 1:
        problems.append(f"{where}: drawer-scroll scrolls by {m['scrollOver']}")
    if m["badText"]:
        problems.append(f"{where}: [object Object]/undefined/NaN in text")
    return problems


def step_one(cdp: Cdp, out: Path, tag: str) -> list[str]:
    goto(cdp, f"{URL}{ASK}", 2.4)
    cdp.shot(out / f"{tag}-questions.png")
    m = read(cdp)
    problems = common(m, "one by one")
    if m["label"].strip() != "1 / 5" or not m["focused"] or m["boxChars"] == 0 or not m["boxInside"]:
        problems.append(
            f"first question: label {m['label']!r} focused {m['focused']} chars {m['boxChars']} inside {m['boxInside']}"
        )
    if m["cards"] != 1 or m["titlepx"] < 22:
        problems.append(
            f"first question: {m['cards']} cards, title {m['titlepx']}px (want 1 card, a big title)"
        )
    problems += probe(cdp, ["textarea[name=Q1]", "[data-ask=back]", "[data-ask=accept]"])["problems"]
    click(cdp, "[data-ask=accept]")
    if read(cdp)["label"].strip() != "2 / 5":
        problems.append("Accept must move to '2 / 5'")
    click(cdp, "[data-mode=all]")
    cdp.shot(out / f"{tag}-questions-all.png")
    m = read(cdp)
    problems += common(m, "all questions")
    if m["boxes"] != 5:
        problems.append(f"All questions must list 5 boxes, found {m['boxes']}")
    cdp.js("document.querySelector('[data-ask=accept-all]').scrollIntoView()")
    problems += probe(cdp, ["[data-ask=accept-all]"])["problems"]
    return problems


def step_nine(cdp: Cdp, out: Path, tag: str) -> list[str]:
    goto(cdp, f"{URL}{ASK9}", 2.4)
    for _ in range(8):
        click(cdp, "[data-ask=accept]")
    cdp.shot(out / f"{tag}-questions9.png")
    m = read(cdp)
    problems = common(m, "9 questions")
    if m["label"].strip() != "9 / 9" or m["accept"].strip() != "OK":
        problems.append(f"last of 9: label {m['label']!r} button {m['accept']!r}")
    problems += probe(cdp, ["textarea[name=Q9]", "[data-ask=accept]"])["problems"]
    return problems


def step_free(cdp: Cdp, out: Path, tag: str) -> list[str]:
    goto(cdp, f"{URL}{FREE}", 2.4)
    cdp.shot(out / f"{tag}-questions-free.png")
    box = cdp.js(
        "(() => { const t = document.querySelector('textarea[name=ask-send]'); return !!t && t.value === '' && t.offsetParent !== null; })()"
    )
    problems = [] if box else ["free-text question needs an empty textarea"]
    problems += probe(cdp, ["[data-action=send]", "textarea[name=ask-send]"])["problems"]
    return problems


def step_questions(cdp: Cdp, url: str, out: Path, tag: str) -> dict[str, Any]:
    del url  # the ask cards live only on the dev mock at 4399
    problems = step_one(cdp, out, tag) + step_nine(cdp, out, tag) + step_free(cdp, out, tag)
    return {"problems": problems}
