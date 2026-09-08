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

`claim_waivers`'s selectors are NOT yet verified against a live session (the
add/drop flow lives on a different page than the roster-move flow tested
above) — verify those the same way before trusting `waivers --apply` for
real. See README.md "Verify the browser-write path before trusting it".
"""

import os
from contextlib import contextmanager
from typing import Iterable, Tuple

from playwright.sync_api import sync_playwright

SELECTORS = {
    "move_button": 'button[aria-label="Select {player_name} to move"]',
    "here_button_in_row": 'tr:has-text("{player_name}") button:has-text("HERE")',
    "confirm_moves_saved": "text=Moves Saved",
}


def _team_url() -> str:
    league_id = os.environ["LEAGUE_ID"]
    team_id = os.environ["TEAM_ID"]
    year = os.environ.get("SEASON_YEAR", "2026")
    return (
        f"https://fantasy.espn.com/football/team"
        f"?leagueId={league_id}&teamId={team_id}&seasonId={year}"
    )


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
def _espn_page():
    headless = os.environ.get("HEADLESS", "true").lower() != "false"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = _authenticated_context(browser)
        page = context.new_page()
        page.goto(_team_url(), wait_until="networkidle")
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
    with _espn_page() as page:
        for add_name, drop_name in claims:
            page.click('text="Add Player"')
            page.fill('input[placeholder="Search Players"]', add_name)
            page.click(f'tr:has-text("{add_name}") >> text="Add"')
            page.click(f'li:has-text("{drop_name}")')
            page.click('button:has-text("Continue")')
            page.click('button:has-text("Submit")')
