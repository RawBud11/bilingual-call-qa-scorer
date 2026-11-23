"""Transcript parsing, greeting and disclosure rules, the suggested score and the
per-agent summary."""

import json

import pytest

import config
from call_qa.scoring import agent_summary, score_call, suggested_score
from call_qa.transcript import UserError, parse_transcript
from helpers import FakeAI, ai_answer, make_call

RUBRIC = json.loads(config.RUBRIC_FILE.read_text(encoding="utf-8"))
WEIGHTS = {i["id"]: i["weight"] for i in RUBRIC["items"]}


def status(result, item_id):
    return next(i for i in result["items"] if i["id"] == item_id)["status"]


def test_parser_numbers_lines_and_joins_wrapped_turns():
    call = parse_transcript(
        "# comment\ncall_id: A1\nagent: Dana P.\nreason: fees\n\n"
        "Agent: Hi, this is Dana.\nCustomer: I have a question\nabout a fee.\n"
        "AGENTE: Claro.\ncliente: Gracias.\n", "x.txt")
    assert [(l["id"], l["speaker"]) for l in call["lines"]] == [
        ("L1", "agent"), ("L2", "customer"), ("L3", "agent"), ("L4", "customer")]
    assert call["lines"][1]["text"] == "I have a question about a fee."
    assert (call["call_id"], call["agent"], call["channel"]) == ("A1", "Dana P.", "phone")


@pytest.mark.parametrize("text,code", [
    ("agent: X\nreason: fees\n\nAgent: hi", "missing_header"),
    ("call_id: 1\nagent: X\nreason: nope\n\nAgent: hi", "bad_reason"),
    ("call_id: 1\nagent: X\nreason: fees\n\n", "no_lines"),
    ("call_id: 1\nagent: X\nreason: fees\nhello\n\nAgent: hi", "bad_header_line"),
])
def test_parser_errors(text, code):
    with pytest.raises(UserError) as info:
        parse_transcript(text, "x.txt")
    assert info.value.code == code


@pytest.mark.parametrize("first,expected", [
    ("Agent: Thanks for calling Puentara, my name is Dana. How can I help?", "met"),
    ("Agente: Gracias por llamar a Puentara, te habla Marco. ¿En qué te puedo ayudar?", "met"),
    ("Agente: Gracias por llamar a PUENTARA, te habla Marco. ¿En que te puedo ayudar?", "met"),
    ("Agent: Puentara, this is Sofia. What do you need?", "partial"),
    ("Agent: Yeah?", "not_met"),
])
def test_greeting(first, expected):
    call = make_call(first, "Customer: Hi.")
    assert status(score_call(call, FakeAI(ai_answer(call)), RUBRIC, "en", "m"), "greeting") == expected


@pytest.mark.parametrize("lines,reason,expected", [
    (["Agent: This call is recorded for quality."], "fees", "met"),
    (["Agente: Esta llamada es grabada con fines de calidad."], "fees", "met"),
    (["Agent: Hi."], "fees", "not_met"),
    (["Agent: This call may be recorded.", "Agent: We review disputes within 10 business days."],
     "charge_dispute", "met"),
    (["Agent: This call may be recorded.", "Agent: You'll definitely get your money back in 10 business days."],
     "charge_dispute", "partial"),
    (["Agente: Hola.", "Agente: Seguro te devolvemos el dinero."], "charge_dispute", "not_met"),
])
def test_disclosures(lines, reason, expected):
    call = make_call(*lines, reason=reason)
    assert status(score_call(call, FakeAI(ai_answer(call)), RUBRIC, "en", "m"), "disclosures") == expected


def test_verification_is_na_on_general_questions_whatever_the_ai_says():
    call = make_call("Agent: Hi, Puentara.", reason="general_question")
    result = score_call(call, FakeAI(ai_answer(call, "not_met")), RUBRIC, "en", "m")
    assert status(result, "identity_verification") == "n/a"


def test_suggested_score_weights_and_skips_na_and_review():
    items = [{"id": "greeting", "status": "met"}, {"id": "empathy", "status": "partial"},
             {"id": "resolution", "status": "needs_review"}, {"id": "identity_verification", "status": "n/a"}]
    # (10*1 + 15*0.5) / (10 + 15) = 70
    assert suggested_score(items, WEIGHTS, auto_fail=False) == 70
    assert suggested_score(items, WEIGHTS, auto_fail=True) == 0
    assert suggested_score([{"id": "empathy", "status": "needs_review"}], WEIGHTS, False) is None


def test_every_result_is_pending():
    call = make_call("Agent: Hi.")
    assert score_call(call, FakeAI(ai_answer(call)), RUBRIC, "en", "m")["reviewer_decision"] == "pending"


def test_agent_summary():
    results = [
        {"agent": "B", "suggested_score": 80, "flags": [], "provisional": False,
         "items": [{"id": "empathy", "status": "not_met"}]},
        {"agent": "A", "suggested_score": 0, "flags": [{"type": "auto_fail"}], "provisional": True,
         "items": [{"id": "empathy", "status": "partial"}, {"id": "greeting", "status": "met"}]},
        {"agent": "A", "suggested_score": 90, "flags": [], "provisional": False,
         "items": [{"id": "empathy", "status": "not_met"}]},
    ]
    summary = agent_summary(results)
    assert [s["agent"] for s in summary] == ["A", "B"]
    assert summary[0] == {"agent": "A", "calls": 2, "average": 45, "to_confirm": 1, "flags": 1,
                          "most_missed": [("empathy", 2)]}
    assert summary[1]["to_confirm"] == 0


@pytest.mark.parametrize("lang,expected", [
    ("en", "100/100 (provisional, 1 item to review)"),
    ("es", "100/100 (provisional, 1 punto por revisar)"),
])
def test_score_with_items_to_review_is_shown_as_provisional(lang, expected):
    from call_qa.report import score_text
    from helpers import ai_item
    call = make_call("Agent: Thanks for calling Puentara, my name is Dana. How can I help? This call is recorded.",
                     "Customer: Hi.", reason="fees")
    answer = ai_answer(call, resolution=ai_item("met", "L1", "words that are not there"))
    result = score_call(call, FakeAI(answer), RUBRIC, lang, "m")
    assert result["provisional"] is True
    assert result["suggested_score"] == 100
    assert result["scored_weight"] == 85  # resolution (weight 15) is not scored yet
    assert score_text(result, lang) == expected


@pytest.mark.parametrize("lang,expected", [
    ("en", "0/100 (provisional, auto-fail flag to confirm)"),
    ("es", "0/100 (provisional, alerta auto-fail por confirmar)"),
])
def test_auto_fail_score_is_shown_as_provisional(lang, expected):
    from call_qa.report import score_text
    call = make_call("Agent: What's your PIN?", reason="account_access")
    result = score_call(call, FakeAI(ai_answer(call)), RUBRIC, lang, "m")
    assert score_text(result, lang) == expected
    assert result["scored_weight"] == 100


def test_final_score_is_plain():
    from call_qa.report import score_text
    call = make_call("Agent: Thanks for calling Puentara.")
    result = score_call(call, FakeAI(ai_answer(call)), RUBRIC, "en", "m")
    assert result["provisional"] is False
    assert score_text(result, "en") == f'{result["suggested_score"]}/100'
