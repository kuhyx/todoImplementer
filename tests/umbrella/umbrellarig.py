"""A booted umbrella world: repos, the umbrella note, a Scheduler, scripted manager and child turns."""

from __future__ import annotations

from typing import Any

from runnerfakes import NO_DEPLOY_MD, Env, FakeClient, make_repo, task
from schedfakes import state, wait
from todoimpl.board import state as store
from todoimpl.runner.scheduler import Scheduler
from umbrellafakes import child_text, umbrella_body

NOTE = "umbr0001"
CARD = f"{NOTE}-0"
KIDS = (("alpha", "aaaa1111", 2), ("beta", "bbbb2222", 3), ("gamma", "cccc3333", 4))
LIVE = (
    {"_fake": "write", "path": "hello.txt", "text": "hi\n"},
    {"_fake": "result", "text": "- [x] C1: ran it -> saw it\n\nD: done"},
)


def manager(*lines: str) -> tuple[dict[str, Any], ...]:
    """Return a manager turn that ends with these CHILD lines."""
    return ({"_fake": "result", "text": "\n".join([*lines, "", "D: done"])},)


def boot(
    world: Env,
    count: int = 3,
    *,
    checks: dict[str, str] | None = None,
    done: tuple[str, ...] = (),
    missing: tuple[str, ...] = (),
    undeployed: tuple[str, ...] = (),
    body: str | None = None,
) -> tuple[Scheduler, FakeClient]:
    """Make `count` repos (not `missing` ones; `undeployed` ones declare no deploy) and an umbrella note."""
    made = KIDS[:count]
    for name, _, _ in made:
        if name not in missing:
            make_repo(
                world,
                name,
                {"README.md": "demo\n", "CLAUDE.md": NO_DEPLOY_MD} if name in undeployed else None,
            )
    text = umbrella_body(
        *((n, k, child_text(f"Make {n} text-free", scan=s, check=(checks or {}).get(n))) for n, k, s in made),
        done=done,
    )
    note = task(NOTE, repo=None, title="Make the repos text-free", body=text if body is None else body)
    client = FakeClient({NOTE: note})
    return Scheduler(client, world.root, check_timeout=20), client


def script_live(world: Env, count: int = 3) -> None:
    """Queue one passing live check (with an edit) for each child."""
    for i in range(count):
        world.script(f"{NOTE}-{i + 1}", *LIVE)


def umbrella(world: Env) -> store.RunState:
    """Return the umbrella's saved state."""
    return state(world, CARD)


def at_rest(world: Env, sched: Scheduler, stage: str) -> store.RunState:
    """Wait until the umbrella rests in `stage` with no drive."""

    def done() -> bool:
        st = store.load(world.root / CARD)
        return st is not None and st.stage == stage and CARD not in sched.running()

    try:
        wait(done)
    except AssertionError as exc:
        raise AssertionError(dump(world)) from exc
    return umbrella(world)


def dump(world: Env) -> str:
    """Return the umbrella's and its children's stages and errors, for a failing wait."""
    out = [f"umbrella {umbrella(world).stage} {umbrella(world).error}"]
    for path in sorted((world.root / CARD / "children").glob("*/state.json")):
        child = store.load(path.parent)
        out.append(f"{path.parent.name}: {child.stage if child else None} {child.error if child else None}")
    return "\n".join(out)
