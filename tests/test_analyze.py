import json

import pytest

from sales_compliance import run_call
from sales_compliance.guardrails import mask_figures
from sales_compliance.io import parse_txt
from sales_compliance.schemas import Call

CALL = Call(
    id="x1",
    segments={"team": "t1"},
    turns=[
        {"speaker": "customer", "text": "Corvex offered 18 dollars per user with 25% off."},
        {"speaker": "rep", "text": "Send me their proposal and I'll beat 18 a user."},
        {"speaker": "customer", "text": "Brightwave never goes down, apparently."},
        {"speaker": "rep", "text": "I can guarantee zero downtime with us."},
    ],
)


def reply(findings=(), good=(), summary="Rep discussed pricing."):
    return {"summary": summary, "findings": list(findings), "good_practice": list(good)}


def f(type_, turn, quote, explanation="e"):
    return {"type": type_, "turn": turn, "quote": quote, "explanation": explanation}


def test_severity_and_route_set_in_code_and_figures_masked(make_engine):
    result = run_call(
        make_engine(reply([f("Solicited Competitor Pricing", 2, "beat 18 a user", "Rep asked to beat 18 a user")]))
        , CALL
    )
    finding = result.findings[0]
    assert (finding["severity"], finding["route"], finding["category"]) == ("high", "compliance", "competitor_information")
    assert finding["quote"] == "beat [FIGURE]" and finding["explanation"] == "Rep asked to beat [FIGURE]"
    assert finding["evidence_verified"] is True
    assert result.outcome == "review"


def test_coordination_escalates_to_legal(make_engine):
    result = run_call(make_engine(reply([f("possible_coordination", 4, "guarantee zero downtime")])), CALL)
    assert result.outcome == "escalate_legal"
    assert result.findings[0]["severity"] == "critical" and result.findings[0]["route"] == "legal"


def test_findings_on_customer_turns_are_discarded(make_engine):
    result = run_call(make_engine(reply([f("false_competitor_statement", 3, "never goes down")])), CALL)
    assert result.findings == [] and result.dropped_findings == 1
    assert result.outcome == "clean"


def test_unverifiable_quote_is_kept_but_flagged(make_engine):
    result = run_call(make_engine(reply([f("absolute_guarantee", 4, "you will never ever have an outage")])), CALL)
    assert result.findings[0]["evidence_verified"] is False
    assert result.unverified_findings == 1
    assert any("check the recording" in r for r in result.review_reasons)


def test_out_of_range_turn_is_unverified(make_engine):
    result = run_call(make_engine(reply([f("absolute_guarantee", 99, "guarantee")])), CALL)
    assert result.findings[0]["evidence_verified"] is False


def test_summary_figures_are_masked(make_engine):
    result = run_call(make_engine(reply(summary="Customer cited 18 dollars per user and 25% off.")), CALL)
    assert "18" not in result.summary and "25%" not in result.summary


def test_good_practice_must_be_a_verified_rep_turn(make_engine):
    good = [
        {"type": "declined_competitor_information", "turn": 2, "quote": "Send me their proposal"},
        {"type": "declined_competitor_information", "turn": 1, "quote": "Corvex offered"},
        {"type": "declined_competitor_information", "turn": 4, "quote": "made up words"},
    ]
    result = run_call(make_engine(reply(good=good)), CALL)
    assert [g["turn"] for g in result.good_practice] == [2]


def test_invalid_finding_type_fails_validation_then_errors(make_engine, tmp_path):
    bad = reply([f("rudeness", 2, "Send me")])
    result = run_call(make_engine([json.dumps(bad), json.dumps(bad)]), CALL)
    assert result.status == "error" and result.outcome == "error"
    record = json.loads((tmp_path / "audit.jsonl").read_text().splitlines()[-1])
    assert record["status"] == "error" and record["attempts"] == 2


def test_pii_redacted_per_turn_before_sending(make_engine):
    call = Call(id="p", turns=[{"speaker": "customer", "text": "Email me at ann@one.example or 07700 900123."}])
    engine = make_engine(reply())
    result = run_call(engine, call)
    sent = engine.provider.calls[0]["user"]
    assert "ann@one.example" not in sent and "900123" not in sent
    assert result.redactions == {"EMAIL": 1, "PHONE": 1}


def test_audit_log_has_no_content(make_engine, tmp_path):
    run_call(make_engine(reply([f("solicited_competitor_pricing", 2, "Send me their proposal")])), CALL)
    record = json.loads((tmp_path / "audit.jsonl").read_text().splitlines()[-1])
    assert record["finding_types"] == ["solicited_competitor_pricing"]
    assert "proposal" not in json.dumps(record)


def test_txt_parsing_with_headers_and_continuations():
    call = parse_txt("# team: uk\nRep: Hello\nthere\nCustomer (Buyer): Hi\n", "c99")
    assert call.segments == {"team": "uk"}
    assert [(t.speaker, t.text) for t in call.turns] == [("rep", "Hello there"), ("customer", "Hi")]
    with pytest.raises(ValueError):
        parse_txt("no speakers here", "bad")


@pytest.mark.parametrize(
    "text,expected",
    [
        ("18 dollars per user with 25% off", "[FIGURE] per user with [FIGURE] off"),
        ("not below 30 a seat", "not below [FIGURE]"),
        ("about £12k a year", "about [FIGURE] a year"),
        ("meeting on 3 November with 20 users", "meeting on 3 November with 20 users"),
    ],
)
def test_mask_figures(text, expected):
    assert mask_figures(text) == expected


def test_quote_must_match_whole_words():
    from sales_compliance.analyze import quote_in

    assert quote_in("Send me their proposal", "Send me their proposal and I'll beat it.")
    assert not quote_in("x", "next steps")
    assert not quote_in("pro", "proposal")
