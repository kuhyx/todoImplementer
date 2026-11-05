"""R1 `questions` step: the task drawer's question UI must fit the screen with no scrolling.

Asserts, per viewport, on the dev mock's real-shaped ask cards (web/src/test/fixture-ask.ts):
 - `.drawer-scroll` and `.ask-grid` do not scroll, `Send answers` sits inside the viewport and is the topmost element;
 - desktop (>= 720 px): the drawer is ~90 % wide, all 5 cards show with no pager, the title is clamped to 2 lines;
 - phone: a stepper ("1 / 5"), Send answers only on the last step;
 - 9 questions paginate ("1-6 of 9") and every page still has no scrollbar.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cdp_driver import Cdp, goto, probe

ASK = "f1a1b2c3-0"
ASK9 = "f2a1b2c3-0"
FREE = "f3a1b2c3-0"
PHONE_MAX = 720
LINES_MAX = 2

METRICS = """(() => {
  const q = (s) => document.querySelector(s);
  const box = (s) => { const e = q(s); return e ? e.getBoundingClientRect() : null; };
  const scroll = q('.drawer-scroll'), grid = q('.ask-grid'), drawer = q('.drawer');
  const title = q('.drawer-title'), send = q('[data-action=spec-answers]');
  const cards = [...document.querySelectorAll('.ask-card')].filter((c) => !c.hidden);
  const zoom = title && title.offsetWidth ? title.getBoundingClientRect().width / title.offsetWidth : 1;
  const lineHeight = title ? parseFloat(getComputedStyle(title).lineHeight) * zoom : 0;
  const sendBox = send ? send.getBoundingClientRect() : null;
  return {
    scrollOver: scroll ? scroll.scrollHeight - scroll.clientHeight : null,
    gridOver: grid ? grid.scrollHeight - grid.clientHeight : null,
    cards: cards.length,
    cardOver: Math.max(0, ...cards.map((c) => c.scrollHeight - c.clientHeight)),
    total: document.querySelectorAll('.ask-card').length,
    label: (q('.ask-page') || {}).innerText || '',
    drawerRatio: drawer ? drawer.getBoundingClientRect().width / innerWidth : null,
    titleLines: title && lineHeight ? Math.round(title.getBoundingClientRect().height / lineHeight) : null,
    titleAttr: title ? title.getAttribute('title') : null,
    needsBox: !!q('.needs'),
    sendVisible: !!(sendBox && sendBox.width > 0),
    sendInside: !!(sendBox && sendBox.bottom <= innerHeight && sendBox.right <= innerWidth),
    dup: document.body.innerText.includes('Spec questions'),
    badText: /\\[object Object\\]|\\bundefined\\b|\\bNaN\\b/.test(document.body.innerText),
    gridBox: box('.ask-grid') && { top: box('.ask-grid').top, bottom: box('.ask-grid').bottom },
  };
})()"""


def read(cdp: Cdp) -> dict[str, Any]:
    return dict(cdp.js(METRICS))


def no_scroll(m: dict[str, Any], where: str) -> list[str]:
    problems = []
    if m["scrollOver"] is None or m["scrollOver"] > 1:
        problems.append(f"{where}: drawer-scroll scrolls by {m['scrollOver']}")
    if m["gridOver"] is None or m["gridOver"] > 1:
        problems.append(f"{where}: ask-grid scrolls by {m['gridOver']}")
    if m["cardOver"] > 1:
        problems.append(f"{where}: a card clips its own text by {m['cardOver']}")
    if m["badText"]:
        problems.append(f"{where}: [object Object]/undefined/NaN in text")
    return problems


def click(cdp: Cdp, selector: str) -> None:
    cdp.js(f"document.querySelector({selector!r}).click()")


def step_desktop(cdp: Cdp, out: Path, tag: str) -> list[str]:
    goto(cdp, f"http://127.0.0.1:4399/#task={ASK}", 2.4)
    cdp.shot(out / f"{tag}-questions.png")
    m = read(cdp)
    problems = no_scroll(m, "5 questions")
    if not (m["sendVisible"] and m["sendInside"]):
        problems.append(f"Send answers not inside the viewport: {m['sendVisible']} {m['sendInside']}")
    problems += probe(cdp, ["[data-action=spec-answers]"])["problems"]
    if m["cards"] != m["total"] or m["total"] != 5 or m["label"]:
        problems.append(
            f"5 questions must fit on one page: showing {m['cards']}/{m['total']} label {m['label']!r}"
        )
    if not (0.86 <= (m["drawerRatio"] or 0) <= 0.92):
        problems.append(f"drawer is {m['drawerRatio']} of the viewport, want ~0.9")
    if (m["titleLines"] or 99) > LINES_MAX or not m["titleAttr"]:
        problems.append(f"title lines {m['titleLines']} / title attr {m['titleAttr']!r}")
    if m["needsBox"] or m["dup"]:
        problems.append("duplicate 'Spec questions' summary box is still there")
    return problems


def step_phone(cdp: Cdp, out: Path, tag: str) -> list[str]:
    goto(cdp, f"http://127.0.0.1:4399/#task={ASK}", 2.4)
    cdp.shot(out / f"{tag}-questions.png")
    m = read(cdp)
    problems = no_scroll(m, "stepper 1")
    if m["cards"] != 1 or m["label"].strip() != "1 / 5":
        problems.append(f"stepper must show one card and '1 / 5': {m['cards']} {m['label']!r}")
    if m["sendVisible"]:
        problems.append("Send answers must wait for the last step")
    for _ in range(4):
        click(cdp, "[data-ask=next]")
    cdp.shot(out / f"{tag}-questions-last.png")
    m = read(cdp)
    problems += no_scroll(m, "stepper 5")
    if m["label"].strip() != "5 / 5" or not (m["sendVisible"] and m["sendInside"]):
        problems.append(f"last step: label {m['label']!r} send {m['sendVisible']} {m['sendInside']}")
    problems += probe(cdp, ["[data-action=spec-answers]"])["problems"]
    return problems


def step_paged(cdp: Cdp, out: Path, tag: str, phone: bool) -> list[str]:
    goto(cdp, f"http://127.0.0.1:4399/#task={ASK9}", 2.4)
    cdp.shot(out / f"{tag}-questions9.png")
    problems: list[str] = []
    seen = 0
    for page in range(12):
        m = read(cdp)
        problems += no_scroll(m, f"9 questions page {page + 1}")
        seen = m["cards"] if phone else seen + m["cards"]
        if page == 0 and not m["label"]:
            problems.append("9 questions must paginate, but there is no pager label")
        nxt = cdp.js(
            "(() => { const b = document.querySelector('[data-ask=next]'); return !!b && !b.disabled && b.offsetParent !== null; })()"
        )
        if not nxt:
            break
        click(cdp, "[data-ask=next]")
    last = read(cdp)
    if not phone and seen != 9:
        problems.append(f"paging 9 questions showed {seen} cards in total")
    if not (last["sendVisible"] and last["sendInside"]):
        problems.append("Send answers not reachable on the last page")
    return problems


def step_free(cdp: Cdp, out: Path, tag: str) -> list[str]:
    goto(cdp, f"http://127.0.0.1:4399/#task={FREE}", 2.4)
    cdp.shot(out / f"{tag}-questions-free.png")
    m = read(cdp)
    problems = no_scroll(m, "free text")
    box = cdp.js(
        "(() => { const t = document.querySelector('textarea[name=ask-send]'); return !!t && t.value === '' && t.offsetParent !== null; })()"
    )
    if not box or m["cards"] != 1:
        problems.append(f"free-text question needs one card with an empty textarea: {box} {m['cards']}")
    problems += probe(cdp, ["[data-action=send]", "textarea[name=ask-send]"])["problems"]
    return problems


def step_questions(cdp: Cdp, url: str, out: Path, tag: str) -> dict[str, Any]:
    del url  # the ask cards live only on the dev mock at 4399
    phone = (cdp.size or (0, 0))[0] < PHONE_MAX
    problems = step_phone(cdp, out, tag) if phone else step_desktop(cdp, out, tag)
    problems += step_paged(cdp, out, tag, phone)
    problems += step_free(cdp, out, tag)
    return {"problems": problems}
