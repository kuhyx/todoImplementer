# Deploy regressions

One row per bug, ids global and never reused. The row's test is named `test_t<N>_...`.

| Id | What went wrong | Test |
| --- | --- | --- |
| T502 | run.sh ran xdg-open attached to its stdout, so the browser held the terminal: run.sh never returned and the browser log flooded it | tests/deploy/test_deploy_run.py |
| T1857 | The credit route needs the Agent SDK, which the stdlib-only server cannot carry: deploy.sh creates its own venv once and applies the exact pin from deploy/requirements-sdk.txt | tests/deploy/test_deploy_script.py |
| T1858 | The missing-tool deploy test put the real /usr/bin on PATH, so it failed once uv was installed system-wide; it now builds its own system bin without uv | tests/deploy/test_deploy_run.py |
| T1859 | deploy.sh under systemd-run had no ~/.local/bin on PATH, did not find uv and ran `sudo pacman -S uv`; it now looks in the per-user install dirs first | tests/deploy/test_deploy_run.py |
