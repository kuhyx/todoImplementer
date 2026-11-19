"""Steps 3, 4 and 5: board and start, parallel runs, each green card ships itself (T2060), then the checks."""

from __future__ import annotations

import json
import subprocess
import time
from typing import Any

from e2e_http import PLACEHOLDER, Client
from e2e_log import PendingError, fail, say
from e2e_world import REPO_NAME, REPO_SLUG, State, real_git, save
from todoimpl.todo_mcp.client import TodoClient
from todoimpl.todo_mcp.items import sections

MAX_PARALLEL = 3
SLICE = 45.0  # seconds one invocation may poll; the step is re-run when it ends PendingError
STUCK = ("needs_you", "cancelled", "yours")


def script_lines(card: str, turn: int, sleep: float = 2.0) -> list[dict[str, Any]]:
    """One fake-claude turn: pause, write hello-<card>.txt, end on a D: tag (turn 0 is the plan)."""
    seen = f"hello-{card}.txt exists: ran `cat hello-{card}.txt`, saw it"
    done = "" if turn == 0 else f"\n- [x] {seen}"
    head = f"# Plan\n\n## Acceptance criteria\n- hello-{card}.txt exists\n{done}"
    text = f"{head}\nWrote hello-{card}.txt.\n\nD: done"
    return [
        {"_fake": "sleep", "sec": sleep},
        {"_fake": "write", "path": f"hello-{card}.txt", "text": f"hello from {card}\n"},
        {"_fake": "text", "text": f"Wrote hello-{card}.txt."},
        {"_fake": "result", "text": text},
    ]


def write_claude_scripts(state: State) -> None:
    """Plan, implement and live_check turns per card (more turns fall back to the shim's default)."""
    for card in state.cards:
        folder = state.path / "fake" / "runs" / card / "default"
        folder.mkdir(parents=True, exist_ok=True)
        for turn in range(3):
            text = "".join(json.dumps(line) + "\n" for line in script_lines(card, turn))
            (folder / f"{turn:03d}.jsonl").write_text(text, encoding="utf-8")


def dump(state: State, name: str, data: object) -> None:
    """Keep a JSON snapshot in the artefacts."""
    (state.path / "artifacts" / name).write_text(json.dumps(data, indent=1), encoding="utf-8")


