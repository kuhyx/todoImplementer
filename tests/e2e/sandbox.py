#!/usr/bin/env python3
"""Sandbox board: the real server on a scratch HOME and root, for live checks that must not touch the board.

    sandbox.py up [idea] scratch world: public repo kuhyx/e2e-demo, private kuhyx/e2e-private, fake todo MCP
                         (one note each), the fake `claude`, the REAL `claude-free` (OmniRoute, free models),
                         the fake Anthropic API (fake_batches.py); `idea` adds a repo-less note (triage)
    sandbox.py credits on [purchased usd]|off   scratch key for the free credits (only the fake API takes it)
    sandbox.py serve [relay sandbox/slotN]   start `python -m todoimpl.http.main` on a free port; prints the
                         board URL; `relay` also serves it to that phone slot build (sandbox_relay.py)
    sandbox.py limit on|off    put the plan limit on (an hour) or lift it
    sandbox.py post <path> [json]   POST to the sandbox server (same-origin, CSRF token)
    sandbox.py cards     one line per card: id, status, route, current line, tier badges
    sandbox.py env       print the server env as `export` lines (for CLIs run against the sandbox)
    sandbox.py down      stop the server and the fake MCP, remove the work dir

Each command ends within 60 s. The repos push to local bare repos and their visibility sits in the scratch
HOME's cache: nothing leaves the machine but the free-model prompts of the public repo. Never touches
kuhy's board, notes or checkouts.
"""

from __future__ import annotations

import json
import shlex
import shutil
import sys
import tempfile
import time
from pathlib import Path

from e2e_procs import free_port, launch, stop, tail, wait_for
from e2e_world import PYTHON, REPO_ROOT, SCRATCH, SHIMS, State, _git, save, server_env, write_shims
from sandbox_credits import env as credit_env
from sandbox_credits import set_credits, start_fake
from sandbox_relay import env as relay_env

HERE = Path(__file__).resolve().parent
POINTER = SCRATCH / "sandbox"
REPOS = {"e2e-demo": "PUBLIC", "e2e-private": "PRIVATE"}
PRIORITY = {"e2e-demo": "low", "e2e-private": "high"}  # the weekly reserve checks (T2533)
FREE = Path.home() / ".local" / "bin" / "claude-free"
KEY = Path.home() / ".config" / "omniroute" / "api_key"


def _load() -> State:
    work = Path(POINTER.read_text(encoding="utf-8"))
    return State(**json.loads((work / "e2e_state.json").read_text(encoding="utf-8")))


