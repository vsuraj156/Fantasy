"""
Slack Events API receiver, deployed as a Vercel serverless function.

Slack requires an ack within 3 seconds, but answering a fantasy-football
question (Claude + web search) can take well over a minute — far longer than
this function is allowed to run. So this function does the minimum needed to
satisfy Slack and hands the real work off to GitHub Actions, which has no
such tight time limit: verify the request signature, extract the question,
trigger a `repository_dispatch` event on the Fantasy repo, and return 200.
The actual answer is generated and posted back to Slack by
`.github/workflows/slack-question.yml` in that repo (main.py's `answer`
command), reusing the same reasoning/memory code as every other flow.

Only stdlib is used deliberately — no requirements.txt, no dependency install,
fast cold starts.
"""

import hashlib
import hmac
import json
import os
import time
import urllib.request
from http.server import BaseHTTPRequestHandler


def _verify_signature(headers, body: bytes) -> bool:
    signing_secret = os.environ["SLACK_SIGNING_SECRET"]
    timestamp = headers.get("X-Slack-Request-Timestamp", "")
    slack_signature = headers.get("X-Slack-Signature", "")

    try:
        # Reject old requests to guard against replay attacks.
        if abs(time.time() - int(timestamp)) > 60 * 5:
            return False
    except ValueError:
        return False

    basestring = f"v0:{timestamp}:{body.decode('utf-8')}".encode("utf-8")
    computed = "v0=" + hmac.new(
        signing_secret.encode("utf-8"), basestring, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(computed, slack_signature)


def _dispatch_to_github(text: str, channel: str, thread_ts: str) -> None:
    repo = os.environ["GITHUB_REPO"]  # e.g. "vsuraj156/Fantasy"
    token = os.environ["GITHUB_DISPATCH_TOKEN"]
    url = f"https://api.github.com/repos/{repo}/dispatches"
    payload = json.dumps(
        {
            "event_type": "slack_question",
            "client_payload": {
                "text": text,
                "channel": channel,
                "thread_ts": thread_ts,
            },
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
    )
    urllib.request.urlopen(req, timeout=8)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        if not _verify_signature(self.headers, body):
            self.send_response(401)
            self.end_headers()
            return

        data = json.loads(body or b"{}")

        # First-time setup: Slack verifies the endpoint by echoing this back.
        if data.get("type") == "url_verification":
            self._respond_json({"challenge": data.get("challenge", "")})
            return

        # Ignore Slack's automatic retries (e.g. if our first ack was slow) —
        # we've already dispatched once, a second answer would be confusing.
        if self.headers.get("X-Slack-Retry-Num"):
            self.send_response(200)
            self.end_headers()
            return

        event = data.get("event", {})
        if data.get("type") == "event_callback" and event.get("type") == "app_mention":
            text = event.get("text", "")
            channel = event.get("channel", "")
            thread_ts = event.get("thread_ts") or event.get("ts", "")
            try:
                _dispatch_to_github(text, channel, thread_ts)
            except Exception:
                # Ack anyway — Slack shouldn't retry indefinitely on our error.
                pass

        self.send_response(200)
        self.end_headers()

    def _respond_json(self, obj) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
