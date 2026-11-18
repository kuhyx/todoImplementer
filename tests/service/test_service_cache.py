"""TaskCache: snapshots, failures never read as empty, the refresh thread."""

import threading

from todoimpl.service.cache import NOT_LOADED, TaskCache
from todoimpl.service.cards import CardTask, card_tasks
from todoimpl.todo_mcp.model import Task, TodoError


def cards(n: int = 1) -> list[CardTask]:
    return [
        c for i in range(n) for c in card_tasks(Task(f"{i:08x}", f"t{i}", "", "kuhyx/r", "todo", "low", None))
    ]


def test_empty_cache_says_not_loaded_not_no_tasks() -> None:
    snap = TaskCache(list).snapshot()
    assert snap.error == NOT_LOADED
    assert snap.tasks == ()


def test_refresh_stores_cards_and_clears_the_error() -> None:
    cache = TaskCache(lambda: cards(2), clock=lambda: 7.0)
    snap = cache.refresh()
    assert (len(snap.tasks), snap.error, snap.at) == (2, None, 7.0)
    assert cache.snapshot() is snap


def test_failure_keeps_old_cards_and_records_the_reason() -> None:
    state = {"fail": False}

    def fetch() -> list[CardTask]:
        if state["fail"]:
            raise TodoError("503 from todo app")
        return cards(3)

    cache = TaskCache(fetch)
    cache.refresh()
    state["fail"] = True
    snap = cache.refresh()
    assert len(snap.tasks) == 3
    assert snap.error == "TodoError: 503 from todo app"
    state["fail"] = False
    assert cache.refresh().error is None


def test_thread_refreshes_repeatedly_and_stops() -> None:
    seen = threading.Semaphore(0)

    def fetch() -> list[CardTask]:
        seen.release()
        return cards()

    cache = TaskCache(fetch, interval=0.01)
    cache.start()
    cache.start()
    assert seen.acquire(timeout=5)
    assert seen.acquire(timeout=5)
    cache.stop()
    assert cache.snapshot().error is None


def test_poke_refreshes_without_waiting_the_interval() -> None:
    seen = threading.Semaphore(0)

    def fetch() -> list[CardTask]:
        seen.release()
        return cards()

    cache = TaskCache(fetch, interval=3600)
    cache.start()
    cache.poke()
    assert seen.acquire(timeout=5)
    cache.stop()


def test_stop_without_start_is_fine() -> None:
    TaskCache(list).stop()


def card(note: str, repo: str, status: str = "todo") -> CardTask:
    return card_tasks(Task(note, note, "", repo, status, "low", None))[0]


def test_t2046_a_repo_patch_swaps_that_repos_open_cards_and_outlives_an_older_fetch() -> None:
    board = [card("aaaa0000", "kuhyx/r"), card("bbbb0000", "kuhyx/r", "done"), card("cccc0000", "kuhyx/o")]
    fresh = [card("dddd0000", "kuhyx/r")]
    began, release = threading.Event(), threading.Event()

    def slow() -> list[CardTask]:
        began.set()
        release.wait(5)
        return board

    cache = TaskCache(lambda: board, repo_fetch=lambda _repo: fresh)
    cache.refresh()
    ids = {c.id for c in cache.refresh_repo("KUHYX/r").tasks}
    assert ids == {"bbbb0000-0", "cccc0000-0", "dddd0000-0"}  # done and other-repo cards stay
    cache._fetch = slow
    flight = threading.Thread(target=cache.refresh)
    flight.start()
    assert began.wait(5)
    cache.refresh_repo("kuhyx/r")  # a patch after that fetch began
    release.set()
    flight.join(5)
    assert "dddd0000-0" in {c.id for c in cache.snapshot().tasks}
    cache.refresh()  # a fetch that began after the patch saw it: the patch is dropped
    assert "dddd0000-0" not in {c.id for c in cache.snapshot().tasks}


def test_without_a_repo_fetch_a_repo_refresh_is_a_full_fetch() -> None:
    cache = TaskCache(lambda: cards(2))
    assert len(cache.refresh_repo("kuhyx/r").tasks) == 2
