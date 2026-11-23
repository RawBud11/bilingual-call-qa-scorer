"""Small fakes shared by the tests. No network, no API key."""

import json

from call_qa.transcript import parse_transcript


class FakeAI:
    """Returns a fixed answer and remembers every request it got."""

    def __init__(self, answer):
        self.answer = answer
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer if isinstance(self.answer, str) else json.dumps(self.answer)


def make_call(*lines, reason="general_question", call_id="T001", agent="Test Agent"):
    """Build a call from ("Agent: ...", "Customer: ...") strings."""
    text = f"call_id: {call_id}\nagent: {agent}\nreason: {reason}\nchannel: phone\n\n" + "\n".join(lines)
    return parse_transcript(text, "test")


def ai_item(status="met", line="L1", quote=None, rationale="test rationale"):
    evidence = [] if quote is None else [{"line": line, "quote": quote}]
    return {"status": status, "rationale": rationale, "evidence": evidence}


def ai_answer(call, status="met", **overrides):
    """A valid AI answer that quotes the first line of the call for every item."""
    first = call["lines"][0]
    quote = first["text"][:20]
    items = {item_id: ai_item(status, first["id"], quote)
             for item_id in ("identity_verification", "sensitive_data", "empathy", "resolution")}
    items.update(overrides)
    return {"items": items}