def _repo(state: State, name: str) -> None:
    work = state.path
    bare = work / f"{name}.git"
    _git(work, "init", "--bare", "-q", "-b", "main", str(bare))
    repo = work / "src" / name
    repo.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    (repo / "README.md").write_text(f"{name}\n", encoding="utf-8")
    (repo / "CLAUDE.md").write_text(f"# {name}\n\n## Commands\n\n- test: `true`\n- deploy: `true`\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    _git(repo, "remote", "add", "origin", str(bare))
    _git(repo, "push", "-q", "-u", "origin", "main")


def _free_shim(state: State) -> None:
    """bin/claude-free: the real wrapper, with bin/ (the fake claude) off PATH so it reaches real claude.

    `--force`: the origins are local bare repos, so the wrapper's own GitHub check cannot see the slug; the
    server already checked it in the scratch visibility cache (`freeroute.public`).
    """
    clean = ":".join(p for p in server_env(state)["PATH"].split(":") if p != str(state.path / "bin"))
    shim = state.path / "bin" / "claude-free"
    shim.write_text(f'#!/bin/sh\nPATH="{clean}" exec "{FREE}" --force "$@"\n', encoding="utf-8")
    shim.chmod(0o755)


def _policy(work: Path) -> None:
    """Kuhy's live session policy (bypass, hooks off), its dirs narrowed to the scratch world.

    Without it turns run in acceptEdits with no allow rules, and the board's own tick command needs approval.
    """
    policy = {
        "permission_mode": "bypassPermissions",
        "add_dirs": [str(work)],
        "disable_hooks": True,
        "deny": [],
    }
    target = work / "home" / ".config" / "todoImplementer" / "session-policy.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(policy), encoding="utf-8")


def up(idea: str = "") -> None:
    """Build the scratch world and start the fake MCP."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    state = State(work=tempfile.mkdtemp(prefix="todoimpl-sandbox-"))
    POINTER.write_text(state.work, encoding="utf-8")
    work = state.path
    for name in ("home", "bin", "src", "fake", "root", "artifacts"):
        (work / name).mkdir(exist_ok=True)
    write_shims(state)
    _free_shim(state)
    for name in REPOS:
        _repo(state, name)
    cache = work / "home" / ".cache" / "omniroute_offload" / "visibility.json"
    cache.parent.mkdir(parents=True)
    seen = {f"kuhyx/{n}": {"visibility": v, "at": time.time() + 86400 * 30} for n, v in REPOS.items()}
    cache.write_text(json.dumps(seen), encoding="utf-8")
    (work / "home" / ".config" / "omniroute").mkdir(parents=True)
    (work / "home" / ".config" / "omniroute" / "api_key").symlink_to(KEY)  # the gateway may rotate it
    _policy(work)
    notes = [
        {
            "repo": f"kuhyx/{n}",
            "title": f"{n} hello",
            "body": "## add hello\nCreate hello.txt with the word hi.",
            "priority": PRIORITY[n],
        }
        for n in REPOS
    ] + (
        [{"repo": None, "title": "a tiny tool idea", "body": "Something to sort my photos."}] if idea else []
    )
    (work / "notes.json").write_text(json.dumps(notes), encoding="utf-8")
    out = work / "mcp.json"
    env = {"PATH": server_env(state)["PATH"], "PYTHONPATH": f"{SHIMS}:{HERE}"}
    argv = [PYTHON, str(HERE / "fake_mcp_proc.py"), str(work / "notes.json"), str(out)]
    state.handles["mcp"] = launch("mcp", argv, env, work / "home", work / "artifacts" / "mcp.log")
    if not wait_for(out.exists, 15):
        sys.exit("fake MCP did not start:\n" + tail(work / "artifacts" / "mcp.log"))
    info = json.loads(out.read_text(encoding="utf-8"))
    state.mcp_url, state.note_ids = info["url"], info["ids"]
    (work / "mcp-token").write_text("test-token\n", encoding="utf-8")
    start_fake(state)
    save(state)
    print(f"sandbox world {work}: notes {', '.join(i[:8] for i in state.note_ids)}")


def serve(relay: str = "") -> None:
    """Start (or restart: the old server stops first) the server on a free port and wait for /version.

    `relay` (a slot's `sandbox/slotN`) also serves the board to that slot build on the phone.
    """
    state = _load()
    if "server" in state.handles:
        stop(state.handles.pop("server"))
    state.port = free_port()
    log = state.path / "artifacts" / "server.log"
    argv = [PYTHON, "-m", "todoimpl.http.main", "--port", str(state.port)]
    full = {**server_env(state), **credit_env(state.path), **(relay_env(state.path, relay) if relay else {})}
    state.handles["server"] = launch("server", argv, full, REPO_ROOT, log)
    save(state)
    import urllib.request  # noqa: PLC0415 - only this command talks HTTP

    def answers() -> bool:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{state.port}/version", timeout=1):
                return True
        except OSError:
            return False

    if not wait_for(answers, 40):
        sys.exit("server never answered:\n" + tail(log))
    print(f"sandbox board http://127.0.0.1:{state.port}/")


def limit(arg: str) -> None:
    """Put the plan limit on for an hour, or lift it."""
    marker = _load().path / "root" / "limit-until"
    if arg == "on":
        marker.write_text(f"{time.time() + 3600}\n", encoding="utf-8")
    else:
        marker.unlink(missing_ok=True)
    print(f"plan limit {arg}")


def post(path: str, body: str = "") -> None:
    """POST to the sandbox server and print the answer."""
    from e2e_http import Client  # noqa: PLC0415 - only these commands talk HTTP

    print(json.dumps(Client(_load().port).request("POST", path, json.loads(body) if body else None)))


def cards() -> None:
    """Print one line per card."""
    from e2e_http import Client  # noqa: PLC0415

    for card in Client(_load().port).get("/api/board")["tasks"]:
        free = "free-badge" if card["tier"]["free"] else ""
        print(card["id"], card["repo"], card["status"], card["route"], free, card["current"], sep=" | ")


def env() -> None:
    """Print the server env as export lines."""
    for key, value in server_env(_load()).items():
        print(f"export {key}={shlex.quote(value)}")


def down() -> None:
    """Stop everything and remove the work dir."""
    state = _load()
    for handle in state.handles.values():
        stop(handle)
    shutil.rmtree(state.path, ignore_errors=True)
    POINTER.unlink(missing_ok=True)
    print("sandbox removed")


def main(argv: list[str]) -> int:
    """Dispatch one command."""
    commands = {"up": up, "serve": serve, "env": env, "down": down, "cards": cards}
    if argv[:1] == ["credits"] and len(argv) in {2, 3}:
        set_credits(_load().path, argv[1], float(argv[2]) if len(argv) == 3 else 0.0)
    elif argv == ["up", "idea"]:
        up("idea")
    elif argv[:2] == ["serve", "relay"] and len(argv) == 3:
        serve(argv[2])
    elif argv[:1] == ["limit"] and len(argv) == 2:
        limit(argv[1])
    elif argv[:1] == ["post"] and len(argv) in {2, 3}:
        post(*argv[1:])
    elif len(argv) == 1 and argv[0] in commands:
        commands[argv[0]]()
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
