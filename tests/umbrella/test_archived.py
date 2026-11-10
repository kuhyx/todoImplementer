"""`archived` asks gh whether a repo is archived; any failure reads as not archived (T1924)."""

from __future__ import annotations

import pytest
from runnerfakes import Env, executable
from todoimpl.umbrella import archived


def test_t1924_gh_saying_true_means_archived(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_GH_ARCHIVED", "kuhyx/a kuhyx/b")
    assert archived.archived("kuhyx/b")
    assert not archived.archived("kuhyx/c")


def test_t1924_a_failing_or_missing_gh_means_not_archived(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable(world.bin / "gh", "#!/bin/sh\necho true\nexit 1\n")
    assert not archived.archived("kuhyx/a")
    monkeypatch.setattr(archived, "GH", str(world.bin / "missing-gh"))
    assert not archived.archived("kuhyx/a")
