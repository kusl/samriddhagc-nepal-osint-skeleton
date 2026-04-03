#!/usr/bin/env python3
"""Local OCR scraper: downloads NA verbatim PDFs, OCRs on Mac, pushes to VPS DB.

Usage:
    python3 run_local_ocr_push.py
"""
import re
import ssl
import io
import json
import subprocess
from uuid import uuid4

import httpx
import fitz  # PyMuPDF
import pytesseract
from PIL import Image

# ─── Config ──────────────────────────────────────────────
SSH_KEY = "~/Downloads/LightsailDefaultKey-us-east-2.pem"
SSH_HOST = "ubuntu@3.148.250.92"
NA_BASE = "https://na.parliament.gov.np"

# Target: latest sessions on १२ असार २०८२
TARGET_PDFS = [
    {
        "title_ne": "अठारौं अधिवेशन_कार्यवाहीको सम्पूर्ण विवरण_१२ असार २०८२ विहिबार (बैठक सङ्ख्या- २३)",
        "pdf_url": "https://na.parliament.gov.np/uploads/attachments/2uxhebokhd79zxge.pdf",
        "date_str": "2026-01-13",
    },
    {
        "title_ne": "अठारौं अधिवेशन_कार्यवाहीको सम्पूर्ण विवरण_१२ असार २०८२ विहिबार (बैठक सङ्ख्या- २४ दोस्रो)",
        "pdf_url": "https://na.parliament.gov.np/uploads/attachments/p10zvha9bt3ri29s.pdf",
        "date_str": "2026-01-13",
    },
]

# ─── Speech parsing ──────────────────────────────────────
SPEECH_PATTERN = re.compile(
    r'\(([०-९\d]{1,2}[:\uff1a][०-९\d]{2})\s*बजे\)'
    r'\s*'
    r'(?:माननीय|सम्माननीय)'
    r'([^(]{1,150}?)'
    r'\(([^)]{2,200})\)'
    r'\s*:?-?\s*',
    re.UNICODE
)

CHAIR_PATTERN = re.compile(
    r'(?:सम्माननीय|स[àa-z]*माननीय)\s*(?:अध्यक्ष|अÚय¢)|'
    r'^अध्यक्ष\s*[:：]',
    re.UNICODE
)

PARTY_RULES = [
    (["माओवाद"], "Nepal Communist Party (Maoist Center)"),
    (["एक", "समाजवाद"], "Communist Party of Nepal (Unified Socialist)"),
    (["एमाले"], "Nepal Communist Party (UML)"),
    (["काँग्रेस"], "Nepali Congress"),
    (["कांग्रेस"], "Nepali Congress"),
    (["जनमोचा"], "Rastriya Janamorcha"),
    (["जनमोर्चा"], "Rastriya Janamorcha"),
    (["लोकता", "समाजवाद"], "Loktantrik Samajwadi Party Nepal"),
    (["जनता", "समाज"], "Janata Samajbadi Party Nepal"),
    (["स्वतन्त्र"], "Rastriya Swotantra Party"),
    (["प्रजातन्त्र"], "Rastriya Prajatantra Party"),
    (["मनोनीत"], "Nominated"),
    (["मनो"], "Nominated"),
    (["जनमत"], "Janamat Party"),
    (["उन्मुक्ति"], "Nagarik Unmukti Party"),
    (["मजदुर", "किसान"], "Nepal Workers Peasants Party"),
]


def translate_party(raw):
    if not raw:
        return None
    cleaned = re.sub(r'\s+', ' ', raw).strip()
    for fragments, en in PARTY_RULES:
        if all(f in cleaned for f in fragments):
            return en
    return None


