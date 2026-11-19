# todoImplementer

A board for kuhy's todo-app notes. Open it, see every open note grouped by repo, start up to three; each runs in its
own git worktree through Spec, Plan, Implement, Checks, Review loop and Verify, then ships itself when green
(push, deploy, close the note, remove the worktree). Live activity feed, a Send-to-Claude box and a copy
resume command per task. Phone friendly.

Task store: the todo app's MCP. Run state: `~/.cache/todoImplementer/<id8>/`. Details: `DOCS-spec.md`.

## Run

    uv sync --frozen
    uv run --frozen python -m todoimpl.http.main      # http://127.0.0.1:8786
    make fast                                         # all gates

Needs `claude` on PATH and the todo app's MCP on `127.0.0.1:8735`. Deployment (systemd user unit, Caddy,
Google sign-in) lives in `deploy/`.
