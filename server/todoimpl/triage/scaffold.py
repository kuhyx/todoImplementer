"""The files of a new repo's first commit (DOCS-triage.md): README, CLAUDE.md (stack open), .gitignore.

CLAUDE.md names no `deploy:` line on purpose: a placeholder that always passes would report a deploy that
never happened. Ship then says "declares no deploy" and the session adds the real line (DOCS-landing.md).
"""

from __future__ import annotations

SKILLS = (
    "build-desktop-ui, build-web-ui, build-mobile-app, build-game, build-backend, build-background-service"
)

GITIGNORE = """.venv/
node_modules/
dist/
build/
__pycache__/
coverage/
.env
*.zip
"""


def readme(name: str, title: str) -> str:
    """Return README.md: the name and the note's title (what kuhy asked for)."""
    return f"# {name}\n\n{title}\n"


def claude_md(name: str, title: str, note: str) -> str:
    """Return CLAUDE.md: what the repo is, where it came from, and the commands the first session fills in."""
    return f"""# {name}

{title}

Created by todoImplementer from todo note `{note}`. The first session picks the stack from kuhy's skills
({SKILLS}), loads the matching one, and replaces the placeholders below.

## Commands

- run: (not chosen yet)
- test: (not chosen yet)
- lint: (not chosen yet)

## Rules

- Write the failing check first, then the code. Commit with a `Todo: {note}` trailer.
- Add a `- deploy: <command>` line (installs, releases and health-checks the change) before the first ship.
"""


def files(name: str, title: str, note: str) -> dict[str, str]:
    """Return the scaffold: relative path -> text."""
    return {
        "README.md": readme(name, title),
        "CLAUDE.md": claude_md(name, title, note),
        ".gitignore": GITIGNORE,
    }
