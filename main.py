import argparse
import sys

from espn_client import get_league, get_my_team
from lineup import format_swaps, suggest_lineup_swaps
from notify import notify
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
    summary = format_swaps(swaps, week)
    print(summary)

    if not swaps:
        notify("lineup", summary)
        return

    def apply_fn() -> None:
        from browser_actions import set_lineup

        set_lineup(week, swaps)

    _finish("lineup", summary, apply, apply_fn, "lineup suggestions:", "lineup changes applied:")


def run_waivers(apply: bool) -> None:
    league = get_league()
    team = get_my_team(league)
    week = league.current_week

    suggestions = suggest_waivers(league, team, week)
    summary = format_waivers(suggestions, week)
    print(summary)

    if not suggestions:
        notify("waivers", summary)
        return

    def apply_fn() -> None:
        from browser_actions import claim_waivers

        claim_waivers([(s.add.name, s.drop.name) for s in suggestions])

    _finish("waivers", summary, apply, apply_fn, "waiver suggestions:", "waiver claims submitted:")


def run_trades() -> None:
    league = get_league()
    team = get_my_team(league)

    targets = suggest_trade_targets(league, team)
    summary = format_trade_targets(targets)
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
