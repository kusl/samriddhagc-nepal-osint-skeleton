"""Extract Q&A data from Nepal HoR 6th Session PDF.

Parses the structured Nepali PDF into JSON for ingestion into the backend.
Two sections:
  - Section क (pages 1-13): Oral questions in house (no answers)
  - Section ख (pages 14-136): Written ministerial Q&A (questions + answers)

Usage:
    python scripts/extract_hor_questions.py /path/to/pdf output.json
"""
import json
import os
import re
import sys
from pathlib import Path

try:
    import fitz  # PyMuPDF — faster, better Nepali support
except ImportError:
    fitz = None

try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None


# ── Nepali numeral conversion ──────────────────────────────────────────

NEPALI_DIGITS = {"०": "0", "१": "1", "२": "2", "३": "3", "४": "4",
                 "५": "5", "६": "6", "७": "7", "८": "8", "९": "9"}

def nepali_to_ascii(s: str) -> str:
    for nd, ad in NEPALI_DIGITS.items():
        s = s.replace(nd, ad)
    return s


def parse_bs_date(raw: str) -> str | None:
    """Parse a BS date like '208२/0५/१९' → '2082-05-19'."""
    cleaned = nepali_to_ascii(raw.strip())
    m = re.match(r"(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})", cleaned)
    if not m:
        return None
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


# ── PDF text extraction ────────────────────────────────────────────────

def extract_text_pymupdf(pdf_path: str) -> str:
    doc = fitz.open(pdf_path)
    pages = []
    for page in doc:
        pages.append(page.get_text())
    return "\n".join(pages)


def extract_text_pypdf2(pdf_path: str) -> str:
    reader = PdfReader(pdf_path)
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(text)
    return "\n".join(pages)


def extract_text(pdf_path: str) -> str:
    if fitz:
        return extract_text_pymupdf(pdf_path)
    if PdfReader:
        return extract_text_pypdf2(pdf_path)
    raise RuntimeError("No PDF library available. Install PyMuPDF or PyPDF2.")


# ── Question parsing ───────────────────────────────────────────────────
# The OCR output has encoding quirks:
#   "माननीय" → "माििीय" or "सम्माििीय"
#   "प्रश्नकर्ता" → "प्रश्नकिातिः" or "प्रश्नकिाताः"
#   "प्रश्न नं." → "प्रश्न िं."
#   Numbers can be ASCII or Nepali digits, often mixed

# Pattern for ministry heading — matches both OCR variants
RE_MINISTRY = re.compile(
    r"(?:माििीय|सम्माििीय|माननीय|सम्माननीय)\s+(.+?)\s*मन्त्रीसँग"
)

# Pattern for date
RE_DATE = re.compile(
    r"(?:सोतिएको|सोधिएको)\s+तमति[ः:]?\s*-?\s*([\d०-९]{3,4}[/\-.][\d०-९]{1,2}[/\-.][\d०-९]{1,2})"
)

# Pattern for questioner — handles both OCR outputs
RE_QUESTIONER = re.compile(
    r"प्रश्नक(?:िातिः|िाताः|र्ता:?|र्ता:)\s*मा[.\s]*\s*(?:डा[.\s]*)?\s*(.+?)$",
    re.MULTILINE,
)

# Pattern for question number — handles mixed ASCII/Nepali digits
RE_QUESTION_NUM = re.compile(
    r"प्रश्न\s+(?:िं|नं|न)[.\s]*([\d०-९]+)\s*[.\s]"
)

# Pattern for answer marker
RE_ANSWER = re.compile(r"^उत्तर[:\s]", re.MULTILINE)

# Pattern for section ख header
RE_SECTION_B = re.compile(r"मन्त्रालयबाट\s+जवाफ\s+प्राप्त\s+भएका\s+मौखि?क\s+प्रश्न")


