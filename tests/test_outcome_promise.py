"""Dispute calls: collect the facts and give a timeline, never promise an outcome."""

import pytest

from call_qa.rules import find_outcome_promises
from helpers import make_call


@pytest.mark.parametrize("line", [
    "You'll definitely get your money back",
    "Don't worry, we'll refund you today.",
    "I guarantee the refund will go through.",
    "Seguro te devolvemos el dinero",
    "Te prometo que te vamos a reembolsar todo.",
    "Tranquila, te vamos a devolver el dinero.",
])
def test_promise_on_dispute_call_is_flagged(line):
    call = make_call("Customer: I want to dispute a charge.", f"Agent: {line}", reason="charge_dispute")
    assert [p["line"] for p in find_outcome_promises(call)] == ["L2"]


@pytest.mark.parametrize("line", [
    "We'll review it and let you know within 10 business days",
    "Vamos a revisarlo y te avisamos en un plazo de 10 días hábiles",
    "If the review is in your favor, we'll refund you.",
    "Si la revisión sale a tu favor, te devolvemos el dinero.",
    "I can't promise you'll get your money back, but we'll review it.",
    "No te puedo prometer que te devolvemos el dinero.",
])
def test_next_steps_are_not_promises(line):
    call = make_call("Cliente: Quiero disputar un cargo.", f"Agent: {line}", reason="charge_dispute")
    assert find_outcome_promises(call) == []


def test_only_dispute_calls_and_agent_lines_are_checked():
    not_dispute = make_call("Agent: You'll definitely get your money back", reason="fees")
    assert find_outcome_promises(not_dispute) == []
    customer = make_call("Customer: You'll definitely give me my money back, right?", reason="charge_dispute")
    assert find_outcome_promises(customer) == []
