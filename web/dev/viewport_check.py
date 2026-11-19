"""R1 viewport driver: own headless chromium (CDP 9333), one size per call, screenshots + layout assertions.

Usage: viewport_check.py --size 390x844 --out DIR [--url URL] [--scheme dark|light] [--steps board,drawer,...]
Prints one JSON line per step with the assertions; exit 1 if any assertion failed.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from cdp_driver import Cdp, goto, launch, page_ws, probe
from viewport_issues import step_issues
from viewport_questions import step_questions
from viewport_sessions import step_detail, step_sessions
from viewport_track import step_track

WORKING = "17a1b2c3-0"
SPEC = "1ca1b2c3-0"
READY = "20a1b2c3-0"


def step_board(cdp: Cdp, url: str, out: Path, tag: str) -> dict[str, Any]:
    goto(cdp, url)
    cdp.shot(out / f"{tag}-board.png")
    selectors = ["input[name=q]", "select[name=repo]", "select[name=sort]", ".col[data-active] .card"]
    # The tab bar only exists below the side-by-side breakpoint (board.css, 1500px).
    if cdp.size is not None and cdp.size[0] < 1500:
        selectors.append(".tab[aria-current]")
    return probe(cdp, selectors)


def step_filtered(cdp: Cdp, url: str, out: Path, tag: str) -> dict[str, Any]:
    goto(cdp, f"{url}#col=backlog&repo=utils&sort=updated&q=fuzzy")
    cdp.shot(out / f"{tag}-filtered.png")
    return probe(cdp, ["input[name=q]", ".col[data-active] .card"])


def step_drawer(cdp: Cdp, url: str, out: Path, tag: str) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for name, task in (("drawer", WORKING), ("drawer-spec", SPEC), ("drawer-ready", READY)):
        goto(cdp, f"{url}#task={task}", 2.4)
        cdp.shot(out / f"{tag}-{name}.png")
        selectors = [".drawer", "[data-close]"] + (
            [".drawer-send textarea", ".dtab"] if task == WORKING else []
        )
        results.append(probe(cdp, selectors))
    cdp.js("document.querySelector('[data-tab=plan]').click()")
    cdp.shot(out / f"{tag}-drawer-plan.png")
    return {"problems": [p for r in results for p in r["problems"]]}


def step_focus(cdp: Cdp, url: str, out: Path, tag: str) -> dict[str, Any]:
    goto(cdp, url)
    seen = []
    for _ in range(4):
        cdp.call("Input.dispatchKeyEvent", type="keyDown", key="Tab", code="Tab", windowsVirtualKeyCode=9)
        cdp.call("Input.dispatchKeyEvent", type="keyUp", key="Tab", code="Tab", windowsVirtualKeyCode=9)
        seen.append(
            cdp.js(
                "document.activeElement.matches(':focus-visible') ? document.activeElement.tagName : 'NO-RING'"
            )
        )
    cdp.shot(out / f"{tag}-focus.png")
    return {"problems": [] if "NO-RING" not in seen else [f"focus ring missing {seen}"], "seen": seen}


def step_flow(cdp: Cdp, url: str, out: Path, tag: str) -> dict[str, Any]:
    goto(cdp, f"{url}#col=ready&task={READY}", 2.4)
    t = cdp.js(
        """(() => { const b = document.querySelector('[data-action=ship]'); b.click(); return !!document.querySelector('[data-confirm]'); })()"""
    )
    clicked = cdp.js(
        """(() => { document.querySelector('[data-confirm]').click(); const s = document.querySelector('[data-action=ship]'); return s ? s.getAttribute('aria-busy') : 'confirm-gone'; })()"""
    )
    time.sleep(1.2)
    loader = cdp.js("document.querySelector('[data-slot=pending] .loader')?.innerText ?? null")
    cdp.shot(out / f"{tag}-flow-pending.png")
    time.sleep(1.2)
    after = cdp.js("document.querySelector('.drawer-chips .chip')?.innerText ?? null")
    problems = []
    if not t:
        problems.append("confirm did not appear synchronously")
    if clicked != "true":
        problems.append(f"no pending state after confirm: {clicked}")
    if not loader:
        problems.append("no loader after 1.2 s wait")
    if after != "Done":
        problems.append(f"server state not shown after ship: {after}")
    return {"problems": problems, "loader": loader, "after": after}


def step_newtask(cdp: Cdp, url: str, out: Path, tag: str) -> dict[str, Any]:
    goto(cdp, url)
    cdp.js("document.querySelector('[data-new-task=open]').click()")
    time.sleep(0.3)
    cdp.shot(out / f"{tag}-newtask.png")
    fields = ["input[name=repo]", "input[name=title]", "textarea[name=body]"]
    buttons = [f"[data-new-task={name}]" for name in ("pick", "cancel", "submit")]
    return probe(cdp, [f"ti-new-task {sel}" for sel in fields] + buttons)


STEPS = {
    "newtask": step_newtask,
    "board": step_board,
    "filtered": step_filtered,
    "drawer": step_drawer,
    "focus": step_focus,
    "flow": step_flow,
    "questions": step_questions,
    "track": step_track,
    "sessions": step_sessions,
    "sessions-detail": step_detail,
    "issues": step_issues,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--url", default="http://127.0.0.1:4399/")
    parser.add_argument("--scheme", default="dark")
    parser.add_argument("--steps", default="board,filtered,drawer")
    args = parser.parse_args()
    width, height = (int(v) for v in args.size.split("x"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    profile = tempfile.mkdtemp(prefix="todoimpl-chromium-")
    proc = launch(width, height, profile)
    failed = False
    try:
        cdp = Cdp(page_ws())
        for domain in ("Page", "Runtime", "Log"):
            cdp.call(f"{domain}.enable")
        cdp.set_viewport(width, height, mobile=width < 720)
        cdp.call(
            "Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": args.scheme}]
        )
        for name in args.steps.split(","):
            result = STEPS[name](cdp, args.url, out, f"{args.size}-{args.scheme}")
            result["errors"] = cdp.errors[:]
            result["problems"] += [f"console: {e}" for e in cdp.errors]
            cdp.errors.clear()
            failed |= bool(result["problems"])
            print(json.dumps({"size": args.size, "step": name, **result}))
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        shutil.rmtree(profile, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
