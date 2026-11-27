"""The reset watch test rig: the real service backend over a fake todo MCP, a recording scheduler."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from errfakes import RunningScheduler
from todoimpl.board.state import RunState, run_dir, save
from todoimpl.repotask.ids import repo_card_id
from todoimpl.runner import limits, resetwatch, tokenopt
from todoimpl.runner.resetwatch import ResetWatch
from todoimpl.usage import oauth

if TYPE_CHECKING:
    from fake_todo_mcp import FakeTodoMcp
    from servicefakes import Rig

CARD = repo_card_id(tokenopt.REPO)
WEEK = 7 * 86400.0
T0 = 1_800_000_000.0  # the first weekly window's end


class Watch:
    """A reset watch over the real service backend, a fake todo MCP and a scheduler that records starts."""

    def __init__(self, rig: Rig, fake: FakeTodoMcp) -> None:
        self.rig, self.fake, self.now = rig, fake, T0 - 3600.0
        assert isinstance(rig.scheduler, RunningScheduler)
        self.sched: RunningScheduler = rig.scheduler
        self.lines: list[tuple[str, str]] = []
        self.creator: Any = rig.backend.new_task_service
        self.watch = self.make()

    def make(self) -> ResetWatch:
        """Build a new watch on the same home: what a server restart does."""
        return ResetWatch(
            self.rig.root,
            lambda: self.rig.backend.cache.snapshot().tasks,
            self.creator,
            self.rig.scheduler,
            feed=lambda card, text: self.lines.append((card, text)),
            clock=lambda: self.now,
        )

    def week(self, resets_at: float, used: float = 0.1) -> None:
        oauth.save(self.rig.root, oauth.Probe(self.now, None, oauth.Window(used, resets_at)))

    def tick(self) -> None:
        self.watch.tick()

    def added(self) -> list[dict[str, Any]]:
        return [args for tool, args in self.fake.calls if tool == "add_task"]

    def starts(self) -> list[tuple[Any, ...]]:
        return [c for c in self.sched.calls if c[0] == "start"]

    def state(self) -> dict[str, Any]:
        return resetwatch.load(self.rig.root)

    def paused(self, until: float) -> None:
        limits.write_until(self.rig.root, until)
        save(run_dir(self.rig.root, "aaaa1111-0"), RunState(task_id="aaaa1111-0", stage="paused_limit"))
