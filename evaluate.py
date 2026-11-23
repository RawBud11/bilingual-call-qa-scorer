"""Measure the scorer on the labeled synthetic test calls (data/test_calls + data/test_labels.csv).

Usage:
  python evaluate.py                     rules layer only (demo mode, no API calls)
  python evaluate.py --live              adds AI agreement with the labels (needs a key in .env)
  python evaluate.py --summary-lang es   output in Spanish

Same approach as bilingual-ticket-triage: in demo mode the AI answers would be
hand-written fixtures, so scoring them would measure nothing. Demo mode reports
the RULES LAYER only (sensitive-data requests, outcome promises, disclosures).
AI agreement numbers only come from --live.
"""

import argparse
import csv
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

import config
from call_qa.ai import AIError, LiveClient
from call_qa.rules import agent_lines, first_line_with, run_rules
from call_qa.scoring import score_call
from call_qa.strings import t
from call_qa.transcript import UserError, load_calls
from score import load_rubric

TEXT = {
    "en": {
        "label": "Labeled test set: synthetic, template-generated, high by construction, not real-world accuracy.",
        "rules_mode": "Mode: rules layer only (demo, no API calls). Run with --live to add AI agreement numbers.",
        "live_mode": "Mode: rules plus Claude ({model}).",
        "calls": "Calls in test set",
        "sensitive": "Sensitive-data request detection",
        "kind": "Right kind (PIN, card, code) when caught",
        "traps": "Trap calls wrongly flagged (customer reads a card number, or agent says \"we never ask\")",
        "promise": "Outcome-promise detection (disputes)",
        "recording": "Recording notice detection",
        "timeline": "Dispute timeline detection",
        "metric": "precision {p}  recall {r}",
        "ai_header": "AI agreement with labels",
        "agree": "{item}: {ok}/{total} agree",
        "review": "AI items sent to review",
        "misses": "Misses",
        "no_misses": "  none",
        "expected": "expected",
        "got": "got",
        "need_key": "--live needs an API key. Add ANTHROPIC_API_KEY to .env, or run without --live.",
        "missing": "Test data not found: {path}. Create it with: python scripts/make_transcripts.py --seed 42",
        "not_labeled": "{path} has no expected_* columns, so there is nothing to compare.",
        "no_label": "Call {call_id} has no row in {path}. Re-run: python scripts/make_transcripts.py --seed 42",
    },
    "es": {
        "label": "Conjunto de prueba etiquetado: datos sintéticos, generados con plantillas, altos por construcción; no es la precisión con llamadas reales.",
        "rules_mode": "Modo: solo la capa de reglas (demo, sin llamadas a la API). Usa --live para agregar el acuerdo de la IA.",
        "live_mode": "Modo: reglas más Claude ({model}).",
        "calls": "Llamadas en el conjunto de prueba",
        "sensitive": "Detección de solicitudes de datos sensibles",
        "kind": "Tipo correcto (PIN, tarjeta, código) al detectarla",
        "traps": "Trampas marcadas por error (el cliente lee su tarjeta o el agente dice \"nunca te pedimos\")",
        "promise": "Detección de promesas de resultado (disputas)",
        "recording": "Detección del aviso de grabación",
        "timeline": "Detección del plazo en disputas",
        "metric": "precisión {p}  exhaustividad {r}",
        "ai_header": "Acuerdo de la IA con las etiquetas",
        "agree": "{item}: {ok}/{total} coinciden",
        "review": "Puntos de la IA enviados a revisión",
        "misses": "No acertados",
        "no_misses": "  ninguno",
        "expected": "esperado",
        "got": "obtenido",
        "need_key": "--live necesita una clave de API. Agrega ANTHROPIC_API_KEY a tu archivo .env, o ejecútalo sin --live.",
        "missing": "No se encontraron los datos de prueba: {path}. Créalos con: python scripts/make_transcripts.py --seed 42",
        "not_labeled": "{path} no tiene columnas expected_*, así que no hay con qué comparar.",
        "no_label": "La llamada {call_id} no tiene fila en {path}. Vuelve a ejecutar: python scripts/make_transcripts.py --seed 42",
    },
}
AI_ITEMS = [("identity_verification", "expected_verification"), ("empathy", "expected_empathy"),
            ("resolution", "expected_resolution")]


def ratio(part, whole):
    if not whole:
        return f"{part}/{whole} (-)"  # nothing to measure; not 0% and not 100%
    return f"{part}/{whole} ({100 * part / whole:.1f}%)"


def detection(pairs):
    """pairs: (expected bool, predicted bool) -> (precision text, recall text)."""
    tp = sum(e and p for e, p in pairs)
    return ratio(tp, sum(p for _, p in pairs)), ratio(tp, sum(e for e, _ in pairs))


def rule_predictions(call, rubric, lang):
    """What the rules say about one call, in the same shape as the labels."""
    rules = run_rules(call, rubric, lang)
    disclosures = next(i for i in rubric["items"] if i["id"] == "disclosures")
    lines = agent_lines(call)
    return {
        "sensitive": bool(rules["sensitive"]),
        "kinds": {r["kind"] for r in rules["sensitive"]},
        "promise": bool(rules["promises"]),
        "recording": first_line_with(lines, disclosures["recording_notice"]) is not None,
        "timeline": first_line_with(lines, disclosures["dispute_timeline"]) is not None,
    }


