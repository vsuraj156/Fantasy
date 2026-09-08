"""
Playwright automation for ESPN roster writes.

`set_lineup` is verified against a live authenticated session (2026-09-07).
The roster page does NOT use a kebab "more options" menu — every player row
(starter or bench) has a button labeled "Select {player name} to move".
Clicking it arms that player; every row it's eligible to move into then shows
a "HERE" button in the Action column in place of its own MOVE button — click
it to complete the move. This works identically whether the target row is
occupied (a swap: the two players trade slots) or empty. On success a green
banner reading "Moves Saved - ..." appears at the bottom of the page.

`claim_waivers` is partially verified (2026-09-07) against a live session: the
entry point is a full page at /football/players/add (not a modal, and not the
"Add Player" text button the old selectors assumed), where each free agent row
has a button labeled "Claim {player} {position} for {team}". Clicking it opens
a full-page claim form at /football/rosterfix, where each of your own players
has a button labeled "Drop Player {name}" (or "Can't drop {name}" if locked);
selecting one enables a "Continue" button. The "Continue" -> submit step past
that point was NOT exercised live (submitting a real claim isn't trivially
reversible the way a lineup swap is — it sits pending until your league's
waiver day) — do one supervised `HEADLESS=false python main.py waivers --apply`
run before trusting this on a schedule, per README.md "Verify the browser-write
path before trusting it".
"""

import os
from contextlib import contextmanager
from typing import Iterable, Tuple

from playwright.sync_api import sync_playwright

SELECTORS = {
    "move_button": 'button[aria-label="Select {player_name} to move"]',
    "here_button_in_row": 'tr:has-text("{player_name}") button:has-text("HERE")',
    "confirm_moves_saved": "text=Moves Saved",
    "claim_button": 'button[aria-label^="Claim {player_name} "]',
    "drop_button": 'button[aria-label="Drop Player {player_name}"]',
    "continue_button": 'button:has-text("Continue")',
    "submit_button": 'button:has-text("Submit")',
}


def _team_url() -> str:
    league_id = os.environ["LEAGUE_ID"]
    team_id = os.environ["TEAM_ID"]
    year = os.environ.get("SEASON_YEAR", "2026")
    return (
        f"https://fantasy.espn.com/football/team"
        f"?leagueId={league_id}&teamId={team_id}&seasonId={year}"
    )


def _add_player_url() -> str:
    league_id = os.environ["LEAGUE_ID"]
    year = os.environ.get("SEASON_YEAR", "2026")
    return f"https://fantasy.espn.com/football/players/add?leagueId={league_id}&seasonId={year}"


def _authenticated_context(browser):
    context = browser.new_context()
    context.add_cookies(
        [
            {
                "name": "espn_s2",
                "value": os.environ["ESPN_S2"],
                "domain": ".espn.com",
                "path": "/",
            },
            {
                "name": "SWID",
                "value": os.environ["ESPN_SWID"],
                "domain": ".espn.com",
                "path": "/",
            },
        ]
    )
    return context


@contextmanager
def _espn_page(start_url: str = None):
    headless = os.environ.get("HEADLESS", "true").lower() != "false"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = _authenticated_context(browser)
        page = context.new_page()
        page.goto(start_url or _team_url(), wait_until="networkidle")
        try:
            yield page
        finally:
            browser.close()


def _swap_players(page, from_player: str, to_player: str) -> None:
    """Arm `from_player`'s MOVE button, then click the HERE button that
    appears in `to_player`'s row to complete the swap between them."""
    page.click(SELECTORS["move_button"].format(player_name=from_player))
    page.click(SELECTORS["here_button_in_row"].format(player_name=to_player))
    page.wait_for_selector(SELECTORS["confirm_moves_saved"], timeout=10000)


def set_lineup(week: int, swaps) -> None:
    with _espn_page() as page:
        for swap in swaps:
            # Arming the starter and targeting the bench player swaps them
            # directly — the bench player takes the starter's slot and the
            # starter drops to bench, in one step.
            _swap_players(page, swap.starter_out.name, swap.bench_in.name)


def claim_waivers(claims: Iterable[Tuple[str, str]]) -> None:
    with _espn_page(start_url=_add_player_url()) as page:
        for add_name, drop_name in claims:
            page.click(SELECTORS["claim_button"].format(player_name=add_name))
            page.click(SELECTORS["drop_button"].format(player_name=drop_name))
            page.click(SELECTORS["continue_button"])
            # Not exercised live — verify this final submit step with one
            # supervised HEADLESS=false run before trusting it unattended.
            page.click(SELECTORS["submit_button"])
            page.goto(_add_player_url(), wait_until="networkidle")