def parse_questions(text: str) -> list[dict]:
    """Parse the full PDF text into structured question records."""
    lines = text.split("\n")
    questions = []

    current_ministry = None
    current_date = None
    current_questioner = None
    current_q_num = None
    current_q_text_lines: list[str] = []
    current_answer_lines: list[str] = []
    in_answer = False
    in_section_b = False
    collecting_question = False

    def flush():
        """Save the current question if we have one."""
        nonlocal current_q_num, current_q_text_lines, current_answer_lines
        nonlocal in_answer, collecting_question

        if current_q_num and (current_q_text_lines or current_answer_lines):
            q_text = "\n".join(current_q_text_lines).strip()
            a_text = "\n".join(current_answer_lines).strip() if current_answer_lines else None

            q_num_ascii = nepali_to_ascii(current_q_num)

            questions.append({
                "question_number": q_num_ascii,
                "external_id": f"hor6-q{q_num_ascii}",
                "questioner": current_questioner,
                "ministry": current_ministry,
                "question_date_bs": current_date,
                "question_type": "written" if in_section_b else "oral",
                "question_text": q_text,
                "answer_text": a_text,
                "answered": a_text is not None and len(a_text) > 10,
                "session": "6th Session, 2082",
            })

        current_q_num = None
        current_q_text_lines = []
        current_answer_lines = []
        in_answer = False
        collecting_question = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Skip page numbers (standalone digits)
        if re.match(r"^[\d०-९]+$", stripped):
            continue

        # Detect section ख
        if RE_SECTION_B.search(stripped):
            flush()
            in_section_b = True
            continue

        # Ministry heading
        m = RE_MINISTRY.search(stripped)
        if m:
            flush()
            current_ministry = m.group(1).strip()
            continue

        # Date
        m = RE_DATE.search(stripped)
        if m:
            flush()
            current_date = parse_bs_date(m.group(1))
            continue

        # Questioner
        m = RE_QUESTIONER.search(stripped)
        if m:
            # Don't flush here — questioner comes before question number
            current_questioner = m.group(1).strip()
            # Remove trailing parenthetical like "(भण्डारी)"
            current_questioner = re.sub(r"\s*\(.*?\)\s*$", "", current_questioner)
            continue

        # Question number — starts a new question
        m = RE_QUESTION_NUM.search(stripped)
        if m:
            flush()
            current_q_num = m.group(1)
            collecting_question = True
            # Text after question number marker — remove annotations
            after = RE_QUESTION_NUM.sub("", stripped).strip()
            after = re.sub(r"\(.*?\)", "", after).strip()
            if after:
                current_q_text_lines.append(after)
            continue

        # Answer marker
        if RE_ANSWER.search(stripped):
            in_answer = True
            after = RE_ANSWER.sub("", stripped).strip()
            if after:
                current_answer_lines.append(after)
            continue

        # Accumulate text
        if collecting_question or current_q_num:
            if in_answer:
                current_answer_lines.append(stripped)
            else:
                current_q_text_lines.append(stripped)

    # Flush last question
    flush()

    return questions


# ── Ministry name normalization ────────────────────────────────────────

