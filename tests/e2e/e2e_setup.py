"""Steps 1, 2 and 6: build the scratch world, start the real server, tear everything down."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from e2e_http import Client
from e2e_log import fail, save_artifacts, say
from e2e_procs import alive, free_port, launch, stop, tail, wait_for
from e2e_world import (
    NOTES,
    POINTER,
    PYTHON,
    REPO_ROOT,
    SCRATCH,
    SHIMS,
    State,
    make_repo,
    save,
    server_env,
    write_shims,
)
from todoimpl.todo_mcp.client import TodoClient

HERE = Path(__file__).resolve().parent


def step1_setup(real_claude: bool) -> State:
    """Scratch HOME, repo with a local bare origin, fake todo MCP with the seeded notes."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    state = State(work=tempfile.mkdtemp(prefix="todoimpl-e2e-"), real_claude=real_claude)
    POINTER.write_text(state.work, encoding="utf-8")
    work = state.path
    say(state, 1, f"work dir {work}" + (" (real claude, haiku, one item)" if real_claude else ""))
    for name in ("home", "bin", "src", "fake", "root", "artifacts"):
        (work / name).mkdir(exist_ok=True)
    write_shims(state)
    say(state, 1, "scratch repo kuhyx/e2e-demo with local bare origin")
    make_repo(state)
    notes = state.notes()
    (work / "notes.json").write_text(json.dumps(notes), encoding="utf-8")
    say(state, 1, f"fake todo MCP seeded with {len(notes)} notes")
    out = work / "mcp.json"
    env = {"PATH": server_env(state)["PATH"], "PYTHONPATH": f"{SHIMS}:{HERE}"}
    argv = [PYTHON, str(HERE / "fake_mcp_proc.py"), str(work / "notes.json"), str(out)]
    state.handles["mcp"] = launch("mcp", argv, env, work / "home", work / "artifacts" / "mcp.log")
    save(state)
    if not wait_for(out.exists, 15):
        fail("fake todo MCP did not publish its URL:\n" + tail(work / "artifacts" / "mcp.log"))
    info = json.loads(out.read_text(encoding="utf-8"))
    state.mcp_url, state.note_ids = info["url"], info["ids"]
    (work / "mcp-token").write_text("test-token\n", encoding="utf-8")
    save(state)
    tasks = TodoClient(state.mcp_url, "test-token").list_tasks()
    want = len(NOTES[1:] if real_claude else NOTES)
    if len(tasks) != want:
        fail(f"fake MCP lists {len(tasks)} notes, expected {want}")
    return state


def step2_server(state: State) -> None:
    """Start `python -m todoimpl.http.main` on a free port and wait for /version."""
    work = state.path
    state.port = free_port()
    log = work / "artifacts" / "server.log"
    say(state, 2, f"starting todoimpl.http.main on 127.0.0.1:{state.port}")
    # E2E_SERVER_ARGV swaps the entry point (e.g. a stub while a module is unfinished); it gets --port.
    entry = os.environ.get("E2E_SERVER_ARGV", "").split() or [PYTHON, "-m", "todoimpl.http.main"]
    argv = [*entry, "--port", str(state.port)]
    state.handles["server"] = launch("server", argv, server_env(state), REPO_ROOT, log)
    save(state)
    client = Client(state.port)

    def up() -> bool:
        if not alive(state.handles["server"]):
            fail("server exited before answering /version:\n" + tail(log))
        try:
            return client.request("GET", "/version")[0] == 200
        except OSError:
            return False

    if not wait_for(up, 30):
        fail("server never answered /version within 30 s:\n" + tail(log))
    version = client.get("/version")
    if not version.get("build") or not version.get("version"):
        fail(f"/version lacks build/version: {version}")
    say(state, 2, f"/version -> {version}")


def step6_teardown(state: State) -> None:
    """Stop the server and the fake MCP, keep the artefacts, remove the work dir."""
    say(state, 6, "stopping server and fake MCP")
    for name in ("server", "mcp"):
        if name in state.handles:
            stop(state.handles[name])
    dest = save_artifacts(state, "pass")
    shutil.rmtree(state.path, ignore_errors=True)
    POINTER.unlink(missing_ok=True)
    print(f"F1 step 6/6: work dir removed; artefacts in {dest}", flush=True)  # say() would recreate the dir
