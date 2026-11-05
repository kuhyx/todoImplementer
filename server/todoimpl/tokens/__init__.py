"""Durable, zero-token store of Claude Code spend.

``ingest`` walks transcripts (reusing the ``audit`` parser, dedup and ``prices``) into SQLite
(``$TODOIMPL_TOKENS_DB``, default ``~/data/token-dashboard/tokens.sqlite``); readers only read it.
"""
