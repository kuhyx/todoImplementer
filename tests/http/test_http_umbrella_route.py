"""The umbrella path matcher answers only its own paths."""

from httpfakes import FakeBackend, Live, call
from todoimpl.http import umbrella


def test_other_paths_are_not_umbrella_paths() -> None:
    backend = FakeBackend()
    assert umbrella.route("/api/board", backend) is None
    assert umbrella.route("/api/umbrella/abcd1234-0/other", backend) is None
    assert umbrella.route("/api/umbrella/abcd1234-0", backend) is not None


def test_t1909_a_note_id_without_an_index_is_an_umbrella_id(live: Live) -> None:
    """GET /api/umbrella/2d0704cd (an umbrella's own id8) was a 400 "ids must look like abcd1234-0"."""
    r = call(live.port, "GET", "/api/umbrella/ffffffff")
    assert (r.status, r.json()["error"]["code"]) == (404, "not_found")
