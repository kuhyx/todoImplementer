"""The triage prompt, the answer parser, the one-shot call and the `gh` repo listing."""

import json
import stat
from pathlib import Path

import pytest
from todoimpl.triage import classify, repos
from todoimpl.triage.label import ALL_REPOS, EXISTING_REPO, NEW_REPO, RESEARCH, Verdict

REPOS = ["kuhyx/utils", "kuhyx/todoImplementer"]


def test_prompt_carries_title_repos_and_a_cut_body() -> None:
    prompt = classify.build_prompt("gui for pacman", "line\n" + "x" * 3000, REPOS)
    assert prompt.startswith("override\n")
    assert "kuhyx/utils, kuhyx/todoImplementer" in prompt
    assert "Note title: gui for pacman" in prompt
    assert "x" * classify.BODY_CHARS not in prompt  # the body is flattened and cut
    assert "(none)" in classify.build_prompt("t", "", [])


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        (
            'noise {"label":"new_repo","name":"pacman-gui","reason":"new\\nmore"} tail',
            Verdict(NEW_REPO, "new", name="pacman-gui"),
        ),
        ('{"label":"existing_repo","repo":"KUHYX/UTILS"}', Verdict(EXISTING_REPO, "", repo="kuhyx/utils")),
        ('{"label":"all_repos","token":" freshness "}', Verdict(ALL_REPOS, "", token="freshness")),
        ('{"label":"all_repos"}', Verdict(ALL_REPOS)),
        ('{"label":"research","reason":"urls"}', Verdict(RESEARCH, "urls")),
        (
            '{"label":"existing_repo","repo":"kuhyx/gone","reason":"x"}',
            Verdict("manual", "unknown repo kuhyx/gone: x"),
        ),
        ('{"label":"new_repo","name":"Bad Name"}', Verdict("manual", "bad repo name Bad Name: ")),
        ('{"label":"new_repo"}', Verdict("manual", "bad repo name None: ")),
    ],
)
def test_parse(reply: str, expected: Verdict) -> None:
    assert classify.parse(reply, REPOS) == expected


@pytest.mark.parametrize("reply", ["no json", '{"label":"bogus"}', "[1]", "{broken}", '{"reason":"x"}'])
def test_parse_refuses_an_answer_without_a_known_label(reply: str) -> None:
    with pytest.raises(classify.ClassifyError, match="not a JSON object"):
        classify.parse(reply, REPOS)


def _script(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_the_call_is_a_narrow_haiku_one_shot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = json.dumps({"type": "result", "result": "answer", "total_cost_usd": 0.001})
    log = tmp_path / "argv"
    fake = _script(tmp_path, "claude", f"#!/bin/sh\necho \"$@\" > {log}\ncat > /dev/null\necho '{out}'\n")
    monkeypatch.setenv("TODOIMPL_CLAUDE", str(fake))
    assert classify.claude_classifier("p", tmp_path / "run") == "answer"
    argv = log.read_text()
    assert "--model haiku" in argv
    assert "--tools" in argv
    assert (tmp_path / "run" / "oneshot-usage.jsonl").exists()  # the cost is recorded as kind triage


def test_a_claude_failure_is_a_classify_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TODOIMPL_CLAUDE", str(_script(tmp_path, "claude", "#!/bin/sh\nexit 3\n")))
    with pytest.raises(classify.ClassifyError, match="exit 3"):
        classify.claude_classifier("p", tmp_path)


def test_the_default_root_is_the_run_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TODOIMPL_HOME", str(tmp_path / "home"))
    fake = _script(tmp_path, "claude", '#!/bin/sh\ncat > /dev/null\necho \'{"result":"ok"}\'\n')
    monkeypatch.setenv("TODOIMPL_CLAUDE", str(fake))
    assert classify.claude_classifier("p") == "ok"


def test_gh_repos_lists_up_to_1000_and_skips_archived() -> None:
    seen: list[list[str]] = []

    def gh(argv: list[str]) -> str:
        seen.append(argv)
        return json.dumps(
            [{"name": "b", "isArchived": False}, {"name": "a"}, {"name": "old", "isArchived": True}]
        )

    assert repos.gh_repos(gh) == ["kuhyx/a", "kuhyx/b"]
    assert seen[0][:5] == ["repo", "list", "kuhyx", "--limit", "1000"]  # gh lists 30 by default


def test_run_gh_runs_the_binary_and_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _script(
        tmp_path,
        "gh",
        '#!/bin/sh\n[ "$1" = bad ] && { echo oops >&2; exit 1; }\n[ "$1" = slow ] && sleep 5\necho "$@"\n',
    )
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")
    assert repos.run_gh(["a", "b"]).strip() == "a b"
    with pytest.raises(OSError, match="gh bad failed: oops"):
        repos.run_gh(["bad"])
    monkeypatch.setattr(repos, "TIMEOUT_S", 0.2)
    with pytest.raises(OSError, match="timed out"):
        repos.run_gh(["slow"])


def test_the_listing_is_cached_and_keeps_the_old_list_when_a_refresh_fails() -> None:
    now, calls = [0.0], []

    def fetch() -> list[str]:
        calls.append(1)
        if len(calls) == 2:
            raise OSError("down")
        return ["kuhyx/a"]

    listing = repos.Listing(fetch, lambda: now[0])
    assert (listing.get(), listing.get()) == (["kuhyx/a"], ["kuhyx/a"])
    assert len(calls) == 1  # inside the TTL: no second call
    now[0] += repos.TTL
    assert listing.get() == ["kuhyx/a"]  # the refresh failed: the list stays
    assert listing.get() == ["kuhyx/a"]
    assert len(calls) == 2  # and a failure also waits for the next TTL
