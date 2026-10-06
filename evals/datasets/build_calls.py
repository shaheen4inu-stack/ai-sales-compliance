"""Build the synthetic sales call transcripts and their labels.

    python evals/datasets/build_calls.py

Each turn can carry tags: a finding type (expected finding at that turn) or "GOOD" (expected
declined_competitor_information). Labels are derived from the tags, so they cannot drift from
the transcripts. All companies and people are invented. "Northstar Cloud" is the seller.
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).parent
R, C = "rep", "customer"

CALLS = [
    # ---------------------------------------------------------------- clean calls
    ("c01", "uk_enterprise", "Clean discovery call using only approved claims", [
        (C, "We're reviewing CRM-adjacent platforms for about 300 users. Uptime is our main worry."),
        (R, "Understood. On the Enterprise plan we offer a 99.9% uptime SLA, and we're SOC 2 Type II certified."),
        (C, "Where would our data live?"),
        (R, "You choose the region: UK, EU or US. For you I'd suggest UK."),
        (C, "And support?"),
        (R, "24/7 support on Premium and Enterprise. Standard gets business-hours support."),
        (C, "Good. Send me a proposal for Enterprise."),
        (R, "Will do. I'll include the SLA terms so your team can review them."),
    ]),
    ("c02", "uk_enterprise", "Absolute guarantee", [
        (C, "Our last provider had three outages this year. That can't happen again."),
        (R, "I hear that a lot. With us you're on the Enterprise plan with a strong SLA."),
        (C, "Strong how?"),
        (R, "Honestly, I can guarantee you'll never have downtime with us. It just doesn't happen.", ["absolute_guarantee"]),
        (C, "That's a bold statement."),
        (R, "Our engineers are the best in the business. Let's get you a proposal."),
    ]),
    ("c03", "uk_midmarket", "Unapproved certification claim", [
        (C, "We handle patient referrals for a few clinics, so compliance matters."),
        (R, "Absolutely. We're SOC 2 Type II certified."),
        (C, "Anything health-specific?"),
        (R, "Yes, we're fully HIPAA certified and ISO 27701 accredited, so you're covered for health data.", ["unapproved_claim"]),
        (C, "That would help with our auditors."),
        (R, "I'll send over a summary of our security documentation."),
    ]),
    ("c04", "uk_midmarket", "False statement about a competitor", [
        (C, "We're also talking to Brightwave Systems."),
        (R, "Sure. Have you looked at their track record on security?"),
        (C, "Not in detail yet."),
        (R, "Brightwave lost a load of customer data last year and covered it up. Everyone in the industry knows.", ["false_competitor_statement"]),
        (C, "I hadn't heard that."),
        (R, "Just something to keep in mind. Our security is SOC 2 Type II certified."),
    ]),
    ("c05", "uk_enterprise", "Rep solicits a competitor's proposal", [
        (C, "Brightwave sent us their proposal last week. It's competitive."),
        (R, "If you can forward me Brightwave's proposal, I'll make sure we beat it line by line.", ["solicited_competitor_pricing"]),
        (C, "I'm not sure I'm allowed to share it."),
        (R, "It stays between us. Even a screenshot of the pricing page of the proposal would do."),
        (C, "Let me think about it."),
        (R, "No problem. I'll send our Enterprise proposal today either way."),
    ]),
    ("c06", "uk_midmarket", "Customer volunteers a confidential quote; rep declines", [
        (C, "Corvex Data offered us 18 dollars per user with 25% off for three years."),
        (R, "Thanks, but I'd rather you didn't share their proposal with me. Let me walk you through our pricing on its own merits.", ["GOOD"]),
        (C, "Fair enough."),
        (R, "Premium is 40 USD per user per month and includes 24/7 support. There's a 30-day free trial."),
        (C, "And the minimum term?"),
        (R, "Twelve months."),
    ], ["18 dollars", "25%"]),
    ("c07", "uk_midmarket", "Customer volunteers a quote; rep uses it", [
        (C, "Corvex Data quoted 18 dollars a user and 25% off if we sign this month."),
        (R, "18 a user with 25% off. What else was in their offer? Send me the PDF and I'll go below it.", ["used_volunteered_competitor_pricing"]),
        (C, "It had onboarding included too."),
        (R, "Then we'll include onboarding as well. Get me the document and I'll build the numbers tonight."),
        (C, "OK, I'll see what I can do."),
    ], ["18 dollars", "18 a user", "25%"]),
    ("c08", "emea_partners", "Public list price reference only", [
        (C, "Brightwave's website lists 30 dollars per user for their standard plan."),
        (R, "That's their published price, yes. Our Standard plan is 25 USD per user per month."),
        (C, "What's the difference in support?"),
        (R, "Standard includes business-hours support. If you need 24/7, that's Premium."),
        (C, "Makes sense."),
    ]),
    ("c09", "uk_enterprise", "Rep discloses another customer's discount", [
        (C, "Your price is high for 500 users."),
        (R, "I understand. We gave Halden Logistics 40% off their renewal last quarter, so there's room.", ["confidential_disclosure"]),
        (C, "Forty percent? That's a lot."),
        (R, "I'd need deal desk approval for anything above 10%, but I'll push for it."),
        (C, "Please do."),
    ], ["40%", "Forty percent"]),
    ("c10", "uk_enterprise", "Possible coordination with a competitor", [
        (C, "We're expecting price cuts from both you and Brightwave this quarter."),
        (R, "Between us, I had a drink with their regional lead. They're not going below 30 a seat this quarter, so there's no need for us to either.", ["possible_coordination"]),
        (C, "Oh. Right."),
        (R, "So I'd lock in our current Enterprise quote."),
        (C, "I'll talk to procurement."),
    ], ["30 a seat"]),
    ("c11", "uk_midmarket", "Misstated contract terms", [
        (C, "We don't want to be locked in."),
        (R, "You won't be. There's no minimum term, you can cancel any month you like.", ["misstated_terms"]),
        (C, "That's unusual for this market."),
        (R, "We're flexible like that. And there's a 30-day free trial on Premium."),
        (C, "Good to know."),
    ]),
    ("c12", "uk_enterprise", "Guarantee and solicitation in one call", [
        (C, "We're comparing you with Corvex Data."),
        (R, "Great. What did Corvex put in front of you? Ballpark is fine.", ["solicited_competitor_pricing"]),
        (C, "I'd rather not say."),
        (R, "Fair. What I can say is that with us your migration is guaranteed to finish in two weeks with zero disruption.", ["absolute_guarantee"]),
        (C, "Zero disruption?"),
        (R, "Zero. We'll put a plan together."),
    ]),
    ("c13", "emea_partners", "Customer says competitor is cheaper, no figures; rep compares features", [
        (C, "I think Brightwave is cheaper."),
        (R, "That may be. Happy to compare features side by side so you can judge value."),
        (C, "Mostly I care about integrations."),
        (R, "We integrate with the major CRM and ERP platforms. Which ones do you use?"),
        (C, "Mainly our ERP."),
        (R, "That's covered. I'll send the integration list."),
    ]),
    ("c14", "uk_midmarket", "Customer mentions a confidential quote; rep moves on without engaging", [
        (C, "Corvex offered us 20 dollars a user, by the way."),
        (R, "OK. Let's focus on your requirements first. How many users need admin rights?"),
        (C, "About twenty."),
        (R, "Then Premium fits. It's 40 USD per user per month with 24/7 support."),
        (C, "Send me the details."),
    ], ["20 dollars"]),
    ("c15", "uk_enterprise", "Approved SLA figure that must not be read as a guarantee", [
        (C, "What uptime can you commit to?"),
        (R, "On Enterprise we commit to a 99.9% uptime SLA, with service credits if we miss it."),
        (C, "And on Premium?"),
        (R, "Premium doesn't carry a contractual SLA. If uptime commitments matter, Enterprise is the right plan."),
        (C, "Understood."),
    ]),
    ("c16", "uk_midmarket", "Rep explicitly refuses to promise zero downtime", [
        (C, "Can you promise we'll never go down?"),
        (R, "I can't promise zero downtime. Nobody honestly can. What we offer is a 99.9% uptime SLA on Enterprise."),
        (C, "I appreciate the honesty."),
        (R, "I'd rather set the right expectations. I'll send the SLA document."),
    ]),
    ("c17", "emea_partners", "Customer repeats a rumour; rep declines to comment", [
        (C, "We heard Corvex Data had a breach recently."),
        (R, "I can't comment on that. I'd check their published security reports."),
        (C, "Fair. What about yours?"),
        (R, "We're SOC 2 Type II certified and I can share the report under NDA."),
    ]),
    ("c18", "uk_enterprise", "Clearly framed personal opinion about a competitor", [
        (C, "What do you think of Brightwave's product?"),
        (R, "I personally find their interface a bit clunky, but you should try both and decide."),
        (C, "We will."),
        (R, "Great. Our 30-day free trial is a good way to compare."),
    ]),
    ("c19", "uk_midmarket", "Indirect solicitation", [
        (C, "Corvex came in lower than you, I'll be honest."),
        (R, "Just between us, what number did they put in front of you? I won't tell anyone.", ["solicited_competitor_pricing"]),
        (C, "I don't think I should."),
        (R, "No worries. Let me see what I can do on our side within my discount authority."),
    ]),
    ("c20", "uk_enterprise", "Confidential disclosure and misstated support terms", [
        (C, "What do other retailers pay?"),
        (R, "Ferris Retail pays 12 dollars a user after their discount.", ["confidential_disclosure"]),
        (C, "Interesting."),
        (R, "And every plan, even Standard, gets 24/7 premium support at no extra cost.", ["misstated_terms"]),
        (C, "That's better than I expected."),
    ], ["12 dollars"]),
    ("c21", "uk_midmarket", "Customer offers to email a competitor proposal; rep declines", [
        (C, "I can email you Brightwave's proposal if that helps you sharpen your offer."),
        (R, "Please don't send me their proposal. Our policy is not to look at competitor quotes.", ["GOOD"]),
        (C, "Oh, OK."),
        (R, "I'll put together our best offer based on your requirements instead."),
    ]),
    ("c22", "emea_partners", "Rep declines, then later solicits", [
        (C, "Corvex's proposal has a big discount in it. Want to see it?"),
        (R, "No thanks, I shouldn't see their proposal.", ["GOOD"]),
        (C, "Sure."),
        (R, "Although, if you could just tell me the discount percentage, that would really help me.", ["solicited_competitor_pricing"]),
        (C, "Hmm, let me check what I'm allowed to share."),
    ]),
]


def main() -> None:
    calls_dir = OUT / "calls"
    calls_dir.mkdir(exist_ok=True)
    labels = []
    for call_id, team, description, turns, *rest in CALLS:
        sensitive = rest[0] if rest else []
        lines = [f"# team: {team}"]
        findings, good = [], []
        for i, turn in enumerate(turns, 1):
            speaker, text, *tags = turn
            tags = tags[0] if tags else []
            lines.append(f"{'Rep' if speaker == R else 'Customer'}: {text}")
            for tag in tags:
                assert speaker == R, f"{call_id} T{i}: tags must be on rep turns"
                if tag == "GOOD":
                    good.append({"type": "declined_competitor_information", "turn": i})
                else:
                    findings.append({"type": tag, "turn": i})
        (calls_dir / f"{call_id}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        labels.append(
            {
                "id": call_id,
                "description": description,
                "expected": {"findings": findings, "good_practice": good},
                "sensitive_figures": sensitive,
            }
        )
    (OUT / "labels.json").write_text(json.dumps({"calls": labels}, indent=1), encoding="utf-8")
    print(f"Wrote {len(labels)} calls")


if __name__ == "__main__":
    main()
