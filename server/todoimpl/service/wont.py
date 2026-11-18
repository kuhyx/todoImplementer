"""Won't do (T2045): kuhy drops a card no turn works on; its resting run is cancelled, its notes abandoned.

`ServiceBackend` binds `wont` from here as its method.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.board.actions import FINAL_STAGES
from todoimpl.board.state import load, run_dir
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
