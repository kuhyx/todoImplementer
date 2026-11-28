"""Turn one permission denial into narrow allow rules, or say why it cannot be allowed automatically."""

from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .waitdeny import is_wait

if TYPE_CHECKING:
    from .stream import Denial

EDIT_TOOLS = ("Edit", "Write", "NotebookEdit")
PLAIN_TOOLS = ("Glob", "Grep", "WebSearch", "NotebookRead", "TodoWrite")
OPERATORS = frozenset({"&&", "||", ";", "|", "&"})
WRAPPERS = frozenset({"time", "nohup", "env", "command", "exec"})
THREE_WORDS = frozenset(
    {
        "uv",
        "pnpm",
        "npm",
        "npx",
        "yarn",
        "cargo",
        "go",
        "git",
        "docker",
        "systemctl",
        "claude",
        "flutter",
        "dart",
        "gh",
    }
)
INTERPRETERS = frozenset(
    {"python", "python3", "node", "bash", "sh", "zsh", "perl", "ruby", "php", "deno", "bun"}
)
RISKY_MCP = re.compile(
    r"(send|delete|trash|remove|share|forward|reply|pay|approve|publish|update|create|kill|exec)"
)
SECRETS = re.compile(
    r"(\.ssh|\.gnupg|\.aws|\.netrc|\.env\b|id_rsa|id_ed25519|credentials|private-denylist|/etc/shadow)"
)
HARD_PUSH = re.compile(r"\bgit\s+(?:-\S+\s+)*push\b")
SUDO = re.compile(r"\b(sudo|doas|chattr)\b")
SETTINGS = re.compile(r"\.claude/(settings[^/\s]*\.json|hooks)")
PIPE_TO_SHELL = re.compile(r"\b(curl|wget)\b[^\n|]*\|\s*(sudo\s+)?(ba|z|da)?sh\b")
REDIRECT = re.compile(r"(?<![0-9&])>{1,2}\s*(['\"]?)(/\S+|~\S*)\1")
SAFE_SINKS = ("/dev/null", "/dev/stderr", "/dev/stdout", "/tmp/")  # noqa: S108
UNBYPASSABLE = "cannot be auto-allowed"


@dataclass(frozen=True)
class Verdict:
    """`rules` to learn in `scope`; `blocked` says why not; `ignore` marks a hard deny, not a gap."""

    rules: tuple[str, ...] = ()
    scope: str = "repo"
    blocked: str | None = None
    ignore: bool = False
    guide: bool = False  # a sensitive-file refusal inside the worktree: no rule helps, write via Bash instead
    grant: tuple[str, ...] = ()  # what kuhy's one-line settings command would allow when we cannot


def abs_rule(tool: str, path: Path) -> str:
    """Claude Code spells a filesystem-absolute path with two leading slashes."""
    return f"{tool}(/{path})"


def _inside(path: Path, *roots: Path) -> bool:
    return any(path == r or r in path.parents for r in roots)


def _simple_commands(command: str) -> list[list[str]]:
    """Split a shell line into simple commands (operators and redirections dropped); [] if unparsable."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        return []
    out: list[list[str]] = [[]]
    skip = False
    for tok in tokens:
        if skip:
            skip = False
        elif tok in OPERATORS:
            out.append([])
        elif tok and set(tok) <= set("<>()"):
            skip = tok in ("<", ">", ">>", "<<")
        else:
            out[-1].append(tok)
    return [c for c in out if c]


def _strip(words: list[str]) -> list[str]:
    """Drop leading VAR=x, wrappers and `cd`-only commands' prefixes so the rule names the real program."""
    i = 0
    while i < len(words):
        w = words[i]
        if re.fullmatch(r"[A-Za-z_]\w*=.*", w) or w in WRAPPERS:
            i += 1
        elif w == "timeout" and i + 1 < len(words):
            i += 2
        elif w == "nice":
            i += 3 if i + 1 < len(words) and words[i + 1] == "-n" else 1
        else:
            break
    return words[i:]


def _plain(tok: str) -> bool:
    return not tok.startswith("-") and not re.search(r"[/.~=*$]", tok)


def _bash_rule(words: list[str], full: str) -> str | None:
    """One rule for one simple command: program plus up to two plain sub-words, exact for code strings."""
    prog = words[0]
    if prog == "cd":
        return None
    if prog == "eval" or (prog in INTERPRETERS and len(words) > 1 and words[1] in ("-c", "-e")):
        return f"Bash({full})"
    keep = [prog]
    if prog in INTERPRETERS and len(words) > 1 and not words[1].startswith("-"):
        keep.append(words[1])
    else:
        limit = 3 if prog in THREE_WORDS else 2
        for tok in words[1:limit]:
            if not _plain(tok):
                break
            keep.append(tok)
    return f"Bash({' '.join(keep)}:*)"


