# ESPN Fantasy Football Automation

Reads your league/roster via the unofficial [`espn-api`](https://github.com/cwendt94/espn-api)
Python client, generates lineup/waiver/trade candidates from projection-based heuristics,
then hands that shortlist to Claude (`reasoning.py`) for a second pass — it uses web search
to check injury/inactive news, matchups, and usage trends before approving or rejecting
each candidate. For lineup + waivers, approved moves can then be applied by driving an
authenticated headless browser against fantasy.espn.com via Playwright. Sends a Slack
notification either way.

## 0. Anthropic API key

The reasoning layer needs `ANTHROPIC_API_KEY` (an [Anthropic API](https://platform.claude.com)
key) set in `.env` / repo secrets. If the model call fails or its response can't be parsed,
the scripts fail *closed* — nothing gets auto-approved, so a bad API day never results in
an unreviewed heuristic move going out via `--apply`; you'll just see it flagged for manual
review instead.

## 0.5. Cross-week memory (optional)

`memory.py` remembers what the reasoning layer decided about specific players across past
weeks (e.g. "held this injured player on waivers 3 weeks running") so future reviews aren't
starting cold every run. Since GitHub Actions runners are stateless, this needs external
storage — backed by [Upstash Redis](https://upstash.com) (free tier): create a database in
the Upstash console, copy its REST URL and token into `.env` as `UPSTASH_REDIS_REST_URL` and
`UPSTASH_REDIS_REST_TOKEN`. This is entirely optional — if unset, or a request fails, memory
is silently skipped (no history in, nothing recorded) rather than breaking anything.

## 1. Get your ESPN cookies

ESPN's private-league API needs two cookies from a logged-in browser session:

1. Log into [fantasy.espn.com](https://fantasy.espn.com) in Chrome.
2. Open DevTools -> Application -> Cookies -> `https://fantasy.espn.com`.
3. Copy the values of `espn_s2` and `SWID` (SWID includes the surrounding `{}`).

These cookies expire periodically (typically ~1 year, sometimes sooner) — if the
scripts start failing auth, re-extract them.

## 2. Find your league/team IDs

- `LEAGUE_ID`: in the URL when viewing your league, e.g.
  `.../leagueId=123456`.
- `TEAM_ID`: in the URL when viewing your team, e.g. `...&teamId=4`.

## 3. Local setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env   # then fill in your values
```

Test read-only suggestions first (no roster changes made):

```bash
python main.py lineup --dry-run
python main.py waivers --dry-run
python main.py trades
```

## 4. Slack notifications

Create a small personal Slack workspace just for this (so you have admin rights to
add webhooks, unlike a work Slack). Make three channels: `#lineup`, `#waivers`,
`#trades`. For each, add an "Incoming Webhook" (Slack -> your workspace -> Settings &
administration -> Manage apps -> search "Incoming Webhooks" -> Add to Slack -> pick
the channel). Put each resulting URL in `.env` as `SLACK_WEBHOOK_URL_LINEUP`,
`SLACK_WEBHOOK_URL_WAIVERS`, `SLACK_WEBHOOK_URL_TRADES`.

## 5. Verify the browser-write path before trusting it

**`set_lineup`'s selectors are verified** (2026-09-07, against a live authenticated
session) — the roster page uses a "select player to move, then click HERE on the
target row" flow, not a kebab menu, and a swap completes in one step (see the
docstring in `browser_actions.py`). **`claim_waivers`'s selectors are partially
verified** (2026-09-07) — the real "Claim {player}" and "Drop Player {name}"
buttons are confirmed, but the final Continue -> Submit step wasn't exercised
live (a submitted waiver claim isn't instantly reversible the way a lineup swap
is). Before enabling `waivers --apply` unattended:

1. Run once with `HEADLESS=false python main.py waivers --apply` during a low-stakes
   week and watch it actually execute in the visible browser window, paying
   particular attention to the final Continue/Submit step.
2. Only then turn on the scheduled GitHub Actions workflow.

(`lineup --apply` doesn't need this — its selectors are already verified — but a
supervised `HEADLESS=false` run before your first unattended `--apply` week is
still a reasonable sanity check.)

## 6. GitHub Actions (runs without your computer on)

In your repo: Settings -> Secrets and variables -> Actions -> New repository secret.
Add: `ESPN_S2`, `ESPN_SWID`, `LEAGUE_ID`, `TEAM_ID`, `SEASON_YEAR`,
`SLACK_WEBHOOK_URL_LINEUP`, `SLACK_WEBHOOK_URL_WAIVERS`, `SLACK_WEBHOOK_URL_TRADES`,
`ANTHROPIC_API_KEY`; optionally `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN`
for cross-week memory, and `SLACK_BOT_TOKEN` for conversational Q&A (section 7).

Four workflows in `.github/workflows/` run on a schedule (adjust the `cron` lines
to your league's actual game/waiver times — see comments in each file):

- `lineup-autoset.yml` — sets your lineup before Thursday/Sunday locks.
- `waivers.yml` — submits suggested waiver claims after processing.
- `trades.yml` — posts a weekly trade-target digest with a proposed give/get
  package and a ready-to-send pitch message per target (suggestion only; ESPN
  trades need the other manager's acceptance, so nothing is auto-proposed or
  auto-accepted — you copy the pitch and send it yourself).
- `emergency-check.yml` — a second, later Sunday check for starters ruled OUT
  with no healthy bench replacement (the main Sunday lineup run only looks at
  your own bench). Falls back to the free-agent pool and posts an alert to
  `#lineup` — **alert-only, never applies anything**, since it runs close to
  kickoff with no time for review.
- `slack-question.yml` — answers a question asked by @-mentioning the Slack
  bot (see section 7 below). Not on a schedule — triggered by a
  `repository_dispatch` from the Vercel relay function.

You can also trigger any of them manually from the Actions tab (`workflow_dispatch`).

## 7. Conversational Slack Q&A (optional)

@-mention the bot in Slack (e.g. "@FantasyBot why did you bench Isaiah Likely") and
get a reply in-thread, using the same reasoning/memory context as everything else.
This needs one extra piece the other flows don't: something to receive Slack's
incoming events. Slack requires an ack within 3 seconds, but a Claude+web-search
answer can take well over a minute, so the flow is split in two:

```
Slack @-mention -> Vercel function (verifies + acks instantly)
                 -> repository_dispatch -> GitHub Actions (does the actual work)
                 -> posts the answer back to Slack
```

**7a. Create the Slack app**

1. Go to [api.slack.com/apps](https://api.slack.com/apps) -> Create New App -> From scratch.
2. **OAuth & Permissions** -> Bot Token Scopes: add `app_mentions:read` and `chat:write`.
3. **Install App** to your workspace -> copy the **Bot User OAuth Token** (`xoxb-...`).
   This is `SLACK_BOT_TOKEN`.
4. **Basic Information** -> copy the **Signing Secret**. This is `SLACK_SIGNING_SECRET`.
5. Invite the bot to your channel (`/invite @YourBotName`).
6. Don't set up Event Subscriptions yet — that needs the Vercel URL from step 7c.

**7b. Create a GitHub token for the relay**

A classic personal access token with the `repo` scope (Settings -> Developer settings ->
Personal access tokens), used only to trigger `repository_dispatch` on this repo. This is
`GITHUB_DISPATCH_TOKEN`.

**7c. Deploy the Vercel relay function**

See `vercel-slack-relay/` in this repo. Full instructions for creating the Vercel project
are below.

**7d. Finish Slack Event Subscriptions**

Back in your Slack app -> **Event Subscriptions** -> enable -> set the Request URL to
`https://<your-vercel-project>.vercel.app/api/slack-events` (Slack will verify it live,
which the function handles). Under "Subscribe to bot events", add `app_mention`. Save,
and reinstall the app if prompted.

**7e. Add secrets**

- Repo secrets (GitHub): add `SLACK_BOT_TOKEN`.
- `.env` (only needed if you want to test `python main.py answer` locally): same var.
- Vercel project env vars: `SLACK_SIGNING_SECRET`, `GITHUB_REPO`, `GITHUB_DISPATCH_TOKEN`
  (see `vercel-slack-relay/README.md`).

## CLI reference

```
python main.py lineup     [--apply | --dry-run]   # default: --dry-run
python main.py waivers    [--apply | --dry-run]   # default: --dry-run
python main.py trades                             # always suggestion-only
python main.py emergency                          # always alert-only, never applies
python main.py answer                             # answers a Slack question (env-driven; not for direct use)
```