# Map OCR-garbled ministry names to clean Nepali names
MINISTRY_CORRECTIONS = {
    "वि िथा वािावरण": "वन तथा वातावरण",
    "सञ्चार िथा सूचिा प्रहवति": "सञ्चार तथा सूचना प्रविधि",
    "स्वास््य िथा जिसंख्या": "स्वास्थ्य तथा जनसंख्या",
    "्वा््य िथा जिसंख्या": "स्वास्थ्य तथा जनसंख्या",
    "कृहष िथा पशुपन्त्छी हवकास": "कृषि तथा पशुपन्छी विकास",
    "कृहर् िथा ुशुन्त्छी हवकास": "कृषि तथा पशुपन्छी विकास",
    "उजात,जलस्रोि िथा तसंचाई": "ऊर्जा, जलस्रोत तथा सिँचाई",
    "उजात,जलस्रोि िथा तसंचाइ": "ऊर्जा, जलस्रोत तथा सिँचाई",
    "ऊजात, जलश्रोि िथा तसंचाई": "ऊर्जा, जलस्रोत तथा सिँचाई",
    "ऊजात, जलस्रोि िथा तसंचाई": "ऊर्जा, जलस्रोत तथा सिँचाई",
    "शहरी हवकास": "शहरी विकास",
    "शहरी विकास": "शहरी विकास",
    "प्रिाि": "प्रधानमन्त्री तथा मन्त्रिपरिषद्को कार्यालय",
    "अथत": "अर्थ मन्त्रालय",
    "गृह": "गृह मन्त्रालय",
    "रक्षा": "रक्षा मन्त्रालय",
    "भौतिक पूवातिार िथा यािायाि": "भौतिक पूर्वाधार तथा यातायात",
    "भौतिक ुूवातिार िथा यािायाि": "भौतिक पूर्वाधार तथा यातायात",
    "उद्योग,वाखणज्य िथा आपूतित": "उद्योग, वाणिज्य तथा आपूर्ति",
    "उद्योग,वाखणज्य िथा आुूतित": "उद्योग, वाणिज्य तथा आपूर्ति",
    "उिोग ,वाखणज्य िथा आुूतित": "उद्योग, वाणिज्य तथा आपूर्ति",
    "खशक्षा,हवज्ञाि िथा प्रहवति": "शिक्षा, विज्ञान तथा प्रविधि",
    "महहला,बालबातलका िथा ज्येष्ठ िागररक": "महिला, बालबालिका तथा ज्येष्ठ नागरिक",
    "श्रम,रोजगार िथा सामखजक सुरक्षा": "श्रम, रोजगार तथा सामाजिक सुरक्षा",
    "श्रम,रोजगार िथा सामाखजक सुरक्षा": "श्रम, रोजगार तथा सामाजिक सुरक्षा",
    "भूतम व्यवस्था,सहकारी िथा गररबी तिवारण": "भूमि व्यवस्था, सहकारी तथा गरिबी निवारण",
    "भूतम व्यव्था,सहकारी िथा गररबी तिवारण": "भूमि व्यवस्था, सहकारी तथा गरिबी निवारण",
    "कािूि,न्त्याय िथा संसदीय मातमला": "कानून, न्याय तथा संसदीय मामिला",
    "संस्कृति,पयतटि िथा िागररक उड्डयि": "संस्कृति, पर्यटन तथा नागरिक उड्डयन",
    "सं्कृति,ुयतटि िथा िागररक उड्डयि": "संस्कृति, पर्यटन तथा नागरिक उड्डयन",
    "संघीय मातमला िथा सामान्त्य प्रशासि": "संघीय मामिला तथा सामान्य प्रशासन",
    "युवा िथा िेलकुद": "युवा तथा खेलकुद",
    "िािेुािी": "खानेपानी मन्त्रालय",
    "ुरराि": "परराष्ट्र मन्त्रालय",
}

# Questioner name normalization (OCR variants → clean name)
QUESTIONER_CORRECTIONS = {
    "मािव साुकोटा": "माधव सापकोटा",
    "मािव सापकोटा": "माधव सापकोटा",
    "सूयत प्रसाद िकाल": "सूर्य प्रसाद ढकाल",
    "सूयत प्रसाद ढकाल": "सूर्य प्रसाद ढकाल",
    "ुूणत बहादुर घतित": "पूर्ण बहादुर घर्ति",
    "पूणत बहादुर घतित": "पूर्ण बहादुर घर्ति",
    "प्रेम सुवाल": "प्रेम सुवाल",
    "सोतबिा गौिम": "सोविता गौतम",
    "तिशा डाँगी": "निशा डाँगी",
    "मेटमणी चौिरी": "मेटमणी चौधरी",
    "खशखशर ििाल": "शिशिर नेपाल",
    "चन्त्दा काकी": "चन्दा कार्की",
    "रोशि काकी": "रोशन कार्की",
    "सराज अहमद फारुकी": "सराज अहमद फारुकी",
    "िारायणी शमात": "नारायणी शर्मा",
}


def normalize_ministry(name: str | None) -> str | None:
    if not name:
        return name
    for garbled, clean in MINISTRY_CORRECTIONS.items():
        if garbled in name:
            return clean
    return name


def normalize_questioner(name: str | None) -> str | None:
    if not name:
        return name
    return QUESTIONER_CORRECTIONS.get(name, name)


