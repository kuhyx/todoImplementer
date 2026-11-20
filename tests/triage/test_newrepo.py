"""Making the repo: private, scaffolded, pushed, cloned; every step resumable; `gh` and `git` shimmed."""

import json
import stat
from pathlib import Path

import pytest
from todoimpl.triage import newrepo, scaffold
from todoimpl.triage.newrepo import NewRepoError

NOTE = "f206969c"
TITLE = "gui for pacman and yay"


class Shell:
    """A fake `gh` and `git`: records argv, knows which steps happened, can fail a command on demand."""

    def __init__(self, existing: list[dict[str, object]] | None = None) -> None:
        self.calls: list[list[str]] = []
        self.existing = existing or []
        self.created = False
        self.pushed = False
        self.fail: str | None = None
        self.files: dict[str, str] = {}

    def gh(self, argv: list[str]) -> str:
        if self.fail == "list":
            raise OSError("gh down")
        return json.dumps(self.existing)

    def __call__(self, argv: list[str], cwd: Path | None) -> str:
        self.calls.append(argv)
        key = " ".join(argv[:3])
        if self.fail and key.startswith(self.fail):
            msg = f"{key} failed"
            raise NewRepoError(msg)
        if argv[:3] == ["gh", "repo", "view"]:
            if not self.created:
                raise NewRepoError("not found")
            return "pacman-gui\n"
        if argv[:3] == ["gh", "repo", "create"]:
            self.created = True
        if argv[:2] == ["git", "ls-remote"]:
            return "abc\trefs/heads/main\n" if self.pushed else ""
        if argv[:2] == ["git", "add"] and cwd is not None:
            self.files = {p.name: p.read_text() for p in cwd.iterdir() if p.is_file()}
        if argv[:2] == ["git", "push"]:
            self.pushed = True
        if argv[:2] == ["git", "clone"]:
            (Path(argv[-1]) / ".git").mkdir(parents=True)
        return ""

    def names(self) -> list[str]:
        return [" ".join(c[:3]) for c in self.calls]


def make(sh: Shell, tmp_path: Path, name: str = "pacman-gui") -> str:
    return newrepo.provision(
        tmp_path / "run", tmp_path / "src", note=NOTE, title=TITLE, name=name, run=sh, gh=sh.gh
    )


def test_t2071_the_repo_is_private_scaffolded_pushed_to_main_and_cloned_for_kuhy(tmp_path: Path) -> None:
    sh = Shell()
    assert make(sh, tmp_path) == "kuhyx/pacman-gui"
    create = next(c for c in sh.calls if c[:3] == ["gh", "repo", "create"])
    assert create[3:5] == ["kuhyx/pacman-gui", "--private"]
    assert (
        sh.names().index("git init -q") < sh.names().index("git push -q") < sh.names().index("git clone -q")
    )
    commit = next(c for c in sh.calls if c[:2] == ["git", "commit"])
    assert commit[-1].endswith(f"Todo: {NOTE}")
    assert sorted(sh.files) == [".gitignore", "CLAUDE.md", "README.md"]
    clone = next(c for c in sh.calls if c[:2] == ["git", "clone"])
    assert clone[-2:] == ["https://github.com/kuhyx/pacman-gui", str(tmp_path / "src" / "pacman-gui")]
    assert (tmp_path / "src" / "pacman-gui" / ".git").is_dir()
    assert json.loads((tmp_path / "run" / "newrepo.json").read_text()) == {
        "name": "pacman-gui",
        "step": "cloned",
    }


def test_t2071_the_scaffold_names_the_stack_open_and_never_fakes_a_deploy_line() -> None:
    claude = scaffold.claude_md("pacman-gui", TITLE, NOTE)
    assert "build-desktop-ui" in claude
    assert TITLE in claude
    assert not [line for line in claude.splitlines() if line.startswith("- deploy:")]
    assert "Todo: f206969c" in claude
    assert scaffold.readme("pacman-gui", TITLE) == f"# pacman-gui\n\n{TITLE}\n"


