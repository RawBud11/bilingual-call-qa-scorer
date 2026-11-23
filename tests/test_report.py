"""The review page: escaped, no form, every call pending, never a verdict on a person."""

import json
import re

import pytest

import config
from call_qa.ai import FixtureClient
from call_qa.report_html import build_html
from call_qa.scoring import agent_summary, score_call
from call_qa.strings import STRINGS
from call_qa.transcript import load_calls
from helpers import FakeAI, ai_answer, make_call

RUBRIC = json.loads(config.RUBRIC_FILE.read_text(encoding="utf-8"))
VERDICT = re.compile(r"\b(pass|passed|passes|fail|failed|fails|failing|aprob\w*|reprob\w*)\b", re.IGNORECASE)


def sample_page(lang):
    results = [score_call(c, FixtureClient(), RUBRIC, lang, "m") for c in load_calls(config.SAMPLE_CALLS_DIR)]
    return results, build_html(results, agent_summary(results), RUBRIC, lang, STRINGS[lang]["banner_demo"])


def test_transcript_text_is_escaped():
    call = make_call("Agent: Thanks for calling Puentara.",
                     "Customer: <script>alert('x')</script> <b>bold</b> & more", call_id="<C1>")
    result = score_call(call, FakeAI(ai_answer(call)), RUBRIC, "en", "m")
    page = build_html([result], agent_summary([result]), RUBRIC, "en", "<banner>")
    assert "<script>" not in page and "<b>bold" not in page and "<banner>" not in page
    assert "&lt;script&gt;" in page and "&amp; more" in page and "&lt;C1&gt;" in page


@pytest.mark.parametrize("lang,pending", [("en", "Reviewer decision: pending"),
                                          ("es", "Decisión del revisor: pendiente")])
def test_no_form_and_every_call_pending(lang, pending):
    results, page = sample_page(lang)
    lowered = page.lower()
    assert "<form" not in lowered and "<button" not in lowered and 'type="submit"' not in lowered
    assert "<input" not in lowered and "<script" not in lowered
    assert page.count(pending) == len(results) == 6


@pytest.mark.parametrize("lang", ["en", "es"])
def test_no_pass_or_fail_about_a_person(lang):
    _, page = sample_page(lang)
    # The only allowed use is the auto-fail flag label ("AUTO-FAIL FLAG" / "ALERTA AUTO-FAIL").
    without_label = re.sub(r"auto-fail", "", page, flags=re.IGNORECASE)
    assert not VERDICT.search(without_label), VERDICT.search(without_label)


def test_no_verdict_words_in_ui_strings():
    for lang, table in STRINGS.items():
        text = re.sub(r"auto-fail", "", json.dumps(table, ensure_ascii=False), flags=re.IGNORECASE)
        assert not VERDICT.search(text), (lang, VERDICT.search(text))


def test_demo_banner_and_evidence_links():
    _, page = sample_page("en")
    assert "Demo mode: AI answers are hand-written fixtures" in page
    assert 'href="#C002-L7"' in page and 'id="C002-L7"' in page
    assert "AUTO-FAIL FLAG: asked for the PIN (L7), reviewer must confirm" in page
    assert "Puentara is a fictional company" in page
    assert "100/100 (provisional, 1 item to review)" in page
    assert "<th>To confirm</th>" in page


def test_spanish_page_uses_spanish_labels_and_keeps_quotes_in_call_language():
    _, page = sample_page("es")
    assert '<html lang="es">' in page
    assert "Resumen por agente" in page and "Verificación de identidad" in page
    assert "Modo demo" in page
    assert "I&#x27;m sorry, that&#x27;s stressful" in page  # EN call quoted in English
