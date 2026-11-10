"""Builders for umbrella tests: the frozen note format with n children, and small helpers."""

from __future__ import annotations

HEADER = "# Make the repos text-free\nUmbrella: per-repo\nTier: cheap\n"


def child_text(title: str, scan: int | None = None, check: str | None = None, extra: str = "") -> str:
    """Return the original note text of one child."""
    lines = [f"# {title}"]
    if scan is not None:
        lines.append(f"Scan textgate: {scan} items")
    if check:
        lines.append(f"done_check: `{check}`")
    if extra:
        lines.append(extra)
    return "\n".join(lines)


def umbrella_body(*children: tuple[str, str, str], done: tuple[str, ...] = ()) -> str:
    """Return the body of an umbrella note; each child is (repo name, orig id8, original text)."""
    boxes = [f"- [{'x' if key in done else ' '}] kuhyx/{repo} ({key})" for repo, key, _ in children]
    sections = [f"## kuhyx/{repo} ({key})\n{text}" for repo, key, text in children]
    return "\n".join([HEADER.rstrip("\n"), *boxes, *sections]) + "\n"


def sample() -> str:
    """Three children: a (scan 5), b (scan 2), c (no scan, short)."""
    return umbrella_body(
        ("alpha", "aaaa1111", child_text("Alpha text", scan=5, check="true")),
        ("beta", "bbbb2222", child_text("Beta text", scan=2, extra="more words here to be longer")),
        ("gamma", "cccc3333", "gamma"),
    )