def extract_session_info(title):
    info = {"session_no": None, "meeting_no": None, "session_date_bs": None}
    ordinals = {
        "पहिलो": 1, "दोस्रो": 2, "तेस्रो": 3, "चौथो": 4, "पाँचौँ": 5,
        "छैठौँ": 6, "सातौँ": 7, "आठौँ": 8, "नवौँ": 9, "दशौँ": 10,
        "एघारौँ": 11, "बाह्रौँ": 12, "तेह्रौँ": 13, "चौधौँ": 14,
        "पन्ध्रौँ": 15, "सोह्रौँ": 16, "सत्रौँ": 17, "अठारौँ": 18, "अठारौं": 18,
        "उन्नाइसौँ": 19, "बीसौँ": 20,
    }
    for word, num in ordinals.items():
        if word in title:
            info["session_no"] = num
            break

    meeting_match = re.search(r'बैठक\s*सङ्?ख्या-?\s*(\d+)', title)
    if not meeting_match:
        nep_match = re.search(r'बैठक\s*सङ्?ख्या-?\s*([०-९]+)', title)
        if nep_match:
            nep_digits = nep_match.group(1)
            info["meeting_no"] = int(nep_digits.translate(
                str.maketrans("०१२३४५६७८९", "0123456789")
            ))
    else:
        info["meeting_no"] = int(meeting_match.group(1))

    bs_match = re.search(r'([०-९\d]+)\s+(\S+)\s+([०-९\d]{4})', title)
    if bs_match:
        info["session_date_bs"] = bs_match.group(0)

    return info


def ocr_pdf(pdf_bytes, dpi=300):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    all_pages = []
    total = len(doc)
    print(f"  OCR: {total} pages at {dpi} DPI")

    for i in range(total):
        page = doc[i]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        text = pytesseract.image_to_string(img, lang="nep+hin", config="--psm 6 --oem 1")
        all_pages.append(text)
        if (i + 1) % 5 == 0 or i == 0 or i == total - 1:
            print(f"  OCR page {i+1}/{total}")

    doc.close()
    return "\n\n".join(all_pages)


def parse_speeches(raw_text):
    speeches = []
    matches = list(SPEECH_PATTERN.finditer(raw_text))
    if not matches:
        print("  WARNING: No speech patterns found!")
        return speeches

    for i, match in enumerate(matches):
        groups = match.groups()
        timestamp = groups[0]
        name_blob = groups[1].strip()
        party = groups[2].strip()

        name = name_blob
        for prefix in ["माननीय", "सम्माननीय", "श्री"]:
            name = name.replace(prefix, "")
        name = re.sub(r'^\s*[:\-]+\s*', '', name).strip()
        if len(name) < 2:
            name = name_blob.strip()

        party = re.sub(r'\s+', ' ', party).strip()

        text_start = match.end()
        text_end = matches[i + 1].start() if i + 1 < len(matches) else len(raw_text)
        speech_text = raw_text[text_start:text_end].strip()
        speech_text = re.sub(r'\n\s*\d+\s*\n', '\n', speech_text)

        if not speech_text or len(speech_text) < 10:
            continue

        is_chair = bool(CHAIR_PATTERN.search(name_blob))

        speeches.append({
            "id": str(uuid4()),
            "speaker_name_ne": name[:250],
            "speaker_party_ne": party[:250] if not is_chair else None,
            "speaker_party_en": translate_party(party) if not is_chair else None,
            "speaker_role": "सम्माननीय अध्यक्ष" if is_chair else "माननीय",
            "timestamp": timestamp,
            "speech_text": speech_text,
            "word_count": len(speech_text.split()),
            "speech_order": i,
        })

    return speeches


def esc(s):
    """Escape string for PostgreSQL."""
    if s is None:
        return "NULL"
    return "'" + str(s).replace("'", "''") + "'"


