"""Run the labelled call set against real models and write a comparison report.

    python -m evals.run_evals                     # provider from config.yaml
    python -m evals.run_evals --provider both     # Claude vs OpenAI side by side
    python -m evals.run_evals --limit 5           # quick smoke test
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evals import metrics  # noqa: E402
from sales_compliance import Engine, run_batch  # noqa: E402
from sales_compliance.config import load_config  # noqa: E402
from sales_compliance.io import load_calls  # noqa: E402
from sales_compliance.providers import ProviderConfigError  # noqa: E402

DATASETS = ROOT / "evals" / "datasets"


def load_dataset(limit: int | None = None) -> tuple[list, list[dict]]:
    labels = json.loads((DATASETS / "labels.json").read_text(encoding="utf-8"))["calls"]
    labels = labels[:limit] if limit else labels
    calls = [load_calls(DATASETS / "calls" / f"{lab['id']}.txt")[0] for lab in labels]
    return calls, labels


def evaluate(engine: Engine, calls: list, labels: list[dict]) -> dict:
    results = run_batch(engine, calls)
    rows, scored = [], []
    for label, result in zip(labels, results):
        pred = result.to_dict()
        score = metrics.score_call(pred, label)
        scored.append((label["id"], score))
        rows.append({"id": label["id"], "description": label["description"], "prediction": pred, "score": score})
    meta = [r["prediction"]["meta"] for r in rows if r["prediction"].get("meta")]
    return {
        "provider": engine.provider.name,
        "model": engine.provider.model,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "metrics": metrics.aggregate(scored),
        "avg_latency_s": round(sum(m["latency_ms"] for m in meta) / len(meta) / 1000, 2) if meta else None,
        "input_tokens": sum(m["input_tokens"] for m in meta),
        "output_tokens": sum(m["output_tokens"] for m in meta),
        "rows": rows,
    }


def hours_per_100(run: dict, config: dict) -> dict:
    """Human QA hours for 100 calls: listen to every call vs review only what the tool flags."""
    base = config["baseline_minutes"]["call_qa"]
    spot = config["review_minutes"]["clean_spot_check"]
    flagged = config["review_minutes"]["flagged"]
    m = run["metrics"]
    n, errors, flagged_n = m["calls"], m["errors"], m["flagged_calls"]
    clean = n - flagged_n - errors
    per_call = (clean * spot + flagged_n * flagged + errors * base) / n if n else 0
    manual, with_ai = base * 100 / 60, per_call * 100 / 60
    return {"manual": manual, "with_ai": with_ai, "saved": manual - with_ai}


def pct(v) -> str:
    return "n/a" if v is None else f"{v:.1%}"


def build_report(runs: list[dict], config: dict) -> str:
    head = " | ".join(f"{r['provider']} ({r['model']})" for r in runs)
    out = [
        "# Evaluation report",
        "",
        f"Run: {runs[0]['timestamp']} UTC. Dataset: {len(runs[0]['rows'])} synthetic labelled sales calls "
        "(`evals/datasets/`).",
        "",
        "> Synthetic transcripts. These results show how the pipeline and guardrails behave, not accuracy on a",
        "> client's calls. Label 50-100 of the client's own calls against their policy and re-run before quoting",
        "> any figure.",
        "",
        "## Detection",
        "",
        f"| Metric | {head} |",
        "|---|" + "---|" * len(runs),
    ]

    def row(label, fn):
        out.append(f"| {label} | " + " | ".join(fn(r) for r in runs) + " |")

    row("Finding recall (all types)", lambda r: pct(r["metrics"]["finding_recall"]))
    for cat in metrics.CATEGORIES:
        row(
            f"Recall: {cat}",
            lambda r, c=cat: f"{pct(r['metrics']['recall_by_category'][c]['recall'])} "
            f"({r['metrics']['recall_by_category'][c]['tp']}/{r['metrics']['recall_by_category'][c]['expected']})",
        )
    row("Finding precision", lambda r: pct(r["metrics"]["finding_precision"]))
    row("Clean calls falsely flagged", lambda r: f"{r['metrics']['clean_calls_falsely_flagged']}/{r['metrics']['clean_calls']}")
    row("Correct refusals recognised (good practice)", lambda r: pct(r["metrics"]["good_practice_recall"]))

    out += ["", "## Guardrails", "", f"| Metric | {head} |", "|---|" + "---|" * len(runs)]
    row("Competitor / confidential figures leaked in output", lambda r: str(r["metrics"]["figures_leaked"]))
    row("Findings without verifiable evidence", lambda r: str(r["metrics"]["unverified_findings"]))
    row("Findings citing customer turns (discarded)", lambda r: str(r["metrics"]["customer_turn_findings_dropped"]))
    row("Errors", lambda r: str(r["metrics"]["errors"]))
    row("Avg model time per call (s)", lambda r: "n/a" if r["avg_latency_s"] is None else f"{r['avg_latency_s']:.2f}")
    row("Tokens in / out", lambda r: f"{r['input_tokens']:,} / {r['output_tokens']:,}")

    out += [
        "",
        "## Efficiency: QA hours per 100 calls",
        "",
        "Manual and review minutes are ASSUMPTIONS from `config.yaml` until measured in a pilot. Clean calls get a",
        "spot check, flagged calls a focused review of the cited turns, failed calls a full listen. Model time is",
        "machine time and is not counted. Coverage also changes: manual QA usually samples calls; this checks all.",
        "",
        "| Provider | Manual hrs | Review hrs with AI | Hours saved | Saved % |",
        "|---|---|---|---|---|",
    ]
    for r in runs:
        h = hours_per_100(r, config)
        out.append(f"| {r['provider']} | {h['manual']:.1f} | {h['with_ai']:.1f} | {h['saved']:.1f} | {h['saved'] / h['manual']:.0%} |")

    out += ["", "## Failures", ""]
    for r in runs:
        m = r["metrics"]
        out.append(f"**{r['provider']}**")
        out.append(f"- Missed findings: {', '.join(m['missed']) or 'none'}")
        out.append(f"- False findings: {', '.join(m['false']) or 'none'}")
        out.append(f"- Right type, wrong turn: {', '.join(m['wrong_turn']) or 'none'}")
        out.append(f"- Figure leaks: {'; '.join(m['leaks']) or 'none'}")
        errs = [f"{x['id']}: {x['prediction'].get('error')}" for x in r["rows"] if x["prediction"]["status"] == "error"]
        out.append(f"- Errors: {'; '.join(errs) or 'none'}")
        out.append("")
    return "\n".join(out)


def write_outputs(runs: list[dict], config: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for r in runs:
        (out_dir / f"eval_{r['provider']}_{stamp}.json").write_text(json.dumps(r, indent=2, default=str), encoding="utf-8")
    report = build_report(runs, config)
    (out_dir / f"eval_report_{stamp}.md").write_text(report, encoding="utf-8")
    latest = out_dir / "eval_latest.md"
    latest.write_text(report, encoding="utf-8")
    return latest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the labelled call set against real models.")
    parser.add_argument("--provider", help="anthropic | openai | both (default: config.yaml)")
    parser.add_argument("--limit", type=int, help="only the first N calls")
    parser.add_argument("--out", default=str(ROOT / "reports"))
    args = parser.parse_args(argv)

    config = load_config()
    provider = args.provider or config["provider"]
    providers = ["anthropic", "openai"] if provider == "both" else [provider]
    calls, labels = load_dataset(args.limit)

    runs = []
    for p in providers:
        print(f"Running {p} on {len(calls)} calls...", flush=True)
        try:
            runs.append(evaluate(Engine(config=config, provider_name=p), calls, labels))
        except ProviderConfigError as exc:
            print(f"Skipping {p}: {exc}", file=sys.stderr)
    if not runs:
        print("No provider could run. Set API keys in .env (see .env.example).", file=sys.stderr)
        return 1
    latest = write_outputs(runs, config, Path(args.out))
    print(f"Report written to {latest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
