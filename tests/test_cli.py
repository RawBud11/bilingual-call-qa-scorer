"""End-to-end runs of score.py and evaluate.py in demo mode, plus bilingual output."""

import csv

import pytest

import config
import evaluate
import score
from call_qa.strings import STRINGS


@pytest.fixture(autouse=True)
def no_key(monkeypatch):
    # Ignore any real .env on this machine: tests must never call the API.
    monkeypatch.setattr(score, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(evaluate, "load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def test_demo_run_writes_csv_html_and_summary(tmp_path, capsys):
    assert score.main(["--out-dir", str(tmp_path)]) == 0
    printed = capsys.readouterr().out
    assert printed.startswith("Demo mode: AI answers are hand-written fixtures")
    assert "AUTO-FAIL FLAG: asked for the PIN (L7), reviewer must confirm" in printed
    assert "Per agent" in printed and "Reviewer decision: pending" in printed
    rows = read_csv(tmp_path / config.CSV_NAME)
    assert [r["call_id"] for r in rows] == ["C001", "C002", "C003", "C004", "C005", "C006"]
    assert (tmp_path / config.CSV_NAME).read_bytes().startswith(b"\xef\xbb\xbf")  # BOM for Excel
    by_id = {r["call_id"]: r for r in rows}
    assert by_id["C002"]["suggested_score"] == "0" and by_id["C002"]["auto_fail_flag"] == "true"
    assert by_id["C006"]["resolution"] == "needs_review"
    assert by_id["C006"]["suggested_score"] == "100" and by_id["C006"]["scored_weight"] == "85"
    assert by_id["C001"]["scored_weight"] == "100"
    assert "100/100 (provisional, 1 item to review)" in printed
    assert "To confirm" in printed
    assert all(r["reviewer_decision"] == "pending" for r in rows)
    assert (tmp_path / config.HTML_NAME).is_file()


def test_demo_run_in_spanish(tmp_path, capsys):
    assert score.main(["--out-dir", str(tmp_path), "--report-lang", "es"]) == 0
    printed = capsys.readouterr().out
    assert printed.startswith("Modo demo: las respuestas de la IA son ejemplos escritos a mano")
    assert "ALERTA AUTO-FAIL: pidió el PIN (L7)" in printed
    assert "Decisión del revisor: pendiente" in printed
    rows = read_csv(tmp_path / config.CSV_NAME)
    assert all(r["reviewer_decision"] == "pendiente" for r in rows)


def test_language_follows_the_customer(tmp_path):
    rows_lang = {}
    assert score.main(["--out-dir", str(tmp_path)]) == 0
    for row in read_csv(tmp_path / config.CSV_NAME):
        rows_lang[row["call_id"]] = row["language"]
    assert rows_lang == {"C001": "en", "C002": "es", "C003": "en", "C004": "es", "C005": "en", "C006": "es"}


def test_limit(tmp_path):
    assert score.main(["--out-dir", str(tmp_path), "--limit", "2"]) == 0
    assert len(read_csv(tmp_path / config.CSV_NAME)) == 2


@pytest.mark.parametrize("lang,expected", [
    ("en", "--live needs an API key. Add ANTHROPIC_API_KEY to .env"),
    ("es", "--live necesita una clave de API. Agrega ANTHROPIC_API_KEY a tu archivo .env"),
])
def test_live_without_key_gives_a_clear_message(tmp_path, capsys, lang, expected):
    assert score.main(["--live", "--out-dir", str(tmp_path), "--report-lang", lang]) == 2
    assert expected in capsys.readouterr().err
    assert not (tmp_path / config.CSV_NAME).exists()


def test_placeholder_key_counts_as_no_key(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "your-key-here")
    assert score.main(["--live", "--out-dir", str(tmp_path)]) == 2
    assert "--live needs an API key" in capsys.readouterr().err


def test_record_without_live(tmp_path, capsys):
    assert score.main(["--record", "--out-dir", str(tmp_path)]) == 2
    assert "--record only works with --live" in capsys.readouterr().err


@pytest.mark.parametrize("files,expected", [
    (None, "Folder not found"),
    ({}, "No .txt transcripts"),
    ({"a.txt": "agent: X\nreason: fees\n\nAgent: hi"}, "missing header field(s): call_id"),
    ({"a.txt": "call_id: A\nagent: X\nreason: refunds\n\nAgent: hi"}, "unknown reason 'refunds'"),
    ({"a.txt": "call_id: A\nagent: X\nreason: fees\n\nhello there"}, "the dialogue must start with 'Agent:'"),
    ({"a.txt": "call_id: A\nagent: X\nreason: fees\n\nAgent: hi",
      "b.txt": "call_id: A\nagent: Y\nreason: fees\n\nAgent: hi"}, "use call_id A"),
])
def test_bad_input_gives_one_clear_line(tmp_path, capsys, files, expected):
    folder = tmp_path / "calls"
    if files is not None:
        folder.mkdir()
        for name, text in files.items():
            (folder / name).write_text(text, encoding="utf-8")
    assert score.main(["--calls", str(folder), "--out-dir", str(tmp_path / "out")]) == 2
    err = capsys.readouterr().err
    assert expected in err
    assert "Traceback" not in err


def test_evaluate_demo_mode_en_and_es(capsys):
    assert evaluate.main([]) == 0
    printed = capsys.readouterr().out
    assert "synthetic, template-generated" in printed
    assert "Sensitive-data request detection" in printed
    assert evaluate.main(["--summary-lang", "es"]) == 0
    assert "sintéticos, generados con plantillas" in capsys.readouterr().out


def test_evaluate_live_without_key(capsys):
    assert evaluate.main(["--live"]) == 2
    assert "--live needs an API key" in capsys.readouterr().err


def test_both_languages_have_the_same_strings():
    def keys(table, prefix=""):
        out = set()
        for key, value in table.items():
            out.add(prefix + key)
            if isinstance(value, dict):
                out |= keys(value, prefix + key + ".")
        return out
    assert keys(STRINGS["en"]) == keys(STRINGS["es"])
    assert set(evaluate.TEXT["en"]) == set(evaluate.TEXT["es"])


def test_rubric_items_have_both_languages():
    import json
    rubric = json.loads(config.RUBRIC_FILE.read_text(encoding="utf-8"))
    for item in rubric["items"]:
        assert set(item["name"]) == set(item["description"]) == {"en", "es"}
        assert item["weight"] > 0
