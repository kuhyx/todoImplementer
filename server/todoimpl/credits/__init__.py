"""Free API credits fallback: the setting, the route a turn takes, the exhausted marker, the overage alert.

While the plan limit is active a turn runs on the Max plan's free monthly API credits (Claude Agent SDK, model
sonnet) instead of waiting. Stdlib only; the SDK itself lives in its own venv (`sdk.py`).
"""
