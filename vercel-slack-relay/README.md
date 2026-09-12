# Slack Events Relay

A single stdlib-only Vercel Python function. It exists only to satisfy Slack's
3-second ack requirement — it verifies the request, extracts the question from
an `app_mention` event, and triggers a `repository_dispatch` on the main
`Fantasy` repo, which does the actual work (Claude + web search can take well
over a minute). See `api/slack-events.py`'s docstring for the full flow, and
the main repo's README for end-to-end setup instructions (Slack app creation,
GitHub token, Vercel project, environment variables).

Deployed as its own Vercel project with **Root Directory** set to
`vercel-slack-relay` (this is a subdirectory of the main repo, not a separate
repo) — the parent repo's Python dependencies (playwright, espn-api, etc.)
have nothing to do with this function and shouldn't be installed for it.

## Environment variables (set in the Vercel project, not `.env`)

- `SLACK_SIGNING_SECRET` — from the Slack app's Basic Information page
- `GITHUB_REPO` — e.g. `yourusername/Fantasy`
- `GITHUB_DISPATCH_TOKEN` — a GitHub personal access token with permission to
  trigger `repository_dispatch` on that repo (classic PAT with `repo` scope,
  or a fine-grained PAT with Contents: Read and write + Actions: Read and write)
