"""One claude turn: pick the session, spawn, tee stdout to the stream file and the live feed, record it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from . import allowlist, claude, files, orphans, session
from .stream import StreamParser, TurnResult, state_tag

if TYPE_CHECKING:
    import subprocess
    from collections.abc import Callable
    from pathlib import Path

    from todoimpl.board.state import RunState


@dataclass(frozen=True)
class TurnEnv:
    """Where a turn runs and who hears about it; `register` hands the live process to cancel."""

    run_dir: Path
    worktree: Path
    publish: Callable[[dict[str, Any]], None]
    register: Callable[[subprocess.Popen[str] | None], None]
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
    """total_cost_usd is cumulative over a resumed session: charge only what this turn added."""
    seen: dict[str, float] = state.extra.setdefault("session_costs", {})
    prev = seen.get(res.session_id, 0.0) if res.session_id else 0.0
    if res.session_id:
        seen[res.session_id] = max(prev, res.cost_usd)
    return max(res.cost_usd - prev, 0.0)


def run_turn(
    env: TurnEnv,
    state: RunState,
    role: str,
    prompt_for: Callable[[session.Situation], str],
    extra_dirs: tuple[Path, ...] = (),
) -> TurnResult:
    """Run to exit; `prompt_for` gets the session situation (killed, idle or plain) and returns the prompt."""
    plan = session.plan_turn(_prior(env, state, role), now=env.now())
    allow = allowlist.rules_for(env.run_dir.parent, state.repo, state.task_id)
    inv = claude.build(role, prompt_for(plan.situation), env.worktree, plan.resume, extra_dirs, allow)
    for note in inv.notes:
        env.activity("error", note)
    stream = files.new_stream(env.run_dir, role, env.now())
    parser = StreamParser()
    err_path = stream.with_name(stream.name.removesuffix(files.STREAM_SUFFIX) + ".stderr.log")
    with stream.open("w", encoding="utf-8") as raw, err_path.open("w", encoding="utf-8") as err:
        proc = claude.spawn(inv, err)
        env.register(proc)
        orphans.record(env.run_dir, proc.pid)
        try:
            for line in proc.stdout or ():
                raw.write(line)
                raw.flush()
                for act in parser.feed(line):
                    env.activity(act.kind, act.text, act.tool)
        finally:
            code = proc.wait()
            orphans.clear(env.run_dir)
            env.register(None)
    res = parser.result
    spent = _turn_cost(state, res)
    record = {
        "session_id": res.session_id,
        "cost_usd": res.cost_usd,
        "turn_cost_usd": spent,
        "tag": res.tag,
        "is_error": res.is_error,
        "finished": res.finished,
        "exit_code": code,
        "num_turns": res.num_turns,
        "denials": [{"tool": d.tool_name, "hook": d.hook, "terminal": d.terminal} for d in res.denials],
    }
    files.write_json(files.result_path(stream), record)
    if res.session_id:
        state.sessions[role] = {"session_id": res.session_id, "last_turn_end": env.now()}
        state.session_id = res.session_id
    state.cost_usd = round(state.cost_usd + spent, 6)
    state.last_tag = state_tag(res.tag)
    env.publish({"type": "cost", "cost_usd": state.cost_usd})
    return res
