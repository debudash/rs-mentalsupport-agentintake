"""Turn OCR lines into name / date of birth / address, never guessing.

Handles labels above values ("NAME" then "JANE DOE") and labels inline ("Name: Jane Doe"),
with fuzzy label matching for OCR misreads. A value is returned only if it parses validly.
"""

import re
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher

from app.ocr.engines import Line

FIELDS = ("name", "date_of_birth", "address")

_LABELS = {
    "name": ["name", "full name", "nm"],
    "date_of_birth": ["date of birth", "dob", "birth date", "born", "d.o.b"],
    "address": ["address", "addr", "residence", "home address"],
}
_STOP = [
    "id no",
    "id number",
    "id",
    "expires",
    "exp",
    "issued",
    "iss",
    "sex",
    "hgt",
    "height",
    "eyes",
    "class",
    "signature",
    "state of riverside",
    "client identification card",
    "identification card",
    "card no",
    "member",
    "restrictions",
    "donor",
]


@dataclass(frozen=True)
class Candidate:
    value: str
    confidence: float


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


def _label_split(line: str, labels: list[str]) -> str | None:
    """If the line starts with one of the labels (fuzzily), return the remainder."""
    raw = line.strip()
    lowered = _norm(raw)
    for label in sorted(labels, key=len, reverse=True):
        target = _norm(label)
        n_words = len(target.split())
        head = " ".join(lowered.split()[:n_words])
        if not head:
            continue
        exact = head == target
        fuzzy = len(target) >= 4 and SequenceMatcher(None, head, target).ratio() >= 0.75
        if exact or fuzzy:
            # Drop the label's words (and any ':' after it) from the original text.
            parts = raw.split()
            remainder = " ".join(parts[n_words:]).lstrip(":-. ").strip()
            return remainder
    return None


def _is_any_label(line: str) -> bool:
    if _label_split(line, _STOP) is not None and len(_norm(line).split()) <= 4:
        return True
    return any(_label_split(line, labels) is not None for labels in _LABELS.values())


def _words_conf(line: Line, text: str) -> float:
    if not line.words:
        return line.confidence
    wanted = set(text.split())
    confs = [c for w, c in line.words if w in wanted] or [line.confidence]
    return sum(confs) / len(confs)


def clean_name(text: str) -> str | None:
    text = re.sub(r"[^A-Za-z\s'\-.]", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .-'")
    letters = re.sub(r"[^A-Za-z]", "", text)
    if len(letters) < 3 or len(text) > 80 or len(text.split()) < 2:
        return None
    return text.title() if text.isupper() or text.islower() else text


_MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1
    )
}


