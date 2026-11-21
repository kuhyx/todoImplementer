"""Name the program a stalled job really runs, from its whole script (T2430, T2438-T2441).

The name is the ticket's signature, so one cause must always give one name. The card shows only the first 60
characters of the first line, which held `cd X &&`, `cat > f <<EOF`, `s=$(date ...)` or a long env prefix in
front of the real program: one stall was filed under `job-cd`, `job-cat`, `job-unknown` and more, a new ticket
per spelling. Here setup words, chores, wrappers and heredoc bodies are skipped and the first real program
names the job; a card's throwaway `scratch/` or `children/` script is just `script`.
"""

from __future__ import annotations

import re
import shlex

ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
HEREDOC = re.compile(r"(?<!<)<<-?(?!<)\s*(['\"]?)([A-Za-z_]\w*)\1")
SUBST = re.compile(r"\$\([^()]*\)|\(\([^()]*\)\)|`[^`]*`")  # $(...), ((...)), `...`, innermost first
SEPARATOR = frozenset(";&|()")
REDIRECT = frozenset("<>")
SETUP = frozenset(
    {"cd", "pushd", "popd", "export", "set", "unset", "source", ".", "true", "false", ":", "trap",
     "local", "shopt", "umask", "test", "[", "[[", "for", "case", "select", "function", "done", "fi", "esac",
     "}", "wait"}
)  # fmt: skip
CHORE = frozenset({"cat", "rm", "mkdir", "touch", "cp", "mv", "echo", "printf", "ln", "chmod"})  # named last
KEYWORD = frozenset({"if", "then", "do", "else", "elif", "while", "until", "!", "{", "time"})
WRAPPER = frozenset(
    {
        "sudo",
        "nice",
        "ionice",
        "env",
        "timeout",
        "exec",
        "command",
        "nohup",
        "stdbuf",
        "capped.sh",
        "systemd-run",
    }
)
VALUED = frozenset(
    {"-p", "-E", "-u", "-n", "-c", "-k", "-s", "--unit", "--slice", "--property", "--setenv", "--description",
     "--working-directory", "--signal", "--kill-after", "--adjustment", "--class", "--classdata"}
)  # fmt: skip
ARG = re.compile(r"^(-.*|\d+(\.\d+)?[smhd]?)$")  # a wrapper's own option or duration
SHELLS = frozenset({"bash", "sh", "zsh", "dash"})
THROWAWAY = re.compile(r"(^|/)(scratch|children)/")
FALLBACK = "shell"


def _lines(script: str) -> str:
    """Join the script's lines as `;`-separated commands, heredoc bodies and substitutions taken out."""
    kept: list[str] = []
    tag = ""
    for line in script.replace("\\\n", " ").splitlines():
        if tag:
            tag = "" if line.strip() == tag else tag
            continue
        if found := HEREDOC.search(line):
            tag = found[2]
        kept.append(line)
    text = " ; ".join(kept)
    while (bare := SUBST.sub("_", text)) != text:
        text = bare
    return text


def _tokens(text: str) -> list[str]:
    """Split shell text into words and operators; a quote left open falls back to plain words."""
    lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        return list(lexer)
    except ValueError:
        return text.split()


def _segments(tokens: list[str]) -> list[list[str]]:
    """Cut the words into simple commands at `;`, `&&`, `|`, `(`; redirects and their targets are dropped."""
    out: list[list[str]] = [[]]
    skip = False
    for token in tokens:
        if skip:
            skip = False
        elif token and set(token) <= SEPARATOR:
            out.append([])
        elif token and set(token) <= REDIRECT | {"&"}:
            skip = True
        else:
            out[-1].append(token)
    return [words for words in out if words]


def _strip(words: list[str]) -> list[str]:
    """Drop env assignments, keywords and wrappers (with their own options) from the front of a command."""
    while words:
        head = _base(words[0]).lower()
        if ASSIGN.match(words[0]) or head in KEYWORD:
            words = words[1:]
        elif head in WRAPPER:
            words = words[1:]
            while words and (ARG.match(words[0]) or ASSIGN.match(words[0])):
                words = words[2:] if words[0] in VALUED else words[1:]
        else:
            return words
    return words


def _base(word: str) -> str:
    return word.rsplit("/", 1)[-1]


def _clean(word: str) -> str:
    return re.sub(r"[^a-z0-9_.-]", "", _base(word).lower())[:30]


def _word(words: list[str]) -> str:
    """Name one simple command: a shell's `-c` text is read again, its script file names it."""
    head = words[0]
    if _base(head) in SHELLS:
        rest = words[1:]
        while rest and rest[0].startswith("-"):
            if "c" in rest[0] and len(rest) > 1:
                return name(rest[1])
            rest = rest[1:]
        if not rest:
            return _clean(head)
        head = rest[0]
    return "script" if THROWAWAY.search(head) and head.endswith(".sh") else _clean(head)


def name(script: str) -> str:
    """Return the program a job runs as a signature word; `shell` when only setup is left, never `unknown`."""
    chores: list[str] = []
    for raw in _segments(_tokens(_lines(script))):
        words = _strip(raw)
        if not words or _base(words[0]) in SETUP:
            continue
        if _base(words[0]) in CHORE:
            chores.append(_clean(words[0]))
            continue
        if word := _word(words):
            return word
    return chores[0] if chores else FALLBACK
