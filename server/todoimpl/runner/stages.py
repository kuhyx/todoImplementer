"""Stage handlers: each runs one step and returns the next stage, or None to rest where it is."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from todoimpl.errors import marks
from todoimpl.repotask import files
from todoimpl.triage.research import ResearchDriver, run_stage
from todoimpl.umbrella import bounce
from todoimpl.umbrella.note import is_umbrella
from todoimpl.umbrella.run import run as run_umbrella

from . import devicework, freeverify, hold, partproof, phone, tiering
from .checks import SENTENCE_NOTE, discover, record, run_all
from .closing import closing_stage
from .files import NeedsYouError, write_json
from .live import rejudge, settle
from .parsing import parse_criteria, parse_questions, parse_self_check
from .shipstage import shipping

if TYPE_CHECKING:
    from collections.abc import Callable

    from todoimpl.board.state import SpecQuestion

    from .pipeline import Driver

MAX_CHECK_FIXES = 2
MAX_PART_NUDGES = 2


def merge_questions(old: list[SpecQuestion], new: list[SpecQuestion]) -> list[SpecQuestion]:
    """Merge new cards: same id replaces an unanswered card; an answered card's reused id gets a fresh one."""
    merged = list(old)
    for card in new:
        index = next((i for i, q in enumerate(merged) if q.id == card.id), None)
        if index is None:
            merged.append(card)
        elif merged[index].answer is None:
            merged[index] = card
        elif merged[index].title != card.title:
            top = max(int(q.id[1:]) for q in merged)
            merged.append(replace(card, id=f"Q{top + 1}"))
    return merged


def _spec(d: Driver) -> str | None:
    st = d.state
    res = d.turn("spec", "spec")
    st.spec_questions = merge_questions(st.spec_questions, parse_questions(res.text))
    write_json(d.ctx.run_dir / "questions.json", [vars(q) for q in st.spec_questions])
    return "spec_wait"


def _plan(d: Driver) -> str | None:
    res = d.turn("plan", "plan")
    if res.tag in ("Q", "A"):
        return None
    plan = d.ctx.run_dir / "plan.md"
    if not parse_criteria(d.plan_md()) and parse_criteria(res.text):
        plan.write_text(res.text, encoding="utf-8")
    if not parse_criteria(d.plan_md()):
        msg = "plan.md has no `## Acceptance criteria` items: send guidance"
        raise NeedsYouError(msg, "run_failed")
    return "implement"


def _implement(d: Driver) -> str | None:  # noqa: PLR0911 - one return per way out of the stage
    if is_umbrella(d.item.body):  # the rounds of an umbrella note (umbrella/run.py)
        return run_umbrella(d)  # type: ignore[arg-type]
    if isinstance(d, ResearchDriver):  # a note of URLs: report and choices (triage/research.py)
        return run_stage(d)
    tail = str(d.state.extra.get("failure_tail", ""))
    res = d.turn("implement", "fix" if tail else "implement", failure_tail=tail)
    if tiering.gave_up(d, res):  # the cheap tier hands over: the same stage again, now on Opus
        return "implement"
    d.state.extra.pop("failure_tail", None)
    d.state.self_check = parse_self_check(res.text)
    if phone.attach_if_present(d.state, d.ctx.run_dir, res.tag):  # the staged ask meets the Pixel at once
        return "live_check"
    if res.tag in ("Q", "A") and bounce.again(d.state):  # an umbrella child has no one to ask (T1952)
        d.state.extra["nudge"] = bounce.brief(res.text)
        return "implement"
    if devicework.to_claude(d, res):  # phone work is never kuhy's: a fresh live check does it (T2523)
        d.state.sessions.pop("live_check", None)
        return "live_check"
    nxt = d.after_tag(res, "shipping" if d.state.extra.get("reship") else "live_check")
    if nxt == "shipping":
        d.state.extra.pop("reship")
    elif nxt == "live_check":  # new work to check: a new live-check session, seeded from the handoff
        d.state.sessions.pop("live_check", None)
        return _owed(d)
    return nxt


def _owed(d: Driver) -> str:
    """Ask twice when a repo task ends its implement turn with parts unticked, then go on (they stay open)."""
    left = files.unticked(d.ctx.run_dir, d.item)
    nudges = int(d.state.extra.get("part_nudges", 0))
    if not left or nudges >= MAX_PART_NUDGES:
        return "live_check"
    d.state.extra["part_nudges"] = nudges + 1
    d.state.extra["nudge"] = (
        "(runner) Parts not ticked: "
        + "; ".join(f"[{p.key}] {p.title}" for p in left)
        + ". Finish and tick each (see the tick command above), or end with `A:` and say what stops you."
    )
    return "implement"


