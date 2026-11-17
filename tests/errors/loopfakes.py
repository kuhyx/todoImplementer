"""The errors loop's test rig: one loop, its source files, and a gate the test can open and shut."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from errfakes import RunningScheduler, shim, write_kartka
from todoimpl.board.state import RunState, run_dir, save
from todoimpl.errors import ledger
from todoimpl.errors.gate import Gate
from todoimpl.errors.loop import ErrorLoop
from todoimpl.errors.sources import Source
from todoimpl.repotask.ids import repo_card_id
from todoimpl.todo_mcp.client import TodoClient

if TYPE_CHECKING:
    from pathlib import Path

    from fake_todo_mcp import FakeTodoMcp
    from servicefakes import Rig

KEY = "kartka:02b0d43d9f"
CARD = repo_card_id("kuhyx/kartka")


class StubGate(Gate):
    """The gate answers whatever the test says (`world.reason`)."""

    def __init__(self, world: World) -> None:
        super().__init__()
        self.world = world

    def check(self, root: Path, repo: str, now: float) -> str | None:
        return self.world.reason


class World:
    """One loop, its source files and a gate the test can open and shut."""

    def __init__(self, rig: Rig, fake: FakeTodoMcp, tmp: Path) -> None:
        self.rig, self.fake, self.tmp = rig, fake, tmp
        self.reason: str | None = "weekly"
        self.hook_log = tmp / "hook.log"
        self.state = tmp / "kartka-state.json"
        hook = shim(tmp / "run.sh", self.hook_log)
        build = shim(tmp / "build.sh", tmp / "build.log", out="88")
        self.source = Source(
            "kartka",
            "kuhyx/kartka",
            "kartka",
            self.state,
            (str(hook), "resolve", "{signature}"),
            (str(build),),
        )
        self.now = 1000.0
        self.gate = StubGate(self)
        assert isinstance(rig.scheduler, RunningScheduler)
        self.sched: RunningScheduler = rig.scheduler
        self.loop = ErrorLoop(
            rig.root,
            cards=lambda: rig.backend.cache.snapshot().tasks,
            tasks=TodoClient(fake.url, fake.token),
            creator=rig.backend.new_task_service,  # type: ignore[arg-type]
            starter=rig.scheduler,
            gate=self.gate,
            sources=lambda: [self.source],
            clock=lambda: self.now,
        )

    def entries(self, *entries: dict[str, Any]) -> None:
        write_kartka(self.state, *entries)

    def tick(self) -> None:
        self.loop.tick()

    def tools(self, name: str) -> list[dict[str, Any]]:
        return [args for tool, args in self.fake.calls if tool == name]

    def note_text(self) -> str:
        return "\n".join(n.text for n in self.fake.store.notes.values())

    def ledger(self) -> dict[str, dict[str, Any]]:
        return ledger.load(self.rig.root)

    def run(self, stage: str) -> None:
        save(run_dir(self.rig.root, CARD), RunState(task_id=CARD, stage=stage))

    def starts(self) -> list[tuple[Any, ...]]:
        return [c for c in self.sched.calls if c[0] == "start"]
