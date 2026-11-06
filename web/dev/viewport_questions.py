"""R1 `questions` step: ONE centered question, its auto-growing answer and two icons, every control on screen.

Asserts, per viewport, on the dev mock's real-shaped ask cards (web/src/test/fixture-ask.ts):
 - the bar holds icon-only Details, All-questions and Close buttons; no tab strip, no counter, no helper text;
 - the task title is whole (not clamped); title, body and answer share one font size and line height;
 - the question block is centered in the drawer (horizontally always, vertically when it fits), the answer is not
   taller than its text, and Back (left) / OK (right) are inside the viewport and topmost without scrolling;
 - the switch icon lists every box in "all" view and its twin returns to one question; OK moves to the next question;
 - 9 questions step to Q9 with OK reachable; the free-text question still has its box.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cdp_driver import Cdp, goto, probe

ASK = "f1a1b2c3-0"
ASK9 = "f2a1b2c3-0"
FREE = "f3a1b2c3-0"
URL = "http://127.0.0.1:4399/#task="
TOL = 2.5  # px of centering tolerance

METRICS = """(() => {
  const q = (s) => document.querySelector(s);
  const vis = (e) => !!e && e.getBoundingClientRect().width > 0 && getComputedStyle(e).display !== 'none';
  const rect = (e) => { const b = e.getBoundingClientRect(); return {l: b.left, r: b.right, t: b.top, b: b.bottom}; };
  const font = (e) => { const s = getComputedStyle(e); return s.fontSize + '/' + s.lineHeight + '/' + s.fontFamily; };
  const box = q('textarea[name]');
  const r = box ? rect(box) : null;
  const step = q('.ask-step');
  const center = q('.ask-center');
  const drawer = q('.drawer');
  const title = q('.drawer-title');
  const bar = [...document.querySelectorAll('.drawer-bar button')].filter(vis);
  const out = {
    boxInside: !!r && r.r - r.l > 0 && r.b <= innerHeight && r.r <= innerWidth,
    boxChars: box ? box.value.length : 0,
    boxGrown: box ? box.scrollHeight <= box.clientHeight + 1 : false,
    focused: !!box && document.activeElement === box,
    cards: document.querySelectorAll('.ask .ask-card').length,
    boxes: document.querySelectorAll('.ask textarea').length,
    qtitle: (q('.ask-title') || {}).innerText || '',
    sendBox: vis(q('.drawer-send')),
    tabsVisible: vis(q('.dtabs')),
    counter: !!q('.ask-page') || /\\d+ \\/ \\d+/.test((q('.ask') || {innerText: ''}).innerText),
    helper: /Your answer|Recommended|One by one/.test(document.body.innerText),
    barNames: bar.map((b) => (b.getAttribute('aria-label') || '') + '|' + (b.title || '') + '|' + b.innerText.trim()),
    titleWhole: title ? title.scrollHeight <= title.clientHeight + 1 && getComputedStyle(title).textOverflow === 'clip' : false,
    titleLines: title ? Math.round(title.getBoundingClientRect().height / parseFloat(getComputedStyle(title).lineHeight)) : 0,
    scrollOver: q('.drawer-scroll') ? q('.drawer-scroll').scrollHeight - q('.drawer-scroll').clientHeight : null,
    stepScrolls: step ? step.scrollHeight > step.clientHeight + 1 : false,
    barHeight: q('.drawer-bar') ? q('.drawer-bar').getBoundingClientRect().height : 0,
    badText: /\\[object Object\\]|\\bundefined\\b|\\bNaN\\b/.test(document.body.innerText),
  };
  if (center && step && drawer) {
    const c = rect(center), s = rect(step), d = rect(drawer);
    out.dx = (c.l - d.l) - (d.r - c.r);
    out.dy = (c.t - s.t) - (s.b - c.b);
    out.measure = Math.round(c.r - c.l);
  }
  const bodyP = q('.ask-body p');
  if (box && q('.ask-title') && bodyP) out.fonts = [font(q('.ask-title')), font(bodyP), font(box)];
  const back = q('[data-ask=back]'), ok = q('[data-ask=accept]');
  if (back && ok) { const mid = (rect(center).l + rect(center).r) / 2; out.okRight = rect(ok).l > rect(back).r && rect(back).l < mid && rect(ok).r > mid; }
  return out;
})()"""


def read(cdp: Cdp) -> dict[str, Any]:
    return dict(cdp.js(METRICS))


def click(cdp: Cdp, selector: str) -> None:
    cdp.js(f"document.querySelector({selector!r}).click()")


def common(m: dict[str, Any], where: str) -> list[str]:
    problems = []
    if m["tabsVisible"]:
        problems.append(f"{where}: the tab strip is visible")
    if m["sendBox"] or m["counter"] or m["helper"]:
        problems.append(
            f"{where}: send box {m['sendBox']} / counter {m['counter']} / helper text {m['helper']}"
        )
    names = m["barNames"]
    if len(names) != 3 or any(
        not n.startswith(
            (
                "Details|Details|",
                "All questions|All questions|",
                "One question at a time|One question at a time|",
                "Close|Close|",
            )
        )
        or not n.endswith("|")
        for n in names
    ):
        problems.append(f"{where}: bar buttons are not three icon-only named buttons: {names}")
    if not m["titleWhole"]:
        problems.append(f"{where}: the task title is clamped or clipped")
    if m["scrollOver"] is None or m["scrollOver"] > 1:
        problems.append(f"{where}: drawer-scroll scrolls by {m['scrollOver']}")
    if m["badText"]:
        problems.append(f"{where}: [object Object]/undefined/NaN in text")
    return problems


def one_question(m: dict[str, Any], where: str) -> list[str]:
    problems = []
    if not m["focused"] or m["boxChars"] == 0 or not m["boxInside"] or not m["boxGrown"]:
        problems.append(
            f"{where}: focused {m['focused']} chars {m['boxChars']} inside {m['boxInside']} grown {m['boxGrown']}"
        )
    if m["cards"] != 1 or not m.get("okRight"):
        problems.append(f"{where}: {m['cards']} cards, OK right of Back {m.get('okRight')}")
    if abs(m.get("dx", 99)) > TOL:
        problems.append(f"{where}: not centered horizontally (dx {m.get('dx')})")
    if not m["stepScrolls"] and abs(m.get("dy", 99)) > TOL:
        problems.append(f"{where}: not centered vertically (dy {m.get('dy')})")
    if len(set(m.get("fonts", [1, 2]))) != 1:
        problems.append(f"{where}: title/body/answer typography differs: {m.get('fonts')}")
    return problems


def step_one(cdp: Cdp, out: Path, tag: str) -> list[str]:
    goto(cdp, f"{URL}{ASK}", 2.4)
    cdp.shot(out / f"{tag}-questions.png")
    m = read(cdp)
    problems = common(m, "one question") + one_question(m, "first question")
    if not m["qtitle"].startswith("Q1"):
        problems.append(f"first question title {m['qtitle']!r}")
    problems += probe(
        cdp, ["textarea[name=Q1]", "[data-ask=back]", "[data-ask=accept]", ".drawer-bar button"]
    )["problems"]
    click(cdp, "[data-ask=accept]")
    if not read(cdp)["qtitle"].startswith("Q2"):
        problems.append("OK must move to Q2")
    click(cdp, "[data-ask-mode]")
    cdp.shot(out / f"{tag}-questions-all.png")
    m = read(cdp)
    problems += common(m, "all questions")
    if m["boxes"] != 5:
        problems.append(f"All questions must list 5 boxes, found {m['boxes']}")
    cdp.js("document.querySelector('[data-ask=accept-all]').scrollIntoView()")
    problems += probe(cdp, ["[data-ask=accept-all]"])["problems"]
    click(cdp, "[data-ask-mode]")
    if read(cdp)["boxes"] != 1:
        problems.append("the switch must return to one question")
    return problems


def step_nine(cdp: Cdp, out: Path, tag: str) -> list[str]:
    goto(cdp, f"{URL}{ASK9}", 2.4)
    for _ in range(8):
        click(cdp, "[data-ask=accept]")
    cdp.shot(out / f"{tag}-questions9.png")
    m = read(cdp)
    problems = common(m, "9 questions") + one_question(m, "last of 9")
    if not m["qtitle"].startswith("Q9"):
        problems.append(f"last of 9: title {m['qtitle']!r}")
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
