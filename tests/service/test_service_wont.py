"""Won't do needs the Scheduler's ItemView to reach the notes (T2045)."""

import pytest
from servicefakes import Rig
from todoimpl.http.backend import BackendError


def test_a_board_without_an_item_view_refuses_wont_and_writes_nothing(rig: Rig) -> None:
    (card,) = rig.sections("only part", title="one")
    with pytest.raises(BackendError, match="no todo view"):
        rig.backend.wont(card)
    (note,) = rig.fake.store.notes.values()
    assert note.status == "todo"
