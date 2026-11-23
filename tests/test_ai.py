"""The AI layer with fake clients only. These tests never call the network.
SDK error tests are copied from bilingual-ticket-triage."""

import json
from types import SimpleNamespace

import anthropic
import pytest

import config
from call_qa.ai import (AIError, FixtureClient, LiveClient, RecordingClient, ai_item_ids,
                        build_request, parse_ai_response)
from call_qa.scoring import score_call
from helpers import ai_answer, make_call

RUBRIC = json.loads(config.RUBRIC_FILE.read_text(encoding="utf-8"))
CALL = make_call("Agent: Thanks for calling Puentara, my name is Dana. How can I help?",
                 "Customer: I lost my card.", reason="card_lost_stolen", call_id="S1")


def test_ai_is_asked_only_about_soft_items_and_sensitive_second_opinion():
    assert ai_item_ids(RUBRIC) == ["identity_verification", "sensitive_data", "empathy", "resolution"]


@pytest.mark.parametrize("lang,language_name", [("en", "English"), ("es", "Spanish")])
def test_request_asks_for_rationale_in_report_language(lang, language_name):
    request = build_request(CALL, RUBRIC, lang, "some-model")
    assert f"in {language_name}" in request["system"]
    for item_id in ai_item_ids(RUBRIC):
        assert item_id in request["system"]
    assert "last 4 digits of the card" in request["system"]  # allowed factors from the rubric
    content = request["messages"][0]["content"]
    assert "L1 Agent: Thanks for calling Puentara" in content
    assert "escalation_required: yes" in content  # lost card -> security team
    assert request["model"] == "some-model"


def test_parse_accepts_json_inside_code_fences():
    text = "```json\n" + json.dumps(ai_answer(CALL)) + "\n```"
    parsed = parse_ai_response(text, CALL, ["empathy"])
    assert parsed["empathy"]["status"] == "met"


class FakeMessages:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.reply)])


def fake_sdk(reply=None, error=None):
    return SimpleNamespace(messages=FakeMessages(reply, error))


def make_error(cls):
    # Build an SDK exception without a real HTTP request or response.
    return cls.__new__(cls)


def test_live_client_sends_only_api_fields_and_returns_text():
    sdk = fake_sdk(reply='{"ok": true}')
    client = LiveClient("test-key", "model-x", sdk_client=sdk)
    assert client.complete(build_request(CALL, RUBRIC, "en", "model-x")) == '{"ok": true}'
    sent = sdk.messages.calls[0]
    assert set(sent) == {"model", "max_tokens", "system", "messages"}
    assert sent["model"] == "model-x"


@pytest.mark.parametrize("error_cls,code,fatal", [
    (anthropic.AuthenticationError, "auth", True),
    (anthropic.PermissionDeniedError, "permission", True),
    (anthropic.NotFoundError, "model", True),
    (anthropic.APITimeoutError, "timeout", False),
    (anthropic.APIConnectionError, "connection", False),
    (anthropic.RateLimitError, "rate_limit", False),
    (anthropic.InternalServerError, "server", False),
])
def test_live_client_turns_sdk_errors_into_clear_codes(error_cls, code, fatal):
    client = LiveClient("test-key", "model-x", sdk_client=fake_sdk(error=make_error(error_cls)))
    with pytest.raises(AIError) as info:
        client.complete(build_request(CALL, RUBRIC, "en", "model-x"))
    assert (info.value.code, info.value.fatal) == (code, fatal)


def test_fatal_error_stops_scoring_but_others_go_to_review():
    fatal = LiveClient("k", "m", sdk_client=fake_sdk(error=make_error(anthropic.AuthenticationError)))
    with pytest.raises(AIError):
        score_call(CALL, fatal, RUBRIC, "en", "m")
    timeout = LiveClient("k", "m", sdk_client=fake_sdk(error=make_error(anthropic.APITimeoutError)))
    result = score_call(CALL, timeout, RUBRIC, "en", "m")
    assert set(result["review_items"]) == {"identity_verification", "empathy", "resolution"}
    review = next(i for i in result["items"] if i["id"] == "empathy")
    assert "the API took too long" in review["rationale"]


