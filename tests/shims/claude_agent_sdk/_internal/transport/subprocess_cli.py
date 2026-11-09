"""Fake CLI transport: runs tests/shims/claude (the fake `claude`) and yields its stream-json events."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

CLAUDE = Path(__file__).resolve().parents[3] / "claude"


class SubprocessCLITransport:
    """Same constructor and `read_messages` as the real one; options are logged for the tests to read."""

    def __init__(self, prompt: str, options: Any) -> None:
        self._prompt, self._options = prompt, options

    def read_messages(self) -> AsyncIterator[dict[str, Any]]:
        return self._read()

    async def _read(self) -> AsyncIterator[dict[str, Any]]:
        opt = self._options
        log = Path(os.environ["FAKE_CLAUDE_DIR"]) / "sdk_options.jsonl"
        with log.open("a", encoding="utf-8") as out:
            out.write(json.dumps({**vars(opt), "prompt": self._prompt}) + "\n")
        argv = [sys.executable, str(CLAUDE), "-p", self._prompt, "--model", str(opt.model)]
        if opt.resume:
            argv += ["--resume", opt.resume]
        env = {**os.environ, "FAKE_VIA_SDK": "1"}
        done = subprocess.run(  # noqa: ASYNC221 - a test fake: blocking is fine
            argv, cwd=opt.cwd, env=env, capture_output=True, text=True, check=False
        )
        for line in done.stdout.splitlines():
            yield json.loads(line)
        if done.returncode:
            msg = f"Command failed with exit code {done.returncode}"
            raise RuntimeError(msg)
