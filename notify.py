import os

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
