"""Load the client's sales policy and render it for the prompt."""

from __future__ import annotations

from pathlib import Path

import yaml

from .config import resolve


def load_policy(path: str | Path) -> dict:
    policy = yaml.safe_load(Path(resolve(path)).read_text(encoding="utf-8"))
    for key in ("company", "approved_claims", "terms", "competitors"):
        if key not in policy:
            raise ValueError(f"Policy file is missing '{key}'")
    return policy


def render_policy(policy: dict) -> str:
    lines = [f"Seller: {policy['company']}", "", "Approved claims:"]
    lines += [f"- {c}" for c in policy["approved_claims"]]
    lines += ["", "Commercial terms:"]
    lines += [f"- {t}" for t in policy["terms"]]
    lines += ["", "Competitors: " + ", ".join(policy["competitors"])]
    return "\n".join(lines)
