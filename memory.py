"""
Cross-week memory for the reasoning layer, backed by Upstash Redis.

GitHub Actions runners are stateless — every scheduled run starts in a fresh
container, so a pattern like "held this injured player on waivers three weeks
running" needs external storage to survive between runs. Upstash's REST API
means no client library and no server to manage: a single JSON blob (keyed by
player name) is read, updated, and written back around each reasoning-layer
call.

Requires UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN (free tier at
upstash.com). If either is unset, or a request fails, memory is skipped
entirely (empty history in, nothing recorded) rather than blocking the rest
of the pipeline — this is a context booster, not something the core flows
should break on.
"""

import json
import os
from typing import Iterable

import requests

MEMORY_KEY = "fantasy:memory"
MAX_EVENTS_PER_PLAYER = 8
_TIMEOUT = 5


def _redis_command(*args: str):
    url = os.environ.get("UPSTASH_REDIS_REST_URL")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    if not url or not token:
        return None
    try:
        resp = requests.post(
            url,
            json=list(args),
            headers={"Authorization": f"Bearer {token}"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json().get("result")
    except requests.RequestException:
        return None


def _load() -> dict:
    raw = _redis_command("GET", MEMORY_KEY)
    if not raw:
        return {"players": {}}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"players": {}}


def _save(memory: dict) -> None:
    _redis_command("SET", MEMORY_KEY, json.dumps(memory))


def record_decisions(kind: str, week: int, entries: Iterable[dict]) -> None:
    """`entries`: iterable of {"player": name, "approve": bool, "reason": str}."""
    memory = _load()
    players = memory.setdefault("players", {})
    for entry in entries:
        name = entry["player"]
        history = players.setdefault(name, [])
        history.append(
            {
                "week": week,
                "kind": kind,
                "approve": entry["approve"],
                "reason": entry.get("reason", ""),
            }
        )
        players[name] = history[-MAX_EVENTS_PER_PLAYER:]
    _save(memory)


def history_for(names: Iterable[str]) -> str:
    """Short text block summarizing past reasoning-layer decisions for the
    given player names, for injection into a prompt. Empty string if there's
    no history yet (including when memory storage isn't configured)."""
    memory = _load()
    players = memory.get("players", {})
    lines = []
    for name in dict.fromkeys(names):  # dedupe, preserve order
        events = players.get(name)
        if not events:
            continue
        recent = "; ".join(
            f"Week {e['week']} {e['kind']}: {'approved' if e['approve'] else 'rejected'}"
            + (f" ({e['reason']})" if e.get("reason") else "")
            for e in events
        )
        lines.append(f"{name} — {recent}")
    if not lines:
        return ""
    return "Recent history for these players from past weeks:\n" + "\n".join(lines)
