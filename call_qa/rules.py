"""Rule checks that do not need AI. They run in demo mode and in live mode.

- sensitive-data request: the agent asks for a full card number, PIN, CVV,
  password or a one-time code -> auto-fail flag. The AI can never clear it.
- outcome promise on a dispute call ("you'll definitely get your money back")
  -> flag for the reviewer (not auto-fail).
- required disclosures (recording notice; on disputes, the timeline) and the
  greeting -> phrase lists from rubric.json.

Only AGENT lines are checked: a customer who reads out their own card number
is not the agent's mistake (and the number is masked anyway).
All matching is done on lowercase text without accents, so "Contraseña",
"contrasena" and "CONTRASEÑA" are the same word.
"""

import re

import config
from call_qa.language import strip_accents
from call_qa.mask import CARD_MASK, CODE_MASK
from call_qa.strings import t

# --- Sensitive-data requests -------------------------------------------------
# First match wins, so "codigo de seguridad" counts as CVV, not as a code.
SENSITIVE_TERMS = [
    ("card_number", re.compile(
        r"\b(card number|full card|16 digits|numero (completo )?de (tu |la )?tarjeta"
        r"|numero completo|numeros de (tu |la )?tarjeta|16 digitos)\b")),
    # CVV also when the agent describes it instead of naming it.
    ("cvv", re.compile(r"\b(cvv2?|cvc|security code|codigo de seguridad|(three|3) (numbers|digits) on the back"
                       r"|signature strip|(tres|3) (numeros|digitos) de atras|numeros de atras)\b")),
    ("pin", re.compile(r"\b(pin|nip)\b")),
    ("password", re.compile(r"\b(password|passcode|contrasena|clave)\b")),
    ("otp", re.compile(r"\b(one[- ]time (pass)?code|verification code|otp|code|codigo)\b")),
]

# A request needs an asking verb in the same sentence. "Your PIN is set in the
# app" is not a request; "What's your PIN?" is.
REQUEST_CUE = re.compile(
    r"\b(give me|tell me|read me|read (it|that|them|out)|what'?s|what is|whats|confirm|provide"
    r"|share|send me|type in|i need|i'll need|i will need|need your|can i (get|have)|go ahead (with|and)"
    r"|may i (get|have)|let me (get|have)|dame|dime|me das|me dices|me lees|leeme|me pasas"
    r"|pasame|me compartes|comparteme|me confirmas|confirma|confirmame|cual es|necesito"
    r"|me puedes (dar|decir|leer|confirmar|compartir|pasar)|me regalas|dictame|me dictas)\b")

# "We will never ask for your PIN", "Nunca te vamos a pedir tu contraseña",
# "Por favor no me compartas el código" are good practice, not requests.
# A negation only counts inside its own clause and BEFORE the asking verb or
# the sensitive word: in "¿Me das tu PIN, no?" the "no" is a tag, not a negation.
NEGATION = re.compile(r"\b(never|don'?t|do not|won'?t|will not|not|no|nunca|jamas|ni)\b")
CLAUSE_SPLIT = re.compile(r",|;| but | pero | y ")
TRAILING_TAG = re.compile(r"\s*\b(no|ok|okay|right|verdad)\s*$")

# Removed before checking, so they do not look like requests or negations.
HARMLESS = re.compile(
    r"\b(error code|zip code|postal code|promo code|referral code|codigo de error|codigo postal"
    r"|codigo promocional|no problem|no worries|no hay problema|no hay lio|no pasa nada|no te preocupes)\b")

# The agent SENDING a code is not asking for one: "I'll send a code to confirm
# your new device", "te envío un código". Reading it back is still a request.
AGENT_SENDS_CODE = re.compile(
    r"\b(i'?ll|i will|we'?ll|we will|i'?m going to|we'?re going to|i'?m sending|we'?re sending"
    r"|i just sent|we just sent|i sent|we sent|te envio|te mando|te enviamos|te mandamos"
    r"|te (vamos|voy) a (enviar|mandar)|te acabo de (enviar|mandar))\b[^,;]{0,40}\b(code|codigo)\b")
# A code that just reached the customer: "te llegó un código", "you just got a code".
CODE_ARRIVED = re.compile(
    r"\b(te llego|te acaba de llegar|you (just )?got|we (just )?texted you|i (just )?texted you)\b"
    r"[^,;]{0,40}\b(code|codigo)\b")
# ...but asking the customer to read that code back IS a one-time-code request:
# "I'll send you a code, read it to me", "Te mando un código y me lo lees".
# In English it needs "back", "to me" or "can you": "if anyone asks you to read
# it to them, hang up" is a warning, not a request.
READ_BACK = re.compile(
    r"\b(read (it|them|that) back( to me)?|read (it|them|that) to me|(can|could|would) you read (it|them|that)"
    r"|me lo (lees|dices|dictas|pasas|confirmas)|me lo (puedes|podrias) (leer|dictar|decir|pasar)"
    r"|leemelo|dictamelo)\b")

