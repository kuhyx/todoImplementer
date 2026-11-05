"""Origin + CSRF token checks and the static site."""

from pathlib import Path

import pytest
from todoimpl.http.auth import DEFAULT_ORIGINS, check_post, new_token
from todoimpl.http.static import StaticSite

ORIGINS = ("http://127.0.0.1:8786", "https://agents.kuhy.duckdns.org")


def test_default_origins_are_the_two_known_ones() -> None:
    assert DEFAULT_ORIGINS == ORIGINS


def test_tokens_are_random_and_long() -> None:
    assert new_token() != new_token()
    assert len(new_token()) >= 32


@pytest.mark.parametrize("origin", ORIGINS)
def test_good_origin_and_token_pass(origin: str) -> None:
    assert check_post(origin, "tok", expected="tok", origins=ORIGINS) is None


@pytest.mark.parametrize(
    ("origin", "token", "why"),
    [
        (None, "tok", "origin"),
        ("https://evil.example", "tok", "origin"),
        ("http://127.0.0.1:8786/", "tok", "origin"),
        ("http://127.0.0.1:8786", None, "token"),
        ("http://127.0.0.1:8786", "wrong", "token"),
        ("http://127.0.0.1:8786", "", "token"),
    ],
)
def test_bad_origin_or_token_is_refused(origin: str | None, token: str | None, why: str) -> None:
    message = check_post(origin, token, expected="tok", origins=ORIGINS)
    assert message is not None
    assert why in message


def make_site(tmp_path: Path) -> StaticSite:
    (tmp_path / "_astro").mkdir()
    (tmp_path / "index.html").write_text("<html><head></head><body>x</body></html>", encoding="utf-8")
    (tmp_path / "_astro" / "a.js").write_text("1", encoding="utf-8")
    (tmp_path / "x.css").write_text("b{}", encoding="utf-8")
    (tmp_path / "blob.zzzunknown").write_bytes(b"\x00")
    (tmp_path.parent / "secret.txt").write_text("nope", encoding="utf-8")
    return StaticSite(tmp_path, token="T0K", build="b<1>")


def test_index_gets_both_meta_tags(tmp_path: Path) -> None:
    reply = make_site(tmp_path).serve("/")
    assert reply is not None
    html = reply.body.decode()
    assert '<meta name="todoimpl-csrf" content="T0K">' in html
    assert '<meta name="todoimpl-build" content="b&lt;1&gt;">' in html
    assert html.index("todoimpl-csrf") < html.index("</head>")
    assert reply.headers == (("Cache-Control", "no-store"),)
    assert reply.ctype.startswith("text/html")


def test_index_without_head_gets_metas_prepended(tmp_path: Path) -> None:
    site = make_site(tmp_path)
    (tmp_path / "index.html").write_text("<p>bare</p>", encoding="utf-8")
    reply = site.serve("/index.html")
    assert reply is not None
    assert reply.body.decode().startswith('<meta name="todoimpl-csrf"')


def test_hashed_assets_are_immutable_others_revalidate(tmp_path: Path) -> None:
    site = make_site(tmp_path)
    asset = site.serve("/_astro/a.js")
    other = site.serve("/x.css")
    assert asset is not None
    assert other is not None
    assert "immutable" in dict(asset.headers)["Cache-Control"]
    assert dict(other.headers)["Cache-Control"] == "no-cache"
    assert other.ctype.startswith("text/css")


def test_unknown_extension_is_octet_stream(tmp_path: Path) -> None:
    reply = make_site(tmp_path).serve("/blob.zzzunknown")
    assert reply is not None
    assert reply.ctype == "application/octet-stream"


@pytest.mark.parametrize(
    "path",
    ["/nope.js", "/_astro", "/../secret.txt", "/%2e%2e/secret.txt", "/_astro/../../secret.txt", "/a\x00b"],
)
def test_missing_directory_and_traversal_are_none(tmp_path: Path, path: str) -> None:
    assert make_site(tmp_path).serve(path) is None


def test_symlink_out_of_dist_is_none(tmp_path: Path) -> None:
    site = make_site(tmp_path)
    (tmp_path / "link.txt").symlink_to(tmp_path.parent / "secret.txt")
    assert site.serve("/link.txt") is None


def test_missing_index_is_none(tmp_path: Path) -> None:
    assert StaticSite(tmp_path, "t", "b").serve("/") is None


PLACEHOLDER = (
    '<html><head><meta charset="utf-8"><meta name="todoimpl-csrf" content="__TODOIMPL_CSRF__">'
    '<meta name="todoimpl-build" content="__TODOIMPL_BUILD__"><title>t</title></head><body></body></html>'
)


def test_t201_placeholder_metas_are_replaced_in_place(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text(PLACEHOLDER, encoding="utf-8")
    reply = StaticSite(tmp_path, token="T0K", build="b1").serve("/")
    assert reply is not None
    html = reply.body.decode()
    assert html.count('name="todoimpl-csrf"') == 1
    assert html.count('name="todoimpl-build"') == 1
    assert "__TODOIMPL" not in html
    assert html.index('name="todoimpl-csrf" content="T0K"') < html.index("<title>")
    assert 'name="todoimpl-build" content="b1"' in html


def test_t201_one_placeholder_only_still_gets_the_other_inserted(tmp_path: Path) -> None:
    page = '<head><meta name="todoimpl-csrf" content="__TODOIMPL_CSRF__"></head>'
    (tmp_path / "index.html").write_text(page, encoding="utf-8")
    html = StaticSite(tmp_path, token="T", build="b").serve("/").body.decode()  # type: ignore[union-attr]
    assert html.count("todoimpl-csrf") == 1
    assert html.count("todoimpl-build") == 1
