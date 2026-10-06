"""Deterministic scoring against ground truth.

A predicted finding matches an expected one when the type and the turn are the same.
Recall is the headline (a missed breach is the costly error); the false-flag rate on clean calls
matters almost as much, because a false finding is an accusation against a rep.
"""

from __future__ import annotations

import json
import re

from sales_compliance.schemas import FINDING_TYPES

CATEGORIES = sorted({c for c, _, _ in FINDING_TYPES.values()})


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


def leaked_figures(pred: dict, sensitive: list[str]) -> list[str]:
    """Sensitive figures from the transcript that appear anywhere in the tool's output."""
    blob = _norm(json.dumps({k: v for k, v in pred.items() if k != "meta"}))
    return [s for s in sensitive if _norm(s) in blob]


def score_call(pred: dict, label: dict) -> dict:
    exp = {(f["type"], f["turn"]) for f in label["expected"]["findings"]}
    got = {(f["type"], f["turn"]) for f in pred.get("findings") or []} if pred["status"] == "ok" else set()
    exp_good = {(g["type"], g["turn"]) for g in label["expected"]["good_practice"]}
    got_good = {(g["type"], g["turn"]) for g in pred.get("good_practice") or []}
    wrong_turn = {t for t, _ in got - exp} & {t for t, _ in exp - got}
    return {
        "status": pred["status"],
        "tp": sorted(exp & got),
        "fn": sorted(exp - got),
        "fp": sorted(got - exp),
        "right_type_wrong_turn": sorted(wrong_turn),
        "expected_clean": not exp,
        "flagged": bool(got),
        "good_tp": len(exp_good & got_good),
        "good_expected": len(exp_good),
        "unverified": pred.get("unverified_findings", 0),
        "dropped": pred.get("dropped_findings", 0),
        "leaked": leaked_figures(pred, label.get("sensitive_figures", [])),
    }


def _rate(num: float, den: float) -> float | None:
    return round(num / den, 3) if den else None


def aggregate(scored: list[tuple[str, dict]]) -> dict:
    rows = [s for _, s in scored]
    tp = sum(len(r["tp"]) for r in rows)
    fn = sum(len(r["fn"]) for r in rows)
    fp = sum(len(r["fp"]) for r in rows)
    by_category = {}
    for cat in CATEGORIES:
        c_tp = sum(1 for r in rows for t, _ in r["tp"] if FINDING_TYPES[t][0] == cat)
        c_fn = sum(1 for r in rows for t, _ in r["fn"] if FINDING_TYPES[t][0] == cat)
        by_category[cat] = {"recall": _rate(c_tp, c_tp + c_fn), "tp": c_tp, "expected": c_tp + c_fn}
    clean = [r for r in rows if r["expected_clean"]]
    return {
        "calls": len(rows),
        "errors": sum(r["status"] == "error" for r in rows),
        "finding_recall": _rate(tp, tp + fn),
        "finding_precision": _rate(tp, tp + fp),
        "expected_findings": tp + fn,
        "false_findings": fp,
        "recall_by_category": by_category,
        "clean_calls": len(clean),
        "clean_calls_falsely_flagged": sum(r["flagged"] for r in clean),
        "good_practice_recall": _rate(sum(r["good_tp"] for r in rows), sum(r["good_expected"] for r in rows)),
        "unverified_findings": sum(r["unverified"] for r in rows),
        "customer_turn_findings_dropped": sum(r["dropped"] for r in rows),
        "figures_leaked": sum(len(r["leaked"]) for r in rows),
        "flagged_calls": sum(r["flagged"] for r in rows),
        "missed": [f"{i} {t} T{n}" for i, r in scored for t, n in r["fn"]],
        "false": [f"{i} {t} T{n}" for i, r in scored for t, n in r["fp"]],
        "wrong_turn": [f"{i} {t}" for i, r in scored for t in r["right_type_wrong_turn"]],
        "leaks": [f"{i}: {', '.join(r['leaked'])}" for i, r in scored if r["leaked"]],
    }
