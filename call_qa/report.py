"""Terminal summary and the CSV file (one row per call).

CSV column names and codes stay in English so a spreadsheet or script that
reads the file does not break when the report language changes. The flag
text and the reviewer decision follow --report-lang.
"""

import csv

from call_qa.strings import t

BASE_COLUMNS = ["call_id", "agent", "reason", "language", "suggested_score", "scored_weight", "auto_fail_flag",
                "flags", "needs_review_items"]
END_COLUMNS = ["masked_items", "reviewer_decision"]


def score_text(result, lang):
    """"85/100", or "100/100 (provisional, 1 item to review)" when a person must still check."""
    if result["suggested_score"] is None:
        return t(lang, "no_score")
    score = result["suggested_score"]
    if result["auto_fail"]:
        return t(lang, "provisional_flag").format(score=score)
    if result["review_items"]:
        count = len(result["review_items"])
        return t(lang, "provisional_review").format(
            score=score, count=count, items=t(lang, "item_word")[0 if count == 1 else 1])
    return t(lang, "score").format(score=score)


def write_csv(path, results, rubric, lang):
    item_ids = [i["id"] for i in rubric["items"]]
    path.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig adds a BOM so Excel on Windows shows accents correctly.
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=BASE_COLUMNS + item_ids + END_COLUMNS)
        writer.writeheader()
        for r in results:
            row = {
                "call_id": r["call_id"], "agent": r["agent"], "reason": r["reason"],
                "language": r["language"],
                "suggested_score": "" if r["suggested_score"] is None else r["suggested_score"],
                "scored_weight": r["scored_weight"],
                "auto_fail_flag": str(r["auto_fail"]).lower(),
                "flags": " | ".join(f["text"] for f in r["flags"]),
                "needs_review_items": " ".join(r["review_items"]),
                "masked_items": r["masked_count"],
                "reviewer_decision": t(lang, "pending"),
            }
            row.update({i["id"]: i["status"] for i in r["items"]})
            writer.writerow(row)


def most_missed_text(entry, rubric, lang):
    names = {i["id"]: i["name"][lang] for i in rubric["items"]}
    if not entry["most_missed"]:
        return t(lang, "none")
    return ", ".join(f"{names[item_id]} ({count})" for item_id, count in entry["most_missed"])


def print_summary(results, summary, rubric, lang, calls_path, html_path, csv_path):
    print()
    print(t(lang, "title"))
    print(t(lang, "read").format(count=len(results), path=calls_path))
    print()
    head = t(lang, "table_header")
    width = max([len(head[3])] + [len(score_text(r, lang)) for r in results])
    print(f"  {head[0]:<7} {head[1]:<12} {head[2]:<7} {head[3]:<{width}} {head[4]}")
    names = {i["id"]: i["name"][lang] for i in rubric["items"]}
    for r in results:
        score = score_text(r, lang)
        flags = [f["text"] for f in r["flags"]]
        if r["review_items"]:
            flags.append(t(lang, "to_review").format(
                items=", ".join(names[i] for i in r["review_items"])))
        flags = flags or [t(lang, "none")]
        print(f'  {r["call_id"]:<7} {r["agent"]:<12} {r["language"]:<7} {score:<{width}} {flags[0]}')
        for extra in flags[1:]:
            print(f'  {"":<7} {"":<12} {"":<7} {"":<{width}} {extra}')

    print()
    print(t(lang, "agents_header"))
    cols = t(lang, "agents_columns")
    print(f"  {cols[0]:<12} {cols[1]:>8} {cols[2]:>18} {cols[3]:>14} {cols[4]:>8}  {cols[5]}")
    for entry in summary:
        average = "-" if entry["average"] is None else t(lang, "score").format(score=entry["average"])
        print(f'  {entry["agent"]:<12} {entry["calls"]:>8} {average:>18} {entry["to_confirm"]:>14} {entry["flags"]:>8}  '
              f'{most_missed_text(entry, rubric, lang)}')

    print()
    print(t(lang, "masked").format(count=sum(r["masked_count"] for r in results)))
    print(t(lang, "pending_note"))
    print(t(lang, "wrote").format(html=html_path, csv=csv_path))
