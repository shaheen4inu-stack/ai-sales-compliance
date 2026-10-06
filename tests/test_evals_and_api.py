"""Dataset integrity, scoring, aggregation, the full eval pipeline and the API, with fake models."""

import json

from fastapi.testclient import TestClient

from evals import run_evals
from sales_compliance import api
from sales_compliance.aggregate import render_markdown, summarise
from sales_compliance.io import load_calls
from sales_compliance.schemas import FINDING_TYPES

from .conftest import DATASETS

NEVER = json.dumps({"summary": "s", "findings": [], "good_practice": []})


def test_dataset_is_consistent():
    labels = json.loads((DATASETS / "labels.json").read_text())["calls"]
    calls = {c.id: c for c in load_calls(DATASETS / "calls")}
    assert len(labels) == 22 and set(calls) == {lab["id"] for lab in labels}
    for lab in labels:
        call = calls[lab["id"]]
        for f in lab["expected"]["findings"] + lab["expected"]["good_practice"]:
            assert call.turns[f["turn"] - 1].speaker == "rep", f"{lab['id']} T{f['turn']}"
        for f in lab["expected"]["findings"]:
            assert f["type"] in FINDING_TYPES
        text = " ".join(t.text for t in call.turns)
        for s in lab["sensitive_figures"]:
            assert s.lower() in text.lower(), f"{lab['id']}: {s} not in transcript"
    covered = {f["type"] for lab in labels for f in lab["expected"]["findings"]}
    assert covered == set(FINDING_TYPES), "every finding type needs at least one example"


def test_perfect_model_scores_perfectly_and_leaks_nothing(make_engine, perfect_model):
    calls, labels = run_evals.load_dataset()
    run = run_evals.evaluate(make_engine(perfect_model), calls, labels)
    m = run["metrics"]
    assert m["finding_recall"] == 1.0 and m["finding_precision"] == 1.0
    assert m["clean_calls_falsely_flagged"] == 0 and m["good_practice_recall"] == 1.0
    assert m["figures_leaked"] == 0, m["leaks"]
    assert m["unverified_findings"] == 0 and m["errors"] == 0


def test_masking_is_what_prevents_leaks(make_engine, perfect_model, monkeypatch):
    """Turn masking off and the same perfect model leaks figures: the metric is real."""
    import sales_compliance.analyze as analyze

    monkeypatch.setattr(analyze, "mask_figures", lambda t: t)
    calls, labels = run_evals.load_dataset()
    m = run_evals.evaluate(make_engine(perfect_model), calls, labels)["metrics"]
    assert m["figures_leaked"] > 0


def test_model_that_never_flags(make_engine, config, tmp_path):
    calls, labels = run_evals.load_dataset()
    run = run_evals.evaluate(make_engine(NEVER), calls, labels)
    m = run["metrics"]
    assert m["finding_recall"] == 0.0 and len(m["missed"]) == 14
    assert m["recall_by_category"]["competition_law"] == {"recall": 0.0, "tp": 0, "expected": 1}
    report = run_evals.write_outputs([run], config, tmp_path).read_text()
    assert "Finding recall (all types) | 0.0%" in report and "c10 possible_coordination T2" in report
    for money in ("$", "USD", "Cost"):
        assert money not in report


def test_model_that_flags_everything_is_penalised(make_engine):
    def flag_turn_two(system, user, images):
        return json.dumps(
            {"summary": "s", "findings": [{"type": "absolute_guarantee", "turn": 2, "quote": "x", "explanation": "e"}], "good_practice": []}
        )

    calls, labels = run_evals.load_dataset()
    m = run_evals.evaluate(make_engine(flag_turn_two), calls, labels)["metrics"]
    assert m["clean_calls_falsely_flagged"] == 10
    assert m["unverified_findings"] == 22


def test_hours_estimate(config):
    run = {"metrics": {"calls": 10, "errors": 1, "flagged_calls": 4}}
    h = run_evals.hours_per_100(run, config)
    assert h["with_ai"] == (5 * 1 + 4 * 10 + 1 * 30) / 10 * 100 / 60
    assert h["manual"] == 30 * 100 / 60


def test_aggregation_routes_and_suppression(make_engine, perfect_model):
    calls, _ = run_evals.load_dataset()
    from sales_compliance import run_batch

    s = summarise(run_batch(make_engine(perfect_model), calls), min_group_size=5)
    assert s["routes"]["legal"] == ["c10"]
    assert s["outcomes"] == {"clean": 10, "review": 11, "escalate_legal": 1, "error": 0}
    assert {"value": "emea_partners", "suppressed": True} in s["groups"]["team"]
    md = render_markdown(s)
    assert "**Legal** (1): c10" in md and "| emea_partners | suppressed |" in md


def test_api(make_engine, perfect_model, monkeypatch):
    engine = make_engine(perfect_model)
    monkeypatch.setattr(api, "ENGINE_FACTORY", lambda provider: engine)
    client = TestClient(api.app)
    assert client.get("/health").json()["status"] == "ok"

    calls = [c.model_dump() for c in load_calls(DATASETS / "calls")]
    resp = client.post("/v1/review-batch", json={"calls": calls})
    assert resp.status_code == 200
    assert resp.json()["summary"]["routes"]["legal"] == ["c10"]
    assert "meta" not in resp.json()["results"][0]
    assert client.post("/v1/review-batch", json={"calls": calls[:1] * 2}).status_code == 400

    monkeypatch.setenv("DEMO_API_KEY", "secret")
    assert client.post("/v1/review-call", json=calls[0]).status_code == 401
