"""Per-call compliance review.

Design rules:
- Every finding must cite a rep turn and a quote that appears word for word in that turn.
  Findings that fail this are kept but marked unverified, so a person checks the recording.
- Severity and routing come from the finding type, in code. The model never chooses them.
- Money amounts and percentages are masked in quotes and explanations of competitor-pricing,
  confidential-disclosure and coordination findings, and in summaries. The tool flags the
  conversation; it never collects competitor or customer pricing.
- Everything is a possible issue for compliance or legal to review, not a determination.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Literal

from .engine import Engine
from .guardrails import mask_figures
from .policy import load_policy, render_policy
from .schemas import FINDING_TYPES, MASKED_TYPES, SEVERITY_ORDER, Call, ModelReview

SYSTEM = (
    "You review sales call transcripts for a compliance team. You identify possible issues in what "
    "the sales rep says, citing the exact turn and an exact quote. You only report what the transcript "
    "shows; you never assume. Statements by the customer are never findings against the rep. "
    "Do not repeat any competitor's prices, discounts or other figures in your explanations or summary."
)

USER_TEMPLATE = """<policy>
{policy}
</policy>

<transcript>
{transcript}
</transcript>

Finding types (report only REP behaviour):
- absolute_guarantee: the rep promises an outcome as certain or absolute ("guaranteed", "never", "zero
  downtime"). A rep explicitly saying they cannot promise something is NOT a finding.
- unapproved_claim: a factual claim about the seller's product, certifications or capabilities that is
  not in the approved claims, or is materially stronger than an approved claim.
- misstated_terms: the rep states prices, contract terms, support levels or discount authority that
  contradict the commercial terms.
- false_competitor_statement: the rep states as fact something negative about a competitor that is not
  supported. Clearly framed personal opinions ("I find their interface clunky") are not findings.
- solicited_competitor_pricing: the rep asks for a competitor's quote, proposal, prices or discount, in
  any form (including "ballpark is fine" or "forward me their proposal").
- used_volunteered_competitor_pricing: the customer offers competitor pricing and the rep asks for more
  detail, asks for the document, or builds an offer on it.
- confidential_disclosure: the rep reveals another customer's prices, discounts or contract terms.
- possible_coordination: anything suggesting contact, agreement or understanding with a competitor about
  prices, discounts, customers or territories.

Good practice (report when present):
- declined_competitor_information: the customer offers or mentions a competitor's confidential pricing and
  the rep explicitly declines it or asks them not to share it.

Referring to a competitor's publicly listed price is not a finding.

Return ONLY a JSON object with exactly these keys:
- summary (one or two sentences, no figures)
- findings (array of objects with type, turn (the T number), quote (exact words from that turn),
  explanation (one sentence))
- good_practice (array of objects with type, turn, quote)
Return empty arrays when there is nothing to report."""


def _norm(text: str) -> str:
    text = text.lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip()


def quote_in(quote: str | None, text: str) -> bool:
    """True if the quote appears in the text as whole words, ignoring case, whitespace and curly
    quotes. Whole-word matching stops fragments like "x" verifying against "next"."""
    if not quote or not quote.strip():
        return False
    q = _norm(quote).strip(" .,'\"")
    if not q:
        return False
    return re.search(r"(?<!\w)" + re.escape(q) + r"(?!\w)", _norm(text)) is not None


def render_transcript(turns: list[tuple[str, str]]) -> str:
    return "\n".join(f"[T{i}] {speaker.upper()}: {text}" for i, (speaker, text) in enumerate(turns, 1))


@dataclass
class CallResult:
    id: str
    status: Literal["ok", "error"]
    outcome: Literal["clean", "review", "escalate_legal", "error"]
    summary: str | None = None
    findings: list[dict] = field(default_factory=list)
    good_practice: list[dict] = field(default_factory=list)
    unverified_findings: int = 0
    dropped_findings: int = 0
    redactions: dict[str, int] = field(default_factory=dict)
    segments: dict[str, str] = field(default_factory=dict)
    review_reasons: list[str] = field(default_factory=list)
    error: str | None = None
    meta: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def get_policy_text(engine: Engine) -> str:
    cache = engine.__dict__.setdefault("_policy_cache", {})
    path = engine.config.get("policy", {}).get("path", "data/policy.yaml")
    if path not in cache:
        cache[path] = render_policy(load_policy(path))
    return cache[path]


def review_call(engine: Engine, call: Call) -> CallResult:
    turns: list[tuple[str, str]] = []
    redactions: dict[str, int] = {}
    for t in call.turns:
        text, counts = engine.guard(t.text)
        turns.append((t.speaker, text))
        for k, v in counts.items():
            redactions[k] = redactions.get(k, 0) + v
    engine.guard("\n".join(text for _, text in turns))  # total size limit

    prompt = USER_TEMPLATE.format(policy=get_policy_text(engine), transcript=render_transcript(turns))
    review, meta = engine.call_json(SYSTEM, prompt, ModelReview)

    findings, unverified, dropped = [], 0, 0
    seen: set[tuple[str, int]] = set()
    for f in review.findings:
        key = (f.type, f.turn)
        if key in seen:
            continue
        seen.add(key)
        in_range = 1 <= f.turn <= len(turns)
        if in_range and turns[f.turn - 1][0] == "customer":
            dropped += 1  # customers' statements are never findings against the rep
            continue
        verified = in_range and quote_in(f.quote, turns[f.turn - 1][1])
        unverified += not verified
        category, severity, route = FINDING_TYPES[f.type]
        masked = f.type in MASKED_TYPES
        findings.append(
            {
                "type": f.type,
                "category": category,
                "severity": severity,
                "route": route,
                "turn": f.turn,
                "quote": mask_figures(f.quote) if masked else f.quote,
                "explanation": mask_figures(f.explanation) if masked else f.explanation,
                "evidence_verified": verified,
            }
        )
    findings.sort(key=lambda x: (SEVERITY_ORDER[x["severity"]], x["turn"]))

    good = []
    for g in review.good_practice:
        ok = 1 <= g.turn <= len(turns) and turns[g.turn - 1][0] == "rep" and quote_in(g.quote, turns[g.turn - 1][1])
        if ok:
            good.append({"type": g.type, "turn": g.turn, "quote": mask_figures(g.quote)})

    reasons = [f"{f['severity'].title()}: {f['type'].replace('_', ' ')} at T{f['turn']}" for f in findings]
    if unverified:
        reasons.append(f"{unverified} finding(s) without a verifiable quote; check the recording")
    if dropped:
        reasons.append(f"{dropped} finding(s) citing customer turns were discarded")

    if any(f["route"] == "legal" for f in findings):
        outcome = "escalate_legal"
    elif findings:
        outcome = "review"
    else:
        outcome = "clean"

    return CallResult(
        id=call.id,
        status="ok",
        outcome=outcome,
        summary=mask_figures(review.summary),
        findings=findings,
        good_practice=good,
        unverified_findings=unverified,
        dropped_findings=dropped,
        redactions=redactions,
        segments=dict(call.segments),
        review_reasons=reasons,
        meta=asdict(meta),
    )


def error_result(call: Call, exc: Exception) -> CallResult:
    meta = getattr(exc, "meta", None)
    return CallResult(
        id=call.id,
        status="error",
        outcome="error",
        segments=dict(call.segments),
        review_reasons=["Review failed; check this call manually"],
        error=f"{type(exc).__name__}: {exc}"[:300],
        meta=asdict(meta) if meta else None,
    )