def push_to_vps(session, speeches, raw_text):
    """Push session + speeches via SSH + psql."""
    sql_parts = []

    # Check for existing session
    sql_parts.append(f"""
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM verbatim_sessions WHERE pdf_url = {esc(session['pdf_url'])}) THEN
        RAISE NOTICE 'Session already exists, skipping';
        RETURN;
    END IF;

    INSERT INTO verbatim_sessions (id, pdf_url, title_ne, session_no, meeting_no, session_date_bs, session_date, chamber, raw_text, page_count, speech_count, is_processed, scraped_at)
    VALUES (
        {esc(session['id'])}::uuid,
        {esc(session['pdf_url'])},
        {esc(session['title_ne'])},
        {session['session_no'] if session['session_no'] else 'NULL'},
        {session['meeting_no'] if session['meeting_no'] else 'NULL'},
        {esc(session['session_date_bs'])},
        {esc(session['session_date'])}::date,
        {esc(session['chamber'])},
        {esc(raw_text)},
        {session['page_count']},
        {len(speeches)},
        true,
        NOW()
    );
""")

    for s in speeches:
        sql_parts.append(f"""
    INSERT INTO parliamentary_speeches (id, session_id, speaker_name_ne, speaker_party_ne, speaker_party_en, speaker_role, timestamp, speech_text, word_count, speech_order)
    VALUES (
        {esc(s['id'])}::uuid,
        {esc(session['id'])}::uuid,
        {esc(s['speaker_name_ne'])},
        {esc(s['speaker_party_ne'])},
        {esc(s['speaker_party_en'])},
        {esc(s['speaker_role'])},
        {esc(s['timestamp'])},
        {esc(s['speech_text'])},
        {s['word_count']},
        {s['speech_order']}
    );""")

    sql_parts.append("\nEND $$;")
    full_sql = "\n".join(sql_parts)

    sql_file = f"/tmp/verbatim_insert_{session['meeting_no'] or 'x'}.sql"
    with open(sql_file, "w") as f:
        f.write(full_sql)
    print(f"  SQL: {len(full_sql)} bytes -> {sql_file}")

    # SCP to VPS host, then docker cp into postgres container, then execute
    subprocess.run([
        "scp", "-i", SSH_KEY, sql_file,
        f"{SSH_HOST}:/tmp/verbatim_insert.sql"
    ], check=True)

    result = subprocess.run([
        "ssh", "-i", SSH_KEY, SSH_HOST,
        "docker cp /tmp/verbatim_insert.sql osint_postgres:/tmp/verbatim_insert.sql && "
        "docker exec osint_postgres psql -U nepal_osint -d nepal_osint -f /tmp/verbatim_insert.sql"
    ], capture_output=True, text=True, timeout=120)

    if result.returncode == 0:
        print(f"  DB push OK: {result.stdout.strip()}")
    else:
        print(f"  DB push ERROR: {result.stderr[:500]}")
    return result.returncode == 0


def main():
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    for item in TARGET_PDFS:
        print(f"\n{'='*60}")
        print(f"Session: {item['title_ne']}")

        # Download
        print("  Downloading PDF...")
        resp = httpx.get(item["pdf_url"], verify=ssl_ctx, timeout=120.0)
        resp.raise_for_status()
        pdf_bytes = resp.content
        print(f"  Downloaded: {len(pdf_bytes) / 1024:.0f} KB")

        # OCR locally
        raw_text = ocr_pdf(pdf_bytes)
        print(f"  OCR done: {len(raw_text)} chars")

        # Detect chamber
        chamber = "na" if "राष्ट्रिय सभा" in raw_text[:3000] else "na"
        print(f"  Chamber: {chamber}")

        # Parse
        info = extract_session_info(item["title_ne"])
        speeches = parse_speeches(raw_text)
        print(f"  Session info: {info}")
        print(f"  Speeches: {len(speeches)}")
        for s in speeches[:3]:
            print(f"    - {s['speaker_name_ne'][:30]} ({s['speaker_party_en'] or s['speaker_party_ne'] or 'chair'}): {s['word_count']} words")

        session = {
            "id": str(uuid4()),
            "pdf_url": item["pdf_url"],
            "title_ne": item["title_ne"],
            "session_no": info["session_no"],
            "meeting_no": info["meeting_no"],
            "session_date_bs": info["session_date_bs"],
            "session_date": item["date_str"],
            "chamber": chamber,
            "page_count": raw_text.count("\n\n") + 1,
        }

        # Push to VPS
        print("  Pushing to VPS...")
        ok = push_to_vps(session, speeches, raw_text)
        if ok:
            print(f"  Session {info['meeting_no']} pushed!")

    print(f"\n{'='*60}")
    print("Done! Now run analysis:")
    print("  OSINT_PASSWORD=devpassword123 python3 run_local_verbatim.py --once")


if __name__ == "__main__":
    main()
