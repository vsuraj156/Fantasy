from dataclasses import dataclass
from typing import List, Optional

BENCH_SLOTS = {"BE", "IR"}
OUT_STATUSES = {"OUT", "DOUBTFUL", "INJURY_RESERVE", "SUSPENSION"}


@dataclass
class Swap:
    slot: str
    starter_out: object
    bench_in: object
    reason: str


def _week_projection(player, week: int) -> float:
    return player.stats.get(week, {}).get("projected_points", 0.0) or 0.0


def _needs_replacement(player, week: int) -> Optional[str]:
    if player.injuryStatus in OUT_STATUSES:
        return f"{player.injuryStatus.title().replace('_', ' ')}"
    if _week_projection(player, week) == 0.0:
        return "likely bye / no projection"
    return None


def suggest_lineup_swaps(team, week: int) -> List[Swap]:
    starters = [p for p in team.roster if p.lineupSlot not in BENCH_SLOTS]
    bench = [p for p in team.roster if p.lineupSlot == "BE"]

    swaps: List[Swap] = []
    used_bench_ids = set()

    for starter in starters:
        reason = _needs_replacement(starter, week)
        candidates = [
            b
            for b in bench
            if b.playerId not in used_bench_ids
            and starter.lineupSlot in b.eligibleSlots
            and _needs_replacement(b, week) is None
        ]
        if not candidates:
            continue
        candidates.sort(key=lambda p: _week_projection(p, week), reverse=True)
        best = candidates[0]

        if not reason:
            upgrade = _week_projection(best, week) - _week_projection(starter, week)
            if upgrade <= 1.0:
                continue
            reason = f"bench player projected {upgrade:.1f} pts higher"

        swaps.append(Swap(starter.lineupSlot, starter, best, reason))
        used_bench_ids.add(best.playerId)

    return swaps


def format_swaps(swaps: List[Swap], week: int) -> str:
    if not swaps:
        return f"Week {week}: lineup already optimal, no swaps suggested."
    lines = [f"Week {week} lineup suggestions:"]
    for s in swaps:
        lines.append(
            f"- [{s.slot}] bench {s.starter_out.name} -> start {s.bench_in.name} ({s.reason})"
        )
    return "\n".join(lines)


@dataclass
class EmergencyPickup:
    slot: str
    starter_out: object
    replacement: object
    reason: str


def find_emergency_replacements(league, team, week: int) -> List[EmergencyPickup]:
    """Starters needing replacement with no healthy bench option — the case
    suggest_lineup_swaps can't fix, because it only looks at your own bench.
    Falls back to the free-agent pool. Intended as a late, alert-only,
    Sunday-morning safety net; nothing here is auto-applied."""
    starters = [p for p in team.roster if p.lineupSlot not in BENCH_SLOTS]
    bench = [p for p in team.roster if p.lineupSlot == "BE"]
    rostered_ids = {p.playerId for p in team.roster}

    free_agents: Optional[list] = None

    def _free_agents():
        nonlocal free_agents
        if free_agents is None:
            free_agents = [
                p
                for p in league.free_agents(week=week, size=50)
                if p.playerId not in rostered_ids
            ]
        return free_agents

    pickups: List[EmergencyPickup] = []
    used_ids = set()

    for starter in starters:
        reason = _needs_replacement(starter, week)
        if not reason:
            continue

        has_bench_option = any(
            b.playerId not in used_ids
            and starter.lineupSlot in b.eligibleSlots
            and _needs_replacement(b, week) is None
            for b in bench
        )
        if has_bench_option:
            continue  # suggest_lineup_swaps already covers this case

        fa_candidates = [
            p
            for p in _free_agents()
            if p.playerId not in used_ids
            and starter.lineupSlot in p.eligibleSlots
            and _needs_replacement(p, week) is None
        ]
        if not fa_candidates:
            continue
        fa_candidates.sort(key=lambda p: _week_projection(p, week), reverse=True)
        best = fa_candidates[0]
        pickups.append(EmergencyPickup(starter.lineupSlot, starter, best, reason))
        used_ids.add(best.playerId)

    return pickups


def format_emergency(pickups: List[EmergencyPickup], week: int) -> str:
    if not pickups:
        return (
            f"Week {week}: no emergency replacements needed — every OUT/bye "
            "starter has a healthy bench option."
        )
    lines = [f"Week {week} EMERGENCY — no healthy bench replacement available:"]
    for p in pickups:
        lines.append(
            f"- [{p.slot}] {p.starter_out.name} is {p.reason} -> pick up "
            f"{p.replacement.name} ({p.replacement.position}) from free agency"
        )
    return "\n".join(lines)
