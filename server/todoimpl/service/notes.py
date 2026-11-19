"""Send to Claude and the model picker; `ServiceBackend` binds them from here as its methods.

A note that is a model command (`modelpick.command`: "run it on claude fable 5.2", "rerun on opus", "default")
pins the card and reruns its stage (`Scheduler.set_model`); it never drafts a lesson. A note that starts with
one ("rerun on opus, keep the palette") sends the rest to the rerun session as an ordinary note (T2221).
Every other note goes on as before: at the gate it is a rejection, so a lesson is drafted in the background.
It also carries the choices kuhy answered that still wait for an open one (`asks.view.held`, T2275).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from todoimpl import modelpick
from todoimpl.asks.view import held
from todoimpl.board.state import load, run_dir
from todoimpl.http.backend import BackendError
from todoimpl.newtask import noteimages, uploads

BAD = "bad_request"

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .backend import ServiceBackend


def send(backend: ServiceBackend, id8: str, text: str, images: Sequence[noteimages.Ref] = ()) -> None:
    """Send to Claude: a model command pins the model (its rest goes on as a note), any other note goes on.

    Images (T2320) are checked first, copied to `<run>/inbox/<ms>-<N>.<ext>` and named in the note; their
    staged uploads go only once the note is accepted, so a refused send can be retried with the same ids.
    """
    directory = run_dir(backend.root, id8)
    try:
        pictures = noteimages.resolve(images, uploads.root())
    except noteimages.ImageError as exc:
        raise BackendError(BAD, str(exc)) from exc
    paths = noteimages.write(pictures, directory / "inbox", f"{time.time_ns() // 1_000_000}-")
    try:
        _send(backend, id8, text, noteimages.legend(paths))
    except BackendError:
        for path in paths:
            path.unlink(missing_ok=True)
        raise
    noteimages.release(pictures)


def _send(backend: ServiceBackend, id8: str, text: str, legend: str) -> None:
    if (picked := modelpick.command(text)) is not None:
        chosen, rest = picked
        rest = f"{rest}\n\n{legend}".strip()  # images ride along to the rerun
        backend._click(id8, "model", lambda: backend.scheduler.set_model(id8, chosen, rest))  # noqa: SLF001
        return
    directory = run_dir(backend.root, id8)
    run = load(directory)
    if run is not None and run.stage == "gate":
        backend.spawn(lambda: backend._draft(id8, text))  # noqa: SLF001 - the backend's own drafter
    task = next((t for t in backend.cache.snapshot().tasks if t.id == id8), None)
    answers = held(task.body if task else "", run, directory, task.parts if task else ())
    note = f"{text}\n\n{legend}".rstrip()
    note = f"{note}\n\n(runner) kuhy answered in the note: {'; '.join(answers)}" if answers else note
    backend._click(id8, "send", lambda: backend.scheduler.send(id8, note))  # noqa: SLF001 - shared click path


def model(backend: ServiceBackend, id8: str, *, model: str) -> None:
    """Pin `model`, or drop the pin with `default` (the picker, POST /api/task/<id>/model)."""
    backend._click(id8, "model", lambda: backend.scheduler.set_model(id8, model))  # noqa: SLF001
