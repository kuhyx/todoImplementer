"""The umbrella note format (DOCS-umbrella.md): one note holding many per-repo tasks.

    # <title>
    Umbrella: per-repo
    Tier: cheap
    - [ ] kuhyx/<repo> (<orig id8>)
    ## kuhyx/<repo> (<orig id8>)
    <the original note's full text>

Pure text functions; nothing here imports another todoimpl module, so the todo-note layer can use them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_MARKER = re.compile(r"^Umbrella:\s*per-repo\s*$", re.IGNORECASE)
_TIER = re.compile(r"^Tier:\s*(\S+)\s*$", re.IGNORECASE)
_HEAD = re.compile(r"^## (?:\[x\] )?(?P<repo>kuhyx/[\w.-]+) \((?P<key>[A-Za-z0-9]{8}(?:-\d+)?)\)\s*$")
_BOX = re.compile(r"^- \[(?P<mark>[ xX])\] (?P<repo>kuhyx/[\w.-]+) \((?P<key>[A-Za-z0-9]{8}(?:-\d+)?)\)\s*$")
_SCAN = re.compile(r"Scan[^:\n]*:\s*(\d+)\s+items?", re.IGNORECASE)
_CHECK = re.compile(r"^(?:member )?done_check:\s*`?(.*?)`?\s*$", re.IGNORECASE)
_FENCE = "```"


def _cid(key: str, occ: int) -> str:
    """Return the child id: a merge labels it `abcd1234`, or `abcd1234-2` for a section of a shared note."""
    return key if "-" in key else f"{key}-{occ}"


@dataclass(frozen=True)
class Child:
    """One per-repo task of an umbrella; `key` is the source note's id8, `index` its place in the umbrella.

    `cid` is the child's run id `<umbrella id8>-<index + 1>`: its own namespace, so a child never shares a
    branch, worktree, gate unit or lease with a live card of its source note (merge cuts and renumbers those).
    `label` names the child's checkbox: the source id8 (or card id), `occ` counting repeats of `key`.
    """

    key: str
    occ: int
    repo: str
    index: int
    text: str
    title: str
    scan: int | None
    done_check: str | None
    done: bool
    cid: str = ""

    @property
    def label(self) -> str:
        """Return the checkbox label: `<key>-<occ>`, or the label itself when it already is a card id."""
        return _cid(self.key, self.occ)


def _outside_fences(lines: list[str]) -> list[bool]:
    """Return per line whether it is outside a code fence (a fence line itself counts as inside)."""
    flags, fenced = [], False
    for line in lines:
        if line.lstrip().startswith(_FENCE):
            fenced = not fenced
            flags.append(False)
        else:
            flags.append(not fenced)
    return flags


def _header_end(lines: list[str], open_: list[bool]) -> int:
    """Return the index of the first `## ` heading outside fences (len(lines) when there is none)."""
    return next((i for i, line in enumerate(lines) if open_[i] and line.startswith("## ")), len(lines))


def is_umbrella(body: str) -> bool:
    """Return True when the header (before the first `## ` heading) has the `Umbrella: per-repo` line."""
    lines = body.split("\n")
    open_ = _outside_fences(lines)
    return any(
        open_[i] and _MARKER.match(line.strip()) for i, line in enumerate(lines[: _header_end(lines, open_)])
    )


def tier(body: str) -> str | None:
    """Return the header's `Tier:` value in lower case, None when it has none."""
    lines = body.split("\n")
    open_ = _outside_fences(lines)
    for i, line in enumerate(lines[: _header_end(lines, open_)]):
        found = _TIER.match(line.strip()) if open_[i] else None
        if found:
            return found.group(1).lower()
    return None


def scan_size(text: str) -> int | None:
    """Return the smallest `Scan ...: N items` number in the text, None when it has none."""
    scans = [int(s) for s in _SCAN.findall(text)]
    return min(scans) if scans else None


def _title(text: str, repo: str) -> str:
    """Return the first non-empty line of the original text without markdown heading marks."""
    for line in text.split("\n"):
        if line.strip():
            return line.strip().lstrip("#").strip() or repo
    return repo


def _boxes(lines: list[str], open_: list[bool], end: int) -> list[tuple[int, str, bool]]:
    """Return (line, key, ticked) of every header checkbox, in order."""
    out = []
    for i, line in enumerate(lines[:end]):
        found = _BOX.match(line.strip()) if open_[i] else None
        if found:
            out.append((i, found.group("key"), found.group("mark") in "xX"))
    return out


def children(body: str, umbrella: str = "") -> list[Child]:
    """Return the children in file order (`umbrella`, the note id8, names their run ids); done = ticked."""
    lines = body.split("\n")
    open_ = _outside_fences(lines)
    boxes = _boxes(lines, open_, _header_end(lines, open_))
    heads = [(i, m) for i, line in enumerate(lines) if open_[i] and (m := _HEAD.match(line))]
    seen: dict[str, int] = {}
    found = []
    for n, (at, head) in enumerate(heads):
        stop = heads[n + 1][0] if n + 1 < len(heads) else len(lines)
        text = "\n".join(lines[at + 1 : stop]).strip()
        check = next((m.group(1) for line in text.split("\n") if (m := _CHECK.match(line.strip()))), None)
        key, repo = head.group("key"), head.group("repo")
        occ = seen[key] = seen.get(key, -1) + 1
        same = [ticked for _, k, ticked in boxes if k == key]
        done = occ < len(same) and same[occ]
        found.append(
            Child(
                key,
                occ,
                repo,
                n,
                text,
                _title(text, repo),
                scan_size(text),
                check or None,
                done,
                f"{umbrella}-{n + 1}",
            )
        )
    return found


def ordered(kids: list[Child]) -> list[Child]:
    """Order easiest first: smallest `Scan ...: N items` number, else shortest text; ties keep file order."""
    return sorted(
        kids, key=lambda c: (c.scan is None, c.scan or 0, len(c.text) if c.scan is None else 0, c.index)
    )


def tick(body: str, cid: str) -> str:
    """Return the body with child `cid`'s header checkbox ticked; unchanged when absent or already ticked."""
    lines = body.split("\n")
    open_ = _outside_fences(lines)
    seen: dict[str, int] = {}
    for i, key, _ in _boxes(lines, open_, _header_end(lines, open_)):
        seen[key] = seen.get(key, -1) + 1
        if _cid(key, seen[key]) == cid:
            lines[i] = lines[i].replace("[ ]", "[x]", 1)
    return "\n".join(lines)
