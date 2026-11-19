"""Send to Claude and the model picker; `ServiceBackend` binds them from here as its methods.

A note that is a model command (`modelpick.command`: "run it on claude fable 5.2", "rerun on opus", "default")
pins the card and reruns its stage (`Scheduler.set_model`); it never drafts a lesson. A note that starts with
one ("rerun on opus, keep the palette") sends the rest to the rerun session as an ordinary note (T2221).
Every other note goes on as before: at the gate it is a rejection, so a lesson is drafted in the background.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl import modelpick
from todoimpl.board.state import load, run_dir

if TYPE_CHECKING:
    from .backend import ServiceBackend


def send(backend: ServiceBackend, id8: str, text: str) -> None:
    """Send to Claude: a model command pins the model (its rest goes on as a note), any other note goes on."""
    if (picked := modelpick.command(text)) is not None:
        chosen, rest = picked
        backend._click(id8, "model", lambda: backend.scheduler.set_model(id8, chosen, rest))  # noqa: SLF001
        return
    run = load(run_dir(backend.root, id8))
    if run is not None and run.stage == "gate":
        backend.spawn(lambda: backend._draft(id8, text))  # noqa: SLF001 - the backend's own drafter
    backend._click(id8, "send", lambda: backend.scheduler.send(id8, text))  # noqa: SLF001 - shared click path


def model(backend: ServiceBackend, id8: str, *, model: str) -> None:
    """Pin `model`, or drop the pin with `default` (the picker, POST /api/task/<id>/model)."""
    backend._click(id8, "model", lambda: backend.scheduler.set_model(id8, model))  # noqa: SLF001
