"""The AI step: build the request, call Claude (or read a fixture), check the answer.

The client classes, AIError, the SDK error handling and strip_tags are copied
from bilingual-ticket-triage (same behavior, keyed by call instead of ticket).

Three clients share one method, complete(request) -> raw text:
  LiveClient       real call through the official anthropic SDK (--live)
  FixtureClient    demo mode: saved answers from fixtures/ai_responses.json
  RecordingClient  wraps LiveClient and saves its answers (--live --record)

The AI only judges the soft items (verification quality, empathy, resolution)
and gives a second opinion on sensitive-data requests. Every judgment must
quote the transcript; check_evidence() makes sure the quote is really there.
"""

import json
import re
from datetime import date

import config
from call_qa.rules import normalize

LANGUAGE_NAMES = {"en": "English", "es": "Spanish"}


class AIError(Exception):
    """An AI problem. `code` is a key in strings.py "ai_problems".

    fatal=True means every call would fail the same way (bad key, unknown
    model), so the run stops with a clear message instead of 6 fallbacks.
    """

    def __init__(self, code, fatal=False):
        super().__init__(code)
        self.code = code
        self.fatal = fatal


TRANSCRIPT_TAG_RE = re.compile(r"<\s*/?\s*transcript\s*>", re.IGNORECASE)


def strip_tags(text):
    """Remove <transcript> / </transcript> said (or typed) inside a call, so a
    line cannot "close" the transcript block and pretend to be instructions."""
    return TRANSCRIPT_TAG_RE.sub("[tag removed]", text)


def ai_item_ids(rubric):
    """Items the AI is asked about: the AI-judged ones plus second opinions."""
    return [i["id"] for i in rubric["items"] if i["checked_by"] == "ai" or i.get("ai_can_raise")]


def build_request(call, rubric, report_lang, model):
    """Build the API request. The call's lines are already masked."""
    asked = set(ai_item_ids(rubric))
    items_text = "\n".join(f'- {i["id"]}: {i["description"]["en"]}'
                           for i in rubric["items"] if i["id"] in asked)
    factors = next((i["allowed_factors"]["en"] for i in rubric["items"] if "allowed_factors" in i), [])
    escalation = any(call["reason"] in i.get("escalation_reasons", []) for i in rubric["items"])
    system = config.PROMPT_FILE.read_text(encoding="utf-8")
    system = (system.replace("{company}", rubric["company"])
                    .replace("{items}", items_text)
                    .replace("{allowed_factors}", ", ".join(factors))
                    .replace("{report_language}", LANGUAGE_NAMES[report_lang]))
    header = (f'call_id: {strip_tags(call["call_id"])}\nreason: {call["reason"]}\n'
              f'escalation_required: {"yes" if escalation else "no"}')
    body = "\n".join(f'{line["id"]} {line["speaker"].capitalize()}: {strip_tags(line["text"])}'
                     for line in call["lines"])
    return {
        "call_id": call["call_id"],   # used by fixtures, not sent to the API
        "report_lang": report_lang,   # same
        "model": model,
        "max_tokens": config.AI_MAX_TOKENS,
        "system": system,
        "messages": [{"role": "user", "content": f"<transcript>\n{header}\n\n{body}\n</transcript>"}],
    }


def clean_quote(text):
    # Models often wrap quotes in quotation marks or cut them with "...".
    return normalize(str(text)).strip(" \"'“”«».…")


def check_evidence(evidence, status, lines_by_id):
    """Return None if the evidence is valid, otherwise a problem code.

    Every line ID must exist and every quote must appear in that line. A
    judgment without evidence is only accepted for "n/a".
    """
    if not isinstance(evidence, list):
        return "no_evidence"
    if not evidence:
        return None if status == "n/a" else "no_evidence"
    for entry in evidence:
        if not isinstance(entry, dict):
            return "no_evidence"
        line = lines_by_id.get(str(entry.get("line", "")).strip().upper())
        if line is None:
            return "bad_line"
        quote = clean_quote(entry.get("quote", ""))
        if len(quote) < 3 or quote not in normalize(line["text"]):
            return "quote_not_found"
    return None


