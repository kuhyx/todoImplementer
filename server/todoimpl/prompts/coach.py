"""Coaching a failing free worker (DOCS-umbrella.md, "Coaching") and the textgate rules for its tasks.

The free worker has no skill context: a textgate child's task file starts with `TEXTGATE_RULES`, so "it is a
proper noun, keep it" is not available as an excuse unless the rules allow it.
"""

from __future__ import annotations

import re

MAX_COACHED = 3
PROMPT_PHASE = "prompt"
_TEXTGATE = re.compile(r"textgate|text-free", re.IGNORECASE)

COACHING = (
    "A free worker that fails, declines, misreads the task or leaves a bad diff is coached, not replaced: "
    "DIAGNOSE why first (read its log and `git diff`), fix the CAUSE, then run the freeworker command "
    "again. "
    "Fixes: rewrite or clarify the worker prompt; add the missing context (the scan output, the exact "
    "files and lines to change, a worked example); or split the task "
    f"smaller. Up to {MAX_COACHED} coached attempts per child. Log each one as an issue line with "
    f'phase "{PROMPT_PHASE}" (symptom = what the worker got wrong, action = what you changed in the '
    f"prompt or context). Only after {MAX_COACHED} failed attempts may you finish the work yourself "
    "(`fixed`) or "
    "`escalate`; never do the edits yourself before coaching."
)

# Wrapped for width; each bullet is one line again in the joined text.
_RULES = (
    "TEXTGATE RULES (kuhy's rule; you have no skill context, these are it)",
    (
        "- Goal: nothing kuhy SEES has words unless he asked: app, game and desktop UI, "
        "dialogs, tooltips, placeholders, notifications, i3bar blocks, lock windows, headings "
        "and titles drawn inside the UI."
    ),
    (
        "- Free, keep: code, identifiers, comments, README/DOCS, logs, `--json` read by "
        "Claude, terminal-only CLI output and `--help` (print/echo are not scanned; Tk and "
        "desktop toasts still are), and content a human wrote that the program only displays "
        "(todo notes, book text, food names, typed values)."
    ),
    (
        "- CHROME, rework: everything Claude wrote around content: titles, headings, helper "
        "text, empty states, status sentences, tooltips, dialog bodies, enum words. A name "
        'shown in the UI for the app, a screen or a window is chrome too: "it is a proper '
        'noun or brand" is NOT an excuse. Only OS-level labels (launcher label, manifest '
        "name, MaterialApp title, .desktop Name=) keep the app's proper noun."
    ),
    (
        '- If the scan still lists an item, the gate counts it: change it. Never answer "no '
        'changes needed" while the scan lists items. Keeping one needs evidence a human wrote '
        "it (`git log -S'<text>'`); else it is chrome."
    ),
    (
        "- Replace with: nothing (the UI already says it), else an icon, pictogram, number or "
        "shape plus a second channel (colour, motion, sound, haptic). Never swap text for "
        "other text, a caption, or a renamed variable."
    ),
    (
        "- Keep old wording only as a spoken-only accessibility label "
        "(Semantics/semanticLabel, aria-label, contentDescription, alt), never as a tooltip."
    ),
    (
        "- Tests assert state, not strings: update tests that read removed text. `rg` every "
        "consumer of a removed string."
    ),
    (
        "- Edit with your Edit/Write tools, not `sed -i`. Run `textgate scan | tail` from the "
        "repo root before and after; the count must drop and the done_check must pass. Do not "
        "push."
    ),
)
TEXTGATE_RULES = "\n".join(_RULES)


def is_textgate(*texts: str) -> bool:
    """Return True when a task text or title is a textgate rework (the worker then needs the rules)."""
    return any(_TEXTGATE.search(t) for t in texts)


def task_text(body: str, *, textgate: bool) -> str:
    """Return a worker task: the textgate rules first when it is a textgate rework, then the task."""
    return f"{TEXTGATE_RULES}\n\n{body}" if textgate else body
