# HTTP and repo-path regressions

Ids are global and never reused; the row's test is named `test_t<N>_...`.

| Id | What went wrong | Test |
| --- | --- | --- |
| T201 | web/dist/index.html ships placeholder csrf/build meta tags; the server appended real ones after them and the page read the first (placeholder) one, so every POST got 403 | tests/http/test_http_auth.py |
| T202 | board.repo_checker looked for `$TODOIMPL_SRC/kuhyx/<name>` while runner worktree.repo_dir uses `$TODOIMPL_SRC/<name>`, so every real Start answered 409 | tests/board/test_board_repo_path.py |
| T203 | static.py 404ed `/usage` and `/usage/` (Astro emits usage/index.html) and only stamped the root index.html, so sub-pages had no csrf token or build id | tests/http/test_http_static_pages.py |
| T1400 | Nested live-check shots ("shots/live2/v1.png") 404ed: the route and backend.shot only served `<run>/shots/<basename>` | tests/service/test_service_backend.py |
