"""Command line.

    python -m sales_compliance review evals/datasets/calls/c07.txt
    python -m sales_compliance batch evals/datasets/calls

Add --provider openai (or anthropic) to override config.yaml.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .aggregate import render_markdown, summarise
from .config import ROOT
from .engine import Engine
from .io import load_calls
from .providers import ProviderConfigError
from .runner import run_batch, run_call


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m sales_compliance")
    parser.add_argument("--provider", choices=["anthropic", "openai"])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("review", help="review one call transcript (.txt or .json)")
    p.add_argument("path")
    p = sub.add_parser("batch", help="review a folder or JSON file of calls and write a report")
    p.add_argument("path")
    p.add_argument("--out", default=str(ROOT / "reports"))
    args = parser.parse_args(argv)

    try:
        engine = Engine(provider_name=args.provider)
        calls = load_calls(args.path)
    except (ProviderConfigError, ValueError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.command == "review":
        result = run_call(engine, calls[0])
        print(json.dumps({k: v for k, v in result.to_dict().items() if k != "meta"}, indent=2))
        return 0 if result.status == "ok" else 1

    print(f"Reviewing {len(calls)} calls...", flush=True)
    results = run_batch(engine, calls)
    min_size = engine.config.get("analysis", {}).get("min_group_size", 5)
    summary = summarise(results, min_group_size=min_size)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with (out / f"results_{stamp}.jsonl").open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps({k: v for k, v in r.to_dict().items() if k != "meta"}) + "\n")
    report_path = out / f"compliance_summary_{stamp}.md"
    report_path.write_text(render_markdown(summary), encoding="utf-8")
    print(f"Wrote {report_path} and per-call results.")
    print(f"Legal: {len(summary['routes']['legal'])}, compliance: {len(summary['routes']['compliance'])}, "
          f"clean: {summary['outcomes']['clean']}, manual check: {len(summary['routes']['manual_check'])}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
