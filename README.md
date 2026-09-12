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
`ANTHROPIC_API_KEY`, and (optional) `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN`
for cross-week memory.

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

You can also trigger any of them manually from the Actions tab (`workflow_dispatch`).

## CLI reference

```
python main.py lineup     [--apply | --dry-run]   # default: --dry-run
python main.py waivers    [--apply | --dry-run]   # default: --dry-run
python main.py trades                             # always suggestion-only
python main.py emergency                          # always alert-only, never applies
```
