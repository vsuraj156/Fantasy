from dataclasses import dataclass
from typing import List

from lineup import _week_projection

MAX_SUGGESTIONS = 3
MIN_UPGRADE = 3.0


@dataclass
class WaiverSuggestion:
    add: object
    drop: object
    projected_upgrade: float


def _drop_candidates(team, week: int):
    bench = [p for p in team.roster if p.lineupSlot == "BE"]
    return sorted(bench, key=lambda p: _week_projection(p, week))


def suggest_waivers(league, team, week: int) -> List[WaiverSuggestion]:
    rostered_ids = {p.playerId for p in team.roster}
    free_agents = league.free_agents(week=week, size=50)
    free_agents = [p for p in free_agents if p.playerId not in rostered_ids]
    free_agents.sort(key=lambda p: _week_projection(p, week), reverse=True)

    drop_pool = _drop_candidates(team, week)
    suggestions: List[WaiverSuggestion] = []
    used_drop_ids = set()

    for candidate in free_agents:
        if len(suggestions) >= MAX_SUGGESTIONS:
            break

        drop = next(
            (
                d
                for d in drop_pool
                if d.playerId not in used_drop_ids
                and candidate.position in d.eligibleSlots
            ),
            None,
        )
        if drop is None:
            continue

        upgrade = _week_projection(candidate, week) - _week_projection(drop, week)
        if upgrade < MIN_UPGRADE:
            continue

        suggestions.append(WaiverSuggestion(candidate, drop, upgrade))
        used_drop_ids.add(drop.playerId)

    return suggestions


def format_waivers(suggestions: List[WaiverSuggestion], week: int) -> str:
    if not suggestions:
        return f"Week {week}: no waiver pickups worth making right now."
    lines = [f"Week {week} waiver suggestions:"]
    for s in suggestions:
        lines.append(
            f"- Add {s.add.name} ({s.add.position}), drop {s.drop.name} "
            f"(+{s.projected_upgrade:.1f} proj pts)"
        )
    return "\n".join(lines)
