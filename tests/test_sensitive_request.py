"""Guardrail: an agent must never ask for a full card number, PIN, CVV, password
or one-time code. The rule flags it in English and Spanish, and the AI cannot
clear the flag."""

import json

import pytest

import config
from call_qa.rules import find_sensitive_requests
from call_qa.scoring import score_call
from helpers import FakeAI, ai_answer, ai_item, make_call

RUBRIC = json.loads(config.RUBRIC_FILE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("line,kind", [
    ("Can you give me your full card number?", "card_number"),
    ("What's your PIN?", "pin"),
    ("Read me the code we just texted you", "otp"),
    ("What's the CVV on the back?", "cvv"),
    ("To verify you, I need your password.", "password"),
    ("¿Me das el número completo de tu tarjeta?", "card_number"),
    ("Dime tu PIN", "pin"),
    ("¿Me lees el código que te llegó por SMS?", "otp"),
    ("¿Cuál es tu contraseña?", "password"),
    ("¿Me confirmas el código de seguridad de atrás?", "cvv"),
    ("CAN YOU READ ME THE ONE-TIME CODE?", "otp"),
    ("¿cual es tu contrasena?", "password"),  # no accents, still caught
    # A negation elsewhere in the sentence does not cancel the request.
    ("No te voy a pedir tu PIN, pero dime los 4 dígitos del PIN.", "pin"),
    ("¿Me das tu PIN, no?", "pin"),
    ("Pásame el código que te llegó, no lo compartas con nadie más.", "otp"),
    ("No hay lío, me dices la clave de la app y listo.", "password"),
    # The CVV described instead of named, and requests without a question.
    ("Flip your card over and read me the three numbers on the back.", "cvv"),
    ("Dame los tres números de atrás de la tarjeta.", "cvv"),
    ("Go ahead with the card number, please.", "card_number"),
    ("Can you confirm your name, and also your PIN?", "pin"),
    ("¿Me confirmas tu nombre y tu clave?", "password"),
    ("No es necesario el correo, dime la clave.", "password"),
    ("Necesito que me digas tu PIN.", "pin"),
    ("Don't worry about it, just read me the code.", "otp"),
    ("What's the verification code we sent you?", "otp"),
    # The agent sends a code and then asks the customer to read it back.
    ("I'll send you a code, read it to me when it arrives.", "otp"),
    ("I'll text you a code and you read it back to me.", "otp"),
    ("Te mando un código y me lo lees, porfa.", "otp"),
    ("Te envío un código, me lo dictas cuando te llegue.", "otp"),
    ("I'm sending you a code now, can you read it back to me?", "otp"),
    ("Te mando un código y me lo pasas.", "otp"),
    # The code and the read-back in different sentences of the same agent line.
    ("I'll send you a code. Read it to me when it arrives.", "otp"),
    ("Te mando un código. Me lo dictas cuando te llegue.", "otp"),
    ("Te acabo de enviar un código, ¿me lo confirmas?", "otp"),
    ("Te llegó un código por SMS, ¿me lo puedes leer?", "otp"),
    ("Te acaba de llegar un código por SMS. ¿Me lo puedes leer?", "otp"),
    ("You just got a code by text. Can you read it to me?", "otp"),
])
def test_agent_request_is_flagged(line, kind):
    call = make_call("Customer: Hi, I need help with my account.", f"Agent: {line}")
    found = find_sensitive_requests(call)
    assert [(f["line"], f["kind"]) for f in found] == [("L2", kind)]


@pytest.mark.parametrize("line", [
    "Can you confirm the last 4 digits of your card?",
    "Can you confirm the last four digits of your card number?",
    "¿Me confirmas los últimos 4 dígitos?",
    "¿Me confirmas los últimos 4 dígitos de tu tarjeta?",
    "We will never ask for your PIN",
    "Nunca te vamos a pedir tu contraseña",
    "Please don't read me your card number",
    "Por favor no me compartas el código",
    "Your new PIN is set in the app.",
    "What's the error code on your screen?",
    "Can you tell me your full name and date of birth?",
    "¿Me confirmas tu nombre completo y tu fecha de nacimiento?",
    "I just sent a confirmation prompt to your Puentara app.",
    # The agent sending a code is not asking for it.
    "Thanks, I'll send a code to confirm your new device.",
    "We'll send you a verification code to confirm the change.",
    "Te voy a enviar un código para confirmar tu dispositivo nuevo.",
    "Gracias, te mando un código por SMS para confirmar que eres tú.",
    "I'll send a code to your phone, don't share it with anyone",
    "Te envío un código por SMS, no se lo des a nadie",
    "I'll send you a code, if anyone asks you to read it to them, hang up.",
    "I'll send you a code, never read it to anyone.",
    "Te mando un código, no me lo dictes, solo tócalo en la app.",
    "I'll send a code, just tap it in the app, you don't need to read it to me.",
    # An asking verb from an earlier clause does not carry into a negated clause.
    "Just to confirm, your PIN is never shared with us.",
    "Dime si te llegó la notificación, el código no lo compartas.",
    "We'll never ask for your PIN, and we won't ask for your password either",
    "No, don't give me your card number, just the last 4",
    "Nunca te pedimos el código, ¿vale?",
])
def test_allowed_agent_lines_are_not_flagged(line):
    call = make_call("Customer: Hola, necesito ayuda.", f"Agent: {line}")
    assert find_sensitive_requests(call) == []


@pytest.mark.parametrize("line", [
    "Customer: My card number is 0000 1234 5678 9012, what's my PIN?",
    "Cliente: ¿Me das mi contraseña? Mi PIN es 1234.",
    "Customer: Can you read me the code you sent?",
])
def test_customer_lines_are_never_checked(line):
    call = make_call("Agent: Thanks for calling Puentara, how can I help?", line)
    assert find_sensitive_requests(call) == []


def test_rule_beats_ai_the_flag_stays_when_ai_says_met():
    call = make_call("Agent: Hi, this is Dana from Puentara.", "Customer: Hi.",
                     "Agent: What's your PIN?", reason="account_access")
    answer = ai_answer(call, "met")  # the AI claims everything is fine
    result = score_call(call, FakeAI(answer), RUBRIC, "en", "m")
    item = next(i for i in result["items"] if i["id"] == "sensitive_data")
    assert item["status"] == "not_met"
    assert item["checked_by"] == "rule"
    assert result["auto_fail"] is True
    assert result["suggested_score"] == 0
    assert result["flags"][0]["text"] == "AUTO-FAIL FLAG: asked for the PIN (L3), reviewer must confirm"


def test_spanish_flag_text():
    call = make_call("Agente: Hola, te habla Marco de Puentara.", "Cliente: Hola.",
                     "Agente: Dime tu PIN", reason="account_access")
    result = score_call(call, FakeAI(ai_answer(call)), RUBRIC, "es", "m")
    assert result["flags"][0]["text"] == "ALERTA AUTO-FAIL: pidió el PIN (L3), un revisor debe confirmarlo"


def test_ai_can_raise_a_concern_the_rules_missed():
    call = make_call("Agent: Thanks for calling Puentara.", "Customer: Hi.",
                     "Agent: Go ahead and spell out those sixteen numbers for me.")
    answer = ai_answer(call, sensitive_data=ai_item("not_met", "L3", "spell out those sixteen numbers"))
    result = score_call(call, FakeAI(answer), RUBRIC, "en", "m")
    item = next(i for i in result["items"] if i["id"] == "sensitive_data")
    assert item["status"] == "needs_review"
    assert item["checked_by"] == "rule+ai"
    assert result["auto_fail"] is False  # only the rule sets the auto-fail flag


def test_ai_concern_without_valid_evidence_is_ignored():
    call = make_call("Agent: Thanks for calling Puentara.", "Customer: Hi.")
    answer = ai_answer(call, sensitive_data=ai_item("not_met", "L9", "made up words"))
    result = score_call(call, FakeAI(answer), RUBRIC, "en", "m")
    item = next(i for i in result["items"] if i["id"] == "sensitive_data")
    assert item["status"] == "met"
