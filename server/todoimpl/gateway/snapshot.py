"""The gateway's raw answers as the contract's `free` object (contracts/free.schema.json).

Only whitelisted fields get through: a connection record also holds a masked API key and account ids, and
none of that may reach the page. What the gateway cannot tell stays out: a provider with no quota record
shows usage and cooldown state only (DOCS-tracking.md, "What it cannot show").
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

OK_STATUS = ("active", "ok", "success")
BAD_STATES = ("failing", "off")


def parse_time(text: object) -> float | None:
    """Return the epoch of an ISO timestamp, None when it is not one."""
    if not isinstance(text, str):
        return None
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def _num(value: object) -> float:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0.0


def _cooldown(conn: dict[str, Any]) -> float | None:
    health = (conn.get("providerSpecificData") or {}).get("apiKeyHealth")
    stamps = [conn.get("rateLimitedUntil")]
    stamps += (
        [k.get("cooldownUntil") for k in health.values() if isinstance(k, dict)]
        if isinstance(health, dict)
        else []
    )
    found = [t for t in map(parse_time, stamps) if t is not None]
    return max(found) if found else None


def connection_state(conn: dict[str, Any], now: float) -> tuple[str, float | None]:
    """Return (ok | cooling | failing | off, cooldown end) of one connection."""
    if conn.get("isActive") is False:
        return "off", None
    if conn.get("testStatus") not in OK_STATUS:
        return "failing", None
    until = _cooldown(conn)
    return ("cooling", until) if until is not None and until > now else ("ok", None)


def _provider_rows(connections: list[Any], now: float) -> list[dict[str, Any]]:
    """One row per provider name; the worst of its connections wins."""
    worst = {"ok": 0, "cooling": 1, "off": 2, "failing": 3}
    rows: dict[str, dict[str, Any]] = {}
    for conn in connections:
        if not isinstance(conn, dict):
            continue
        name = str(conn.get("name") or conn.get("provider") or "?")
        state, until = connection_state(conn, now)
        row = {"id": name, "state": state, "until": until, "failures": int(_num(conn.get("backoffLevel")))}
        kept = rows.get(name)
        if kept is None or worst[state] > worst[kept["state"]]:
            rows[name] = row
    return sorted(rows.values(), key=lambda r: r["id"])


def _quotas(raw: dict[str, Any], connections: list[Any]) -> list[dict[str, Any]]:
    """Remaining-quota rows, only where the gateway reports a real limit (a `total` above zero)."""
    names = {
        str(c.get("id")): str(c.get("name") or c.get("provider")) for c in connections if isinstance(c, dict)
    }
    out = []
    for conn_id, answer in raw.items():
        quotas = answer.get("quotas") if isinstance(answer, dict) else None
        if not isinstance(quotas, dict):
            continue
        for label, quota in quotas.items():
            total = _num(quota.get("total")) if isinstance(quota, dict) else 0.0
            if total <= 0 or quota.get("unlimited"):
                continue
            used = _num(quota.get("used"))
            out.append({
                "provider": names.get(conn_id, "?"), "label": str(label), "used": used, "total": total,
                "left_pct": max(0.0, min(100.0, 100.0 * (total - used) / total)),
                "reset_at": parse_time(quota.get("resetAt")),
            })  # fmt: skip
    return sorted(out, key=lambda q: (q["provider"], q["label"]))


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _step(step: dict[str, Any], targets: dict[str, Any], states: dict[str, str]) -> dict[str, Any]:
    """One link of the chain: the provider's state, else failing when the link's last call was not ok."""
    seen = _dict(targets.get(str(step.get("id"))))
    provider = str(step.get("providerId", "?"))
    state = states.get(provider, "ok")
    if state == "off" or (state == "ok" and seen.get("lastStatus") not in (None, "ok")):
        state = "failing"
    return {
        "provider": provider, "model": str(step.get("model", "?")), "state": state,
        "requests": int(_num(seen.get("requests"))),
        "ok_pct": _num(seen["successRate"]) if "successRate" in seen else None,
        "last": parse_time(seen.get("lastUsedAt")),
    }  # fmt: skip


def _combo(combos: object, metrics: object, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    first = next((c for c in _dict(combos).get("combos") or [] if isinstance(c, dict)), None)
    if first is None:
        return None
    name = str(first.get("name"))
    stats = _dict(_dict(_dict(metrics).get("metrics")).get(name))
    targets, states = _dict(stats.get("byTarget")), {r["id"]: r["state"] for r in rows}
    return {
        "name": name, "requests": int(_num(stats.get("totalRequests"))),
        "ok_pct": _num(stats["successRate"]) if "successRate" in stats else None,
        "fallback_pct": _num(stats["fallbackRate"]) if "fallbackRate" in stats else None,
        "steps": [_step(s, targets, states) for s in first.get("models") or [] if isinstance(s, dict)],
    }  # fmt: skip


def _tokens(analytics: object, now: float, ours: int | None) -> dict[str, Any] | None:
    trend = analytics.get("dailyTrend") if isinstance(analytics, dict) else None
    if not isinstance(trend, list):
        return None
    today = datetime.fromtimestamp(now, UTC).date().isoformat()
    day = next((d for d in trend if isinstance(d, dict) and d.get("date") == today), {})
    return {
        "in": int(_num(day.get("promptTokens"))), "out": int(_num(day.get("completionTokens"))),
        "requests": int(_num(day.get("requests"))), "ours": ours,
    }  # fmt: skip


def build(raw: dict[str, Any], now: float, ours: int | None = None) -> dict[str, Any]:
    """Return the `free` body (no at/state/error) from the raw answers; missing sections are null or empty."""
    providers = raw.get("providers")
    connections = providers.get("connections") if isinstance(providers, dict) else None
    connections = connections if isinstance(connections, list) else []
    rows = _provider_rows(connections, now)
    quotas = _quotas(raw.get("quotas") or {}, connections)
    health = raw.get("health")
    models = health.get("data") if isinstance(health, dict) else None
    models = [m for m in models or [] if isinstance(m, dict)]
    known = {q["provider"] for q in quotas}
    return {
        "tokens": _tokens(raw.get("analytics"), now, ours),
        "providers": [{**r, "quota": r["id"] in known} for r in rows],
        "quotas": quotas,
        "combo": _combo(raw.get("combos"), raw.get("metrics"), rows),
        "models": {"total": len(models), "cooling": sum(m.get("state") == "cooling" for m in models)},
        "counts": {
            "providers": len(rows), "ok": sum(r["state"] == "ok" for r in rows),
            "cooling": sum(r["state"] == "cooling" for r in rows),
            "failing": sum(r["state"] in BAD_STATES for r in rows), "quota_known": len(known),
        },
    }  # fmt: skip
