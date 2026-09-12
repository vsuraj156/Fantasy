"""
LLM reasoning layer on top of the deterministic candidate generators in
lineup.py / waivers.py / trades.py.

Those modules do cheap, threshold-based pre-filtering (projection deltas,
injury status flags) to produce a short list of plausible moves. This module
hands that shortlist to Claude, which uses web search to pull in context the
heuristics can't see — current injury reports, beat-writer news, opponent
matchup strength, recent usage trends — and decides which candidates to keep,
with a one-sentence rationale each plus an overall summary for Slack.

If the model call fails or its output can't be parsed, we fail CLOSED: no
candidate is treated as approved, so a bad API day (or a model response that
fails structured-output parsing) never results in an unreviewed heuristic
move going out via --apply. The raw model text, if any, is surfaced as the
summary so a human can still see what happened and act manually. This is a
deliberate asymmetry with "fail open" — the point of this layer is to gate
risky automated actions, so an inconclusive review must default to "don't
act," not "trust the heuristic anyway."
"""

import json
import re
from dataclasses import dataclass
from typing import Callable, List, Optional

import anthropic

MODEL = "claude-sonnet-5"

_client: Optional[anthropic.Anthropic] = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


@dataclass
class Decision:
    index: int
    approve: bool
    reason: str


@dataclass
class ReasonedPlan:
    decisions: List[Decision]
    summary: str


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("no JSON object found in model output")
    return json.loads(match.group(0))


def _run(system: str, user: str) -> str:
    runner = _get_client().beta.messages.tool_runner(
        model=MODEL,
        max_tokens=4096,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        tools=[{"type": "web_search_20260209", "name": "web_search"}],
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    final_text = ""
    for message in runner:
        if message.stop_reason == "end_turn":
            final_text = next(
                (b.text for b in message.content if b.type == "text"), ""
            )
    return final_text


def review_candidates(
    kind_description: str,
    week: int,
    count: int,
    describe: Callable[[int], str],
    guidance: str,
    reason_hint: str = "one sentence",
) -> ReasonedPlan:
    """Ask Claude to approve/reject each of `count` pre-filtered candidates.

    `describe(i)` returns a one-line description of candidate i (0-indexed).
    `guidance` is kind-specific instruction for what to research/weigh.
    """
    if count == 0:
        return ReasonedPlan(decisions=[], summary="")

    fallback = ReasonedPlan(
        decisions=[Decision(index=i, approve=False, reason="") for i in range(count)],
        summary="",
    )

    candidates = "\n".join(f"{i}. {describe(i)}" for i in range(count))

    system = (
        "You are a fantasy football analyst reviewing candidate "
        f"{kind_description} that were pre-filtered by a projection-based "
        "heuristic. " + guidance + " Use web search for anything time-sensitive "
        "(injury status, inactives, weather, beat-writer reports, recent "
        "snap counts) rather than relying on prior knowledge. Be decisive."
    )
    user = (
        f"Week {week} candidate {kind_description}:\n{candidates}\n\n"
        "Research each candidate as needed, then respond with ONLY a fenced "
        "```json code block containing an object of this exact shape:\n"
        '{"decisions": [{"index": 0, "approve": true, "reason": "' + reason_hint + '"}, '
        '...], "summary": "2-4 sentence overall summary suitable for a Slack '
        'message"}\n'
        "Include exactly one decision entry per candidate index listed above. "
        "The JSON must be strictly valid: escape every double quote inside a "
        "string with a backslash, or better, avoid embedding literal quote "
        "marks in reason/summary text entirely (paraphrase instead of quoting)."
    )

    try:
        text = _run(system, user)
    except anthropic.APIError as exc:
        fallback.summary = (
            f"AI review step failed ({exc}) — nothing was auto-approved. "
            "Review the heuristic candidates manually."
        )
        return fallback

    try:
        data = _extract_json(text)
        decisions = [
            Decision(
                index=int(d["index"]),
                approve=bool(d["approve"]),
                reason=str(d.get("reason", "")),
            )
            for d in data["decisions"]
        ]
        summary = str(data.get("summary", ""))
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        decisions = fallback.decisions
        summary = (
            "AI review step failed to parse a valid response — nothing was "
            "auto-approved. Raw model output for manual review:\n\n"
            + text.strip()
        )

    return ReasonedPlan(decisions=decisions, summary=summary)


def answer_question(question: str, context: str) -> str:
    """Conversational Q&A, used by the Slack app-mention flow (main.py's
    `answer` command). Reuses the same _run() tool-runner call as
    review_candidates, but returns plain text instead of parsed JSON — this
    is a chat reply, not a gated decision."""
    system = (
        "You are a fantasy football assistant answering a manager's question "
        "about their own team, in a Slack channel. Use the provided roster and "
        "decision-history context, plus web search for anything time-sensitive "
        "(injury news, matchups, recent performance, box scores). Answer "
        "directly and conversationally in 2-5 sentences — this is a chat "
        "reply, not a written report."
    )
    user = f"Team context:\n{context}\n\nQuestion: {question}"

    try:
        text = _run(system, user)
    except anthropic.APIError as exc:
        return f"Sorry, I couldn't look into that right now ({exc})."

    return text.strip() or "I looked into it but didn't come up with a clear answer — try rephrasing?"


def approved_items(items: list, plan: ReasonedPlan) -> list:
    approved_idx = {d.index for d in plan.decisions if d.approve}
    return [item for i, item in enumerate(items) if i in approved_idx]


def format_reasoned(kind_label: str, week: int, items: list, plan: ReasonedPlan, describe_item: Callable[[object], str]) -> str:
    reasons = {d.index: d.reason for d in plan.decisions}
    approved_idx = {d.index for d in plan.decisions if d.approve}
    approved = [(i, item) for i, item in enumerate(items) if i in approved_idx]

    if not approved:
        header = f"Week {week}: no {kind_label} approved after AI review."
        return f"{header}\n\n{plan.summary}" if plan.summary else header

    lines = [f"Week {week} {kind_label} (AI-reviewed):"]
    for i, item in approved:
        reason = reasons.get(i, "")
        suffix = f" — {reason}" if reason else ""
        lines.append(f"- {describe_item(item)}{suffix}")
    if plan.summary:
        lines.append("")
        lines.append(plan.summary)
    return "\n".join(lines)
