"""Put rules and AI together for one call, and compute the suggested score.

Who decides what:
- rule items (greeting, sensitive data, disclosures) and "n/a" items: the rules.
- AI items (verification, empathy, resolution): the AI, but only with valid
  evidence. Anything wrong with the AI answer -> "needs_review".
- sensitive data: the rule always wins. The AI can only raise a concern the
  rules missed (-> "needs_review"); it can never clear a rule flag.

The suggested score is a weighted average of the items that have a status
(met = 1, partial = 0.5, not_met = 0). "n/a" and "needs_review" items are left
out. An auto-fail flag sets the suggested score to 0 until a reviewer confirms.
"""

from collections import Counter, defaultdict

import config
from call_qa.ai import AIError, ai_item_ids, build_request, parse_ai_response
from call_qa.rules import item, run_rules
from call_qa.strings import t


def needs_review(item_id, problem, lang):
    detail = t(lang, "ai_problems").get(problem, problem)
    return item(item_id, "needs_review", t(lang, "needs_review_reason").format(problem=detail),
                checked_by="ai")


def merge_sensitive(rule_item, ai_answer, lang):
    """Rule first. The AI can send a 'met' to review, never turn a flag into 'met'."""
    if rule_item["status"] != "met" or not ai_answer or "problem" in ai_answer:
        return rule_item
    if ai_answer["status"] != "not_met":
        return rule_item
    lines = ", ".join(e["line"] for e in ai_answer["evidence"])
    rationale = t(lang, "rules")["sensitive_ai_concern"].format(lines=lines, rationale=ai_answer["rationale"])
    return item("sensitive_data", "needs_review", rationale, ai_answer["evidence"], checked_by="rule+ai")


def suggested_score(items, weights, auto_fail):
    if auto_fail:
        return 0
    counted = [(weights[i["id"]], config.STATUS_VALUES[i["status"]])
               for i in items if i["status"] in config.STATUS_VALUES]
    total = sum(w for w, _ in counted)
    if not total:
        return None
    return round(100 * sum(w * v for w, v in counted) / total)


def scored_weight(items, weights):
    """How much of the rubric that applies to this call (out of 100) is really scored.
    Below 100 means some items wait for a person ("needs_review")."""
    total = sum(weights[i["id"]] for i in items if i["status"] != "n/a")
    counted = sum(weights[i["id"]] for i in items if i["status"] in config.STATUS_VALUES)
    return round(100 * counted / total) if total else 0


def score_call(call, client, rubric, lang, model):
    """Score one call. Only fatal AI errors (bad key, unknown model) are raised."""
    rules = run_rules(call, rubric, lang)
    ai_answers, ai_problem = {}, None
    try:
        raw = client.complete(build_request(call, rubric, lang, model))
        ai_answers = parse_ai_response(raw, call, ai_item_ids(rubric))
    except AIError as error:
        if error.fatal:
            raise
        ai_problem = error.code  # every AI item goes to review, rules still count

    items = []
    for rubric_item in rubric["items"]:
        item_id = rubric_item["id"]
        answer = ai_answers.get(item_id)
        if item_id == "sensitive_data" and rubric_item.get("ai_can_raise"):
            result = merge_sensitive(rules["items"][item_id], answer, lang)
        elif item_id in rules["items"]:
            result = rules["items"][item_id]
        elif answer is None:
            result = needs_review(item_id, ai_problem or "missing_item", lang)
        elif "problem" in answer:
            result = needs_review(item_id, answer["problem"], lang)
        else:
            result = item(item_id, answer["status"], answer["rationale"], answer["evidence"], "ai")
        items.append(result)

    kinds = t(lang, "sensitive_kinds")
    flags = [{"type": "auto_fail", "line": r["line"],
              "text": t(lang, "flags")["auto_fail"].format(kind=kinds[r["kind"]], line=r["line"])}
             for r in rules["sensitive"]]
    flags += [{"type": "outcome_promise", "line": p["line"],
               "text": t(lang, "flags")["outcome_promise"].format(line=p["line"])}
              for p in rules["promises"]]
    auto_fail = any(f["type"] == "auto_fail" for f in flags)
    weights = {i["id"]: i["weight"] for i in rubric["items"]}
    review_items = [i["id"] for i in items if i["status"] == "needs_review"]
    return {
        **{key: call[key] for key in ("call_id", "agent", "reason", "channel", "language",
                                      "lines", "masked_count")},
        "items": items,
        "flags": flags,
        "auto_fail": auto_fail,
        "suggested_score": suggested_score(items, weights, auto_fail),
        "scored_weight": scored_weight(items, weights),
        "review_items": review_items,
        # Provisional: a person still has to confirm a flag or review an item
        # before this score means anything.
        "provisional": auto_fail or bool(review_items),
        "reviewer_decision": "pending",  # always: this tool never decides
    }


def agent_summary(results):
    """Per agent: calls, average suggested score, calls still to confirm, flags, most-missed items."""
    by_agent = defaultdict(list)
    for result in results:
        by_agent[result["agent"]].append(result)
    summary = []
    for agent in sorted(by_agent):
        calls = by_agent[agent]
        scores = [c["suggested_score"] for c in calls if c["suggested_score"] is not None]
        missed = Counter(i["id"] for c in calls for i in c["items"]
                         if i["status"] in ("not_met", "partial"))
        summary.append({
            "agent": agent,
            "calls": len(calls),
            "average": round(sum(scores) / len(scores)) if scores else None,
            "to_confirm": sum(c["provisional"] for c in calls),
            "flags": sum(len(c["flags"]) for c in calls),
            "most_missed": missed.most_common(2),
        })
    return summary
