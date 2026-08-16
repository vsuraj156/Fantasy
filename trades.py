from collections import defaultdict
from dataclasses import dataclass
from typing import List

TRADEABLE_POSITIONS = {"QB", "RB", "WR", "TE"}
MAX_TARGETS = 3


@dataclass
class TradeTarget:
    position: str
    player: object
    team_name: str


def _my_weakest_positions(team) -> List[str]:
    starters_by_pos = defaultdict(list)
    for p in team.roster:
        if p.lineupSlot in ("BE", "IR"):
            continue
        if p.position in TRADEABLE_POSITIONS:
            starters_by_pos[p.position].append(p.total_points)

    avg_by_pos = {
        pos: sum(pts) / len(pts) for pos, pts in starters_by_pos.items() if pts
    }
    return sorted(avg_by_pos, key=avg_by_pos.get)


def _bench_candidates_by_position(league, team) -> dict:
    candidates = defaultdict(list)
    for other in league.teams:
        if other.team_id == team.team_id:
            continue
        for p in other.roster:
            if p.lineupSlot == "BE" and p.position in TRADEABLE_POSITIONS:
                candidates[p.position].append((p, other.team_name))

    for pos_candidates in candidates.values():
        pos_candidates.sort(key=lambda pair: pair[0].total_points, reverse=True)
    return candidates


def suggest_trade_targets(league, team) -> List[TradeTarget]:
    weak_positions = _my_weakest_positions(team)
    if not weak_positions:
        return []

    candidates_by_pos = _bench_candidates_by_position(league, team)

    targets: List[TradeTarget] = []
    for pos in weak_positions:
        for player, team_name in candidates_by_pos.get(pos, [])[:1]:
            targets.append(TradeTarget(pos, player, team_name))

        if len(targets) >= MAX_TARGETS:
            break

    return targets[:MAX_TARGETS]


def format_trade_targets(targets: List[TradeTarget]) -> str:
    if not targets:
        return "No clear trade targets this week."
    lines = ["Trade targets to consider (suggestion only, not auto-proposed):"]
    for t in targets:
        lines.append(
            f"- [{t.position}] {t.player.name} (benched on {t.team_name}, "
            f"{t.player.total_points:.1f} pts this season) - your weakest starting spot is {t.position}"
        )
    return "\n".join(lines)
