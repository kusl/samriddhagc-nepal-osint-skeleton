#!/usr/bin/env python3
"""Local bill OCR + Sonnet analysis runner.

Scrapes HoR bill PDFs, OCRs locally, summarizes via Claude CLI (Sonnet 4.6),
and pushes results to VPS.

Usage:
    OSINT_PASSWORD=your-osint-password python3 run_local_bill_ocr.py
    OSINT_PASSWORD=your-osint-password python3 run_local_bill_ocr.py --limit 5
    OSINT_PASSWORD=your-osint-password python3 run_local_bill_ocr.py --limit 5 --skip-ocr
"""
import argparse
import io
import json
import logging
import os
import re
import shutil
import ssl
import subprocess
import sys
import time

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Config ──
VPS_URL = os.environ.get("VPS_URL", "http://3.148.250.92")
OSINT_EMAIL = os.environ.get("OSINT_EMAIL", "dev@narada.dev")
OSINT_PASSWORD = os.environ.get("OSINT_PASSWORD", "")
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", shutil.which("claude") or "claude")
SONNET_MODEL = "claude-sonnet-4-6"

HOR_BASE = "https://hr.parliament.gov.np"

vps_token = None


# ── VPS Auth ──
def login():
    global vps_token
    r = httpx.post(
        f"{VPS_URL}/api/v1/auth/login",
        json={"email": OSINT_EMAIL, "password": OSINT_PASSWORD},
        timeout=10,
    )
    r.raise_for_status()
    vps_token = r.json()["access_token"]
    log.info("VPS login OK")


def auth_headers():
    global vps_token
    if not vps_token:
        login()
    return {"Authorization": f"Bearer {vps_token}"}


def vps_get(path, params=None):
    for attempt in range(2):
        r = httpx.get(f"{VPS_URL}{path}", params=params, headers=auth_headers(), timeout=30)
        if r.status_code == 401 and attempt == 0:
            login()
            continue
        r.raise_for_status()
        return r.json()
    return {}


def vps_post(path, data):
    for attempt in range(2):
        r = httpx.post(f"{VPS_URL}{path}", json=data, headers=auth_headers(), timeout=60)
        if r.status_code == 401 and attempt == 0:
            login()
            continue
        r.raise_for_status()
        return r.json()
    return {}


# ── HoR Scraping ──
def get_ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def scrape_bill_list(limit=5):
    """Scrape HoR registered bills page and return bill metadata."""
    ssl_ctx = get_ssl_ctx()
    bills = []

    # Scrape registered bills (type=reg) — these are the most recent
    url = f"{HOR_BASE}/en/bills?type=reg&ref=BILL"
    log.info(f"Scraping bill list: {url}")

    resp = httpx.get(url, verify=ssl_ctx, timeout=30)
    html = resp.text

    # Parse table rows
    tables = re.findall(r'<table[^>]*>(.*?)</table>', html, re.DOTALL)
    for table in tables:
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table, re.DOTALL)
        for row in rows:
            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.DOTALL)
            if len(cells) < 5:
                continue
            cells_clean = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            if cells_clean[0] == "Session":
                continue

            links = re.findall(r'href="([^"]+/bills/[^"]+)"', row)
            if not links:
                continue

            slug = links[0].split("/bills/")[-1]
            bills.append({
                "slug": slug,
                "session": cells_clean[0],
                "reg_no": cells_clean[1] if len(cells_clean) > 1 else "",
                "date": cells_clean[2] if len(cells_clean) > 2 else "",
                "title": cells_clean[3] if len(cells_clean) > 3 else "",
                "ministry": cells_clean[4] if len(cells_clean) > 4 else "",
            })

            if len(bills) >= limit:
                break
        if len(bills) >= limit:
            break

    log.info(f"Found {len(bills)} bills")
    return bills