def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_hor_questions.py <pdf_path> [output.json]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "hor6_questions.json"

    if not Path(pdf_path).exists():
        print(f"Error: PDF not found: {pdf_path}")
        sys.exit(1)

    print(f"Extracting text from {pdf_path}...")
    text = extract_text(pdf_path)
    print(f"Extracted {len(text):,} characters")

    print("Parsing questions...")
    questions = parse_questions(text)

    # Normalize ministry and questioner names
    for q in questions:
        q["ministry"] = normalize_ministry(q["ministry"])
        q["questioner"] = normalize_questioner(q["questioner"])

    print(f"Found {len(questions)} questions")

    # Stats
    oral = sum(1 for q in questions if q["question_type"] == "oral")
    written = sum(1 for q in questions if q["question_type"] == "written")
    answered = sum(1 for q in questions if q["answered"])
    ministries = set(q["ministry"] for q in questions if q["ministry"])

    print(f"  Oral: {oral}, Written: {written}")
    print(f"  Answered: {answered}")
    print(f"  Ministries: {len(ministries)}")
    for m in sorted(ministries):
        count = sum(1 for q in questions if q["ministry"] == m)
        print(f"    - {m}: {count}")

    output = {
        "session": "6th Session, 2082",
        "chamber": "hor",
        "period": "2082/01/12 - 2082/05/27",
        "total_questions": len(questions),
        "questions": questions,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nSaved to {output_path}")

    # Print first 3 questions as sample
    print("\n── Sample questions ──")
    for q in questions[:3]:
        print(f"  Q{q['question_number']}: {q['questioner']} → {q['ministry']}")
        print(f"    {q['question_text'][:100]}...")
        if q["answered"]:
            print(f"    Answer: {q['answer_text'][:80]}...")
        print()


def ingest_to_backend(questions: list[dict], base_url: str, password: str):
    """POST extracted questions to the backend ingest endpoint."""
    import urllib.request
    import urllib.error

    # Get auth token
    auth_url = f"{base_url}/api/v1/auth/dev-login"
    req = urllib.request.Request(
        auth_url,
        data=json.dumps({"password": password}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = urllib.request.urlopen(req)
    token = json.loads(resp.read())["access_token"]

    # Ingest questions in batches
    batch_size = 50
    total_created = 0
    total_updated = 0

    for i in range(0, len(questions), batch_size):
        batch = questions[i : i + batch_size]
        payload = []
        for q in batch:
            payload.append({
                "external_id": q["external_id"],
                "questioner": q["questioner"],
                "ministry": q["ministry"],
                "question_type": q["question_type"],
                "question_text": q["question_text"],
                "answer_text": q.get("answer_text"),
                "answered": q["answered"],
                "question_date_bs": q.get("question_date_bs"),
                "question_number": q.get("question_number"),
                "session": q.get("session"),
            })

        req = urllib.request.Request(
            f"{base_url}/api/v1/parliament/questions/ingest",
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            method="POST",
        )
        resp = urllib.request.urlopen(req)
        result = json.loads(resp.read())
        total_created += result.get("created", 0)
        total_updated += result.get("updated", 0)
        print(f"  Batch {i // batch_size + 1}: created={result['created']}, updated={result['updated']}")

    print(f"Total: created={total_created}, updated={total_updated}")


if __name__ == "__main__":
    main()

    # If --ingest flag, also POST to backend
    if "--ingest" in sys.argv:
        base_url = "http://localhost:8000"
        password = os.environ.get("OSINT_PASSWORD", "")
        for arg in sys.argv:
            if arg.startswith("--url="):
                base_url = arg.split("=", 1)[1]
            if arg.startswith("--password="):
                password = arg.split("=", 1)[1]
        if not password:
            raise SystemExit("Set OSINT_PASSWORD or pass --password=<value> to ingest questions")

        output_path = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "hor6_questions.json"
        with open(output_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        print(f"\nIngesting {len(data['questions'])} questions to {base_url}...")
        ingest_to_backend(data["questions"], base_url, password)
