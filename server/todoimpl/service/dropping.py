"""The two clicks that end a card by hand; `ServiceBackend` binds them from here as its methods.

Won't do (T2045): a card no turn works on is dropped; its resting run is cancelled, its notes abandoned.
Done manually (T2064): kuhy did the work; every note is closed as done, the run is stopped and rests in Done.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.board.actions import FINAL_STAGES
from todoimpl.board.state import load, run_dir
from todoimpl.board.status import DONE_STAGES, MANUAL_STAGE
from todoimpl.runner.scheduler import RunnerError
from todoimpl.todo_mcp.model import TodoError

from .view import ItemView

if TYPE_CHECKING:
    from .backend import ServiceBackend


def wont(backend: ServiceBackend, id8: str) -> None:
    """Abandon the notes first (it refuses before any write), then cancel a run that has not ended."""

    def drop() -> None:
        view = getattr(backend.scheduler, "client", None)  # the real Scheduler reads notes via an ItemView
        if not isinstance(view, ItemView):
            msg = "this board has no todo view to abandon notes through"
            raise TodoError(msg)
        view.wont(id8)
        run = load(run_dir(backend.root, id8))
        if run is not None and run.stage not in FINAL_STAGES:
            backend.scheduler.cancel(id8)

    backend._click(id8, "wont", drop)  # noqa: SLF001 - the shared click path: errors, poke, intervention log


EVIDENCE = "done manually: kuhy finished it himself"


def done_manually(backend: ServiceBackend, id8: str) -> None:
    """Close the notes first (it refuses before any write), then stop the run and rest it."""

    def finish() -> None:
        view = getattr(backend.scheduler, "client", None)
        if not isinstance(view, ItemView):
            msg = "this board has no todo view to close notes through"
            raise TodoError(msg)
        run = load(run_dir(backend.root, id8))
        if run is not None and run.stage == "shipping":
            msg = "shipping cannot be stopped"
            raise RunnerError(msg, "disabled")
        if run is not None and run.stage in (*DONE_STAGES, MANUAL_STAGE):
            msg = f"The card is already {run.stage}"
            raise RunnerError(msg, "disabled")
        found = view.done_manually(id8, EVIDENCE)
        backend.scheduler.done_manually(id8, repo=found.repo, title=found.title, repotask=bool(found.parts))

    backend._click(id8, "done_manually", finish)  # noqa: SLF001 - the shared click path
