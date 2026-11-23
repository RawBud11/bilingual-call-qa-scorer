"""Score EN/ES support call transcripts against a QA rubric, for a person to review.

Usage:
  python score.py                              scores data/sample_calls (demo mode)
  python score.py --report-lang es             same, report in Spanish
  python score.py --calls path/to/folder       your own transcripts (one .txt per call)
  python score.py --live --limit 1             call Claude (needs ANTHROPIC_API_KEY in .env)
  python score.py --live --record              also save the answers to fixtures/

Writes output/qa_review.html and output/qa_scores.csv. Scores are suggestions:
every call shows "Reviewer decision: pending". Puentara is a fictional company.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

import config
from call_qa.ai import AIError, FixtureClient, LiveClient, RecordingClient
from call_qa.report import print_summary, write_csv
from call_qa.report_html import write_html
from call_qa.scoring import agent_summary, score_call
from call_qa.strings import t
from call_qa.transcript import UserError, load_calls


def load_rubric(path=config.RUBRIC_FILE):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def shown(path):
    """Print paths relative to the current folder when possible (shorter, no user name)."""
    try:
        return path.resolve().relative_to(Path.cwd())
    except ValueError:
        return path


def make_client(args, lang, fixtures_path):
    """Pick live or demo mode. Returns (client, model, banner text for the HTML)."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if api_key == "your-key-here":  # the placeholder from .env.example
        api_key = ""
    model = os.getenv("ANTHROPIC_MODEL", "").strip() or config.DEFAULT_MODEL
    if args.record and not args.live:
        raise UserError("record_needs_live")
    if args.live:
        if not api_key:
            raise UserError("need_key")
        print(t(lang, "live_mode").format(model=model))
        client = LiveClient(api_key, model)
        client = RecordingClient(client) if args.record else client
        return client, model, t(lang, "banner_live").format(model=model)
    client = FixtureClient(fixtures_path)
    sources = client.sources()
    if sources <= {"hand-written"}:
        print(t(lang, "demo_with_key" if api_key else "demo_no_key").format(source=t(lang, "source_hand")))
        return client, model, t(lang, "banner_demo")
    source = t(lang, "source_recorded" if sources == {"recorded"} else "source_mixed")
    print(t(lang, "demo_recorded").format(source=source))
    return client, model, t(lang, "banner_recorded").format(source=source)


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Score EN/ES call transcripts against a QA rubric (demo company Puentara is fictional).")
    parser.add_argument("--calls", type=Path, default=config.SAMPLE_CALLS_DIR,
                        help="folder with one .txt transcript per call (default: data/sample_calls)")
    parser.add_argument("--live", action="store_true",
                        help="call Claude for the AI-judged items (needs a key in .env)")
    parser.add_argument("--record", action="store_true",
                        help="with --live: save the real answers to fixtures/ for demo mode")
    parser.add_argument("--limit", type=int, default=None,
                        help="only score the first N calls (useful with --live)")
    parser.add_argument("--report-lang", choices=["en", "es"], default="en",
                        help="language of the report, terminal summary and AI rationale (default: en)")
    parser.add_argument("--out-dir", type=Path, default=config.OUTPUT_DIR, help=argparse.SUPPRESS)
    parser.add_argument("--fixtures", type=Path, default=config.FIXTURES_FILE, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be 1 or more")
    return args


def main(argv=None):
    # Windows consoles default to an old code page; force UTF-8 so á, ñ and ¿ print.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    load_dotenv(config.PROJECT_DIR / ".env")
    args = parse_args(argv)
    lang = args.report_lang
    html_path, csv_path = args.out_dir / config.HTML_NAME, args.out_dir / config.CSV_NAME
    try:
        # Read the transcripts first, so a bad path fails before the mode line prints.
        calls = load_calls(args.calls, args.limit)
        rubric = load_rubric()
        client, model, banner = make_client(args, lang, args.fixtures)
        results = [score_call(call, client, rubric, lang, model) for call in calls]
    except UserError as error:
        print(t(lang, error.code).format(**error.details), file=sys.stderr)
        return 2
    except AIError as error:  # only fatal ones reach here (bad key, unknown model)
        detail = t(lang, "ai_problems").get(error.code, error.code)
        print(t(lang, "fatal_ai").format(error=detail), file=sys.stderr)
        return 1
    summary = agent_summary(results)
    write_csv(csv_path, results, rubric, lang)
    write_html(html_path, results, summary, rubric, lang, banner)
    print_summary(results, summary, rubric, lang, shown(args.calls), shown(html_path), shown(csv_path))
    if isinstance(client, RecordingClient):
        count = client.save(args.fixtures)
        print(t(lang, "recorded").format(count=count, path=args.fixtures))
    return 0


if __name__ == "__main__":
    sys.exit(main())
