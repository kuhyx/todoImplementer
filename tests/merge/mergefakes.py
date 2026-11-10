"""Test doubles for the merge tests: a seeded fake MCP, a client, a cache and an umbrella creator."""

from dataclasses import dataclass, field
from pathlib import Path

from fake_todo_mcp import FakeTodoMcp
from todoimpl.board.state import RunState, run_dir, save
from todoimpl.merge.store import MergeStore
from todoimpl.service.cache import TaskCache
from todoimpl.service.cards import CardTask, card_tasks
from todoimpl.todo_mcp.client import TodoClient


@dataclass
class Rig:
    """A fake MCP, the client on it, a TaskCache over it and a temp run root."""

    fake: FakeTodoMcp
    client: TodoClient
    cache: TaskCache
    root: Path
    umbrellas: list[str] = field(default_factory=list)

    def sections(self, repo: str, rows: list[tuple[str, str]]) -> list[str]:
        """Seed one multi-section note for the repo; return the card ids of its sections."""
        note = self.fake.seed_sections(repo, rows)
        self.cache.refresh()
        return [f"{note[:8]}-{i}" for i in range(len(rows))]

    def cards(self, ids: list[str]) -> list[CardTask]:
        """Return the cached cards with these ids, in the given order."""
        by_id = {t.id: t for t in self.cache.snapshot().tasks}
        return [by_id[i] for i in ids]

    def open_titles(self, repo: str) -> list[str]:
        """Titles of the open cards of a repo, read fresh from the fake MCP."""
        out: list[str] = []
        for note in self.client.list_tasks(repo=repo, full=True):
            out += [c.title for c in card_tasks(note) if c.status != "done"]
        return out

    def run(self, card_id: str, stage: str) -> None:
        """Write a state.json for a card."""
        save(run_dir(self.root, card_id), RunState(task_id=card_id, stage=stage))

    def create_umbrella(self, text: str) -> str:
        """Stand-in for the todo CLI: seed a note with no repo and return its full id."""
        title, _, body = text.partition("\n")
        self.umbrellas.append(text)
        return self.fake.seed(None, title.removeprefix("# "), body)

    def store(self) -> MergeStore:
        """Return the merge store under the run root."""
        return MergeStore(self.root)


def make_rig(fake: FakeTodoMcp, root: Path) -> Rig:
    """Wire a client and a cache over the fake MCP."""
    client = TodoClient(fake.url, fake.token)

    def fetch() -> list[CardTask]:
        return [card for note in client.list_tasks(full=True) for card in card_tasks(note)]

    return Rig(fake, client, TaskCache(fetch), root)
