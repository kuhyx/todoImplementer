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
        with subprocess.Popen(  # noqa: ASYNC220 - a test fake: blocking is fine; lines stream as the fake prints them
            argv, cwd=opt.cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
        ) as proc:
            assert proc.stdout is not None  # PIPE was asked for
            for line in proc.stdout:
                yield json.loads(line)
        if proc.returncode:
            msg = f"Command failed with exit code {proc.returncode}"
            raise RuntimeError(msg)
