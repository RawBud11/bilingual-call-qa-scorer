"""Generate the labeled synthetic test calls for evaluate.py.

Usage:  python scripts/make_transcripts.py --seed 42

Writes:
  data/test_calls/T001.txt ... T040.txt   40 calls, half English, half Spanish
  data/test_labels.csv                    the expected answer for each call

Every call is assembled from segment variants in scripts/call_templates.py
(greeting, recording notice, verification, empathy, resolution, traps), so the
labels come from the variants picked, not from anyone's judgment.
All data is synthetic. Puentara is a fictional company. Card numbers are
made-up 16-digit strings that start with 0000, which no real card does.
The 6 demo calls in data/sample_calls are hand-written, not generated here.
"""

import argparse
import csv
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import call_templates as T  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CALLS_DIR = ROOT / "data" / "test_calls"
LABELS_FILE = ROOT / "data" / "test_labels.csv"
REASONS = list(T.PROBLEMS)
LABEL_COLUMNS = ["call_id", "language", "reason", "agent",
                 "expected_sensitive_request", "expected_sensitive_kind", "expected_outcome_promise",
                 "expected_recording_notice", "expected_dispute_timeline",
                 "expected_verification", "expected_empathy", "expected_resolution",
                 "variants"]


def fake_card(rng):
    digits = "0000" + "".join(str(rng.randint(0, 9)) for _ in range(12))
    return " ".join(digits[i:i + 4] for i in range(0, 16, 4))


def build_call(number, lang, rng):
    reason = REASONS[number % len(REASONS)]  # every reason appears in both languages
    agent = rng.choice(T.AGENTS)
    customer = rng.choice(T.CUSTOMERS[lang])
    greeting = rng.random() < 0.8
    recording = rng.random() < 0.75
    verify = rng.choices(["allowed", "full_card", "pin", "otp", "skipped"], [8, 2, 2, 2, 2])[0]
    empathy = rng.choice(["ack", "ack", "curt"])
    if reason == "charge_dispute":
        # Fixed cycle, not random: only ~5 dispute calls, and each variant must appear.
        resolution = ["next_steps", "promise", "vague", "promise", "next_steps"][(number // len(REASONS)) % 5]
    else:
        resolution = rng.choice(["next_steps", "next_steps", "vague"])
    volunteers = verify != "skipped" and rng.random() < 0.25
    never_ask = rng.random() < 0.25

    agent_first = agent.split()[0]
    first = T.GREETING[lang].format(agent=agent_first) if greeting else T.NO_GREETING[lang]
    if recording:
        first += rng.choice(T.RECORDING[lang])
    amount = f"${rng.randint(20, 900)}.{rng.randint(0, 99):02d}"
    if verify == "allowed":
        answer = T.CUSTOMER_ANSWER["volunteer" if volunteers else "allowed"][lang]
    elif verify == "skipped":
        answer = T.CUSTOMER_ANSWER["skipped"][lang]
    else:
        answer = T.CUSTOMER_ANSWER["volunteer" if volunteers else "sensitive"][lang]
    if resolution == "next_steps":
        template = T.RESOLUTION["next_steps"].get(reason, T.RESOLUTION["next_steps"]["default"])
        closing_text = template[lang].format(step=T.NEXT_STEP.get(reason, {}).get(lang, ""))
    else:
        closing_text = T.RESOLUTION[resolution][lang]

    agent_label, customer_label = ("Agent", "Customer") if lang == "en" else ("Agente", "Cliente")
    turns = [
        (agent_label, first),
        (customer_label, T.PROBLEMS[reason][lang].format(amount=amount)),
        (agent_label, rng.choice(T.EMPATHY[empathy][lang]) + " " + rng.choice(T.VERIFY[verify][lang])),
        (customer_label, answer.format(name=customer, card=fake_card(rng))),
        (agent_label, T.ACCOUNT_LINE[lang] + (T.NEVER_ASK[lang] if never_ask else "")),
        (customer_label, T.CUSTOMER_FOLLOWUP[lang]),
        (agent_label, closing_text),
        (customer_label, T.CUSTOMER_THANKS[lang]),
        (agent_label, T.CLOSING[lang]),
    ]
    call_id = f"T{number:03d}"
    text = ("# Synthetic test call (template-generated). Puentara is a fictional company; "
            "every name and number is made up.\n"
            f"call_id: {call_id}\nagent: {agent}\nreason: {reason}\nchannel: phone\n\n"
            + "\n".join(f"{who}: {what}" for who, what in turns) + "\n")

    sensitive = verify in T.SENSITIVE_KIND
    is_dispute = reason == "charge_dispute"
    if reason == "general_question":
        verification = "n/a"
    else:
        verification = "met" if verify == "allowed" else "not_met"
    if resolution == "next_steps":
        expected_resolution = "met"
    elif reason == "card_lost_stolen":
        expected_resolution = "not_met"  # no escalation to the security team
    else:
        expected_resolution = "partial"
    labels = {
        "call_id": call_id, "language": lang, "reason": reason, "agent": agent,
        "expected_sensitive_request": "yes" if sensitive else "no",
        "expected_sensitive_kind": T.SENSITIVE_KIND.get(verify, ""),
        "expected_outcome_promise": "yes" if resolution == "promise" else "no",
        "expected_recording_notice": "yes" if recording else "no",
        "expected_dispute_timeline": ("yes" if resolution == "next_steps" else "no") if is_dispute else "n/a",
        "expected_verification": verification,
        "expected_empathy": "met" if empathy == "ack" else "not_met",
        "expected_resolution": expected_resolution,
        "variants": f"greeting={greeting} recording={recording} verify={verify} empathy={empathy} "
                    f"resolution={resolution} volunteers_card={volunteers} never_ask={never_ask}",
    }
    return call_id, text, labels


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate labeled synthetic test calls.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--count", type=int, default=40, help="number of calls (half EN, half ES)")
    args = parser.parse_args(argv)
    rng = random.Random(args.seed)

    CALLS_DIR.mkdir(parents=True, exist_ok=True)
    for old in CALLS_DIR.glob("T*.txt"):
        old.unlink()  # only files this script made, so a smaller --count leaves no leftovers
    rows = []
    for number in range(1, args.count + 1):
        lang = "en" if number % 2 else "es"
        call_id, text, labels = build_call(number, lang, rng)
        (CALLS_DIR / f"{call_id}.txt").write_text(text, encoding="utf-8")
        rows.append(labels)
    with open(LABELS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LABEL_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} calls to {CALLS_DIR.relative_to(ROOT)} and labels to {LABELS_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
