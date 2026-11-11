"""One claude turn: pick the session, launch the host (or adopt the turn a restart found), follow its stream.

The result is consumed exactly once: `state.extra["consumed_turn"]` names the last stem whose cost and session
were applied, saved in the same write as them. A crash before that write re-applies on the next start; a crash
after it (record not yet cleared) only replays the stream. A turn of another role than the one asked for is
waited for (never killed), its cost kept, its result dropped, and then the asked turn starts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from todoimpl.board import state as store
from todoimpl.credits import ledger, live

from . import adopt, allowlist, claude, credit, creditguard, files, guard, launch, orphans, session
from .files import KilledError
from .stream import StreamParser, TurnResult, state_tag

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from todoimpl.board.state import RunState

MAX_LOST = 3  # turns lost in one call: a host that keeps dying is for kuhy to look at


@dataclass(frozen=True)
class TurnEnv:
    """Where a turn runs and who hears about it; `register` hands the live turn to cancel (None: it ended)."""

    run_dir: Path
    worktree: Path
    publish: Callable[[dict[str, Any]], None]
    register: Callable[[launch.Handle | None], None]
    now: Callable[[], float]

    def activity(self, kind: str, text: str, tool: str | None = None) -> None:  # noqa: D102
        self.publish({"type": "activity", "at": self.now(), "kind": kind, "text": text, "tool": tool})


def _prior(env: TurnEnv, state: RunState, role: str) -> session.Prior | None:
    killed = files.killed_stream(env.run_dir, role)
    entry = state.sessions.get(role)
    if killed is None:
        return session.prior_from(entry)
    files.write_json(files.result_path(killed), {"lost": True})
    prior = session.lost_prior(killed, entry)
    env.activity("system", f"resuming a killed {role} turn; last recorded: {prior.lost}")
    return prior


def _turn_cost(state: RunState, res: TurnResult) -> float:
    """total_cost_usd is cumulative over a resumed session: charge what this turn added (`ledger.delta`)."""
    seen: dict[str, float] = state.extra.setdefault("session_costs", {})
    return ledger.delta(seen, res.session_id, res.cost_usd)


def _launch(  # noqa: PLR0913, PLR0917 - the turn environment plus its route
    env: TurnEnv,
    state: RunState,
    role: str,
    prompt_for: Callable[[session.Situation], str],
    extra_dirs: tuple[Path, ...],
    route: str,
    model: str | None,
    effort: str | None,
) -> orphans.Record:
    plan = session.plan_turn(_prior(env, state, role), now=env.now())
    allow = allowlist.rules_for(files.root_of(env.run_dir), state.repo, state.task_id)
    build = credit.build if route == "credits" else claude.build
    inv = build(role, prompt_for(plan.situation), env.worktree, plan.resume, extra_dirs, allow, model, effort)
    wanted = model or claude.model_for(role)
    ran = credit.MODEL if route == "credits" else wanted
    if ran != wanted:  # kuhy's rule: every role on credits is sonnet; the feed says when a role wanted more
        env.activity("system", f"turn on free API credits: the {role} role wants {wanted}, runs on {ran}")
    else:
        env.activity(
            "system", "turn on free API credits (Agent SDK)" if route == "credits" else "turn on the plan"
        )
    for note in inv.notes:
        env.activity("error", note)
    stem = files.new_stream(env.run_dir, role, env.now()).name.removesuffix(files.STREAM_SUFFIX)
    ask = {"wanted": wanted, "ran": ran, "effort": claude.effort_for(role, effort)}
    files.write_json(files.sibling(env.run_dir, stem, files.MODEL_SUFFIX), ask)
    return launch.start(env.run_dir, stem, role, inv)


def _models(env: TurnEnv, state: RunState, stem: str, role: str) -> dict[str, str]:
    """Return {wanted, ran} of a turn and keep `extra.credit_downgrade[role]` while the role is held back."""
    models: dict[str, str] = files.read_json(files.sibling(env.run_dir, stem, files.MODEL_SUFFIX)) or {}
    held: dict[str, dict[str, str]] = state.extra.setdefault("credit_downgrade", {})
    if models.get("wanted") != models.get("ran") and models:
        held[role] = {"wanted": models["wanted"], "ran": models["ran"]}
    else:
        held.pop(role, None)
    if not held:
        state.extra.pop("credit_downgrade")
    return models


def _apply(env: TurnEnv, state: RunState, rec: orphans.Record, res: TurnResult, code: int) -> None:
    """Write result.json, then cost and session into the state in one save that marks the turn consumed."""
    stem, role = str(rec.stem), str(rec.role)
    route = files.route_of(env.run_dir, stem)
    spent = _turn_cost(state, res)
    models = _models(env, state, stem, role)
    record = {
        "model": models.get("ran"),
        "wanted_model": models.get("wanted"),
        "effort": models.get("effort"),
        "session_id": res.session_id,
        "cost_usd": res.cost_usd,
        "total_cost_usd": res.cost_usd if res.finished else None,  # the stream's cumulative session total
        "model_usage": res.model_usage,
        "turn_cost_usd": spent,
        "route": route,
        "tag": res.tag,
        "is_error": res.is_error,
        "finished": res.finished,
        "exit_code": code,
        "num_turns": res.num_turns,
        "denials": [{"tool": d.tool_name, "hook": d.hook, "terminal": d.terminal} for d in res.denials],
    }
    files.write_json(files.sibling(env.run_dir, stem, files.RESULT_SUFFIX), record)
    ledger.record(
        files.root_of(env.run_dir), task=env.run_dir.name, stem=stem, role=role, route=route,
        session_id=res.session_id, cumulative=res.cost_usd if res.finished else None, ended_at=env.now(),
        estimate=res.live_usd,
    )  # fmt: skip
    if res.session_id:
        state.sessions[role] = {"session_id": res.session_id, "last_turn_end": env.now(), "route": route}
        state.session_id = res.session_id
    state.extra["route"] = route
    state.cost_usd = round(state.cost_usd + spent, 6)
    state.extra["consumed_turn"] = stem
    state.extra["last_exit"] = code
    store.save(env.run_dir, state)
    env.publish({"type": "cost", "cost_usd": state.cost_usd})


def _consume(env: TurnEnv, state: RunState, rec: orphans.Record) -> TurnResult | None:
    """Follow the recorded turn to its end and apply its result once; None when the turn was lost."""
    stem, role = str(rec.stem), str(rec.role)
    handle = launch.handle_for(env.run_dir, rec)
    env.register(handle)
    parser: StreamParser = StreamParser()
    if files.route_of(env.run_dir, stem) == "credits":  # an adopted turn counts as running too
        root, card = files.root_of(env.run_dir), env.run_dir.name
        live.begin(root, card)
        live.attach(root, card, lambda: state.extra.update(cap_hit=True), handle.stop)
        parser = creditguard.CreditGuard(root, card, env.now)
    else:  # the free credits cannot spend overage; the plan can
        parser = guard.OverageGuard(
            files.root_of(env.run_dir),
            env.run_dir.name,
            handle.stop,
            lambda text: env.activity("error", text),
            lambda until: state.extra.__setitem__("overage_hit", until),
            env.now,
        )
    try:
        code = adopt.follow(env.run_dir, rec, parser, env.activity, handle.detach)
    finally:
        env.register(None)
    if code is None:
        env.activity("error", f"turn lost: the {role} turn has no exit record and its host is gone")
        orphans.clear(env.run_dir)
        return None
    res = parser.result
    if state.extra.get("consumed_turn") != stem:
        _apply(env, state, rec, res, code)
    state.last_tag = state_tag(res.tag)
    orphans.clear(env.run_dir)
    return res


def run_turn(  # noqa: PLR0913, PLR0917 - the turn environment plus its route
    env: TurnEnv,
    state: RunState,
    role: str,
    prompt_for: Callable[[session.Situation], str],
    extra_dirs: tuple[Path, ...] = (),
    route: str = "plan",
    model: str | None = None,
    effort: str | None = None,
) -> TurnResult:
    """Run to exit; `prompt_for` gets the session situation (killed, idle or plain) and returns the prompt.

    `model` and `effort` override the role's defaults (the cheap tier, a fix turn); credits are always sonnet.
    """
    lost = 0
    adopt.reap_legacy(env.run_dir)
    try:
        while True:
            rec = orphans.read(env.run_dir) or _launch(
                env, state, role, prompt_for, extra_dirs, route, model, effort
            )
            if (res := _consume(env, state, rec)) is None:
                lost += 1
                if lost >= MAX_LOST:
                    msg = f"The {role} turn was lost {lost} times: its host keeps dying; read the journal"
                    raise KilledError(msg)
            elif rec.role == role:
                return res
    finally:  # the credit claim (`route.claim`) or an adopted turn's mark ends with the turn, however it ends
        live.end(files.root_of(env.run_dir), env.run_dir.name)
