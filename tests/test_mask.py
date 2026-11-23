"""Masking. The first tests are copied from bilingual-ticket-triage; the last ones
check that no card number or code reaches the AI request, the CSV or the HTML."""

import json
import re
from types import SimpleNamespace

import pytest

import config
import score
from call_qa.ai import LiveClient
from call_qa.mask import CARD_MASK, CODE_MASK, mask_sensitive
from call_qa.scoring import score_call
from helpers import make_call

RUBRIC = json.loads(config.RUBRIC_FILE.read_text(encoding="utf-8"))
LONG_DIGITS = re.compile(r"\d{13,19}")


@pytest.mark.parametrize("text", [
    "My card number is 0000123456789012, please block it.",
    "My card number is 0000 1234 5678 9012, please block it.",
    "Mi tarjeta es 0000-1234-5678-9012, bloquéenla por favor.",
])
def test_masks_card_numbers(text):
    masked, count = mask_sensitive(text)
    assert CARD_MASK in masked
    assert count == 1
    assert not re.search(r"\d{4}", masked)


@pytest.mark.parametrize("text,secret", [
    ("Someone used my card, CVV 123", "123"),
    ("el cvv: 4821 por si lo necesitas", "4821"),
    ("Mi código de seguridad es 907", "907"),
    ("I got a code 482913 I never asked for", "482913"),
    ("Me llegó el código 482913 por SMS", "482913"),
    ("my PIN is 1234", "1234"),
    ("OTP: 99210", "99210"),
    ("mi código es 123 456, no me deja entrar", "123 456"),
])
def test_masks_cvv_and_codes(text, secret):
    masked, count = mask_sensitive(text)
    assert secret not in masked
    assert CODE_MASK in masked
    assert count == 1


@pytest.mark.parametrize("text", [
    "I sent $139.85 on Oct 15 and it says pending.",
    "The card ending in 0042 is frozen.",
    "Terminan en 0042.",  # last 4 digits alone are fine to keep
    "Within 10 business days.",
])
def test_leaves_normal_numbers_alone(text):
    assert mask_sensitive(text) == (text, 0)


def secret_call():
    return make_call(
        "Agent: Thanks for calling Puentara, my name is Dana. How can I help?",
        "Customer: My card is 0000 1043 3218 1960, CVV 529, and the code was 482913.",
        "Cliente: Mi tarjeta es 0000-1111-2222-3333 y mi PIN 4321.",
        reason="card_lost_stolen")


def test_transcript_lines_are_masked_when_read():
    call = secret_call()
    text = " ".join(line["text"] for line in call["lines"])
    for secret in ("0000 1043", "529", "482913", "0000-1111", "4321"):
        assert secret not in text
    assert call["masked_count"] == 5


class FakeMessages:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text='{"items": {}}')])


def test_request_sent_to_the_sdk_has_no_card_numbers_or_codes():
    sdk = SimpleNamespace(messages=FakeMessages())
    client = LiveClient("test-key", "model-x", sdk_client=sdk)
    score_call(secret_call(), client, RUBRIC, "en", "model-x")
    sent = json.dumps(sdk.messages.calls[0], ensure_ascii=False)
    assert not LONG_DIGITS.search(sent.replace(" ", "").replace("-", ""))
    for secret in ("529", "482913", "4321"):
        assert secret not in sent
    assert CARD_MASK in sent


def test_csv_and_html_have_no_card_numbers_or_codes(tmp_path, monkeypatch):
    monkeypatch.setattr(score, "load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    calls_dir = tmp_path / "calls"
    calls_dir.mkdir()
    (calls_dir / "x.txt").write_text(
        "call_id: X1\nagent: Test\nreason: card_lost_stolen\n\n"
        "Agent: Thanks for calling Puentara.\n"
        "Customer: My card is 0000 1043 3218 1960, CVV 529, code 482913.\n", encoding="utf-8")
    out = tmp_path / "out"
    assert score.main(["--calls", str(calls_dir), "--out-dir", str(out)]) == 0
    for name in (config.CSV_NAME, config.HTML_NAME):
        text = (out / name).read_text(encoding="utf-8-sig")
        assert not LONG_DIGITS.search(text.replace(" ", "").replace("-", ""))
        assert "529" not in text and "482913" not in text
    assert CARD_MASK in (out / config.HTML_NAME).read_text(encoding="utf-8")
