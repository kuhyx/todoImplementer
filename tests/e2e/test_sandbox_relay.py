"""The sandbox relay links kuhy's relay credentials into the scratch HOME, again on every serve."""

from pathlib import Path

from sandbox_relay import LINKS, env


def test_t2620_a_link_the_server_replaced_with_a_file_is_linked_again(tmp_path: Path) -> None:
    real, work = tmp_path / "real", tmp_path / "work"
    for rel in LINKS:
        (real / rel).parent.mkdir(parents=True, exist_ok=True)
        (real / rel).write_text("real")
    assert env(work, "sandbox/slot2", real)["TODOIMPL_RELAY_NAMESPACE"] == "sandbox/slot2"
    link = work / "home" / LINKS[2]
    link.unlink()
    link.write_text("a token the sandbox server refreshed")  # an atomic save swaps the link for a file
    env(work, "sandbox/slot2", real)  # the next serve
    assert all((work / "home" / rel).is_symlink() for rel in LINKS)
    assert link.read_text() == "real"
