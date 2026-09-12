import os
from typing import Optional

import requests

_WEBHOOK_ENV = {
    "lineup": "SLACK_WEBHOOK_URL_LINEUP",
    "waivers": "SLACK_WEBHOOK_URL_WAIVERS",
    "trades": "SLACK_WEBHOOK_URL_TRADES",
}


def notify(channel: str, text: str) -> None:
    env_var = _WEBHOOK_ENV[channel]
    url = os.environ.get(env_var)
    if not url:
        print(f"[notify:{channel}] {env_var} not set, skipping Slack post:\n{text}")
        return
    resp = requests.post(url, json={"text": text}, timeout=10)
    resp.raise_for_status()


def reply_in_thread(channel: str, thread_ts: Optional[str], text: str) -> None:
    """Post a conversational reply via the Slack Web API (chat.postMessage),
    as used by the app-mention Q&A flow — distinct from `notify`, which only
    posts to a fixed channel via an incoming webhook and can't reply in a
    specific thread. Requires a bot token (SLACK_BOT_TOKEN), not a webhook."""
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        print(f"[notify:reply] SLACK_BOT_TOKEN not set, skipping Slack reply:\n{text}")
        return
    payload = {"channel": channel, "text": text}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    resp = requests.post(
        "https://slack.com/api/chat.postMessage",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        print(f"[notify:reply] Slack API error: {data.get('error')}")