def scrape_bill_detail(slug):
    """Scrape individual bill detail page for presenter, PDF link, timeline."""
    ssl_ctx = get_ssl_ctx()
    url = f"{HOR_BASE}/en/bills/{slug}"
    log.info(f"  Scraping detail: {url}")

    resp = httpx.get(url, verify=ssl_ctx, timeout=30)
    html = resp.text

    detail = {"presenter": None, "pdf_url": None, "category": None, "bill_type": None}

    # Extract key-value pairs
    kv_pairs = re.findall(
        r'<div[^>]*class="[^"]*label[^"]*"[^>]*>(.*?)</div>\s*'
        r'<div[^>]*class="[^"]*value[^"]*"[^>]*>(.*?)</div>',
        html, re.DOTALL
    )
    if not kv_pairs:
        # Fallback: try table-based layout
        idx = html.find("single-bill-view")
        if idx > 0:
            chunk = html[idx:idx + 8000]
            table_rows = re.findall(r'<tr[^>]*>(.*?)</tr>', chunk, re.DOTALL)
            for tr in table_rows:
                tds = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, re.DOTALL)
                if len(tds) >= 2:
                    key = re.sub(r'<[^>]+>', '', tds[0]).strip()
                    val = re.sub(r'<[^>]+>', '', tds[1]).strip()
                    if "Presenter" in key and val:
                        detail["presenter"] = val
                    elif "Category" in key and val:
                        detail["category"] = val
                    elif "Original/Amendment" in key and val:
                        detail["bill_type"] = val

    for key, val in kv_pairs:
        key_clean = re.sub(r'<[^>]+>', '', key).strip()
        val_clean = re.sub(r'<[^>]+>', '', val).strip()
        if "Presenter" in key_clean and val_clean:
            detail["presenter"] = val_clean
        elif "Category" in key_clean and val_clean:
            detail["category"] = val_clean

    # Find PDF download link
    pdf_links = re.findall(r'href="([^"]*\.pdf[^"]*)"', html)
    if pdf_links:
        pdf_url = pdf_links[0]
        if not pdf_url.startswith("http"):
            pdf_url = HOR_BASE + pdf_url
        detail["pdf_url"] = pdf_url
    else:
        # Try download button link
        dl_links = re.findall(r'href="([^"]*download[^"]*)"', html, re.IGNORECASE)
        if dl_links:
            dl_url = dl_links[0]
            if not dl_url.startswith("http"):
                dl_url = HOR_BASE + dl_url
            detail["pdf_url"] = dl_url

    return detail


# ── OCR ──
def ocr_pdf(pdf_bytes, dpi=250):
    """OCR a PDF using PyMuPDF + pytesseract. Try text extraction first."""
    import fitz
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total = len(doc)
    log.info(f"  PDF: {total} pages")

    # First try direct text extraction (much faster if PDF has text layer)
    all_text = []
    has_text = False
    for i in range(total):
        page = doc[i]
        text = page.get_text()
        if text.strip():
            has_text = True
            all_text.append(text)

    if has_text and len("\n".join(all_text)) > 200:
        doc.close()
        result = "\n\n".join(all_text)
        log.info(f"  Text extraction: {len(result)} chars (no OCR needed)")
        return result

    # Fall back to OCR
    log.info(f"  OCR: {total} pages at {dpi} DPI")
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        log.error("  pytesseract/PIL not installed. Install: pip install pytesseract Pillow")
        doc.close()
        return "\n\n".join(all_text) if all_text else ""

    all_pages = []
    for i in range(total):
        page = doc[i]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        text = pytesseract.image_to_string(img, lang="nep+eng", config="--psm 6 --oem 1")
        all_pages.append(text)
        if (i + 1) % 5 == 0 or i == 0 or i == total - 1:
            log.info(f"  OCR page {i+1}/{total}")

    doc.close()
    result = "\n\n".join(all_pages)
    log.info(f"  OCR done: {len(result)} chars")
    return result


# ── Claude Sonnet Analysis ──
def call_sonnet(prompt, timeout=120):
    """Call Claude Sonnet 4.6 via CLI (Max subscription = free)."""
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    cmd = [
        CLAUDE_BIN,
        "-p", prompt,
        "--output-format", "text",
        "--model", SONNET_MODEL,
        "--max-turns", "1",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    if result.returncode != 0:
        raise RuntimeError(f"Claude CLI error: {result.stderr[:300]}")
    return result.stdout.strip()


def parse_json(text):
    """Extract JSON from Claude response."""
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start:end + 1])
    raise ValueError(f"No JSON found: {text[:200]}")


