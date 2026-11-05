"""Sub-pages of the Astro build: /usage and /usage/ resolve to usage/index.html, every .html is stamped."""

import pytest
from httpfakes import Live, call

PAGE = "<!doctype html><html><head><title>usage</title></head><body>usage page</body></html>"


@pytest.fixture
def usage_page(live: Live) -> Live:
    (live.dist / "usage").mkdir()
    (live.dist / "usage" / "index.html").write_text(PAGE, encoding="utf-8")
    (live.dist / "plain.html").write_text(PAGE, encoding="utf-8")
    return live


@pytest.mark.parametrize("path", ["/usage", "/usage/", "/usage/index.html", "/plain.html"])
def test_t203_subpages_are_served_and_stamped(usage_page: Live, path: str) -> None:
    r = call(usage_page.port, "GET", path)
    assert r.status == 200
    assert r.headers["content-type"].startswith("text/html")
    html = r.body.decode()
    assert f'name="todoimpl-csrf" content="{usage_page.token}"' in html
    assert 'name="todoimpl-build" content="abc1234"' in html
    assert "<title>usage</title>" in html
    assert r.headers["cache-control"] == "no-store"


def test_directory_without_index_is_404(live: Live) -> None:
    (live.dist / "empty").mkdir()
    assert call(live.port, "GET", "/empty").status == 404
    assert call(live.port, "GET", "/_astro").status == 404
