import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sales_compliance.analyze import render_transcript  # noqa: E402
from sales_compliance.audit import AuditLog  # noqa: E402
from sales_compliance.config import load_config  # noqa: E402
from sales_compliance.engine import Engine  # noqa: E402
from sales_compliance.guardrails import redact  # noqa: E402
from sales_compliance.io import load_calls  # noqa: E402
from sales_compliance.providers import FakeProvider  # noqa: E402

DATASETS = ROOT / "evals" / "datasets"


@pytest.fixture
def config():
    return load_config()


@pytest.fixture
def make_engine(config, tmp_path):
    def _make(responder, cfg=None):
        if isinstance(responder, dict):
            responder = json.dumps(responder)
        return Engine(config=cfg or config, provider=FakeProvider(responder), audit=AuditLog(tmp_path / "audit.jsonl"))

    return _make


def transcript_from_prompt(user: str) -> str:
    return re.search(r"<transcript>\n(.*?)\n</transcript>", user, re.S).group(1)


@pytest.fixture
def perfect_model():
    """Answers with the ground truth, quoting whole rep turns and repeating their figures in the
    explanation and summary, so tests prove masking removes them."""
    labels = {c["id"]: c for c in json.loads((DATASETS / "labels.json").read_text())["calls"]}
    index = {}
    for call in load_calls(DATASETS / "calls"):
        turns = [(t.speaker, redact(t.text).text) for t in call.turns]
        index[render_transcript(turns)] = (labels[call.id], turns)

    def respond(system, user, images):
        label, turns = index[transcript_from_prompt(user)]
        findings = [
            {
                "type": f["type"],
                "turn": f["turn"],
                "quote": turns[f["turn"] - 1][1],
                "explanation": f"The rep said: {turns[f['turn'] - 1][1]}",
            }
            for f in label["expected"]["findings"]
        ]
        good = [{"type": g["type"], "turn": g["turn"], "quote": turns[g["turn"] - 1][1]} for g in label["expected"]["good_practice"]]
        summary = " ".join(text for _, text in turns[:2])
        return json.dumps({"summary": summary, "findings": findings, "good_practice": good})

    return respond