def analyze_bill(title, ocr_text):
    """Use Sonnet to analyze bill text."""
    # Truncate to ~15K chars to fit context comfortably
    text_for_analysis = ocr_text[:15000] if len(ocr_text) > 15000 else ocr_text

    prompt = f"""You are analyzing a Nepali parliamentary bill. The text was extracted via OCR so may have minor errors.

BILL TITLE: {title}

BILL TEXT:
{text_for_analysis}

Provide a JSON analysis with these fields:
{{
  "summary": "2-3 sentence plain English summary of what this bill does",
  "key_provisions": ["list of 3-5 key provisions or changes the bill introduces"],
  "sectors_affected": ["list of sectors/groups affected, e.g. 'agriculture', 'technology', 'judiciary'"],
  "significance": "low|medium|high — how significant is this bill for governance/citizens",
  "significance_reason": "1 sentence explaining significance rating",
  "amendment_of": "Name of existing act being amended, or null if new legislation"
}}

Respond with ONLY the JSON object, no other text."""

    raw = call_sonnet(prompt)
    return parse_json(raw)


# ── Main Pipeline ──
def main():
    parser = argparse.ArgumentParser(description="Local bill OCR + Sonnet analysis")
    parser.add_argument("--limit", type=int, default=5, help="Number of bills to process")
    parser.add_argument("--skip-ocr", action="store_true", help="Skip OCR, only scrape metadata")
    parser.add_argument("--skip-analysis", action="store_true", help="Skip Sonnet analysis")
    args = parser.parse_args()

    if not OSINT_PASSWORD:
        log.error("Set OSINT_PASSWORD env var")
        sys.exit(1)

    login()

    # Step 1: Scrape bill list from HoR
    bills = scrape_bill_list(limit=args.limit)
    if not bills:
        log.info("No bills found")
        return

    ssl_ctx = get_ssl_ctx()
    results = []

    for i, bill in enumerate(bills):
        log.info(f"\n{'='*60}")
        log.info(f"[{i+1}/{len(bills)}] {bill['title']}")

        # Step 2: Scrape detail page
        detail = scrape_bill_detail(bill["slug"])
        log.info(f"  Presenter: {detail['presenter']}")
        log.info(f"  PDF URL: {detail['pdf_url']}")

        ocr_text = None
        ai_analysis = None

        # Step 3: Download PDF and OCR
        if detail["pdf_url"] and not args.skip_ocr:
            try:
                log.info(f"  Downloading PDF...")
                resp = httpx.get(detail["pdf_url"], verify=ssl_ctx, timeout=120, follow_redirects=True)
                if resp.status_code == 200 and len(resp.content) > 1000:
                    log.info(f"  Downloaded: {len(resp.content) / 1024:.0f} KB")
                    ocr_text = ocr_pdf(resp.content)
                else:
                    log.warning(f"  PDF download failed: status={resp.status_code}, size={len(resp.content)}")
            except Exception as e:
                log.error(f"  PDF/OCR error: {e}")

        # Step 4: Sonnet analysis
        if ocr_text and not args.skip_analysis:
            try:
                log.info(f"  Running Sonnet analysis...")
                analysis = analyze_bill(bill["title"], ocr_text)
                ai_analysis = json.dumps(analysis, ensure_ascii=False)
                log.info(f"  Analysis: {analysis.get('summary', '')[:100]}")
                log.info(f"  Significance: {analysis.get('significance', '?')}")
            except Exception as e:
                log.error(f"  Analysis error: {e}")

        result = {
            "external_id": bill["slug"],
            "presented_by": detail["presenter"],
            "pdf_url": detail["pdf_url"],
        }
        if ocr_text:
            result["ocr_text"] = ocr_text
        if ai_analysis:
            result["ai_analysis"] = ai_analysis

        results.append(result)

        # Be polite to parliament server
        time.sleep(1)

    # Step 5: Push to VPS
    if results:
        log.info(f"\nPushing {len(results)} bills to VPS...")
        try:
            resp = vps_post("/api/v1/parliament/bills/ingest-analysis", results)
            log.info(f"  Result: {resp}")
        except Exception as e:
            log.error(f"  Push error: {e}")
            # Save locally as backup
            backup = "/tmp/bill_analysis_backup.json"
            with open(backup, "w") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            log.info(f"  Saved backup to {backup}")

    log.info(f"\n{'='*60}")
    log.info(f"Done! Processed {len(results)} bills.")


if __name__ == "__main__":
    main()
