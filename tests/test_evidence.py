"""Every AI judgment must quote the transcript. Made-up evidence -> needs_review."""

import json

import pytest

import config
from call_qa.ai import check_evidence, parse_ai_response
from call_qa.scoring import score_call
from helpers import FakeAI, ai_answer, ai_item, make_call

RUBRIC = json.loads(config.RUBRIC_FILE.read_text(encoding="utf-8"))
CALL = make_call(
    "Agent: Thanks for calling Puentara, my name is Dana. How can I help?",
    "Customer: I lost my card yesterday.",
    "Agent: I'm sorry, that's stressful. Let's lock it now.",
    "Agente: Entiendo, es frustrante quedarse sin acceso.",
    reason="card_lost_stolen",
)
LINES = {line["id"]: line for line in CALL["lines"]}


def status_of(result, item_id):
    return next(i for i in result["items"] if i["id"] == item_id)["status"]


@pytest.mark.parametrize("evidence", [
    [{"line": "L3", "quote": "that's stressful"}],
    [{"line": "l3", "quote": "  \"I'm sorry, that's stressful\" "}],    # quotes and case are fine
    [{"line": "L4", "quote": "entiendo, es FRUSTRANTE"}],
    [{"line": "L4", "quote": "Entiendo, es frustrante quedarse sin acceso"}],
    [{"line": "L4", "quote": "es frustrante quedarse..."}],               # cut with an ellipsis
])
def test_valid_quotes_pass(evidence):
    assert check_evidence(evidence, "met", LINES) is None


def test_accents_do_not_matter_in_quotes():
    assert check_evidence([{"line": "L4", "quote": "es frustrante quedarse sin acceso"}], "met", LINES) is None
    assert check_evidence([{"line": "L4", "quote": "Entiendo, es frustránte"}], "met", LINES) is None


@pytest.mark.parametrize("evidence,problem", [
    ([{"line": "L99", "quote": "that's stressful"}], "bad_line"),
    ([{"line": "X3", "quote": "that's stressful"}], "bad_line"),
    ([{"line": "L3", "quote": "I completely understand your frustration"}], "quote_not_found"),
    ([{"line": "L1", "quote": "that's stressful"}], "quote_not_found"),     # right words, wrong line
    ([{"line": "L3", "quote": ""}], "quote_not_found"),
    ([], "no_evidence"),
    ("L3", "no_evidence"),
    (["L3"], "no_evidence"),
])
def test_bad_evidence_is_caught(evidence, problem):
    assert check_evidence(evidence, "met", LINES) == problem


def test_na_needs_no_evidence():
    assert check_evidence([], "n/a", LINES) is None


def test_made_up_quote_sends_item_to_review():
    answer = ai_answer(CALL, empathy=ai_item("met", "L3", "I completely understand your frustration"))
    result = score_call(CALL, FakeAI(answer), RUBRIC, "en", "m")
    assert status_of(result, "empathy") == "needs_review"
    assert "empathy" in result["review_items"]
    assert status_of(result, "resolution") == "met"  # other items keep their status


def test_made_up_line_id_sends_item_to_review():
    answer = ai_answer(CALL, resolution=ai_item("met", "L42", "Let's lock it now"))
    result = score_call(CALL, FakeAI(answer), RUBRIC, "es", "m")
    item = next(i for i in result["items"] if i["id"] == "resolution")
    assert item["status"] == "needs_review"
    assert "no existe" in item["rationale"]  # explained in the report language


def test_valid_quote_passes_through_scoring():
    answer = ai_answer(CALL, empathy=ai_item("met", "L3", "I'm sorry, that's stressful"))
    result = score_call(CALL, FakeAI(answer), RUBRIC, "en", "m")
    assert status_of(result, "empathy") == "met"
    assert result["review_items"] == []


@pytest.mark.parametrize("answer,problem", [
    ({"status": "great", "rationale": "x", "evidence": [{"line": "L3", "quote": "stressful"}]}, "bad_status"),
    ({"status": "met", "rationale": "", "evidence": [{"line": "L3", "quote": "stressful"}]}, "bad_rationale"),
    ({"status": "met", "rationale": "x"}, "no_evidence"),
])
def test_other_bad_items(answer, problem):
    text = json.dumps({"items": {"empathy": answer}})
    assert parse_ai_response(text, CALL, ["empathy"])["empathy"] == {"problem": problem}


def test_missing_item_and_broken_json():
    parsed = parse_ai_response('{"items": {}}', CALL, ["empathy"])
    assert parsed["empathy"] == {"problem": "missing_item"}
    result = score_call(CALL, FakeAI("Sorry, I can't help with that."), RUBRIC, "en", "m")
    for item_id in ("identity_verification", "empathy", "resolution"):
        assert status_of(result, item_id) == "needs_review"
    assert status_of(result, "greeting") == "met"  # rules still work without the AI


def test_demo_fixture_has_one_deliberately_broken_quote():
    from call_qa.ai import FixtureClient
    from call_qa.transcript import load_calls
    calls = {c["call_id"]: c for c in load_calls(config.SAMPLE_CALLS_DIR)}
    result = score_call(calls["C006"], FixtureClient(), RUBRIC, "en", "m")
    assert result["review_items"] == ["resolution"]