def _rm_outside(words: list[str], wt: Path, run_dir: Path) -> bool:
    """Say whether a recursive rm names a target not clearly inside the worktree or run dir."""
    if words[0] != "rm" or not any(
        w == "--recursive" or re.fullmatch(r"-[a-zA-Z]*[rR][a-zA-Z]*", w) for w in words
    ):
        return False
    for tok in (w for w in words[1:] if not w.startswith("-")):
        if re.search(r"[$`*]", tok):
            return True
        if not _inside(Path(os.path.realpath(wt / Path(tok).expanduser())), wt, run_dir):
            return True
    return False


def _never_bash(  # noqa: PLR0911
    command: str, cmds: list[list[str]], wt: Path, run_dir: Path
) -> str | None:
    if SUDO.search(command):
        return "uses sudo/chattr"
    if SETTINGS.search(command):
        return "touches kuhy's Claude settings or hooks"
    if PIPE_TO_SHELL.search(command):
        return "pipes a download into a shell"
    systemctl = any(c[0] == "systemctl" and "--user" not in c for c in map(_strip, cmds) if c)
    if systemctl:
        return "system-level systemctl"
    if any(c and _rm_outside(c, wt, run_dir) for c in map(_strip, cmds)):
        return "rm -r outside the worktree"
    for m in REDIRECT.finditer(command):
        target = Path(os.path.realpath(Path(m.group(2)).expanduser()))
        if not m.group(2).startswith(SAFE_SINKS) and not _inside(target, wt, run_dir):
            return "writes outside the worktree"
    return None


def _bash(d: Denial, wt: Path, run_dir: Path, *, strict: bool) -> Verdict:
    command = str(d.tool_input.get("command", ""))
    cmds = _simple_commands(command)
    if strict and HARD_PUSH.search(command):
        return Verdict(ignore=True)
    if strict and (why := _never_bash(command, cmds, wt, run_dir)):
        return Verdict(blocked=why)
    stripped = [_strip(c) for c in cmds]
    rules = [r for c in stripped if c and (r := _bash_rule(c, " ".join(c)))]
    if not rules or any("(" in r.removeprefix("Bash(").removesuffix(")") for r in rules):
        return Verdict(blocked="too complex for a narrow rule")
    return Verdict(tuple(dict.fromkeys(rules)))


def _target(d: Denial, wt: Path) -> Path | None:
    given = str(d.tool_input.get("file_path") or d.tool_input.get("notebook_path") or "")
    if not given:
        return None
    return Path(os.path.realpath(Path(given).expanduser() if given.startswith("~") else wt / given))


def _path_tool(d: Denial, wt: Path, run_dir: Path, *, strict: bool) -> Verdict:
    path = _target(d, wt)
    if path is None:
        return Verdict(blocked="no file path in the call")
    if d.safety and d.tool_name in EDIT_TOOLS and _inside(path, wt, run_dir):
        return Verdict(guide=True)
    tool = "Read" if d.tool_name == "Read" else "Edit"
    rule = abs_rule(tool, path)
    if tool == "Read":
        return Verdict(blocked="a secrets path") if SECRETS.search(str(path)) else Verdict((rule,), "task")
    if SETTINGS.search(str(path)):
        return Verdict(blocked="kuhy's Claude settings or hooks")
    if strict and (not _inside(path, wt, run_dir) or ".git" in path.parts):
        return Verdict(blocked="outside the worktree and run dir", grant=(rule,))
    return Verdict((rule,), "task")


def classify(  # noqa: PLR0911
    d: Denial, worktree: Path, run_dir: Path, *, strict: bool = True
) -> Verdict:
    """Map a denial to rules; `strict` (no session policy file) applies the never-list."""
    wt = Path(os.path.realpath(worktree))
    rd = Path(os.path.realpath(run_dir))
    if is_wait(d):  # a hard deny (waitdeny.py): the session ends its turn on `run_job`, never gets a rule
        return Verdict(ignore=True)
    if d.hook:
        return Verdict(blocked="a hook blocked it (allow rules cannot lift a hook)")
    if UNBYPASSABLE in d.message:
        return Verdict(blocked="Claude Code refuses rule-based approval for this call")
    tool = d.tool_name
    if tool == "Bash":
        return _bash(d, wt, rd, strict=strict)
    if tool in EDIT_TOOLS or tool == "Read":
        return _path_tool(d, wt, rd, strict=strict)
    if tool.startswith("mcp__"):
        if strict and RISKY_MCP.search(tool.rsplit("__", 1)[-1]):
            return Verdict(blocked="an MCP tool that changes outside state", grant=(tool,))
        return Verdict((tool,), "global")
    if tool == "WebFetch":
        host = re.sub(r"^\w+://([^/]+).*", r"\1", str(d.tool_input.get("url", "")))
        return Verdict((f"WebFetch(domain:{host})",)) if host else Verdict(blocked="no url in the call")
    if tool in PLAIN_TOOLS:
        return Verdict((tool,))
    return Verdict(blocked=f"no narrow rule for the {tool} tool")
