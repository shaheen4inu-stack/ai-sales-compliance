"""Batch-level reporting, computed in code. Reports by team, never by named rep.

Groups with fewer calls than `min_group_size` are suppressed so individuals cannot be singled out.
"""

from __future__ import annotations

from collections import Counter

from .analyze import CallResult
from .schemas import FINDING_TYPES, SEVERITY_ORDER


def summarise(results: list[CallResult], min_group_size: int = 5) -> dict:
    ok = [r for r in results if r.status == "ok"]
    findings = [f for r in ok for f in r.findings]
    by_type = Counter(f["type"] for f in findings)

    types = [
        {
            "type": t,
            "category": FINDING_TYPES[t][0],
            "severity": FINDING_TYPES[t][1],
            "route": FINDING_TYPES[t][2],
            "findings": by_type[t],
            "calls": sum(any(f["type"] == t for f in r.findings) for r in ok),
        }
        for t in FINDING_TYPES
        if by_type[t]
    ]
    types.sort(key=lambda x: (SEVERITY_ORDER[x["severity"]], -x["findings"]))

    groups: dict[str, list[dict]] = {}
    for key in sorted({k for r in results for k in r.segments}):
        rows = []
        for value in sorted({r.segments[key] for r in results if key in r.segments}):
            group = [r for r in results if r.segments.get(key) == value]
            if len(group) < min_group_size:
                rows.append({"value": value, "suppressed": True})
                continue
            rows.append(
                {
                    "value": value,
                    "suppressed": False,
                    "calls": len(group),
                    "clean": sum(r.outcome == "clean" for r in group),
                    "with_findings": sum(r.outcome in ("review", "escalate_legal") for r in group),
                    "pct_with_findings": round(100 * sum(bool(r.findings) for r in group) / len(group), 1),
                }
            )
        groups[key] = rows

    return {
        "calls": len(results),
        "reviewed": len(ok),
        "errors": sum(r.status == "error" for r in results),
        "outcomes": {o: sum(r.outcome == o for r in results) for o in ("clean", "review", "escalate_legal", "error")},
        "findings": len(findings),
        "unverified_findings": sum(r.unverified_findings for r in ok),
        "good_practice": sum(len(r.good_practice) for r in ok),
        "finding_types": types,
        "routes": {
            "legal": [r.id for r in results if r.outcome == "escalate_legal"],
            "compliance": [r.id for r in results if r.outcome == "review"],
            "manual_check": [r.id for r in results if r.status == "error"],
        },
        "min_group_size": min_group_size,
        "groups": groups,
    }


def render_markdown(s: dict, title: str = "Sales call compliance review") -> str:
    out = [
        f"# {title}",
        "",
        f"{s['calls']} calls, {s['reviewed']} reviewed, {s['errors']} failed (listed for manual checking).",
        "",
        "> Findings are possible issues for compliance or legal to review, not determinations. Every finding cites",
        "> a rep turn; quotes are verified against the transcript. Money amounts and percentages are masked in",
        "> competitor-pricing, confidential-disclosure and coordination findings.",
        "",
        "## Outcomes",
        "",
        "| Outcome | Calls |",
        "|---|---|",
        f"| Escalate to legal | {s['outcomes']['escalate_legal']} |",
        f"| Compliance review | {s['outcomes']['review']} |",
        f"| Clean | {s['outcomes']['clean']} |",
        f"| Failed (manual check) | {s['outcomes']['error']} |",
        "",
        f"{s['findings']} findings ({s['unverified_findings']} without verifiable evidence); "
        f"{s['good_practice']} instances of reps correctly declining competitor information.",
        "",
        "## Findings by type",
        "",
        "| Type | Category | Severity | Route | Findings | Calls |",
        "|---|---|---|---|---|---|",
    ]
    for t in s["finding_types"]:
        out.append(
            f"| {t['type']} | {t['category']} | {t['severity']} | {t['route']} | {t['findings']} | {t['calls']} |"
        )
    out += ["", "## Routing", ""]
    out.append(f"- **Legal** ({len(s['routes']['legal'])}): {', '.join(s['routes']['legal']) or 'none'}")
    out.append(f"- **Compliance** ({len(s['routes']['compliance'])}): {', '.join(s['routes']['compliance']) or 'none'}")
    out.append(f"- **Manual check** ({len(s['routes']['manual_check'])}): {', '.join(s['routes']['manual_check']) or 'none'}")
    out += ["", "## By group", "", f"Groups with fewer than {s['min_group_size']} calls are suppressed. No per-rep reporting.", ""]
    for key, rows in s["groups"].items():
        out += [f"**By {key}**", "", "| Value | Calls | Clean | With findings | % with findings |", "|---|---|---|---|---|"]
        for r in rows:
            if r["suppressed"]:
                out.append(f"| {r['value']} | suppressed | | | |")
            else:
                out.append(f"| {r['value']} | {r['calls']} | {r['clean']} | {r['with_findings']} | {r['pct_with_findings']}% |")
        out.append("")
    return "\n".join(out)