# Asking for the last 4 digits of the card is an allowed verification factor.
LAST_FOUR = re.compile(r"\b(last (4|four)|ultimos? (4|cuatro)|termina en|ends in)\b")

# --- Outcome promises on dispute calls --------------------------------------
PROMISES = [
    re.compile(r"\b(definitely|for sure|guarantee[ds]?|certainly|absolutely|i promise|we promise|100 ?%)\b"
               r".{0,40}\b(money back|refund(ed)?|reimburs\w*|get it back|win|credit(ed)?|revers\w*)"),
    re.compile(r"\b(you'?ll|you will|we'?ll|we will)\s+(\w+\s+){0,2}(get|give)\s+(you\s+)?(your|the)\s+money back"),
    re.compile(r"\b(we'?ll|we will) (definitely |for sure )?refund (you|it|the)"),
    re.compile(r"\b(seguro|seguramente|sin duda|garantiz\w*|te prometo|te lo prometo|de seguro|por supuesto|100 ?%)\b"
               r".{0,40}\b(devolv\w*|devuelv\w*|reembols\w*|reintegr\w*|recuper\w*|ganas)"),
    re.compile(r"\bte (devolvemos|vamos a devolver|reembolsamos|vamos a reembolsar) (el|tu|todo|los)"),
]
# "If the review is in your favor, we'll refund you" is a next step, not a promise.
CONDITIONAL = re.compile(
    r"\b(if|unless|depending|depends|in case|can'?t promise|cannot promise|can'?t guarantee"
    r"|cannot guarantee|si (la|el|se|procede|resulta|confirman|aprueban)|depende|dependiendo"
    r"|en caso de|no (te )?(puedo|podemos) (prometer|garantizar)|no te prometo)\b")

SENTENCE_SPLIT = re.compile(r"[.?!;¿¡]+")


def normalize(text):
    """Lowercase, no accents, no mask tokens, single spaces."""
    text = text.replace(CARD_MASK, " ").replace(CODE_MASK, " ").replace("’", "'")
    return " ".join(strip_accents(text).split())


def sentences(text):
    return [s.strip() for s in SENTENCE_SPLIT.split(normalize(text)) if s.strip()]


def agent_lines(call):
    return [line for line in call["lines"] if line["speaker"] == "agent"]


def sensitive_term(clause):
    """(kind, position) of the first sensitive word in a clause, or (None, None)."""
    for kind, pattern in SENSITIVE_TERMS:
        if kind == "card_number" and LAST_FOUR.search(clause):
            continue  # "confirm the last 4 digits of your card number" is allowed
        if kind == "otp" and AGENT_SENDS_CODE.search(clause):
            continue  # the agent sends a code; asking to read it back is a separate clause
        found = pattern.search(clause)
        if found:
            return kind, found.start()
    return None, None


def sensitive_kind(sentence, context=None):
    """Return the kind of sensitive data this sentence asks for, or None.

    `context` is shared by the sentences of one agent line, so "I'll send you
    a code. Read it to me when it arrives." is caught across the period.

    The sentence is split into clauses. An asking verb in an earlier clause
    still counts ("Can you confirm your name, and also your PIN?"), unless that
    verb was itself negated ("Please don't read me your card number"), or the
    current clause has any negation ("Just to confirm, your PIN is never shared").
    """
    sentence = HARMLESS.sub(" ", sentence)
    context = {} if context is None else context
    asking = False
    for clause in CLAUSE_SPLIT.split(sentence):
        clause = TRAILING_TAG.sub("", clause.strip())
        cue = REQUEST_CUE.search(clause)
        negation = NEGATION.search(clause)
        cue_ok = cue is not None and not (negation and negation.start() < cue.start())
        if AGENT_SENDS_CODE.search(clause) or CODE_ARRIVED.search(clause):
            context["code"] = True
        read_back = READ_BACK.search(clause)
        if context.get("code") and read_back and not (negation and negation.start() < read_back.start()):
            return "otp"
        kind, position = sensitive_term(clause)
        if kind:
            neg_before_term = negation is not None and negation.start() < position
            if (cue_ok and not neg_before_term) or (asking and negation is None):
                return kind
        asking = asking or cue_ok
    return None


def find_sensitive_requests(call):
    """[{"line": "L7", "kind": "pin", "quote": "..."}] for agent lines only."""
    found = []
    for line in agent_lines(call):
        context = {}  # shared by the sentences of this line only
        for sentence in sentences(line["text"]):
            kind = sensitive_kind(sentence, context)
            if kind:
                found.append({"line": line["id"], "kind": kind, "quote": line["text"]})
                break  # one flag per line is enough
    return found


