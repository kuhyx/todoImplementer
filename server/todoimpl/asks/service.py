"""Clicks on asks: answer, take recommended, run, undo, screenshot verdict, auto-adopt after 24 h."""
# ruff: noqa: EM101

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from todoimpl.board.state import load, run_dir
from todoimpl.http.backend import BackendError

from . import allow, cmdrun, store
from .parse import Ask
from .view import DAY, is_open, source, work_asks

if TYPE_CHECKING:
    from todoimpl.service.cache import TaskCache
    from todoimpl.service.scheduling import SchedulerLike

log = logging.getLogger("todoimpl.asks")
TICK = 300.0
Runner = Callable[[str, Path | None], dict[str, Any]]


def refuse(code: str, message: str) -> BackendError:
    """Return the refusal the page shows as-is."""
    return BackendError(code, message)


class AskService:
    """Everything behind POST /api/task/<id>/ask/<verb>; refusals are BackendError."""

    def __init__(
        self,
        cache: TaskCache,
        scheduler: SchedulerLike,
        root: Path,
        *,
        clock: Callable[[], float] = time.time,
        runner: Runner = cmdrun.run,
    ) -> None:
        """Wire the collaborators; tests inject a clock and a command runner."""
        self.cache, self.scheduler, self.root, self._clock, self._runner = (
            cache,
            scheduler,
            root,
            clock,
            runner,
        )

    def _card(self, id8: str) -> tuple[list[Ask], Path, list[Ask]]:
        """Return the card's asks, its run dir and the asks the session waits on (`_scope`)."""
        task = next((t for t in self.cache.snapshot().tasks if t.id == id8), None)
        if task is None:
            raise refuse("not_found", "unknown task")
        directory = run_dir(self.root, id8)
        run = load(directory)
        asks = source(task.body, run, task.parts)
        if not asks:
            raise refuse("disabled", "this card has no asks")
        return asks, directory, _scope(asks, work_asks(task.body, run, task.parts))

    def _find(self, id8: str, ask_id: str) -> tuple[Ask, list[Ask], Path]:
        asks, directory, scope = self._card(id8)
        ask = next((a for a in asks if a.id == ask_id), None)
        if ask is None:
            raise refuse("not_found", "no such ask")
        return ask, scope, directory

    def _resolve(self, id8: str, directory: Path, asks: list[Ask], text: str) -> None:
        """Tell the session once no choice is left open; the saved state is already durable."""
        data = store.load(directory, asks)
        if any(a.type == "choice" and is_open(data["items"].get(a.id)) for a in asks):
            return
        if load(directory) is None:
            return
        try:
            self.scheduler.send(id8, f"(runner) kuhy answered in the note: {text}")
        except Exception:
            log.exception("ask answer for %s not delivered", id8)

    def _set(self, directory: Path, ask: Ask, record: dict[str, Any]) -> None:
        data = store.load(directory, [ask])
        data["items"][ask.id] = {**record, "at": self._clock()}
        store.save(directory, data)
        self.cache.poke()  # the last answer may hand a MANUAL part to Claude: rebuild the cards now (T1994)

    def answer(self, id8: str, ask_id: str, option: str) -> None:
        """Click an option of a choice."""
        ask, asks, directory = self._find(id8, ask_id)
        if ask.type != "choice" or option not in ask.options:
            raise refuse("bad_request", "not an option of this ask")
        self._set(directory, ask, {"state": "answered", "answer": option})
        if ask in asks:  # a manual part's answer beside the session's asks is kuhy's, not news for it
            self._resolve(id8, directory, asks, f"{ask.title}: {option}")

    def take_recommended(self, id8: str) -> None:
        """Every open choice the session waits on takes its recommended option (`_scope`)."""
        _all, directory, asks = self._card(id8)
        data = store.load(directory, asks)
        taken = [a for a in asks if a.type == "choice" and is_open(data["items"].get(a.id))]
        if not taken:
            raise refuse("disabled", "no open choice")
        for ask in taken:
            self._set(directory, ask, {"state": "answered", "answer": ask.recommended})
        self._resolve(id8, directory, asks, "; ".join(f"{a.title}: {a.recommended}" for a in taken))

    def run_command(self, id8: str, ask_id: str, *, add: bool) -> dict[str, Any]:
        """RUN (allow-listed) or add-then-run; never for the never-add set or a root command."""
        ask, _asks, directory = self._find(id8, ask_id)
        command = ask.command or ""
        if ask.type != "command":
            raise refuse("bad_request", "not a command ask")
        how = allow.mode(self.root, command)
        if how == "terminal" or (how == "add_run" and not (add and allow.add(self.root, command))):
            raise refuse("disabled", "run this one in a terminal")
        run = load(directory)
        result = self._runner(command, Path(run.worktree) if run and run.worktree else None)
        self._set(directory, ask, {"state": "done", "result": result})
        return result

    def undo(self, id8: str, ask_id: str) -> None:
        """Reopen an auto-adopted choice; it never auto-adopts again."""
        ask, _asks, directory = self._find(id8, ask_id)
        record = store.load(directory, [ask])["items"].get(ask_id) or {}
        if ask.type != "choice" or record.get("state") != "auto":
            raise refuse("disabled", "nothing to undo")
        self._set(directory, ask, {"state": "open", "undone": True})

    def verdict(self, id8: str, ask_id: str, *, approve: bool) -> None:
        """Approve a screenshot, or reject it and send the card back to its session."""
        ask, asks, directory = self._find(id8, ask_id)
        if ask.type != "screenshot":
            raise refuse("bad_request", "not a screenshot ask")
        self._set(directory, ask, {"state": "approved" if approve else "rejected"})
        if not approve and load(directory) is not None:
            self.scheduler.send(id8, f"(runner) kuhy rejected the screenshot: {ask.title}")
        elif approve and ask in asks:
            self._resolve(id8, directory, asks, f"approved: {ask.title}")

    def adopt_due(self) -> int:
        """Take the recommended option of every reversible choice open for 24 h; return how many."""
        now, count = self._clock(), 0
        for task in self.cache.snapshot().tasks:
            directory = run_dir(self.root, task.id)
            run = load(directory)
            asks = source(task.body, run, task.parts)
            if asks:
                scope = _scope(asks, work_asks(task.body, run, task.parts))
                count += self._adopt_card(task.id, directory, (asks, scope), now)
        return count

    def _adopt_card(self, id8: str, directory: Path, lists: tuple[list[Ask], list[Ask]], now: float) -> int:
        asks, scope = lists
        data = store.load(directory, asks)
        taken = []
        for ask in asks:
            data["seen"].setdefault(ask.id, now)
            record = data["items"].get(ask.id) or {}
            due = now - data["seen"][ask.id] >= DAY
            if (
                ask.type == "choice"
                and ask.risk == "reversible"
                and is_open(record)
                and not record.get("undone")
                and due
            ):
                data["items"][ask.id] = {"state": "auto", "answer": ask.recommended, "at": now}
                data["log"].append(f"auto-adopted {ask.id}: {ask.recommended}")
                taken.append(ask)
        store.save(directory, data)
        if news := [a for a in taken if a in scope]:
            self._resolve(
                id8, directory, scope, "; ".join(f"{a.title}: {a.recommended} (auto)" for a in news)
            )
        return len(taken)

    def start(self) -> None:
        """Tick adopt_due on a daemon thread."""

        def loop() -> None:
            while True:
                try:
                    self.adopt_due()
                except Exception:
                    log.exception("auto-adopt tick failed")
                time.sleep(TICK)

        threading.Thread(target=loop, name="ask-adopt", daemon=True).start()


def _scope(asks: list[Ask], work: list[Ask]) -> list[Ask]:
    """Return the asks delivery and Take recommended cover: the work's, else (only manual ones) all.

    On a repo card a manual part's asks sit beside the session's (T2114): they must neither hold back the
    session's answers nor be answered by a click meant for the session, which would release kuhy's work.
    """
    return work or asks
