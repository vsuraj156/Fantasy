import os

from dotenv import load_dotenv
from espn_api.football import League

load_dotenv()


def get_league() -> League:
    return League(
        league_id=int(os.environ["LEAGUE_ID"]),
        year=int(os.environ.get("SEASON_YEAR", 2026)),
        espn_s2=os.environ["ESPN_S2"],
        swid=os.environ["ESPN_SWID"],
    )


def get_my_team(league: League):
    team_id = int(os.environ["TEAM_ID"])
    team = next((t for t in league.teams if t.team_id == team_id), None)
    if team is None:
        raise ValueError(f"No team with TEAM_ID={team_id} in this league")
    return team
