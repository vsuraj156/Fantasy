"""
Playwright automation for ESPN roster writes.

IMPORTANT: ESPN's roster-edit page is a JS-driven, no-stable-DOM-contract UI, and
these selectors were written from general knowledge of the page's structure, not
verified against a live logged-in session (this environment has no ESPN account
credentials to test with). Before relying on --apply for real:

  1. Run `playwright codegen https://fantasy.espn.com/football/team?...` while
     logged in, manually do one swap, and diff the generated selectors against
     the SELECTORS map below.
  2. Test once with HEADLESS=false (see debug() below) and watch it run.

See README.md "Verification" section.
"""

import os
from contextlib import contextmanager
from typing import Iterable, Tuple

from playwright.sync_api import sync_playwright

SELECTORS = {
    "player_row": 'tr[class*="Table__TR"]:has-text("{player_name}")',
    "kebab_menu": 'button[aria-label="More options icon"]',
    "move_to_slot": 'li:has-text("{slot_label}")',
    "confirm_lineup_saved": 'text=Lineup Saved',
}

SLOT_LABEL_MAP = {
    "QB": "Move to QB",
    "RB": "Move to RB",
    "WR": "Move to WR",
    "TE": "Move to TE",
    "FLEX": "Move to FLEX",
    "D/ST": "Move to D/ST",
    "K": "Move to K",
    "BE": "Move to Bench",
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


def set_lineup(week: int, swaps) -> None:
    with _espn_page() as page:
        for swap in swaps:
            _move_player(page, swap.starter_out.name, "Move to Bench")
            slot_label = SLOT_LABEL_MAP.get(swap.slot, f"Move to {swap.slot}")
            _move_player(page, swap.bench_in.name, slot_label)


def claim_waivers(claims: Iterable[Tuple[str, str]]) -> None:
    with _espn_page() as page:
        for add_name, drop_name in claims:
            page.click('text="Add Player"')
            page.fill('input[placeholder="Search Players"]', add_name)
            page.click(f'tr:has-text("{add_name}") >> text="Add"')
            page.click(f'li:has-text("{drop_name}")')
            page.click('button:has-text("Continue")')
            page.click('button:has-text("Submit")')


def _move_player(page, player_name: str, slot_label: str) -> None:
    row = SELECTORS["player_row"].format(player_name=player_name)
    page.click(f'{row} >> {SELECTORS["kebab_menu"]}')
    page.click(SELECTORS["move_to_slot"].format(slot_label=slot_label))
