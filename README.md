# ESPN Fantasy Football Automation

Reads your league/roster via the unofficial [`espn-api`](https://github.com/cwendt94/espn-api)
Python client, generates lineup/waiver/trade suggestions, and (for lineup + waivers) can
apply them by driving an authenticated headless browser against fantasy.espn.com via
Playwright. Sends a Slack notification either way.

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

`browser_actions.py`'s selectors are written from general knowledge of ESPN's roster
page, not verified against a live session (no test account was available while
building this). Before enabling `--apply` for real:

1. Log in locally, run `playwright codegen "https://fantasy.espn.com/football/team?leagueId=<id>&teamId=<id>&seasonId=<year>"`,
   manually perform one bench/start swap, and compare the generated selectors to
   `SELECTORS` / `SLOT_LABEL_MAP` in `browser_actions.py`. Fix any mismatches.
2. Run once with `HEADLESS=false python main.py lineup --apply` during a low-stakes
   week and watch it actually execute in the visible browser window.
3. Only then turn on the scheduled GitHub Actions workflow.

## 6. GitHub Actions (runs without your computer on)

In your repo: Settings -> Secrets and variables -> Actions -> New repository secret.
Add: `ESPN_S2`, `ESPN_SWID`, `LEAGUE_ID`, `TEAM_ID`, `SEASON_YEAR`,
`SLACK_WEBHOOK_URL_LINEUP`, `SLACK_WEBHOOK_URL_WAIVERS`, `SLACK_WEBHOOK_URL_TRADES`.

Three workflows in `.github/workflows/` run on a schedule (adjust the `cron` lines
to your league's actual game/waiver times — see comments in each file):

- `lineup-autoset.yml` — sets your lineup before Thursday/Sunday locks.
- `waivers.yml` — submits suggested waiver claims after processing.
- `trades.yml` — posts a weekly trade-target digest (suggestion only; ESPN trades
  need the other manager's acceptance, so nothing is auto-proposed or auto-accepted).

You can also trigger any of them manually from the Actions tab (`workflow_dispatch`).

## CLI reference

```
python main.py lineup  [--apply | --dry-run]   # default: --dry-run
python main.py waivers [--apply | --dry-run]   # default: --dry-run
python main.py trades                          # always suggestion-only
```
