# Deploy regressions

One row per bug, ids global and never reused. The row's test is named `test_t<N>_...`.

| Id | What went wrong | Test |
| --- | --- | --- |
| T502 | run.sh ran xdg-open attached to its stdout, so the browser held the terminal: run.sh never returned and the browser log flooded it | tests/deploy/test_deploy_run.py |
| T1857 | The credit route needs the Agent SDK, which the stdlib-only server cannot carry: deploy.sh creates its own venv once and applies the exact pin from deploy/requirements-sdk.txt | tests/deploy/test_deploy_script.py |
| T1858 | The missing-tool deploy test put the real /usr/bin on PATH, so it failed once uv was installed system-wide; it now builds its own system bin without uv | tests/deploy/test_deploy_run.py |
| T1859 | deploy.sh under systemd-run had no ~/.local/bin on PATH, did not find uv and ran `sudo pacman -S uv`; it now looks in the per-user install dirs first | tests/deploy/test_deploy_run.py |
| T1906 | The board unit was `Restart=on-failure` with the default start limit and deploy never checked lingering, so a stray SIGTERM or a boot before login left a multi-day run without its server; the unit is `Restart=always` with no start limit and deploy turns lingering on | tests/deploy/test_deploy_script.py, tests/deploy/test_deploy_static.py |
| T1987 | Ship read the deploy line with `git show HEAD:CLAUDE.md`, which for a CLAUDE.md that is a git symlink to AGENTS.md returns the link text, so Ship failed "declares no deploy: command" (leetcode-guard, todo-app); `command_of` now follows in-repo symlinks at HEAD | tests/runner/test_runner_deploy_link.py |
| T2044 | A Ship that deploys this board restarts it, and the server took ~29 s to answer /version against deploy.sh's 60 x 0.5 s budget: a miss failed the deploy, and the resumed Ship relaunched it, restarting the board again until its resumes ran out; the default is 240 looks (2 min) | tests/deploy/test_deploy_script.py |