def sample_peak(state: State, api: Client, seconds: float = 6.0) -> None:
    """Record the most runs seen working at once; steps are separate calls, so the start step must look."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        board = api.get("/api/board")
        running = sum(t["status"] == "working" for t in board["tasks"] if t["id"] in state.cards)
        state.peak = max(state.peak, board["slots"]["used"], running)
        if state.peak >= len(state.cards):
            break
        time.sleep(0.3)
    save(state)


def step3_board_and_start(state: State) -> None:
    """GET the board (every item in Backlog, grouped by repo), then POST start on each."""
    api = Client(state.port)
    want = sum(len(n["sections"]) if n.get("sections") else 1 for n in state.notes())
    say(state, 3, f"GET /api/board: expect {want} cards in Backlog")
    board = api.get("/api/board")
    dump(state, "board-backlog.json", board)
    tasks = board["tasks"]
    if len(tasks) != want or {t["column"] for t in tasks} != {"backlog"}:
        fail(f"board has {[(t['title'], t['column']) for t in tasks]}, expected {want} in backlog")
    if board["repos"] != [REPO_SLUG]:
        fail(f"board repos {board['repos']}, expected {[REPO_SLUG]}")
    state.cards = {t["id"]: t["title"] for t in tasks}
    save(state)
    if not state.real_claude:
        write_claude_scripts(state)
    for card, title in state.cards.items():
        say(state, 3, f"POST /api/task/{card}/start ({title})")
        reply = api.post(f"/api/task/{card}/start")
        if not reply.get("ok"):
            fail(f"start {card}: {reply}")
    say(state, 3, "sampling how many runs work at once")
    sample_peak(state, api)
    say(state, 3, "GET /api/live: first event of the live feed")
    event = api.first_event(f"/api/live?id={next(iter(state.cards))}")
    if event.get("type") != "stage":
        fail(f"live feed opened with {event}, expected a stage snapshot")
    metas = api.csrf_metas()
    if len(metas) != 1 or metas[0] == PLACEHOLDER:
        fail(f"page carries csrf metas {metas}: the page reads the first, it must be the one real token")


def check_ready(state: State) -> None:
    """Each card that reached the gate left plan.md and live_check.md (the card may be shipped by now)."""
    for card, title in state.cards.items():
        run = state.path / "root" / card
        for name in ("plan.md", "live_check.md"):
            if not (run / name).is_file() or not (run / name).read_text(encoding="utf-8").strip():
                fail(f"{title}: {run / name} missing or empty")
        say(state, 4, f"{title}: plan.md and live_check.md written")


def step4_wait_ready(state: State) -> None:
    """Poll until every card ships (or is shipped); record the peak of concurrent runs."""
    api = Client(state.port)
    say(state, 4, "waiting for every card to reach shipping")
    end = time.monotonic() + SLICE
    while True:
        board = api.get("/api/board")
        tasks = [t for t in board["tasks"] if t["id"] in state.cards]
        running = sum(t["status"] == "working" for t in tasks)
        state.peak = max(state.peak, board["slots"]["used"], running)
        stuck = [t for t in tasks if t["status"] in STUCK]
        if stuck:
            dump(state, "board-stuck.json", board)
            fail("; ".join(f"{t['title']} is {t['status']}: {t.get('needs')}" for t in stuck))
        if all(t["status"] in ("shipping", "done") for t in tasks):  # no Ready column, no click (T2060)
            break
        if time.monotonic() > end:
            save(state)
            raise PendingError(", ".join(f"{t['title']}={t['status']}" for t in tasks))
        time.sleep(0.4)
    dump(state, "board-ready.json", board)
    say(state, 4, f"peak concurrent runs {state.peak}")
    if state.peak > MAX_PARALLEL:
        fail(f"{state.peak} runs at once, the cap is {MAX_PARALLEL}")
    if not state.real_claude and len(state.cards) > 1 and state.peak < 2:
        fail(f"runs did not overlap (peak {state.peak}); they are not parallel")
    check_ready(state)


def git_out(*args: str) -> str:
    """Stdout of a git command (the real git, never a push)."""
    return subprocess.run([real_git(), *args], check=True, capture_output=True, text=True).stdout


def verify_shipped(state: State) -> None:
    """Bare remote commits and trailers, notes closed in the fake MCP, worktrees gone."""
    bare, repo = state.path / "remote.git", state.path / "src" / REPO_NAME
    messages = git_out("--git-dir", str(bare), "log", "main", "--format=%B%x00").split("\0")
    trailers = sorted(
        line.split(": ", 1)[1].strip()[:8]
        for message in messages
        for line in message.splitlines()
        if line.startswith("Todo: ")
    )
    want = sorted(
        nid[:8]
        for nid, note in zip(state.note_ids, state.notes(), strict=True)
        for _ in note.get("sections") or [0]
    )
    if trailers != want:
        fail(f"remote main has Todo trailers {trailers}, expected {want}")
    client = TodoClient(state.mcp_url, "test-token")
    for nid, note in zip(state.note_ids, state.notes(), strict=True):
        got = client.get_task(nid)
        marks = [s.done for s in sections(got.body)] if note.get("sections") else [True]
        if got.status != "done" or not all(marks):
            fail(f"note {nid[:8]} is {got.status} with sections done={marks}")
    listed = git_out("-C", str(repo), "worktree", "list", "--porcelain").count("worktree ")
    leftovers = [p.name for p in (state.path / "root" / "worktrees").glob("*")]
    if listed != 1 or leftovers:
        fail(f"worktrees left: {listed - 1} registered, dirs {leftovers}")
    say(state, 5, f"remote has {len(trailers)} Todo commits, notes done, worktrees removed")


def step5_ship(state: State) -> None:
    """Wait until every card has shipped on its own (no Ship click), then verify the world."""
    api = Client(state.port)
    end = time.monotonic() + SLICE
    for card, title in state.cards.items():
        if card in state.shipped:
            continue
        while True:
            code, body = api.request("GET", f"/api/task/{card}")
            if code == 404:  # closing the note's last open item drops the note from the open list
                break
            task = body["card"]
            if task["status"] == "done":
                break
            if task["status"] in STUCK:
                dump(state, f"ship-{card}.json", task)
                fail(f"{title}: ship ended in {task['status']}: {task.get('needs')}")
            if time.monotonic() > end:
                text = f"{title} is {task['status']}"
                raise PendingError(text)
            time.sleep(0.4)
        state.shipped.append(card)
        save(state)
    verify_shipped(state)