def parse_date(text: str, today: date | None = None) -> str | None:
    today = today or date.today()
    t = text.strip().lower().replace("o", "0") if re.search(r"\d", text) else text.lower()
    candidates: list[date] = []
    for m in re.finditer(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", t):
        candidates.append((int(m[1]), int(m[2]), int(m[3])))
    for m in re.finditer(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", t):
        candidates.append((int(m[3]), int(m[1]), int(m[2])))  # US order MM/DD/YYYY
    for m in re.finditer(r"(\d{1,2})\s*([a-z]{3})[a-z]*\.?\s*(\d{4})", text.lower()):
        if m[2] in _MONTHS:
            candidates.append((int(m[3]), _MONTHS[m[2]], int(m[1])))
    for m in re.finditer(r"([a-z]{3})[a-z]*\.?\s*(\d{1,2}),?\s*(\d{4})", text.lower()):
        if m[1] in _MONTHS:
            candidates.append((int(m[3]), _MONTHS[m[1]], int(m[2])))
    for year, month, day in candidates:
        try:
            value = date(year, month, day)
        except ValueError:
            continue
        if date(1900, 1, 1) <= value <= today:
            return value.isoformat()
    return None


def clean_address_line(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9\s,.#'\-]", " ", text)
    return re.sub(r"\s+", " ", text).strip(" ,.")


def valid_address(text: str) -> bool:
    return (
        bool(re.search(r"\d", text))
        and len(re.findall(r"[A-Za-z]{2,}", text)) >= 2
        and len(text) <= 200
    )


def extract(lines: list[Line], today: date | None = None) -> dict[str, Candidate | None]:
    found: dict[str, Candidate | None] = dict.fromkeys(FIELDS)
    texts = [ln.text.strip() for ln in lines]
    for i, line in enumerate(lines):
        for field, labels in _LABELS.items():
            if found[field] is not None:
                continue
            remainder = _label_split(texts[i], labels)
            if remainder is None:
                continue
            value_lines: list[tuple[Line, str]] = []
            if remainder:
                value_lines.append((line, remainder))
            j = i + 1
            limit = 2 if field == "address" else 1
            while len(value_lines) < limit and j < len(lines):
                if _is_any_label(texts[j]):
                    break
                if texts[j]:
                    value_lines.append((lines[j], texts[j]))
                j += 1
                if field != "address" and value_lines:
                    break
            if not value_lines:
                continue
            conf = sum(_words_conf(ln, t) for ln, t in value_lines) / len(value_lines)
            if field == "name":
                value = clean_name(value_lines[0][1])
            elif field == "date_of_birth":
                value = parse_date(" ".join(t for _, t in value_lines), today)
            else:
                joined = ", ".join(clean_address_line(t) for _, t in value_lines if t)
                value = joined if valid_address(joined) else None
            if value:
                found[field] = Candidate(value, conf)
    if not all(found.values()):
        _by_shape(lines, texts, found, today)
    return found


# ---- label-free fallback ------------------------------------------------------------------
# Photographed cards sometimes lose their (small, coloured) labels in OCR while the values
# read perfectly. Each fallback fires only when exactly one line has the field's shape, so
# an ambiguous card stays blank rather than guessed.

_STREET = re.compile(
    r"^\d{1,6}\s+[A-Za-z][A-Za-z.'\- ]*\b(?:st|street|ave|avenue|rd|road|ln|lane|dr|drive|way|"
    r"ct|court|blvd|boulevard|pl|place|ter|terrace|cir|circle|hwy|pkwy)\b",
    re.I,
)
_CITY_LINE = re.compile(r"^[A-Za-z][A-Za-z.'\- ]+,\s*[A-Z]{2}\s+\d{5}(?:-\d{4})?$")
_HEADER_WORDS = {
    "state",
    "riverside",
    "card",
    "member",
    "identification",
    "client",
    "license",
    "issued",
    "expires",
    "signature",
    "id",
    "no",
}


def _by_shape(lines: list[Line], texts: list[str], found: dict, today: date | None) -> None:
    date_rows = [i for i, t in enumerate(texts) if parse_date(t, today)]
    if found["date_of_birth"] is None and len(date_rows) == 1:
        i = date_rows[0]
        found["date_of_birth"] = Candidate(
            parse_date(texts[i], today), _words_conf(lines[i], texts[i])
        )

    street_rows = [i for i, t in enumerate(texts) if _STREET.match(t)]
    if found["address"] is None and len(street_rows) == 1:
        i = street_rows[0]
        parts = [(lines[i], texts[i])]
        if i + 1 < len(texts) and _CITY_LINE.match(texts[i + 1].strip()):
            parts.append((lines[i + 1], texts[i + 1]))
            joined = ", ".join(clean_address_line(t) for _, t in parts)
            if valid_address(joined):
                conf = sum(_words_conf(ln, t) for ln, t in parts) / len(parts)
                found["address"] = Candidate(joined, conf)

    if found["name"] is None and len(date_rows) == 1 and date_rows[0] > 0:
        i = date_rows[0] - 1  # the name sits directly above the date of birth
        words = {w.lower().strip(".:") for w in texts[i].split()}
        name = clean_name(texts[i]) if not words & _HEADER_WORDS else None
        if name and not re.search(r"\d", texts[i]):
            found["name"] = Candidate(name, _words_conf(lines[i], texts[i]))
