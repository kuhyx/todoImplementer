"""MergeService: background classification (throttled, cached), the GET view, merge and dismiss clicks."""

import json
import re
from collections.abc import Callable

from mergefakes import Rig
from todoimpl.merge.service import INTERVAL, MergeService
from todoimpl.merge.text import fingerprint


class Clock:
    def __init__(self) -> None:
        self.now = 10_000.0

    def __call__(self) -> float:
        return self.now


class Brain:
    """The classifier stand-in: answers one group per call from `answer`, records its prompts."""

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.answer: Callable[[list[str]], str] = lambda ids: json.dumps(
            {"groups": [{"ids": ids[:2], "title": "Both", "reason": "same work"}]}
        )
        self.error: Exception | None = None

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        ids = re.findall(r"^([0-9a-f]{8}-\d+) \| ", prompt, re.MULTILINE)
        return self.answer(ids)


def make(rig: Rig, brain: Brain, clock: Clock, jobs: list[Callable[[], None]] | None = None) -> MergeService:
    spawn = jobs.append if jobs is not None else (lambda job: job())
    return MergeService(
        rig.client,
        rig.cache,
        rig.root,
        classifier=brain,
        clock=clock,
        spawn=spawn,
        umbrella=rig.create_umbrella,
    )


def seed(rig: Rig) -> list[str]:
    return rig.sections("kuhyx/a", [("Make a text-free", "x"), ("Make b text-free", "y"), ("Other", "z")])


def test_a_get_classifies_in_the_background_and_caches_the_groups(rig: Rig) -> None:
    ids = seed(rig)
    brain = Brain()
    jobs: list[Callable[[], None]] = []
    service = make(rig, brain, Clock(), jobs)
    assert service.suggestions() == {"suggestions": []}  # nothing waits on Haiku
    assert brain.prompts == []
    jobs.pop()()
    view = service.suggestions()["suggestions"]
    assert [s["title"] for s in view] == ["Both"]
    first = view[0]
    stored = rig.store().load().groups[0]["ids"]
    assert {m["id"] for m in first["members"]} == set(stored) <= set(ids)
    assert first["id"] == fingerprint(stored)
    assert [a["id"] for a in first["actions"]] == ["merge", "dismiss"]
    assert all(a["enabled"] and a["reason"] is None for a in first["actions"])


def test_the_job_is_not_repeated_while_ids_and_clock_stand_still(rig: Rig) -> None:
    seed(rig)
    brain, clock = Brain(), Clock()
    service = make(rig, brain, clock)
    service.suggestions()
    service.suggestions()
    assert len(brain.prompts) == 1  # same ids: no second call


def test_new_ids_wait_for_the_ten_minute_gap(rig: Rig) -> None:
    seed(rig)
    brain, clock = Brain(), Clock()
    service = make(rig, brain, clock)
    service.suggestions()
    rig.sections("kuhyx/b", [("New one", "")])
    clock.now += INTERVAL - 1
    service.suggestions()
    assert len(brain.prompts) == 1
    clock.now += 2
    service.suggestions()
    assert len(brain.prompts) == 2
    assert "New one" in brain.prompts[1]


def test_a_second_job_does_not_start_while_one_runs(rig: Rig) -> None:
    seed(rig)
    jobs: list[Callable[[], None]] = []
    service = make(rig, Brain(), Clock(), jobs)
    assert service.refresh_if_due() is True
    assert service.refresh_if_due() is False
    assert len(jobs) == 1


def test_a_restart_with_the_same_ids_does_not_ask_again(rig: Rig) -> None:
    seed(rig)
    brain, clock = Brain(), Clock()
    make(rig, brain, clock).suggestions()
    make(rig, brain, clock).suggestions()  # a new server over the same merge.json
    assert len(brain.prompts) == 1


def test_fewer_than_two_open_notes_never_ask(rig: Rig) -> None:
    rig.sections("kuhyx/a", [("Only", "")])
    brain = Brain()
    assert make(rig, brain, Clock()).refresh_if_due() is False
    assert brain.prompts == []


def test_manual_and_repoless_notes_are_not_candidates(rig: Rig) -> None:
    rig.sections("kuhyx/a", [("MANUAL WORK REQUIRED: do it", ""), ("Real", ""), ("Real two", "")])
    rig.fake.seed(None, "No repo", "")
    brain = Brain()
    make(rig, brain, Clock()).suggestions()
    assert "MANUAL" not in brain.prompts[0]
    assert "No repo" not in brain.prompts[0]


def test_a_failing_classifier_keeps_the_old_groups_and_retries_after_the_gap(rig: Rig) -> None:
    seed(rig)
    brain, clock = Brain(), Clock()
    service = make(rig, brain, clock)
    service.suggestions()
    rig.sections("kuhyx/b", [("New one", "")])
    clock.now += INTERVAL + 1
    brain.error = RuntimeError("haiku down")
    service.suggestions()
    assert len(service.suggestions()["suggestions"]) == 1  # the old group is still shown
    assert len(brain.prompts) == 2
    brain.error = None
    clock.now += INTERVAL + 1
    service.suggestions()
    assert len(brain.prompts) == 3


def test_garbage_from_the_classifier_is_a_failed_run(rig: Rig) -> None:
    seed(rig)
    brain = Brain()
    brain.answer = lambda _ids: "not json"
    service = make(rig, brain, Clock())
    assert service.suggestions() == {"suggestions": []}
    assert rig.store().load().ids is None
