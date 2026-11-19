# HTTP and repo-path regressions

Ids are global and never reused; the row's test is named `test_t<N>_...`.

| Id | What went wrong | Test |
| --- | --- | --- |
| T201 | web/dist/index.html ships placeholder csrf/build meta tags; the server appended real ones after them and the page read the first (placeholder) one, so every POST got 403 | tests/http/test_http_auth.py |
| T202 | board.repo_checker looked for `$TODOIMPL_SRC/kuhyx/<name>` while runner worktree.repo_dir uses `$TODOIMPL_SRC/<name>`, so every real Start answered 409 | tests/board/test_board_repo_path.py |
| T203 | static.py 404ed `/usage` and `/usage/` (Astro emits usage/index.html) and only stamped the root index.html, so sub-pages had no csrf token or build id | tests/http/test_http_static_pages.py |
| T1400 | Nested live-check shots ("shots/live2/v1.png") 404ed: the route and backend.shot only served `<run>/shots/<basename>` | tests/service/test_service_backend.py |
| T1855 | The free-credits toggle is not task-scoped: POST /api/settings/credits-fallback must pass the same Origin and CSRF checks and a strict body | tests/http/test_http_settings.py |
| T2218 | The board had no way to pick a card's model or to show it: every run card now carries a `model` action (choices from the server, `value` = the pin or `default`, disabled while shipping) and the card's `model` (the pin, else the latest turn's), and `POST /api/task/<id>/model {model}` (relay kind `task_model`) takes a known id or `default` only | tests/board/test_board_model.py, tests/http/test_http_model.py |
| T2320 | Send to Claude took text only, so kuhy described screenshots by hand: the box now takes pasted and picked png/jpeg/webp/gif images (10 MB each, 8 per message) as `#N` chips that insert `[Image #N]`; the send POST carries `images: [{upload}]`, the server copies each into `<run>/inbox/<ms>-N.<ext>` and the note names each absolute path (a refused send keeps the staged files) | tests/service/test_service_send_images.py, tests/http/test_http_send_images.py, web/src/components/send-images.test.ts |
| T2321 | The New task form's images reached the note unnumbered, so the details could not say which picture they meant: image files are now `#N` chips that insert `[Image #N]`, go as `new_task.images: [{upload}]` (other files stay `files`), and the note writes `[Image #N]` above each image link (image() files no longer post as `files`) | tests/service/test_service_newtask_images.py, tests/http/test_http_send_images.py, web/src/components/new-task-images.test.ts |
| T2322 | A phone cannot stream `/api/upload` through the relay, so `image_ref` also takes inline `{data_b64}` (png/jpeg/webp/gif, 6 MB) for `send` and `new_task`, and both the route and the relay give `/send` the 40 MB new-task body cap instead of 256 KB | tests/http/test_http_send_images.py, tests/relay/test_guards.py |
