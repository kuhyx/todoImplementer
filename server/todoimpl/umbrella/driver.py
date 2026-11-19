"""The Driver of an umbrella note: no worktree of its own, and one cancel handle for all its turns."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from todoimpl.runner.pipeline import Ctx, Driver
from todoimpl.triage.label import RESEARCH, label_of
from todoimpl.triage.research import ResearchDriver

from .children import Fan, make_fan
from .note import is_umbrella

if TYPE_CHECKING:
    from todoimpl.board.state import RunState
    from todoimpl.prompts import PromptContext
    from todoimpl.todo_mcp.items import Item


class UmbrellaDriver(Driver):
    """Runs the umbrella handler. Its cwd is its run dir; `fan` carries every live turn to Cancel."""

    fan: Fan
    brief: str = ""  # the round's children, rendered for the manager prompt

    def _worktree(self) -> None:
        self.state.worktree = str(self.ctx.run_dir)
        self.save()

    def context(self, **kwargs: bool | str) -> PromptContext:
        """Return the normal prompt context plus this round's brief."""
        return replace(super().context(**kwargs), brief=self.brief)  # type: ignore[arg-type]


def driver_for(ctx: Ctx, state: RunState, item: Item) -> Driver:
    """Return the Driver of a note: the umbrella one for an umbrella, else the normal one."""
    if not is_umbrella(item.body):
        research = (
            item.repo is None and label_of(ctx.run_dir) == RESEARCH
        )  # a note of URLs: no repo, no worktree
        return (ResearchDriver if research else Driver)(ctx, state, item)
    fan = make_fan(ctx.run_dir)
    ctx.register(fan)  # the engine cancels or detaches the whole fan
    driver = UmbrellaDriver(replace(ctx, register=fan.slot("manager")), state, item)
    driver.fan = fan
    return driver