def test_fixture_client_reads_by_call_and_language(tmp_path):
    path = tmp_path / "fx.json"
    path.write_text(json.dumps({"responses": {"S1": {
        "en": {"source": "hand-written", "response": ai_answer(CALL)},
        "es": {"source": "hand-written", "response": "not json"},
    }}}), encoding="utf-8")
    client = FixtureClient(path)
    assert client.sources() == {"hand-written"}
    assert json.loads(client.complete({"call_id": "S1", "report_lang": "en"}))["items"]
    assert client.complete({"call_id": "S1", "report_lang": "es"}) == "not json"
    with pytest.raises(AIError):
        client.complete({"call_id": "S2", "report_lang": "en"})


def test_recording_marks_answers_as_recorded_and_keeps_others(tmp_path):
    path = tmp_path / "fx.json"
    path.write_text(json.dumps({"_about": "x", "responses": {
        "S0": {"en": {"source": "hand-written", "response": {"items": {}}}}}}), encoding="utf-8")
    live = LiveClient("test-key", "model-x", sdk_client=fake_sdk(reply=json.dumps(ai_answer(CALL))))
    recorder = RecordingClient(live)
    score_call(CALL, recorder, RUBRIC, "es", "model-x")
    assert recorder.save(path) == 1
    data = json.loads(path.read_text(encoding="utf-8"))
    entry = data["responses"]["S1"]["es"]
    assert (entry["source"], entry["model"]) == ("recorded", "model-x")
    assert data["responses"]["S0"]["en"]["source"] == "hand-written"
    assert data["_about"] == "x"


def test_sample_fixtures_cover_every_demo_call_and_are_labeled():
    with open(config.FIXTURES_FILE, encoding="utf-8") as f:
        data = json.load(f)
    assert "NOT real model output" in data["_about"]
    assert set(data["responses"]) == {"C001", "C002", "C003", "C004", "C005", "C006"}
    for by_lang in data["responses"].values():
        assert set(by_lang) == {"en", "es"}
        assert all(entry["source"] == "hand-written" for entry in by_lang.values())


# --- The real SDK with a fake HTTP layer (still no network) ----------------

def sdk_with_fake_http(handler):
    """A real anthropic.Anthropic client whose HTTP calls go to `handler`.
    httpx2 is the HTTP library the anthropic SDK 1.x installs; if a future SDK
    switches libraries, these tests are skipped instead of failing."""
    httpx2 = pytest.importorskip("httpx2")
    return anthropic.Anthropic(api_key="test-key", base_url="https://api.anthropic.com", max_retries=0,
                               http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))


def test_live_client_with_real_sdk_and_fake_http():
    httpx2 = pytest.importorskip("httpx2")
    sent = {}

    def handler(request):
        sent["url"] = str(request.url)
        sent["body"] = json.loads(request.content)
        return httpx2.Response(200, json={
            "id": "msg_test", "type": "message", "role": "assistant", "model": "model-x",
            "content": [{"type": "text", "text": json.dumps(ai_answer(CALL))}], "stop_reason": "end_turn",
            "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1}})

    call = make_call("Agent: Thanks for calling Puentara.", "Customer: My card is 0000 1234 5678 9012",
                     call_id="S1")
    client = LiveClient("test-key", "model-x", sdk_client=sdk_with_fake_http(handler))
    result = score_call(call, client, RUBRIC, "en", "model-x")
    assert sent["url"].endswith("/v1/messages")
    assert "0000 1234" not in json.dumps(sent["body"])
    assert next(i for i in result["items"] if i["id"] == "empathy")["status"] == "met"


@pytest.mark.parametrize("status,error_type,code,fatal", [
    (401, "authentication_error", "auth", True),
    (404, "not_found_error", "model", True),
    (429, "rate_limit_error", "rate_limit", False),
    (529, "overloaded_error", "server", False),
])
def test_real_sdk_http_errors_become_clear_codes(status, error_type, code, fatal):
    httpx2 = pytest.importorskip("httpx2")

    def handler(request):
        return httpx2.Response(status, json={"type": "error", "error": {"type": error_type, "message": "test"}})

    client = LiveClient("test-key", "model-x", sdk_client=sdk_with_fake_http(handler))
    with pytest.raises(AIError) as info:
        client.complete(build_request(CALL, RUBRIC, "en", "model-x"))
    assert (info.value.code, info.value.fatal) == (code, fatal)
