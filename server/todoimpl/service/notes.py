"""Send to Claude and the model picker; `ServiceBackend` binds them from here as its methods.

A note that is a model command (`modelpick.parse`: "run it on claude fable 5.2", "rerun on opus", "default")
pins the card and reruns its stage (`Scheduler.set_model`); it never reaches the session or drafts a lesson.
Every other note goes on as before: at the gate it is a rejection, so a lesson is drafted in the background.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl import modelpick
from todoimpl.board.state import load, run_dir

if TYPE_CHECKING:
    from .backend import ServiceBackend


def send(backend: ServiceBackend, id8: str, text: str) -> None:
    """Send to Claude: a model command pins the model, any other note goes to the session."""
    if (picked := modelpick.parse(text)) is not None:
        model(backend, id8, model=picked)
        return
    run = load(run_dir(backend.root, id8))
    if run is not None and run.stage == "gate":
        backend.spawn(lambda: backend._draft(id8, text))  # noqa: SLF001 - the backend's own drafter
    backend._click(id8, "send", lambda: backend.scheduler.send(id8, text))  # noqa: SLF001 - shared click path


def model(backend: ServiceBackend, id8: str, *, model: str) -> None:
    """Pin `model`, or drop the pin with `default` (the picker, POST /api/task/<id>/model)."""
    backend._click(id8, "model", lambda: backend.scheduler.set_model(id8, model))  # noqa: SLF001
