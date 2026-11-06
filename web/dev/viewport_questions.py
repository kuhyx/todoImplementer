"""R1 `questions` step: the full-browser answer view with fixed slots (title, question, answer, Back/OK).

Asserts, per viewport, on the dev mock's real-shaped ask cards (web/src/test/fixture-ask.ts: a short and a very long
question body, a multi-line task title, a long recommendation):
 - the drawer covers the whole browser and the content column is centered on it; Details opened gives the side panel back;
 - the bar holds icon-only Details, All-questions (not for a plain Claude question) and Close buttons; no tab strip,
   no counter, no helper text; the task title is whole and its slot is three lines at most;
 - KEY: the top y of the task title, question title, answer box, Back and OK is identical (+-1px) for EVERY question of
   the 5-question card, the 9-question card and the plain Claude question, whatever the text length;
 - title slot, question slot, answer slot and Back/OK do not overlap and sit inside the viewport;
 - the switch icon lists every box in "all" view and its twin returns to one question; OK moves to the next question.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, NamedTuple

from cdp_driver import Cdp, goto, probe

ASK = "f1a1b2c3-0"
ASK9 = "f2a1b2c3-0"
FREE = "f3a1b2c3-0"
URL = "http://127.0.0.1:4399/#task="
TOL = 2.5  # px of centering tolerance
SAME = 1.0  # px a slot may differ between questions
SLOTS = ("title", "question", "answer", "back", "ok")

METRICS = """(() => {
  const q = (s) => document.querySelector(s);
  const vis = (e) => !!e && e.getBoundingClientRect().width > 0 && getComputedStyle(e).display !== 'none';
  const rect = (e) => { const b = e.getBoundingClientRect(); return {l: b.left, r: b.right, t: b.top, b: b.bottom}; };
  const font = (e) => { const s = getComputedStyle(e); return s.fontSize + '/' + s.lineHeight + '/' + s.fontFamily; };
  // One text line as the browser lays it out (4K runs zoomed, so computed line heights are not on-screen pixels).
  const oneLine = (e) => { const p = document.createElement('span'); p.textContent = 'x'; p.style.display = 'block'; e.append(p); const h = p.getBoundingClientRect().height; p.remove(); return h; };
  const box = q('textarea[name]');
  const center = q('.ask-center');
  const drawer = q('.drawer');
  const title = q('.drawer-title');
  const slot = q('[data-slot=head]');
  const bar = [...document.querySelectorAll('.drawer-bar button')].filter(vis);
  const back = q('[data-ask=back]'), ok = q('[data-ask=accept]'), qa = q('.ask-q');
  const out = {
    focused: !!box && document.activeElement === box,
    boxChars: box ? box.value.length : 0,
    cards: document.querySelectorAll('.ask .ask-card').length,
    boxes: document.querySelectorAll('.ask textarea').length,
    qtitle: (q('.ask-title') || {}).innerText || '',
    sendBox: vis(q('.drawer-send')),
    sendBtn: vis(q('[data-action=send]')),
    tabsVisible: vis(q('.dtabs')),
    counter: !!q('.ask-page') || /\\d+ \\/ \\d+/.test((q('.ask') || {innerText: ''}).innerText),
    helper: /Your answer|Recommended|One by one/.test(document.body.innerText),
    barNames: bar.map((b) => (b.getAttribute('aria-label') || '') + '|' + (b.title || '') + '|' + b.innerText.trim()),
    titleWhole: title ? title.scrollHeight <= title.clientHeight + 1 && getComputedStyle(title).textOverflow === 'clip' : false,
    slotLines: slot && title ? Math.round(slot.getBoundingClientRect().height / oneLine(title) * 10) / 10 : 0,
    scrollOver: q('.drawer-scroll') ? q('.drawer-scroll').scrollHeight - q('.drawer-scroll').clientHeight : null,
    badText: /\\[object Object\\]|\\bundefined\\b|\\bNaN\\b/.test(document.body.innerText),
    innerW: innerWidth,
    drawerW: drawer ? rect(drawer).r - rect(drawer).l : 0,
    onlyAsk: !!drawer && drawer.classList.contains('drawer--only-ask'),
  };
  if (center && title && box && back && ok && qa) {
    const c = rect(center), tt = rect(title), bx = rect(box), q1 = rect(qa), bk = rect(back), k = rect(ok);
    out.colMid = (c.l + c.r) / 2;
    out.measure = Math.round(c.r - c.l);
    out.tops = {title: tt.t, question: rect(q('.ask-title')).t, answer: bx.t, back: bk.t, ok: k.t};
    out.stack = {slotB: rect(slot).b, qT: q1.t, qB: q1.b, aT: bx.t, aB: bx.b, navT: Math.min(bk.t, k.t)};
    out.okRight = k.l > bk.r && bk.l < out.colMid && k.r > out.colMid;
    out.inside = [bx, bk, k].every((r) => r.l >= 0 && r.r <= innerWidth && r.t >= 0 && r.b <= innerHeight);
    const bodyP = q('.ask-body p');
    if (bodyP) out.fonts = [font(q('.ask-title')), font(bodyP), font(box)];
  }
  return out;
})()"""

BAR_NAMES = (
    "Details|Details|",
    "All questions|All questions|",
    "One question at a time|One question at a time|",
    "Close|Close|",
)


def read(cdp: Cdp) -> dict[str, Any]:
    return dict(cdp.js(METRICS))


def click(cdp: Cdp, selector: str) -> None:
    cdp.js(f"document.querySelector({selector!r}).click()")


def common(m: dict[str, Any], where: str, bar_buttons: int = 3) -> list[str]:
    problems = []
    if m["tabsVisible"]:
        problems.append(f"{where}: the tab strip is visible")
    if m["sendBox"] or m["sendBtn"] or m["counter"] or m["helper"]:
        problems.append(
            f"{where}: send box {m['sendBox']} / send button {m['sendBtn']} / counter {m['counter']} / helper {m['helper']}"
        )
    names = m["barNames"]
    if len(names) != bar_buttons or any(not n.startswith(BAR_NAMES) or not n.endswith("|") for n in names):
        problems.append(f"{where}: bar buttons are not {bar_buttons} icon-only named buttons: {names}")
    if not m["titleWhole"]:
        problems.append(f"{where}: the task title is clamped or clipped")
    if m["slotLines"] > 3.05:
        problems.append(f"{where}: the task-title slot is {m['slotLines']} lines, 3 at most")
    if m["scrollOver"] is None or m["scrollOver"] > 1:
        problems.append(f"{where}: drawer-scroll scrolls by {m['scrollOver']}")
    if m["badText"]:
        problems.append(f"{where}: [object Object]/undefined/NaN in text")
    if not m["onlyAsk"] or abs(m["drawerW"] - m["innerW"]) > 0.5:
        problems.append(f"{where}: drawer is {m['drawerW']}px of {m['innerW']}px (only-ask {m['onlyAsk']})")
    return problems


def one_question(m: dict[str, Any], where: str) -> list[str]:
    problems = []
    if not m["focused"] or not m.get("inside"):
        problems.append(f"{where}: focused {m['focused']} chars {m['boxChars']} inside {m.get('inside')}")
    if m["cards"] != 1 or not m.get("okRight"):
        problems.append(f"{where}: {m['cards']} cards, OK right of Back {m.get('okRight')}")
    if abs(m.get("colMid", 0) - m["innerW"] / 2) > TOL:
        problems.append(
            f"{where}: column not centered in the browser (mid {m.get('colMid')} of {m['innerW']})"
        )
    s = m.get("stack", {})
    if s and not (s["slotB"] <= s["qT"] + 1 and s["qB"] <= s["aT"] + 1 and s["aB"] <= s["navT"] + 1):
        problems.append(f"{where}: slots overlap {s}")
    if len(set(m.get("fonts", [1, 2]))) != 1:
        problems.append(f"{where}: title/body/answer typography differs: {m.get('fonts')}")
    return problems


class Card(NamedTuple):
    """A mock ask card: its questions, the bar icons it shows and which question to screenshot under which name."""

    id: str
    count: int
    bar_buttons: int
    shots: dict[int, str]


def walk(cdp: Cdp, out: Path, tag: str, card: Card) -> tuple[list[str], list[dict[str, float]]]:
    """Open `card` and step through its questions with OK (never past the last: that would send)."""
    goto(cdp, f"{URL}{card.id}", 2.4)
    problems: list[str] = []
    tops: list[dict[str, float]] = []
    for index in range(card.count):
        m = read(cdp)
        where = f"{card.id} question {index + 1}"
        problems += common(m, where, card.bar_buttons) + one_question(m, where)
        if not m["qtitle"].startswith(f"Q{index + 1}"):
            problems.append(f"{where}: title {m['qtitle']!r}")
        tops.append(m.get("tops", {}))
        if index in card.shots:
            cdp.shot(out / f"{tag}-{card.shots[index]}.png")
        if index < card.count - 1:
            click(cdp, "[data-ask=accept]")
    return problems, tops


def same_slots(tops: list[dict[str, float]]) -> list[str]:
    """The KEY check: each slot starts at one y for every question of every card."""
    problems = []
    for slot in SLOTS:
        values = [t[slot] for t in tops if slot in t]
        if len(values) != len(tops) or max(values) - min(values) > SAME:
            problems.append(f"slot {slot} moves between questions: {sorted({round(v, 1) for v in values})}")
    return problems


def step_questions(cdp: Cdp, url: str, out: Path, tag: str) -> dict[str, Any]:
    del url  # the ask cards live only on the dev mock at 4399
    problems: list[str] = []
    every: list[dict[str, float]] = []
    for card in (
        Card(ASK, 5, 3, {0: "questions", 2: "questions-short", 3: "questions-long"}),
        Card(ASK9, 9, 3, {8: "questions9"}),
        Card(FREE, 1, 2, {0: "questions-free"}),
    ):
        found, tops = walk(cdp, out, tag, card)
        problems += found
        every += tops
    problems += same_slots(every)
    problems += probe(
        cdp, ["textarea[name=Q1]", "[data-ask=back]", "[data-ask=accept]", ".drawer-bar button"]
    )["problems"]
    problems += all_view_and_details(cdp, out, tag)
    return {"problems": problems, "tops": every[:1]}


def all_view_and_details(cdp: Cdp, out: Path, tag: str) -> list[str]:
    goto(cdp, f"{URL}{ASK}", 2.4)
    problems: list[str] = []
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
    click(cdp, "[data-details]")
    cdp.shot(out / f"{tag}-questions-details.png")
    m = read(cdp)
    if m["onlyAsk"] or (m["innerW"] > 960 and m["drawerW"] >= m["innerW"]):
        problems.append(f"Details must give the side panel back (drawer {m['drawerW']}px of {m['innerW']}px)")
    return problems
