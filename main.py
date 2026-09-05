import argparse
import sys

from espn_client import get_league, get_my_team
from lineup import format_swaps, suggest_lineup_swaps
from notify import notify
from reasoning import approved_items, format_reasoned, review_candidates
from trades import format_trade_targets, suggest_trade_targets
from waivers import format_waivers, suggest_waivers


def _finish(
    channel: str, summary: str, apply: bool, apply_fn, dry_run_text: str, applied_text: str
) -> None:
    if apply:
        apply_fn()
        notify(channel, summary.replace(dry_run_text, applied_text))
    else:
        notify(channel, summary + "\n\n(dry run - nothing applied)")


def run_lineup(apply: bool) -> None:
    league = get_league()
    team = get_my_team(league)
    week = league.current_week

    swaps = suggest_lineup_swaps(team, week)
    if not swaps:
        summary = format_swaps(swaps, week)
        print(summary)
        notify("lineup", summary)
        return

    plan = review_candidates(
        "lineup swaps",
        week,
        len(swaps),
        lambda i: (
            f"[{swaps[i].slot}] bench {swaps[i].starter_out.name} "
            f"({swaps[i].starter_out.position}, {swaps[i].starter_out.proTeam}, "
            f"injury={swaps[i].starter_out.injuryStatus}) -> start "
            f"{swaps[i].bench_in.name} ({swaps[i].bench_in.position}, "
            f"{swaps[i].bench_in.proTeam}, injury={swaps[i].bench_in.injuryStatus}) "
            f"— heuristic reason: {swaps[i].reason}"
        ),
        "Decide whether each proposed start/bench swap is still correct given "
        "the latest injury/inactive news and this week's matchups.",
    )
    approved = approved_items(swaps, plan)
    summary = format_reasoned(
        "lineup swaps",
        week,
        swaps,
        plan,
        lambda s: f"[{s.slot}] bench {s.starter_out.name} -> start {s.bench_in.name}",
    )
    print(summary)

    if not approved:
        notify("lineup", summary)
        return

    def apply_fn() -> None:
        from browser_actions import set_lineup

        set_lineup(week, approved)

    _finish(
        "lineup",
        summary,
        apply,
        apply_fn,
        "lineup swaps (AI-reviewed):",
        "lineup changes applied (AI-reviewed):",
    )


def run_waivers(apply: bool) -> None:
    league = get_league()
    team = get_my_team(league)
    week = league.current_week

    suggestions = suggest_waivers(league, team, week)
    if not suggestions:
        summary = format_waivers(suggestions, week)
        print(summary)
        notify("waivers", summary)
        return

    plan = review_candidates(
        "waiver pickups",
        week,
        len(suggestions),
        lambda i: (
            f"Add {suggestions[i].add.name} ({suggestions[i].add.position}, "
            f"{suggestions[i].add.proTeam}, injury={suggestions[i].add.injuryStatus}), "
            f"drop {suggestions[i].drop.name} ({suggestions[i].drop.position}, "
            f"{suggestions[i].drop.proTeam}) — heuristic projected upgrade: "
            f"+{suggestions[i].projected_upgrade:.1f} pts"
        ),
        "Decide whether each proposed add/drop is still worth making given "
        "the latest injury news, role/usage trends, and matchup for the add.",
    )
    approved = approved_items(suggestions, plan)
    summary = format_reasoned(
        "waiver pickups",
        week,
        suggestions,
        plan,
        lambda s: f"Add {s.add.name} ({s.add.position}), drop {s.drop.name}",
    )
    print(summary)

    if not approved:
        notify("waivers", summary)
        return

    def apply_fn() -> None:
        from browser_actions import claim_waivers

        claim_waivers([(s.add.name, s.drop.name) for s in approved])

    _finish(
        "waivers",
        summary,
        apply,
        apply_fn,
        "waiver pickups (AI-reviewed):",
        "waiver claims submitted (AI-reviewed):",
    )


def run_trades() -> None:
    league = get_league()
    team = get_my_team(league)
    week = league.current_week

    targets = suggest_trade_targets(league, team)
    if not targets:
        summary = format_trade_targets(targets)
        print(summary)
        notify("trades", summary)
        return

    plan = review_candidates(
        "trade targets",
        week,
        len(targets),
        lambda i: (
            f"[{targets[i].position}] {targets[i].player.name} "
            f"(benched on {targets[i].team_name}, "
            f"{targets[i].player.total_points:.1f} pts this season)"
        ),
        "Decide whether each trade target is genuinely worth pursuing given "
        "current injury status, role, and rest-of-season outlook — this is "
        "suggestion-only, never auto-proposed to the other manager.",
    )
    summary = format_reasoned(
        "trade targets",
        week,
        targets,
        plan,
        lambda t: f"[{t.position}] {t.player.name} (benched on {t.team_name})",
    )
    print(summary)
    notify("trades", summary)


def _add_apply_flags(parser: argparse.ArgumentParser, apply_help: str) -> None:
    apply_group = parser.add_mutually_exclusive_group()
    apply_group.add_argument("--apply", action="store_true", help=apply_help)
    apply_group.add_argument("--dry-run", action="store_true", help="Only print/notify suggestions (default)")


def main() -> None:
    parser = argparse.ArgumentParser(description="ESPN Fantasy Football automation")
    subparsers = parser.add_subparsers(dest="command", required=True)

    lineup_parser = subparsers.add_parser("lineup", help="Suggest/apply lineup swaps")
    _add_apply_flags(lineup_parser, "Apply suggested swaps via browser automation")

    waivers_parser = subparsers.add_parser("waivers", help="Suggest/apply waiver claims")
    _add_apply_flags(waivers_parser, "Submit suggested waiver claims via browser automation")

    subparsers.add_parser("trades", help="Suggest trade targets (suggestion only, never auto-applied)")

    args = parser.parse_args()

    if args.command == "lineup":
        run_lineup(apply=args.apply)
    elif args.command == "waivers":
        run_waivers(apply=args.apply)
    elif args.command == "trades":
        run_trades()


if __name__ == "__main__":
    sys.exit(main())
