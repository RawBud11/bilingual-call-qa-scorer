"""Read call transcripts (plain text) into numbered, masked lines.

File format (one call per .txt file, UTF-8):

    # Lines starting with # are comments.
    call_id: C001
    agent: Dana P.
    reason: card_lost_stolen
    channel: phone

    Agent: Thanks for calling Puentara, my name is Dana. How can I help?
    Customer: Hi, I lost my card.
    Agente: ...      (Spanish labels work too: Agente / Cliente)

The header ends at the first blank line. A dialogue line without a speaker
label is added to the line before it (transcription exports often wrap long turns).
Every speaker line gets an ID (L1, L2, ...) and is masked right away, so the
raw card number or code never leaves this module.
"""

import re

import config
from call_qa.language import detect_language
from call_qa.mask import mask_sensitive

HEADER_RE = re.compile(r"^\s*([a-z_]+)\s*:\s*(.*)$", re.IGNORECASE)
SPEAKER_RE = re.compile(r"^\s*([A-Za-z]+)\s*:\s*(.*)$")
REQUIRED_HEADERS = ["call_id", "agent", "reason"]


class UserError(Exception):
    """A problem the user can fix. `code` is a key in strings.py; printed as one line."""

    def __init__(self, code, **details):
        super().__init__(code)
        self.code = code
        self.details = details


def parse_transcript(text, source="(text)"):
    """Turn transcript text into a call dict. Raises UserError on bad input."""
    header, lines = {}, []
    in_header = True
    for raw in (text or "").splitlines():
        stripped = raw.strip()
        if stripped.startswith("#"):
            continue
        if not stripped:
            # The header ends at the first blank line. It has to: "agent: Dana"
            # (header) and "Agent: Hi" (speaker) look the same to a regex.
            if header:
                in_header = False
            continue
        if in_header:
            field = HEADER_RE.match(stripped)
            if not field:
                raise UserError("bad_header_line", path=source, line=stripped[:60])
            header[field.group(1).lower()] = field.group(2).strip()
            continue
        speaker = SPEAKER_RE.match(stripped)
        if speaker and speaker.group(1).lower() in config.SPEAKERS:
            lines.append({"speaker": config.SPEAKERS[speaker.group(1).lower()],
                          "text": speaker.group(2).strip()})
        elif lines:
            lines[-1]["text"] += " " + stripped  # wrapped turn: keep it on the same line
        else:
            raise UserError("no_speaker", path=source, line=stripped[:60])

    missing = [key for key in REQUIRED_HEADERS if not header.get(key)]
    if missing:
        raise UserError("missing_header", path=source, fields=", ".join(missing))
    if header["reason"] not in config.REASONS:
        raise UserError("bad_reason", path=source, reason=header["reason"],
                        reasons=", ".join(config.REASONS))
    if not lines:
        raise UserError("no_lines", path=source)

    masked_total = 0
    for number, line in enumerate(lines, start=1):
        line["id"] = f"L{number}"
        line["text"], count = mask_sensitive(line["text"])
        masked_total += count

    customer_text = " ".join(l["text"] for l in lines if l["speaker"] == "customer")
    language = detect_language(customer_text)
    if language == "other":  # customer said almost nothing: use the whole call
        language = detect_language(" ".join(l["text"] for l in lines))
    return {
        "call_id": header["call_id"],
        "agent": header["agent"],
        "reason": header["reason"],
        "channel": header.get("channel", "phone"),
        "language": language,
        "lines": lines,
        "masked_count": masked_total,
        "source": str(source),
    }


def load_calls(folder, limit=None):
    """Read every .txt file in `folder` (sorted by name). Raises UserError."""
    if not folder.exists():
        raise UserError("folder_missing", path=folder)
    if not folder.is_dir():
        raise UserError("not_a_folder", path=folder)
    files = sorted(folder.glob("*.txt"))
    if not files:
        raise UserError("no_transcripts", path=folder)
    if limit:
        files = files[:limit]
    calls = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            raise UserError("bad_encoding", path=path) from None
        calls.append(parse_transcript(text, path.name))
    seen = set()
    for call in calls:
        if call["call_id"] in seen:
            raise UserError("duplicate_id", call_id=call["call_id"], path=folder)
        seen.add(call["call_id"])
    return calls
