"""The umbrella path matcher answers only its own paths."""

from httpfakes import FakeBackend
from todoimpl.http import umbrella


def test_other_paths_are_not_umbrella_paths() -> None:
    backend = FakeBackend()
    assert umbrella.route("/api/board", backend) is None
    assert umbrella.route("/api/umbrella/abcd1234-0/other", backend) is None
    assert umbrella.route("/api/umbrella/abcd1234-0", backend) is not None
