"""Read NDRRMA's Rasuwa situation-report PDFs.

The authority publishes the same event twice a day in two languages, and the
two behave differently under text extraction. The English reports come out
clean. The Nepali ones come out with doubled vowel signs — "रसुुवाा" for
"रसुवा" — because the PDF encodes the conjuncts as separate glyphs; the
Devanagari numerals survive intact, but the prose does not, so no attempt is
made to parse Nepali figures out of it.

Only what is printed is stored. Every regex here is anchored on the wording
NDRRMA actually uses in its highlights block, and a figure that does not match
is left null rather than inferred from a neighbouring one. A sitrep with three
parsed fields is a truthful record of three published figures; a sitrep with
ten fields, seven of them guessed, is a fabrication that looks like data.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

# The highlights block is a bullet list; the prose that follows it is the
# situation overview and carries no new figures.
_HIGHLIGHT_SPLIT = re.compile(r"[••]")


def extract_pdf_text(data: bytes) -> str:
    """All text in a PDF, best extractor first.

    PyMuPDF keeps the reading order of NDRRMA's two-column highlights block
    better than PyPDF2 does, so it is preferred where the image has it; PyPDF2
    is a working fallback and is what ships in this container today.
    """
    if not data:
        return ""

    try:
        import fitz  # PyMuPDF

        with fitz.open(stream=data, filetype="pdf") as doc:
            return clean_text("\n".join(page.get_text() for page in doc))
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001 — fall through to PyPDF2
        logger.warning("PyMuPDF failed on a sitrep, trying PyPDF2: %s", exc)

    try:
        import io

        import PyPDF2

        reader = PyPDF2.PdfReader(io.BytesIO(data))
        return clean_text(
            "\n".join((page.extract_text() or "") for page in reader.pages))
    except Exception as exc:  # noqa: BLE001
        logger.warning("PDF text extraction failed: %s", exc)
        return ""


# PDF extraction emits NUL and other C0 controls where a glyph had no mapping.
# Postgres rejects NUL in text outright, so text is scrubbed at the boundary
# rather than at every call site that might store it.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(text: str) -> str:
    """Extracted text with unmappable control bytes removed."""
    return _CONTROL_RE.sub("", text or "")


def looks_english(text: str) -> bool:
    """True when extraction actually produced Latin prose.

    Several reports carry an English title over a Nepali document. Those
    extract as broken Devanagari, and storing that as an English excerpt would
    put mojibake on the desk under an English heading.
    """
    sample = (text or "")[:4000]
    letters = [c for c in sample if c.isalpha()]
    if len(letters) < 100:
        return False
    latin = sum(1 for c in letters if c.isascii())
    return latin / len(letters) > 0.6


def _to_ascii_digits(value: str) -> str:
    return (value or "").translate(_DEVANAGARI_DIGITS)


def _norm(text: str) -> str:
    """Collapse the whitespace the PDF layout injects mid-sentence.

    Extraction breaks lines wherever the column does, so "5 districts are\\n
    affected" and "Deceased bodies 987  and" both need flattening before any
    regex can span them.
    """
    return re.sub(r"\s+", " ", _to_ascii_digits(text or ""))


def _first(text: str, *patterns: str) -> Optional[int]:
    """The first figure any of these patterns finds, or None."""
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            digits = re.sub(r"[^0-9]", "", match.group(1))
            if digits:
                return int(digits)
    return None


def parse_english_sitrep(text: str) -> dict:
    """Published figures from an English situation report.

    Keys are omitted, not zeroed, when the report does not carry them.
    """
    flat = _norm(text)
    if not flat:
        return {}

    extracted: dict[str, object] = {}

    def put(key: str, value: Optional[int]) -> None:
        if value is not None:
            extracted[key] = value

    put("deaths", _first(
        flat,
        r"deceased\s+bodies?\s+([\d,]+)",
        r"dead\s+bodies?\s+([\d,]+)",
        r"([\d,]+)\s+(?:deceased|dead)\s+bodies",
        r"(?:deceased|death\s+toll|fatalities)\s*[:\-]?\s*([\d,]+)",
    ))
    put("missing", _first(
        flat,
        r"missing\s+individuals?\s+([\d,]+)",
        r"([\d,]+)\s+(?:individuals?|persons?|people)\s+(?:are\s+|remain\s+)?missing",
        r"missing\s*[:\-]?\s*([\d,]+)",
    ))
    put("injured", _first(
        flat,
        r"injured\s+([\d,]+)",
        r"([\d,]+)\s+injured",
    ))
    put("rescued", _first(
        flat,
        r"([\d,]+)\s+(?:individuals?|persons?|people)\s+have\s+been\s+rescued",
        r"rescued\s+([\d,]+)\s+(?:individuals?|persons?|people)",
        r"total\s+(?:of\s+)?([\d,]+)\s+(?:individuals?|persons?|people)\s+rescued",
    ))
    put("personnel", _first(
        flat,
        r"deployed\s+([\d,]+)\s+security\s+personnel",
        r"([\d,]+)\s+security\s+personnel",
        r"([\d,]+)\s+personnel\s+(?:have\s+been\s+)?(?:deployed|mobilis|mobiliz)",
    ))
    put("foreign_rescued", _first(
        flat,
        r"rescued\s+([\d,]+)\s+foreign\s+nationals?",
        r"([\d,]+)\s+foreign\s+nationals?\s+(?:have\s+been\s+|were\s+)?(?:successfully\s+)?rescued",
    ))
    put("bridges_washed", _first(
        flat,
        r"([\d,]+)\s+(?:motorable\s+)?bridges?\s+(?:have\s+been\s+|has\s+been\s+|were\s+)?washed\s+away",
        r"bridges?\s+washed\s+away\s*[:\-]?\s*([\d,]+)",
    ))
    put("bridges_damaged", _first(
        flat,
        r"additional\s+([\d,]+)\s+bridges?\s+(?:have\s+been\s+|has\s+been\s+|were\s+)?damaged",
        r"([\d,]+)\s+bridges?\s+(?:have\s+been\s+|has\s+been\s+|were\s+)?damaged",
    ))

    # Households and their population are printed as one clause; taking them
    # together avoids matching the population figure onto a different bullet.
    pair = re.search(
        r"([\d,]+)\s+households?\s*,?\s*comprising\s+a\s+population\s+of\s+([\d,]+)",
        flat, re.IGNORECASE)
    if pair:
        extracted["households_isolated"] = int(re.sub(r"[^0-9]", "", pair.group(1)))
        extracted["population_isolated"] = int(re.sub(r"[^0-9]", "", pair.group(2)))
    else:
        put("households_isolated", _first(
            flat, r"([\d,]+)\s+households?\s+(?:remain\s+)?(?:isolated|cut\s+off)"))
        put("population_isolated", _first(
            flat, r"population\s+of\s+([\d,]+)\s+(?:remain\s+)?(?:isolated|cut\s+off)"))

    put("districts_affected", _first(
        flat,
        r"total\s+of\s+([\d,]+)\s+districts?\s+are\s+affected",
        r"([\d,]+)\s+districts?\s+are\s+affected",
        r"([\d,]+)\s+(?:districts?)\s+affected",
    ))

    highlights = _highlights(flat)
    if highlights:
        extracted["highlights"] = highlights

    return extracted


def _highlights(flat: str) -> list[str]:
    """The bullet list under 'Highlights', as published."""
    start = re.search(r"Highlights", flat, re.IGNORECASE)
    if not start:
        return []
    tail = flat[start.end():]
    stop = re.search(r"Situation\s+Overview|Key\s+Response", tail, re.IGNORECASE)
    block = tail[:stop.start()] if stop else tail[:4000]

    bullets = []
    for chunk in _HIGHLIGHT_SPLIT.split(block):
        cleaned = re.sub(r"\s+", " ", chunk).strip(" .,-")
        # Short fragments are column artefacts, not sentences.
        if len(cleaned) >= 25:
            bullets.append(cleaned)
    return bullets[:12]


def sitrep_number_from_title(title: str) -> Optional[int]:
    """The report number a title carries: '# ११', '#8', '#01', 'Report #7'.

    Returns None rather than a guess when the title has no number — the daily
    Nepali updates are published without one and must not be given a sequence
    position they were never assigned.
    """
    if not title:
        return None
    ascii_title = _to_ascii_digits(title)
    match = re.search(r"#\s*(\d{1,3})", ascii_title)
    if match:
        return int(match.group(1))
    match = re.search(r"(?:situation\s+report|प्रतिवेदन)\s*[#:\-]?\s*(\d{1,3})",
                      ascii_title, re.IGNORECASE)
    return int(match.group(1)) if match else None


def sitrep_lang(title: str) -> str:
    """'en' or 'ne', from the title alone.

    NDRRMA marks the English editions in the title, and the Nepali ones are
    written in Devanagari, so a script check settles it without opening the
    file. Ambiguity resolves to Nepali: that is the majority of the series, and
    running the English figure regexes over a Nepali report yields nothing
    rather than something wrong.
    """
    if not title:
        return "ne"
    if re.search(r"\bENG\b|English", title, re.IGNORECASE):
        return "en"
    if re.search(r"[ऀ-ॿ]", title):
        return "ne"
    # Titled entirely in Latin script: NDRRMA's own English-edition naming.
    return "en" if re.search(r"[A-Za-z]{4}", title) else "ne"


def sitrep_time_from_title(title: str) -> Optional[str]:
    """The clock a title prints, kept in the form it was published in.

    '(August 29, 6:30 PM)' -> '6:30 PM'; 'साँझ ६:०० बजे' -> 'साँझ ६:००'. Not
    normalised to a 24-hour string: these are the authority's own words, and a
    report that says only 'बिहान ९' has not published a minute.
    """
    if not title:
        return None

    match = re.search(r"(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?)", title)
    if match:
        return match.group(1).strip()
    match = re.search(r"(\d{1,2}\s*(?:AM|PM|am|pm))", title)
    if match:
        return match.group(1).strip()

    # Nepali: an optional time-of-day word then Devanagari digits, with or
    # without minutes.
    match = re.search(
        r"((?:बिहान|साँझ|दिउसो|राति|अपरान्ह)?\s*[०१२३४५६७८९]{1,2}(?::[०१२३४५६७८९]{2})?)\s*बजे",
        title)
    if match:
        return re.sub(r"\s+", " ", match.group(1)).strip() or None
    return None