def is_outcome_promise(sentence):
    if CONDITIONAL.search(sentence):
        return False
    return any(p.search(sentence) for p in PROMISES)


def find_outcome_promises(call):
    """Promised outcomes on dispute calls (agent lines only)."""
    if call["reason"] not in config.DISPUTE_REASONS:
        return []
    return [{"line": line["id"], "quote": line["text"]} for line in agent_lines(call)
            if any(is_outcome_promise(s) for s in sentences(line["text"]))]


def first_line_with(lines, phrases):
    """The first line that contains one of the phrases (compared without accents)."""
    wanted = [normalize(p) for p in phrases]
    for line in lines:
        text = normalize(line["text"])
        if any(p in text for p in wanted):
            return line
    return None


def item(item_id, status, rationale, evidence=(), checked_by="rule"):
    return {"id": item_id, "status": status, "rationale": rationale,
            "evidence": list(evidence), "checked_by": checked_by}


def evidence_of(line):
    return {"line": line["id"], "quote": line["text"]}


def check_greeting(call, rubric_item, company, lang):
    lines = agent_lines(call)[:rubric_item.get("agent_lines_to_check", 2)]
    parts = {"company": first_line_with(lines, [company]),
             "name": first_line_with(lines, rubric_item["phrases"]["name"]),
             "offer_help": first_line_with(lines, rubric_item["phrases"]["offer_help"])}
    names = t(lang, "greeting_parts")
    missing = [names[key] for key, line in parts.items() if line is None]
    found = {line["id"]: line for line in parts.values() if line}
    evidence = [evidence_of(line) for line in found.values()]
    if not missing:
        return item("greeting", "met", t(lang, "rules")["greeting_met"], evidence)
    status = "not_met" if len(missing) == len(parts) else "partial"
    return item("greeting", status, t(lang, "rules")["greeting_missing"].format(
        missing=", ".join(missing)), evidence)


def check_sensitive(requests, lang):
    if not requests:
        return item("sensitive_data", "met", t(lang, "rules")["sensitive_ok"])
    kinds = t(lang, "sensitive_kinds")
    asked = ", ".join(dict.fromkeys(kinds[r["kind"]] for r in requests))
    lines = ", ".join(r["line"] for r in requests)
    return item("sensitive_data", "not_met",
                t(lang, "rules")["sensitive_flag"].format(kinds=asked, lines=lines),
                [{"line": r["line"], "quote": r["quote"]} for r in requests])


def check_disclosures(call, rubric_item, promises, lang):
    lines = agent_lines(call)
    names = t(lang, "disclosure_parts")
    checks = {"recording": first_line_with(lines, rubric_item["recording_notice"])}
    if call["reason"] in config.DISPUTE_REASONS:
        checks["timeline"] = first_line_with(lines, rubric_item["dispute_timeline"])
    found = [key for key, line in checks.items() if line]
    missing = [names[key] for key, line in checks.items() if not line]
    evidence = [evidence_of(line) for line in checks.values() if line]
    total, ok = len(checks), len(found)
    if call["reason"] in config.DISPUTE_REASONS:
        total += 1
        if promises:
            missing.append(names["no_promise"])
            evidence += [{"line": p["line"], "quote": p["quote"]} for p in promises]
        else:
            ok += 1
    if not missing:
        return item("disclosures", "met", t(lang, "rules")["disclosures_met"], evidence)
    status = "not_met" if ok == 0 else "partial"
    return item("disclosures", status,
                t(lang, "rules")["disclosures_missing"].format(missing=", ".join(missing)), evidence)


def run_rules(call, rubric, lang):
    """Rule results for one call: {"items": {...}, "sensitive": [...], "promises": [...]}."""
    by_id = {i["id"]: i for i in rubric["items"]}
    requests = find_sensitive_requests(call)
    promises = find_outcome_promises(call)
    items = {}
    if "greeting" in by_id:
        items["greeting"] = check_greeting(call, by_id["greeting"], rubric["company"], lang)
    if "sensitive_data" in by_id:
        items["sensitive_data"] = check_sensitive(requests, lang)
    if "disclosures" in by_id:
        items["disclosures"] = check_disclosures(call, by_id["disclosures"], promises, lang)
    for rubric_item in rubric["items"]:  # e.g. verification on a general question
        if call["reason"] in rubric_item.get("not_applicable_reasons", []):
            items[rubric_item["id"]] = item(rubric_item["id"], "n/a", t(lang, "rules")["not_applicable"])
    return {"items": items, "sensitive": requests, "promises": promises}