def evaluate(calls, labels, rubric, lang, client=None, model=""):
    rows = []
    for call in calls:
        label = labels[call["call_id"]]
        pred = rule_predictions(call, rubric, lang)
        result = score_call(call, client, rubric, lang, model) if client else None
        rows.append((call, label, pred, result))
    return rows


def print_report(rows, rubric, lang, live, model):
    x = TEXT[lang]
    yes = lambda value: value == "yes"  # noqa: E731
    print(x["label"])
    print(x["live_mode"].format(model=model) if live else x["rules_mode"])
    print()
    print(f'  {x["calls"]:<52} {len(rows)}')
    checks = [("sensitive", "expected_sensitive_request", rows),
              ("promise", "expected_outcome_promise", [r for r in rows if r[0]["reason"] in config.DISPUTE_REASONS]),
              ("recording", "expected_recording_notice", rows),
              ("timeline", "expected_dispute_timeline", [r for r in rows if r[0]["reason"] in config.DISPUTE_REASONS])]
    misses = []
    for key, column, subset in checks:
        pairs = [(yes(label[column]), pred[key]) for _, label, pred, _ in subset]
        p, r = detection(pairs)
        print(f'  {x[key]:<52} {x["metric"].format(p=p, r=r)}')
        misses += [(call["call_id"], x[key], label[column], "yes" if pred[key] else "no")
                   for call, label, pred, _ in subset if yes(label[column]) != pred[key]]
    caught = [(label, pred) for _, label, pred, _ in rows if yes(label["expected_sensitive_request"]) and pred["sensitive"]]
    right_kind = sum(label["expected_sensitive_kind"] in pred["kinds"] for label, pred in caught)
    print(f'  {x["kind"]:<52} {ratio(right_kind, len(caught))}')
    # Traps must NOT be flagged: only calls whose agent did not ask for anything count here.
    traps = [pred for _, label, pred, _ in rows if not yes(label["expected_sensitive_request"])
             and ("volunteers_card=True" in label["variants"] or "never_ask=True" in label["variants"])]
    print(f'  {x["traps"]}: {ratio(sum(p["sensitive"] for p in traps), len(traps))}')

    if live:
        print()
        print(x["ai_header"])
        names = {i["id"]: i["name"][lang] for i in rubric["items"]}
        sent_to_review = total_ai = 0
        for item_id, column in AI_ITEMS:
            got = [(label[column], next(i["status"] for i in res["items"] if i["id"] == item_id))
                   for _, label, _, res in rows]
            ok = sum(e == g for e, g in got)
            sent_to_review += sum(g == "needs_review" for _, g in got)
            total_ai += len(got)
            print(f'  {x["agree"].format(item=names[item_id], ok=ok, total=len(got))}')
            misses += [(call["call_id"], item_id, label[column], status)
                       for (call, label, _, _), (_, status) in zip(rows, got) if label[column] != status]
        print(f'  {x["review"]:<52} {ratio(sent_to_review, total_ai)}')

    print()
    print(f'{x["misses"]} ({len(misses)})')
    for call_id, what, expected, got in misses:
        print(f'  {call_id}  {what}: {x["expected"]} {expected}, {x["got"]} {got}')
    if not misses:
        print(x["no_misses"])


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    load_dotenv(config.PROJECT_DIR / ".env")
    parser = argparse.ArgumentParser(description="Evaluate the scorer on synthetic labeled calls (Puentara is fictional).")
    parser.add_argument("--calls", type=Path, default=config.TEST_CALLS_DIR)
    parser.add_argument("--labels", type=Path, default=config.TEST_LABELS_FILE)
    parser.add_argument("--live", action="store_true", help="also measure Claude's judgments (needs a key)")
    parser.add_argument("--summary-lang", choices=["en", "es"], default="en")
    args = parser.parse_args(argv)
    lang = args.summary_lang
    x = TEXT[lang]

    if not args.labels.is_file() or not args.calls.is_dir():
        print(x["missing"].format(path=args.labels if not args.labels.is_file() else args.calls), file=sys.stderr)
        return 2
    with open(args.labels, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        labels = {row["call_id"]: row for row in reader}
    if "expected_sensitive_request" not in (reader.fieldnames or []):
        print(x["not_labeled"].format(path=args.labels), file=sys.stderr)
        return 2

    model = os.getenv("ANTHROPIC_MODEL", "").strip() or config.DEFAULT_MODEL
    client = None
    if args.live:
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not api_key or api_key == "your-key-here":
            print(x["need_key"], file=sys.stderr)
            return 2
        client = LiveClient(api_key, model)
    try:
        calls = load_calls(args.calls)
        missing = next((c["call_id"] for c in calls if c["call_id"] not in labels), None)
        if missing:
            print(x["no_label"].format(call_id=missing, path=args.labels), file=sys.stderr)
            return 2
        rubric = load_rubric()
        rows = evaluate(calls, labels, rubric, lang, client, model)
    except UserError as error:
        print(t(lang, error.code).format(**error.details), file=sys.stderr)
        return 2
    except AIError as error:  # fatal only: bad key or unknown model
        print(t(lang, "fatal_ai").format(error=t(lang, "ai_problems").get(error.code, error.code)),
              file=sys.stderr)
        return 1
    print_report(rows, rubric, lang, args.live, model)
    return 0


if __name__ == "__main__":
    sys.exit(main())