def parse_ai_response(text, call, item_ids):
    """Check the model's answer item by item.

    Returns {item_id: {"status", "rationale", "evidence"}} for good items and
    {item_id: {"problem": code}} for items a person must review. Raises
    AIError("bad_json") if the answer is not usable at all.
    """
    # Models sometimes wrap JSON in ```json fences or add a sentence; take the
    # first {...} block and ignore the rest.
    found = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not found:
        raise AIError("bad_json")
    try:
        data = json.loads(found.group(0))
    except json.JSONDecodeError:
        raise AIError("bad_json") from None
    if not isinstance(data, dict) or not isinstance(data.get("items"), dict):
        raise AIError("bad_json")

    lines_by_id = {line["id"]: line for line in call["lines"]}
    results = {}
    for item_id in item_ids:
        answer = data["items"].get(item_id)
        if not isinstance(answer, dict):
            results[item_id] = {"problem": "missing_item"}
            continue
        status = answer.get("status")
        rationale = " ".join(str(answer.get("rationale") or "").split())[:300]
        if status not in config.AI_STATUSES:
            results[item_id] = {"problem": "bad_status"}
        elif not rationale:
            results[item_id] = {"problem": "bad_rationale"}
        else:
            problem = check_evidence(answer.get("evidence", []), status, lines_by_id)
            if problem:
                results[item_id] = {"problem": problem}
            else:
                evidence = [{"line": str(e["line"]).strip().upper(), "quote": str(e["quote"]).strip()}
                            for e in answer.get("evidence", [])]
                results[item_id] = {"status": status, "rationale": rationale, "evidence": evidence}
    return results


class LiveClient:
    def __init__(self, api_key, model, sdk_client=None):
        # Imported here, not at the top: the SDK takes seconds to load and
        # demo mode does not need it.
        import anthropic
        self.model = model
        # sdk_client lets tests pass a fake, so tests never touch the network.
        self.sdk = sdk_client or anthropic.Anthropic(
            api_key=api_key, timeout=config.AI_TIMEOUT_SECONDS, max_retries=2)

    def complete(self, request):
        import anthropic  # already loaded by __init__, so this is instant
        try:
            response = self.sdk.messages.create(
                model=request["model"], max_tokens=request["max_tokens"],
                system=request["system"], messages=request["messages"])
        except anthropic.AuthenticationError:
            raise AIError("auth", fatal=True) from None
        except anthropic.PermissionDeniedError:
            raise AIError("permission", fatal=True) from None
        except anthropic.NotFoundError:
            raise AIError("model", fatal=True) from None
        except anthropic.APITimeoutError:
            raise AIError("timeout") from None
        except anthropic.APIConnectionError:
            raise AIError("connection") from None
        except anthropic.RateLimitError:
            raise AIError("rate_limit") from None
        except anthropic.BadRequestError:
            raise AIError("bad_request") from None
        except anthropic.APIError:
            raise AIError("server") from None
        return "".join(block.text for block in response.content
                       if getattr(block, "type", "") == "text")


class FixtureClient:
    """Demo mode. Fixture file layout:
    {"responses": {"C001": {"en": {"source": "hand-written", "response": {...}}}}}
    "response" is a JSON object, or a string for raw (possibly broken) text.
    """

    def __init__(self, path=config.FIXTURES_FILE):
        with open(path, encoding="utf-8") as f:
            self.responses = json.load(f).get("responses", {})

    def sources(self):
        """Set of labels in the file: {"hand-written"}, {"recorded"} or both."""
        return {entry["source"] for by_lang in self.responses.values()
                for entry in by_lang.values()}

    def complete(self, request):
        entry = self.responses.get(request["call_id"], {}).get(request["report_lang"])
        if entry is None:
            raise AIError("no_fixture")
        response = entry["response"]
        return response if isinstance(response, str) else json.dumps(response, ensure_ascii=False)


class RecordingClient:
    """Calls the live client and keeps every raw answer, to save as fixtures."""

    def __init__(self, live_client):
        self.live = live_client
        self.recorded = []  # (call_id, lang, raw_text)

    def complete(self, request):
        text = self.live.complete(request)
        self.recorded.append((request["call_id"], request["report_lang"], text))
        return text

    def save(self, path=config.FIXTURES_FILE):
        """Merge recorded answers into the fixture file, labeled "recorded"."""
        data = {"responses": {}}
        if path.exists():
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        today = date.today().isoformat()
        for call_id, lang, text in self.recorded:
            try:
                response = json.loads(text)  # store readable JSON when possible
            except json.JSONDecodeError:
                response = text
            data.setdefault("responses", {}).setdefault(call_id, {})[lang] = {
                "source": "recorded", "model": self.live.model,
                "recorded_at": today, "response": response}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        return len(self.recorded)
