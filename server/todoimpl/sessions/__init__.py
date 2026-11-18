"""Manual Claude Code sessions: a live index classified by the final status tag, and four guarded mutations.

Every interactive session ends its last assistant message on a status tag
(``DONE:``, ``NEEDS ACTION:``, ``D:``, ...). Reading that tag is what turns a
1000-row ``/resume`` list into "these three still need me". Headless runs
(``entrypoint`` sdk-cli / sdk-py, which is what the board starts) are not listed.

Deliberately not backed by a periodically refreshed store: a session list that
lags behind the terminal is wrong in exactly the case it exists for. The scan
reads the JSONL transcripts directly, cached per file version.

``tags``, ``parse``, ``scan``, ``markstore`` and ``api`` only read. The four
mutations (``resume`` in a terminal, ``mark`` done by hand, ``delete`` into a
recoverable trash, ``handoff`` to the board) sit behind the POST guard of ``todoimpl.http`` (same-origin
Origin plus CSRF token, like Ship). Ported from control-panel's sessions page.
"""
