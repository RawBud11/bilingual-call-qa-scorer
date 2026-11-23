"""Settings in one place: model, file paths, statuses and score values.

The rubric itself (items, weights, phrase lists) lives in rubric.json so a QA
lead can edit it without touching code. Puentara is a fictional company.
"""

from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent

# --- Claude API -------------------------------------------------------------
# Used when ANTHROPIC_MODEL is not set in .env. A small, fast model is
# enough to judge three rubric items with quotes, and the code checks every
# quote anyway.
DEFAULT_MODEL = "claude-haiku-5-5"
AI_TIMEOUT_SECONDS = 60
AI_MAX_TOKENS = 1500

# --- Files --------------------------------------------------------------------
RUBRIC_FILE = PROJECT_DIR / "rubric.json"
PROMPT_FILE = PROJECT_DIR / "prompts" / "qa_system.txt"
FIXTURES_FILE = PROJECT_DIR / "fixtures" / "ai_responses.json"
SAMPLE_CALLS_DIR = PROJECT_DIR / "data" / "sample_calls"
TEST_CALLS_DIR = PROJECT_DIR / "data" / "test_calls"
TEST_LABELS_FILE = PROJECT_DIR / "data" / "test_labels.csv"
OUTPUT_DIR = PROJECT_DIR / "output"
HTML_NAME = "qa_review.html"
CSV_NAME = "qa_scores.csv"

# --- Call reasons (the shared Puentara ticket categories) --------------------
REASONS = [
    "account_access",
    "identity_verification",
    "card_lost_stolen",
    "transfer_failed_pending",
    "charge_dispute",
    "fees",
    "tax_forms",
    "app_bug",
    "general_question",
]
DISPUTE_REASONS = ["charge_dispute"]

# --- Item statuses and how they count in the suggested score ----------------
# AI and rules both use the first four. needs_review is set by the code only:
# the item is left out of the score until a person looks at it.
AI_STATUSES = ["met", "partial", "not_met", "n/a"]
STATUS_VALUES = {"met": 1.0, "partial": 0.5, "not_met": 0.0}  # n/a, needs_review: not counted

# Speaker labels accepted in transcript files (lowercase, without the colon).
SPEAKERS = {"agent": "agent", "agente": "agent", "customer": "customer", "cliente": "customer"}