def _retry(d: Driver, key: str, cap: int, tail: str, stop: NeedsYouError) -> str:
    fixes = int(d.state.extra.get(key, 0))
    if fixes >= cap:
        raise stop
    d.state.extra[key] = fixes + 1
    d.state.extra["failure_tail"] = tail
    return "implement"


def _live_check(d: Driver) -> str | None:  # noqa: PLR0911 - one return per way out of the stage
    st, run_dir = d.state, d.ctx.run_dir
    if st.extra.get("resettle"):
        return rejudge(d)
    report_file, shots = run_dir / "live_check.md", run_dir / "shots"
    if not st.extra.get("r_continue"):  # a continued turn keeps the report it already wrote
        report_file.unlink(missing_ok=True)
    shots.mkdir(parents=True, exist_ok=True)
    redo = str(st.extra.pop("live_redo", ""))  # set: ask for the checklist only, verify nothing again
    brief, kind = partproof.ask(st, redo)  # a proof round asks only for the parts Ship named (T2467)
    attached, info = bool(st.extra.get("phone_attached")), st.extra.get("waiting_phone")
    carried = bool(st.extra.pop(phone.REPLY_CARRY, False))  # the reply came in before a hands nudge
    st.extra.pop(phone.REPLIED, None)  # else only a reply taken in by THIS turn counts
    res = d.turn("live_check", "live_check", failure_tail=brief, prompt=kind)
    replied = bool(st.extra.pop(phone.REPLIED, False)) or carried
    if phone.hands_nudge(st, res, attached=attached, info=info):  # Claude tries the phone itself first
        st.extra[phone.REPLY_CARRY] = replied
        return "live_check"
    if phone.attach_if_present(st, run_dir, res.tag):  # the Pixel is in adb: test on it, never rest (T2083)
        return "live_check"
    settles = phone.answered(st, run_dir, res.tag, replied=replied)
    if res.tag == "Q" or (res.tag == "A" and not settles and not devicework.to_claude(d, res)):
        if not bounce.again(st):
            return None
        st.extra["failure_tail"] = bounce.brief(res.text)  # a child fixes what its live check found (T1952)
        return "implement"
    st.extra.pop("bounces", None)
    if res.tag == "R":  # background work: continue first; settle's one redo only when this runs out
        if (again := d.r_continue(res)) is not None:
            return again
    else:
        st.extra.pop("r_continues", None)
    if not report_file.exists() and res.tag != "R":
        report_file.write_text(res.text, encoding="utf-8")
    report = report_file.read_text(encoding="utf-8") if report_file.exists() else ""
    report = partproof.settled(st, report_file, report)
    st.live_check = {
        "report_md": report,
        "shots": sorted(str(p.relative_to(run_dir)) for p in shots.rglob("*") if p.is_file()),
    }
    return settle(d, report)


def _checks(d: Driver) -> str | None:
    if (verify := freeverify.gate(d)) is not None:  # free-model work: Claude re-checks it first (T2531)
        return verify
    st, wt = d.state, Path(str(d.state.worktree))
    found = discover(wt, d.item.done_check)
    if d.item.done_check and not any(name == "done_check" for name, _ in found):
        d.activity(f"checks: done_check not run, {SENTENCE_NOTE}")
    results, log = run_all(found, wt, d.ctx.run_dir, d.ctx.check_timeout)
    st.checks = record(results, log, d.ctx.now())
    red = [r for r in results if not r.passed]
    d.activity(
        "checks: " + (", ".join(f"{r.name} {'red' if r in red else 'ok'}" for r in results) or "none found")
    )
    if not red:
        st.extra.pop("check_fixes", None)
        child = "umbrella_round" in st.extra  # an umbrella child ships itself when green (T1923)
        st.auto_ship = st.auto_ship or child
        ticked = files.ticked(d.ctx.run_dir, d.item) if d.item.parts else []
        own = marks.ships_itself(st, ticked, d.item.body)  # an app-error fix needs no done_check to ship
        auto = child or (st.auto_ship and (d.item.done_check or own))
        return "gate" if hold.held() and not auto else "shipping"  # T2060: no click, every card ships
    tail = bounce.red_tail(
        st, "\n\n".join(f"== {r.name}: {r.command} (exit {r.exit_code})\n{r.tail}" for r in red)
    )
    cap = bounce.check_cap(st, MAX_CHECK_FIXES)
    why = f"Checks still red after {cap} fix attempts: {', '.join(r.name for r in red)}"
    return _retry(d, "check_fixes", cap, tail, NeedsYouError(why, "checks_failed"))


HANDLERS: dict[str, Callable[[Driver], str | None]] = {
    "spec": _spec,
    "plan": _plan,
    "implement": _implement,
    "live_check": _live_check,
    "checks": _checks,
    "shipping": shipping,
    "closing": closing_stage,
}
