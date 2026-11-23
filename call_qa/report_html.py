"""The review page: output/qa_review.html, one static file, no JavaScript.

Every piece of text from a transcript, the rubric or the AI goes through
html.escape(), so a line like "<script>" shows as text and cannot run.
There is no form and no submit button: the page prepares the review, a
person writes the decision in their own QA tool.
"""

from html import escape

from call_qa.report import score_text
from call_qa.strings import t

CSS = """
body{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#f5f6f8;color:#1f2933;line-height:1.45}
main{max-width:1050px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:1.5rem;margin:0 0 4px} h2{font-size:1.2rem;margin:32px 0 8px}
h3{font-size:1.05rem;margin:0}
.banner{background:#fff4d6;border:1px solid #e6c46a;padding:10px 14px;border-radius:6px;margin:12px 0}
.card{background:#fff;border:1px solid #d9dee5;border-radius:8px;padding:16px;margin:16px 0}
table{border-collapse:collapse;width:100%;font-size:.92rem} th,td{border-bottom:1px solid #e4e7eb;padding:6px 8px;text-align:left;vertical-align:top}
th{background:#eef1f5}
.meta{color:#52606d;margin:4px 0 10px}
.score{font-size:1.3rem;font-weight:600}
.flag{background:#fde2e1;border:1px solid #e5a3a0;border-radius:6px;padding:6px 10px;margin:6px 0;font-weight:600}
.promise{background:#fff0db;border-color:#e8bc7c}
.s-met{color:#1d7a46;font-weight:600} .s-partial{color:#9a6700;font-weight:600}
.s-not_met{color:#b42318;font-weight:600} .s-needs_review{color:#6941c6;font-weight:600} .s-n\\/a{color:#52606d}
.quote{font-style:italic} .evidence a{font-weight:600}
.transcript{font-family:Consolas,monospace;font-size:.88rem;background:#fafbfc;border:1px solid #e4e7eb;border-radius:6px;padding:8px}
.line{padding:2px 4px} .line:target{background:#fff3b0} .line.flagged{background:#fde2e1}
.lid{color:#7b8794;display:inline-block;width:3.2em} .agent{color:#1849a9;font-weight:600} .customer{color:#5c3b9e;font-weight:600}
.decision{border:2px dashed #9aa5b1;border-radius:6px;padding:10px 14px;margin-top:12px}
.notes{height:3em;border-bottom:1px solid #9aa5b1}
footer{color:#7b8794;font-size:.85rem;margin-top:32px}
"""


def status_cell(status, lang):
    return f'<span class="s-{escape(status)}">{escape(t(lang, "statuses")[status])}</span>'


def evidence_cell(call_id, evidence):
    parts = []
    for e in evidence:
        anchor = escape(f'{call_id}-{e["line"]}')
        quote = e["quote"] if len(e["quote"]) <= 160 else e["quote"][:157] + "..."
        parts.append(f'<a href="#{anchor}">{escape(e["line"])}</a> '
                     f'<span class="quote">&ldquo;{escape(quote)}&rdquo;</span>')
    return "<br>".join(parts) or "-"


def agents_table(summary, rubric, lang):
    names = {i["id"]: i["name"][lang] for i in rubric["items"]}
    cols = t(lang, "agents_columns")
    rows = []
    for e in summary:
        average = "-" if e["average"] is None else t(lang, "score").format(score=e["average"])
        missed = ", ".join(f"{names[i]} ({n})" for i, n in e["most_missed"]) or t(lang, "none")
        rows.append(f'<tr><td>{escape(e["agent"])}</td><td>{e["calls"]}</td><td>{escape(average)}</td>'
                    f'<td>{e["to_confirm"]}</td><td>{e["flags"]}</td><td>{escape(missed)}</td></tr>')
    head = "".join(f"<th>{escape(c)}</th>" for c in cols)
    return f'<table><tr>{head}</tr>{"".join(rows)}</table>'


def call_section(r, rubric, lang):
    by_id = {i["id"]: i for i in rubric["items"]}
    meta = t(lang, "call_meta")
    score = score_text(r, lang)
    notes = []
    if r["auto_fail"]:
        notes.append(t(lang, "score_note_flag"))
    if r["review_items"]:
        notes.append(t(lang, "score_note_review").format(count=len(r["review_items"])))
    flags = "".join(f'<div class="flag{" promise" if f["type"] != "auto_fail" else ""}">'
                    f'{escape(f["text"])}</div>' for f in r["flags"]) or f'<p>{escape(t(lang, "no_flags"))}</p>'

    cols = "".join(f"<th>{escape(c)}</th>" for c in t(lang, "item_columns"))
    rows = []
    for i in r["items"]:
        info = by_id[i["id"]]
        weight = t(lang, "weight").format(weight=info["weight"])
        rows.append(
            f'<tr><td><strong>{escape(info["name"][lang])}</strong><br><small>{escape(weight)}</small></td>'
            f'<td>{status_cell(i["status"], lang)}</td>'
            f'<td>{escape(t(lang, "checked_by")[i["checked_by"]])}</td>'
            f'<td>{escape(i["rationale"])}</td>'
            f'<td class="evidence">{evidence_cell(r["call_id"], i["evidence"])}</td></tr>')

    flagged = {f["line"] for f in r["flags"]}
    speakers = t(lang, "speakers")
    lines = "".join(
        f'<div class="line{" flagged" if line["id"] in flagged else ""}" id="{escape(r["call_id"])}-{line["id"]}">'
        f'<span class="lid">{line["id"]}</span><span class="{line["speaker"]}">{escape(speakers[line["speaker"]])}:</span> '
        f'{escape(line["text"])}</div>' for line in r["lines"])

    return f"""
<section class="card" id="{escape(r["call_id"])}">
  <h3>{escape(r["call_id"])}</h3>
  <p class="meta">{escape(meta[0])}: {escape(r["agent"])} &middot; {escape(meta[1])}: {escape(t(lang, "reasons")[r["reason"]])}
  &middot; {escape(meta[2])}: {escape(t(lang, "languages").get(r["language"], r["language"]))}</p>
  <p>{escape(meta[3])}: <span class="score">{escape(score)}</span> {escape(" ".join(notes))}</p>
  {flags}
  <table><tr>{cols}</tr>{"".join(rows)}</table>
  <h3 style="margin-top:14px">{escape(t(lang, "transcript"))}</h3>
  <div class="transcript">{lines}</div>
  <div class="decision"><strong>{escape(t(lang, "decision"))}</strong>
    <p>{escape(t(lang, "decision_notes"))}</p><div class="notes"></div></div>
</section>"""


def build_html(results, summary, rubric, lang, banner):
    calls = "".join(call_section(r, rubric, lang) for r in results)
    return f"""<!doctype html>
<html lang="{lang}">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(t(lang, "html_title"))}</title><style>{CSS}</style></head>
<body><main>
<h1>{escape(t(lang, "html_title"))}</h1>
<p>{escape(t(lang, "html_intro"))}</p>
<div class="banner">{escape(banner)}</div>
<h2>{escape(t(lang, "html_agents"))}</h2>
<div class="card">{agents_table(summary, rubric, lang)}</div>
<h2>{escape(t(lang, "html_calls"))}</h2>
{calls}
<footer>{escape(t(lang, "footer"))}</footer>
</main></body></html>
"""


def write_html(path, results, summary, rubric, lang, banner):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_html(results, summary, rubric, lang, banner), encoding="utf-8")