def test_t2071_the_name_is_unique_against_every_repo_even_archived_and_the_src_dir(tmp_path: Path) -> None:
    (tmp_path / "src" / "pacman-gui-3").mkdir(parents=True)
    sh = Shell([{"name": "Pacman-GUI"}, {"name": "pacman-gui-2", "isArchived": True}])
    assert make(sh, tmp_path) == "kuhyx/pacman-gui-4"
    assert (tmp_path / "src" / "pacman-gui-4" / ".git").is_dir()


def test_t2071_a_failed_step_resumes_without_a_second_repo(tmp_path: Path) -> None:
    sh = Shell()
    sh.fail = "git push"
    with pytest.raises(NewRepoError, match="git push"):
        make(sh, tmp_path)
    assert json.loads((tmp_path / "run" / "newrepo.json").read_text())["step"] == "created"
    sh.fail = None
    sh.existing = [{"name": "pacman-gui"}]  # the repo now exists: the reserved name is still ours
    assert make(sh, tmp_path, name="other") == "kuhyx/pacman-gui"
    assert sum(c[:3] == ["gh", "repo", "create"] for c in sh.calls) == 1
    assert sum(c[:2] == ["git", "clone"] for c in sh.calls) == 1


def test_t2071_a_repo_or_main_or_clone_that_already_exists_is_not_made_again(tmp_path: Path) -> None:
    sh = Shell()
    state = tmp_path / "run"
    state.mkdir()
    (state / "newrepo.json").write_text(json.dumps({"name": "pacman-gui", "step": "named"}))
    sh.created = sh.pushed = True
    (tmp_path / "src" / "pacman-gui" / ".git").mkdir(parents=True)
    assert make(sh, tmp_path) == "kuhyx/pacman-gui"
    assert [c[:2] for c in sh.calls] == [["gh", "repo"], ["git", "ls-remote"]]  # checked, nothing made


def test_t2071_a_run_cut_after_the_push_only_clones_and_a_finished_one_does_nothing(tmp_path: Path) -> None:
    sh = Shell()
    state = tmp_path / "run"
    state.mkdir()
    (state / "newrepo.json").write_text(json.dumps({"name": "pacman-gui", "step": "pushed"}))
    assert make(sh, tmp_path) == "kuhyx/pacman-gui"
    assert [c[:2] for c in sh.calls] == [["git", "clone"]]
    sh.calls.clear()
    assert make(sh, tmp_path) == "kuhyx/pacman-gui"  # step cloned: nothing left
    assert sh.calls == []


def test_t2071_no_repo_list_means_no_proof_the_name_is_free(tmp_path: Path) -> None:
    sh = Shell()
    sh.fail = "list"
    with pytest.raises(NewRepoError, match="cannot list kuhyx repos"):
        make(sh, tmp_path)
    assert sh.calls == []  # nothing outward happened


def _bin(tmp_path: Path, name: str, text: str) -> None:
    path = tmp_path / name
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_t2071_the_real_runner_reports_exit_timeout_and_a_missing_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bin(
        tmp_path,
        "git",
        '#!/bin/sh\ncase "$1" in push) echo denied >&2; exit 1;; slow) sleep 5;; esac\necho "$1"\n',
    )
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")
    assert newrepo.run_cmd(["git", "status"], tmp_path).strip() == "status"
    with pytest.raises(NewRepoError, match="git push failed: denied"):  # a push never reaches GitHub here
        newrepo.run_cmd(["git", "push"], tmp_path)
    monkeypatch.setattr(newrepo, "TIMEOUT_S", 0.2)
    with pytest.raises(NewRepoError, match="git slow"):
        newrepo.run_cmd(["git", "slow"])
    with pytest.raises(NewRepoError, match="nonesuch"):
        newrepo.run_cmd(["nonesuch"])


@pytest.mark.parametrize(("public", "flag"), [(True, "--public"), (False, "--private")])
def test_t2395_the_repo_takes_the_visibility_the_note_asks_for(
    tmp_path: Path, public: bool, flag: str
) -> None:
    sh = Shell()
    newrepo.provision(
        tmp_path / "run", tmp_path / "src", note=NOTE, title=TITLE, name="pacman-gui", public=public, run=sh,
        gh=sh.gh,
    )  # fmt: skip
    create = next(c for c in sh.calls if c[:3] == ["gh", "repo", "create"])
    assert create[3:5] == ["kuhyx/pacman-gui", flag]
