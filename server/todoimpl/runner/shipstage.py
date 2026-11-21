"""The shipping stage: squash, rebase, gate, push, deploy and close one run (DOCS-landing.md)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from todoimpl.board.status import SHIP_STEP
from todoimpl.repotask import files
from todoimpl.umbrella import bounce
from todoimpl.umbrella.note import is_umbrella
from todoimpl.umbrella.run import run as run_umbrella

from . import appfix, deploy, shipfix
from .checks import discover
from .deploy import DeployFailedError
from .deployheal import DirtyCheckoutError
from .deployline import NoDeployLineError
from .files import NeedsYouError
from .gate import GateRedError
from .parsing import parse_live
from .ship import CommitRefusedError, RedAfterRebaseError, ShipPlan, ship
from .shipfix import MAX_SHIP_FIXES
from .worktree import base_ref, repo_dir

if TYPE_CHECKING:
    from .pipeline import Driver


def _word(row: dict[str, object]) -> str:
    return "deferred" if row["deferred"] else "done" if row["done"] else "not done"


def live_summary(report: str) -> str:
    """One line per criterion of the live check, for the close evidence."""
    rows = parse_live(report)
    return "\n".join(f"live {r['criterion']}{_key(r)}: {_word(r)} ({r['note']})" for r in rows)


def _key(row: dict[str, object]) -> str:
    return f" [{row['part']}]" if row["part"] else ""


def _ship_plan(d: Driver, wt: Path, live: str) -> ShipPlan:
    """Build the ship's plan; its `step` hook puts the step the ship is in on the card's line (T2060)."""
    st = d.state

    def step(name: str) -> None:
        st.extra[SHIP_STEP] = name
        d.save()
        d.activity(f"shipping: {name}")

    checks = discover(wt, d.item.done_check)
    return ShipPlan(
        repo_dir(d.item.repo), wt, str(st.branch), d.item, checks, d.ctx.run_dir, d.ctx.check_timeout, live,
        str(st.base_sha or ""), step,
    )  # fmt: skip


def _heal(d: Driver, failed: GateRedError | NoDeployLineError | DeployFailedError) -> str:
    """Send a failure Claude can fix to the session's fix turn (`shipfix.heal` raises a rerun or kuhy's)."""
    d.activity(shipfix.heal(d.state, failed, d.ctx.now()))
    if isinstance(failed, NoDeployLineError):  # the new line must reach origin: squash it, never skip deploy
        deploy.forget(d.ctx.run_dir)
    return "implement"


def _check_parts(d: Driver, report: str) -> None:
    """Refuse a ship that closes no part, or a ticked part no passed live row names (T2447)."""
    if not d.item.parts:  # a plain card: nothing to tick
        return
    if not files.ticked(d.ctx.run_dir, d.item):
        msg = "No part is ticked, so Ship would close nothing: tick the finished parts, then Retry"
        raise NeedsYouError(msg, "run_failed")
    if unproven := files.unproven(d.ctx.run_dir, d.item, parse_live(report)):
        keys = ", ".join(f"[{p.key}] {p.title}" for p in unproven)
        msg = (
            f"No passed live criterion names {keys}: check it live as `Cn [<key>]`, or untick it, then Retry"
        )
        raise NeedsYouError(msg, "run_failed")


def shipping(d: Driver) -> str | None:
    """Ship the run (an umbrella ships its children); return `shipped`, or the stage a refusal sends it to."""
    if is_umbrella(d.item.body):  # Ship ships every child at its gate
        return run_umbrella(d)  # type: ignore[arg-type]
    if bounce.unverified(d.state):  # a child ships only on green checks, whatever path led here (T1955)
        return "checks"
    st, wt = d.state, Path(str(d.state.worktree))
    report = str((st.live_check or {}).get("report_md", ""))
    _check_parts(d, report)
    live = live_summary(report)
    plan = _ship_plan(d, wt, live)
    st.extra.pop(SHIP_STEP, None)
    try:
        st.ship = ship(plan, d.ctx.client, d.ctx.now, allow_empty=st.auto_ship)
    except (CommitRefusedError, RedAfterRebaseError) as refused:  # the session fixes it first (T1226, T2008)
        fixes = int(st.extra.get("ship_fixes", 0))
        if fixes >= MAX_SHIP_FIXES:
            raise
        d.activity(f"ship refused, the session fixes it ({fixes + 1}/{MAX_SHIP_FIXES}): {refused.text[:100]}")
        st.extra.update(ship_fixes=fixes + 1, failure_tail=refused.output, reship=True)
        return "implement"
    except DirtyCheckoutError as blocked:  # kuhy's edits block the deploy's pull: wait, never touch them
        shipfix.wait_for_edits(st, blocked, d.ctx.now())
    except (GateRedError, NoDeployLineError, DeployFailedError) as failed:  # Claude's to fix (T2340-T2343)
        return _heal(d, failed)
    sha = st.ship["commit"]
    if sha:
        st.head_sha = sha
        appfix.shipped(d.ctx.root, d.ctx.run_dir, d.item, sha, d.ctx.now())
    if sha and "pushed_at" not in st.ship:  # ship() closed it because the session pushed it already (T1865)
        d.activity(f"closed: the session already pushed {sha[:12]}")
        return "shipped"
    d.activity(
        f"shipped {sha[:12]} to origin/{base_ref(plan.repo)[1]}" if sha else "closed with no code change"
    )
    return "shipped"
