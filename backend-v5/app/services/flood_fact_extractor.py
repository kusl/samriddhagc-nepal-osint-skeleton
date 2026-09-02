"""
FLOOD FACT EXTRACTOR — turns the story store into typed, sourced, placed facts.

Runs on a schedule over every story that mentions the event and has not been
read yet. Two extractors, layered:

* RULES (always on): sentence-level patterns in Nepali and English — a figure
  next to a body word and a verb (buried / recovered / managed / brought /
  identified), a country next to a team word, a project alias next to a tunnel
  word, a highway word next to a cut/open word — plus a gazetteer of the
  corridor's places and the affected districts' municipalities to name the
  place. Deterministic, keyless, and honest about what it cannot read.
* LLM (when `openai_api_key` is set): the same story is sent once through the
  desk's OpenAI-compatible runtime with a strict JSON schema; its facts are
  merged with the rules' by dedupe key and marked with the model name.

Every fact keeps the sentence verbatim, is geocoded through Nominatim
(cached, one query per second, Nepal only) and lands in `flood_facts` with
status `auto`. The boards render `auto` rows beside their verified seeds and
say so; nothing here overwrites a verified figure.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from sqlalchemy import select, text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flood_event import FloodExtractionRun, FloodFact, GeocodeCache

logger = logging.getLogger(__name__)

EVENT_KEY = "trishuli-2026-08"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
NOMINATIM_UA = "nepalosint-desk/1.0 (https://nepalosint.com)"
_last_geocode = {"at": 0.0}

# ------------------------------------------------------------------ language helpers

_NE_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_NE_WORD_NUM = {
    "एक": 1, "दुई": 2, "तीन": 3, "चार": 4, "पाँच": 5, "छ": 6, "सात": 7, "आठ": 8, "नौ": 9, "दश": 10, "दस": 10,
    "बीस": 20, "तीस": 30, "चालीस": 40, "पचास": 50, "साठी": 60, "सत्तरी": 70, "असी": 80, "नब्बे": 90,
    "सय": 100, "हजार": 1000,
}


def normalise(s: str) -> str:
    s = s.translate(_NE_DIGITS)
    s = s.replace("‍", "").replace("‌", "")
    return re.sub(r"[ \t]+", " ", s)


def _num(tok: str) -> Optional[float]:
    tok = tok.replace(",", "").strip()
    try:
        return float(tok)
    except ValueError:
        return None


def _ne_compound_number(s: str) -> Optional[float]:
    """'एक हजार एक सय १८' -> 1118; 'सात' -> 7; 'तीन सय' -> 300. Digits win when present."""
    s = normalise(s).strip()
    m = re.fullmatch(r"\d{1,3}(?:,\d{3})+|\d+", s)
    if m:
        return _num(s)
    toks = s.split()
    total = 0.0
    cur = 0.0
    seen = False
    for t in toks:
        if re.fullmatch(r"\d+", t):
            cur += float(t)
            seen = True
        elif t in ("सय", "हजार"):
            mult = _NE_WORD_NUM[t]
            cur = (cur or 1) * mult
            if t == "हजार":
                total += cur
                cur = 0
            seen = True
        elif t in _NE_WORD_NUM:
            cur += _NE_WORD_NUM[t]
            seen = True
        else:
            return None
    return (total + cur) if seen else None


NUM_NE = r"(?:\d{1,3}(?:,\d{3})+|\d+|(?:(?:एक|दुई|तीन|चार|पाँच|छ|सात|आठ|नौ|दश|दस|बीस|तीस|चालीस|पचास|साठी|सत्तरी|असी|नब्बे)\s*)+(?:सय|हजार)?(?:\s*(?:एक|दुई|तीन|चार|पाँच|छ|सात|आठ|नौ|दश|दस|बीस|तीस|चालीस|पचास|साठी|सत्तरी|असी|नब्बे|\d+)\s*(?:सय)?)*)"

# ------------------------------------------------------------------ patterns

BODY_NE = r"(?:शव|लाश|मृतक|मानव अवशेष)"
BODY_EN = r"(?:bod(?:y|ies)|remains|corpses?|dead)"

RULES: list[dict[str, Any]] = [
    # Burial / management of unidentified remains
    {"type": "burial", "lang": "ne", "re": re.compile(rf"(?P<n>{NUM_NE})\s*(?:वटा|जना)?\s*{BODY_NE}[^।]*?(?:गाडि|गाड्|व्यवस्थापन गरि|समाधिस्थ|दफन)", re.U), "unit": "bodies", "conf": 0.7},
    {"type": "burial", "lang": "en", "re": re.compile(rf"(?P<n>\d[\d,]*)\s+(?:unidentified\s+|unclaimed\s+)?{BODY_EN}[^.]*?\b(?:buried|interred|temporary burial|managed)\b", re.I), "unit": "bodies", "conf": 0.7},
    # Recovery from the river / found
    {"type": "recovery", "lang": "ne", "re": re.compile(rf"(?P<n>{NUM_NE})\s*(?:वटा|जना)?\s*{BODY_NE}[^।]*?(?:फेला|निकालि|बरामद|भेटि|उद्धार गरि)", re.U), "unit": "bodies", "conf": 0.6},
    {"type": "recovery", "lang": "en", "re": re.compile(rf"(?P<n>\d[\d,]*)\s+{BODY_EN}[^.]*?\b(?:recovered|retrieved|found|pulled)\b", re.I), "unit": "bodies", "conf": 0.6},
    # Identification
    {"type": "forensic", "lang": "ne", "re": re.compile(rf"(?P<n>{NUM_NE})\s*(?:वटा|जना)?\s*{BODY_NE}[^।]*?(?:सनाखत|पहिचान)", re.U), "unit": "identified", "conf": 0.6},
    {"type": "forensic", "lang": "en", "re": re.compile(rf"(?P<n>\d[\d,]*)\s+{BODY_EN}[^.]*?\bidentified\b", re.I), "unit": "identified", "conf": 0.6},
    # Brought to / received at a place (mortuary)
    {"type": "mortuary", "lang": "ne", "re": re.compile(rf"(?P<n>{NUM_NE})\s*(?:वटा|जना)?\s*{BODY_NE}[^।]*?(?:ल्याइ|पुर्‍?याइ|राखिए)", re.U), "unit": "bodies", "conf": 0.5},
    {"type": "mortuary", "lang": "en", "re": re.compile(rf"(?P<n>\d[\d,]*)\s+{BODY_EN}[^.]*?\b(?:brought to|taken to|kept at|held at)\b", re.I), "unit": "bodies", "conf": 0.5},
    # Foreign teams
    {"type": "team", "lang": "en", "re": re.compile(r"(?P<n>\d{1,3})[- ]member\s+(?P<what>[A-Za-z ]{3,60}?)\s*(?:team|contingent)", re.I), "unit": "personnel", "conf": 0.6},
    {"type": "team", "lang": "ne", "re": re.compile(rf"(?P<n>{NUM_NE})\s*(?:सदस्यीय|जनाको)\s*(?P<what>[^।]{{3,60}}?)\s*(?:टोली|टिम)", re.U), "unit": "personnel", "conf": 0.6},
    # Aid tonnage / money
    {"type": "aid", "lang": "en", "re": re.compile(r"(?P<n>\d[\d,.]*)\s*(?:metric\s+)?(?:tons?|tonnes?)\s+of\s+(?P<what>[a-z ,]{3,60})", re.I), "unit": "t", "conf": 0.6},
    {"type": "aid", "lang": "ne", "re": re.compile(rf"(?P<n>{NUM_NE})\s*(?:मेट्रिक\s+)?टन", re.U), "unit": "t", "conf": 0.6},
    {"type": "money", "lang": "en", "re": re.compile(r"(?P<cur>USD|US\$|\$|AUD|EUR|€|£|GBP|CHF|Rs\.?|NPR|NRs\.?)\s?(?P<n>\d[\d,.]*)\s*(?P<mag>million|billion|m|bn|lakh|crore)?", re.I), "unit": "money", "conf": 0.5},
    {"type": "money", "lang": "ne", "re": re.compile(rf"(?:रु\.?|रुपैयाँ)\s*(?P<n>{NUM_NE})\s*(?P<mag>लाख|करोड|अर्ब)?", re.U), "unit": "money", "conf": 0.5},
    # Highway status
    {"type": "road", "lang": "en", "re": re.compile(r"(?P<what>Prithvi Highway|Pasang Lhamu Highway|Narayangadh[- ]Mugling|Mugling[- ]Narayangadh|BP Highway|Araniko Highway)[^.]*?\b(?P<state>cut|blocked|closed|reopened|opened|restored|one-way)\b", re.I), "unit": "status", "conf": 0.6},
    {"type": "road", "lang": "ne", "re": re.compile(r"(?P<what>पृथ्वी राजमार्ग|पासाङ ल्हामु राजमार्ग|नारायणगढ[- ]मुग्लिन|मुग्लिन[- ]नारायणगढ)[^।]*?(?P<state>अवरुद्ध|बन्द|खुल्यो|खुला|सञ्चालन|खोलियो)", re.U), "unit": "status", "conf": 0.6},
]

COUNTRY_WORDS = {
    "IN": r"india|indian|भारत|भारतीय", "CN": r"china|chinese|चीन|चिनियाँ", "KR": r"south korea|republic of korea|korean?|कोरिया|कोरियाली",
    "SG": r"singapore|सिंगापुर", "US": r"united states|u\.s\.|american|usaid|अमेरिका|अमेरिकी", "AU": r"australia|australian|अष्ट्रेलिया",
    "AE": r"\buae\b|united arab emirates|emirati|युएई", "JP": r"japan|japanese|जापान", "GB": r"united kingdom|britain|british|\buk\b|बेलायत",
    "QA": r"qatar|कतार", "NZ": r"new zealand", "MY": r"malaysia|मलेसिया", "BD": r"bangladesh|बंगलादेश", "PK": r"pakistan|पाकिस्तान",
    "DE": r"germany|german|जर्मनी", "CH": r"switzerland|swiss|स्विट्जरल्याण्ड", "FR": r"france|french|फ्रान्स", "TR": r"türkiye|turkey|turkish",
    "IL": r"israel|israeli|इजरायल", "CA": r"canada|canadian|क्यानडा", "EU": r"european union|\beu\b|युरोपेली संघ",
}

# Projects: alias -> key (mirrors the tunnel ledger's aliases; kept short here, the
# ledger's own alias table is merged in at runtime).
TUNNEL_WORDS = r"tunnel|सुरुङ|सुरूङ"

# Sentence split for both scripts.
_SENT_RE = re.compile(r"(?<=[।.!?])\s+|\n+")

# ------------------------------------------------------------------ gazetteer

# name -> (district, english). Nepali and English spellings both resolve.
GAZETTEER: dict[str, tuple[str, str]] = {}


def _gz(en: str, district: str, *names: str) -> None:
    for n in (en, *names):
        GAZETTEER[n.lower()] = (district, en)


_gz("Rasuwagadhi", "Rasuwa", "रसुवागढी", "Gyirong Port", "केरुङ", "Kerung", "Gyirong")
_gz("Timure", "Rasuwa", "टिमुरे")
_gz("Syabrubesi", "Rasuwa", "स्याफ्रुबेसी", "स्याब्रुबेसी", "Syaphrubesi")
_gz("Dhunche", "Rasuwa", "धुन्चे")
_gz("Chilime", "Rasuwa", "चिलिमे")
_gz("Langtang", "Rasuwa", "लाङटाङ", "लाङटाङ")
_gz("Haku", "Rasuwa", "हाकु")
_gz("Mailung", "Rasuwa", "माइलुङ", "मैलुङ")
_gz("Betrawati", "Nuwakot", "बेत्रावती")
_gz("Trishuli Bazar", "Nuwakot", "त्रिशूली बजार", "त्रिशुली बजार", "Bidur", "बिदुर")
_gz("Kakani", "Nuwakot", "काकनी")
_gz("Galchhi", "Dhading", "गल्छी")
_gz("Gajuri", "Dhading", "गजुरी")
_gz("Malekhu", "Dhading", "मलेखु")
_gz("Krishnabhir", "Dhading", "कृष्णभीर", "Krishna Bhir")
_gz("Benighat", "Dhading", "बेनीघाट")
_gz("Dhadingbesi", "Dhading", "धादिङबेसी", "Nilkantha", "नीलकण्ठ")
_gz("Mugling", "Chitwan", "मुग्लिन", "मुग्लिङ")
_gz("Narayanghat", "Chitwan", "नारायणघाट", "Narayangadh", "नारायणगढ")
_gz("Bharatpur", "Chitwan", "भरतपुर")
_gz("Devghat", "Tanahun", "देवघाट")
_gz("Damauli", "Tanahun", "दमौली")
_gz("Bardaghat", "Nawalparasi West", "बर्दघाट")
_gz("Sunwal", "Nawalparasi West", "सुनवल")
_gz("Ramgram", "Nawalparasi West", "रामग्राम", "Parasi", "परासी")
_gz("Triveni", "Nawalparasi West", "त्रिवेणी", "Gandak", "गण्डक")
_gz("Kawasoti", "Nawalparasi East", "कावासोती")
_gz("Gaindakot", "Nawalparasi East", "गैंडाकोट")
_gz("Gorkha Bazar", "Gorkha", "गोरखा बजार")
_gz("Hetauda", "Makwanpur", "हेटौंडा", "हेटौडा")
_gz("Kathmandu", "Kathmandu", "काठमाडौं", "काठमाडौँ")
_gz("Gokarneshwor", "Kathmandu", "गोकर्णेश्वर", "Gokarneshwar")
_gz("Maharajgunj", "Kathmandu", "महाराजगन्ज", "महाराजगञ्ज", "Maharajganj")
_gz("Nepal Police Hospital", "Kathmandu", "प्रहरी अस्पताल", "Police Hospital")
_gz("TU Teaching Hospital", "Kathmandu", "शिक्षण अस्पताल", "Teaching Hospital", "टिचिङ अस्पताल")
_gz("Tribhuvan International Airport", "Kathmandu", "त्रिभुवन विमानस्थल", "त्रिभुवन अन्तर्राष्ट्रिय विमानस्थल", "TIA")
_gz("Pokhara", "Kaski", "पोखरा")
_gz("Tansen", "Palpa", "तानसेन", "Palpa", "पाल्पा")
_gz("Butwal", "Rupandehi", "बुटवल")
_gz("Bhairahawa", "Rupandehi", "भैरहवा")
_gz("Birgunj", "Parsa", "वीरगन्ज", "वीरगञ्ज")
_gz("Rasuwa", "Rasuwa", "रसुवा")
_gz("Nuwakot", "Nuwakot", "नुवाकोट")
_gz("Dhading", "Dhading", "धादिङ")
_gz("Chitwan", "Chitwan", "चितवन")
_gz("Tanahun", "Tanahun", "तनहुँ", "तनहुं")
_gz("Gorkha", "Gorkha", "गोरखा")
_gz("Nawalparasi", "Nawalparasi West", "नवलपरासी")
_gz("Makwanpur", "Makwanpur", "मकवानपुर")

_GZ_RE = re.compile("|".join(sorted((re.escape(k) for k in GAZETTEER), key=len, reverse=True)), re.I)

STOP_PLACES = {"nepal", "नेपाल"}

# A dateline — "काठमाडौं :", "Kathmandu, Sept 2:", "रूपन्देही –" — names where the
# reporter sat, not where the fact happened. Stripped before place reading.
_DATELINE_RE = re.compile(r"^\s*[^\s,:–—-]{2,40}(?:\s*,\s*[A-Za-z]+\.?\s*\d{1,2})?\s*[:–—-]\s*", re.U)
# A national running total: the authority or a "so far" word. Not a place fact.
_NATIONAL_RE = re.compile(r"अहिलेसम्म|हालसम्म|कुल|जम्मा|प्राधिकरण|NDRRMA|so far|in total|nationwide|altogether|death toll|मृत्यु हुनेको सङ्ख्या|मृतकको सङ्ख्या", re.I | re.U)
# District and capital names are datelines or scope words far more often than
# sites; a body fact needs a named locality or facility to be placed at all.
DISTRICT_NAMES = {"rasuwa", "nuwakot", "dhading", "chitwan", "tanahun", "gorkha", "nawalparasi", "makwanpur", "kathmandu",
                  "रसुवा", "नुवाकोट", "धादिङ", "चितवन", "तनहुँ", "तनहुं", "गोरखा", "नवलपरासी", "मकवानपुर", "काठमाडौं", "काठमाडौँ"}


def places_in(sentence: str) -> list[tuple[str, str, str]]:
    """(matched text, english name, district) for every gazetteer hit, longest first, deduped.
    The dateline at the head of a sentence is not a place the fact happened."""
    out: list[tuple[str, str, str]] = []
    seen = set()
    body = _DATELINE_RE.sub("", sentence, count=1) if _DATELINE_RE.match(sentence) and _GZ_RE.match(sentence.strip()) else sentence
    for m in _GZ_RE.finditer(body):
        key = m.group(0).lower()
        if key in seen or key in STOP_PLACES:
            continue
        seen.add(key)
        district, en = GAZETTEER[key]
        out.append((m.group(0), en, district))
    return out


# ------------------------------------------------------------------ geocoding

async def geocode(db: AsyncSession, place_en: str, district: Optional[str]) -> Optional[dict[str, Any]]:
    q = f"{place_en}, {district}, Nepal" if district and district.lower() not in place_en.lower() else f"{place_en}, Nepal"
    row = await db.get(GeocodeCache, q)
    if row:
        return {"lat": row.lat, "lng": row.lng, "display_name": row.display_name, "kind": row.osm_class} if row.lat is not None else None
    # Nominatim usage policy: one request per second, identified UA.
    wait = 1.1 - (time.monotonic() - _last_geocode["at"])
    if wait > 0:
        await asyncio.sleep(wait)
    _last_geocode["at"] = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": NOMINATIM_UA}) as client:
            r = await client.get(NOMINATIM, params={"format": "json", "limit": 1, "countrycodes": "np", "q": q})
            r.raise_for_status()
            res = r.json()
    except Exception as e:  # noqa: BLE001
        logger.warning("geocode %r failed: %s", q, e)
        return None
    if res:
        hit = res[0]
        rec = GeocodeCache(query=q, lat=float(hit["lat"]), lng=float(hit["lon"]), display_name=hit.get("display_name"),
                           osm_type=hit.get("osm_type"), osm_class=hit.get("class"))
        db.add(rec)
        await db.commit()
        return {"lat": rec.lat, "lng": rec.lng, "display_name": rec.display_name, "kind": rec.osm_class}
    db.add(GeocodeCache(query=q, lat=None, lng=None, display_name=None))
    await db.commit()
    return None


# ------------------------------------------------------------------ rules extractor

def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_RE.split(text) if s and len(s.strip()) > 12]


def _money_value(n: str, mag: Optional[str], cur: Optional[str]) -> tuple[Optional[float], str]:
    v = _num(n)
    if v is None:
        return None, "money"
    mag = (mag or "").lower()
    if mag in ("million", "m"):
        v *= 1e6
    elif mag in ("billion", "bn", "अर्ब"):
        v *= 1e9
    elif mag in ("lakh", "लाख"):
        v *= 1e5
    elif mag in ("crore", "करोड"):
        v *= 1e7
    c = (cur or "").upper().replace(".", "")
    unit = {"$": "USD", "US$": "USD", "RS": "NPR", "NRS": "NPR", "€": "EUR", "£": "GBP"}.get(c, c or "NPR")
    return v, unit


def rules_extract(story: dict[str, Any], project_aliases: dict[str, list[str]]) -> list[dict[str, Any]]:
    """Facts from one story by pattern. Each fact carries its sentence verbatim."""
    blob = " ".join(x for x in (story.get("title"), story.get("summary"), story.get("content")) if x)
    blob = normalise(blob)
    facts: list[dict[str, Any]] = []
    for sent in _sentences(blob):
        low = sent.lower()
        plc = places_in(sent)
        # A district split ("रसुवामा 115, नुवाकोटमा 12, ...") names several districts
        # with several figures: one place cannot own one figure, so it is a toll
        # sentence, not a site fact.
        district_hits = sum(1 for m in plc if m[0].lower() in DISTRICT_NAMES)
        national = bool(_NATIONAL_RE.search(sent)) or district_hits >= 3
        place = next((m for m in plc if m[0].lower() not in DISTRICT_NAMES), None)
        if national:
            place = None
        countries = [c for c, pat in COUNTRY_WORDS.items() if re.search(pat, sent, re.I)]
        for rule in RULES:
            for m in rule["re"].finditer(sent):
                gd = m.groupdict()
                figure: Optional[float] = None
                unit = rule["unit"]
                subject = None
                if rule["type"] == "money":
                    figure, unit = _money_value(gd.get("n") or "", gd.get("mag"), gd.get("cur"))
                elif gd.get("n"):
                    figure = _ne_compound_number(gd["n"]) if rule["lang"] == "ne" else _num(gd["n"])
                if rule["type"] in ("team", "aid", "money"):
                    if not countries:
                        continue  # a team or a shipment with no sender is not a fact for the board
                    subject = countries[0]
                if rule["type"] == "road":
                    subject = gd.get("what")
                    figure = None
                    unit = (gd.get("state") or "").lower()
                if rule["type"] in ("burial", "recovery", "forensic", "mortuary") and (figure is None or figure <= 0 or figure > 5000):
                    continue
                ftype = rule["type"]
                if ftype in ("burial", "recovery", "forensic", "mortuary") and (national or (figure or 0) >= 1000 or place is None):
                    # No locality, or a figure only a national count reaches: a toll line, not a site.
                    ftype = "toll"
                if rule["type"] == "team" and (figure is None or figure > 500):
                    continue
                facts.append({
                    "fact_type": ftype,
                    "subject": (gd.get("what") or "").strip() or None if rule["type"] != "road" else subject,
                    "subject_code": subject if rule["type"] in ("team", "aid", "money") else None,
                    "place_text": place[0] if place else None,
                    "place_en": place[1] if place else None,
                    "district": place[2] if place else None,
                    "figure": figure,
                    "unit": unit,
                    "quote": sent[:600],
                    "language": rule["lang"],
                    "confidence": rule["conf"] + (0.1 if place else 0.0),
                })
        # Tunnel status: a project alias with a tunnel word in the sentence.
        if re.search(TUNNEL_WORDS, low):
            for key, aliases in project_aliases.items():
                if any(a.lower() in low for a in aliases if len(a) >= 4):
                    m = re.search(rf"(?P<n>{NUM_NE})\s*(?:जना|workers?|people|persons?|staff|कर्मचारी|मजदुर)", sent, re.I | re.U)
                    figure = _ne_compound_number(m.group("n")) if m else None
                    facts.append({
                        "fact_type": "tunnel", "subject": key, "subject_code": key,
                        "place_text": place[0] if place else None, "place_en": place[1] if place else None,
                        "district": place[2] if place else None,
                        "figure": figure, "unit": "people" if figure is not None else None,
                        "quote": sent[:600], "language": "ne" if re.search(r"[ऀ-ॿ]", sent) else "en",
                        "confidence": 0.5 + (0.1 if figure is not None else 0.0),
                    })
    return facts


# ------------------------------------------------------------------ LLM extractor (optional)

LLM_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "fact_type": {"type": "string", "enum": ["burial", "recovery", "forensic", "mortuary", "transfer", "team", "aid", "money", "tunnel", "road"]},
                    "subject": {"type": ["string", "null"]},
                    "country_code": {"type": ["string", "null"]},
                    "place": {"type": ["string", "null"]},
                    "district": {"type": ["string", "null"]},
                    "figure": {"type": ["number", "null"]},
                    "unit": {"type": ["string", "null"]},
                    "quote": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["fact_type", "quote", "confidence"],
            },
        }
    },
    "required": ["facts"],
}

LLM_PROMPT = (
    "You are an OSINT analyst reading Nepali and English press about the 2026 Bhote Koshi / Trishuli flood in Nepal. "
    "Extract ONLY facts that are stated in the text, each with the exact sentence it comes from (verbatim, original language). "
    "Types: burial (unidentified remains buried/managed at a place), recovery (bodies recovered from a river/place), "
    "forensic (bodies identified / DNA), mortuary (bodies brought to or held at a hospital), transfer (bodies lifted/flown between places), "
    "team (a foreign team with a size and country), aid (relief tonnage with sender country), money (a pledge with currency and sender), "
    "tunnel (status or figure for a named hydropower tunnel), road (a highway cut or reopened). "
    "Give place names as written, the district if stated, the figure as a number and its unit. "
    "Never infer a figure that is not in the text. Return JSON only."
)


async def llm_extract(story: dict[str, Any]) -> tuple[list[dict[str, Any]], Optional[str]]:
    try:
        from app.services.openai_runtime import get_openai_runtime
        rt = get_openai_runtime()
    except Exception:  # noqa: BLE001
        return [], None
    if not rt.available:
        return [], None
    text = " ".join(x for x in (story.get("title"), story.get("summary"), (story.get("content") or "")[:3500]) if x)
    try:
        out = await rt.json_completion(
            system_prompt=LLM_PROMPT,
            user_prompt=text,
            schema_name="flood_facts",
            schema=LLM_SCHEMA,
            max_completion_tokens=900,
            cache_scope="flood-facts",
            usage_bucket="flood-facts",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("llm extract failed: %s", e)
        return [], None
    model = getattr(rt.settings, "openai_chat_model", None) or getattr(rt.settings, "openai_model", None) or "llm"
    facts = []
    for f in (out or {}).get("facts", []) if isinstance(out, dict) else []:
        if not f.get("quote"):
            continue
        plc = places_in(f.get("place") or "") or places_in(f["quote"])
        facts.append({
            "fact_type": f["fact_type"], "subject": f.get("subject"), "subject_code": (f.get("country_code") or None),
            "place_text": f.get("place") or (plc[0][0] if plc else None), "place_en": plc[0][1] if plc else (f.get("place") or None),
            "district": f.get("district") or (plc[0][2] if plc else None),
            "figure": f.get("figure"), "unit": f.get("unit"), "quote": f["quote"][:600],
            "language": "ne" if re.search(r"[ऀ-ॿ]", f["quote"]) else "en",
            "confidence": max(0.0, min(1.0, float(f.get("confidence") or 0.5))),
        })
    return facts, f"llm:{model}"


# ------------------------------------------------------------------ run

STORY_TERMS = r"flood|rasuwa|trishuli|trisuli|bhote ?koshi|bhotekoshi|tunnel|बाढी|रसुवा|भोटेकोशी|त्रिशूली|त्रिशुली|सुरुङ|शव"


def _dedupe_key(story_url: str, fact: dict[str, Any]) -> str:
    h = hashlib.sha256(f"{story_url}|{fact['fact_type']}|{fact.get('subject_code') or fact.get('subject') or ''}|{fact.get('figure')}|{fact['quote'][:120]}".encode()).hexdigest()
    return h[:64]


async def _project_aliases() -> dict[str, list[str]]:
    try:
        from app.services import flood_hydropower_service as hydro
        t = hydro.load_truth()
        al = dict(t.get("aliases", {}))
        for p in t.get("projects", []):
            al.setdefault(p["key"], []).extend([p.get("name") or "", p.get("short") or ""])
        return al
    except Exception:  # noqa: BLE001
        return {}


async def run(db: AsyncSession, event_key: str = EVENT_KEY, days: int = 3, limit: int = 250) -> dict[str, Any]:
    """Read unread stories, extract, geocode, store. Returns counts."""
    q = sql_text(
        "SELECT s.id, s.title, s.summary, s.content, s.source_name, s.url, s.published_at, s.language "
        "FROM stories s LEFT JOIN flood_extraction_runs r ON r.story_id = s.id "
        "WHERE r.story_id IS NULL AND s.published_at > now() - make_interval(days => :days) "
        "AND (s.title ~* :terms OR s.summary ~* :terms) "
        "ORDER BY s.published_at DESC LIMIT :lim"
    )
    rows = (await db.execute(q, {"days": days, "terms": STORY_TERMS, "lim": limit})).all()
    aliases = await _project_aliases()
    stored = 0
    read = 0
    geocoded = 0
    for sid, title, summary, content, outlet, url, published_at, language in rows:
        story = {"id": sid, "title": title, "summary": summary, "content": content, "url": url}
        facts = rules_extract(story, aliases)
        extractor = "rules"
        llm_facts, llm_name = await llm_extract(story)
        if llm_name:
            facts.extend(llm_facts)
            extractor = f"rules+{llm_name}"
        n = 0
        seen_keys: set[str] = set()
        for f in facts:
            key = _dedupe_key(url or str(sid), f)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            exists = await db.execute(select(FloodFact.id).where(FloodFact.dedupe_key == key))
            if exists.first():
                continue
            # A reviewer's rejection teaches the extractor: the same reading (type,
            # place, figure) from any outlet's reprint is not stored again.
            rejected = await db.execute(select(FloodFact.id).where(
                FloodFact.status == "rejected", FloodFact.fact_type == f["fact_type"],
                FloodFact.figure == f.get("figure"), FloodFact.place_text == f.get("place_text")))
            if rejected.first():
                continue
            lat = lng = None
            conf = None
            if f.get("place_en"):
                g = await geocode(db, f["place_en"], f.get("district"))
                if g:
                    lat, lng = g["lat"], g["lng"]
                    conf = "gazetteer+nominatim"
                    geocoded += 1
            db.add(FloodFact(
                event_key=event_key, story_id=sid, story_url=url, outlet=outlet, published_at=published_at,
                fact_type=f["fact_type"], subject=f.get("subject"), subject_code=f.get("subject_code"),
                place_text=f.get("place_text"), district=f.get("district"), place_lat=lat, place_lng=lng,
                place_confidence=conf, figure=f.get("figure"), unit=f.get("unit"), quote=f["quote"],
                language=f.get("language"), extractor=extractor if not f.get("_llm") else extractor,
                confidence=float(f.get("confidence") or 0.5), status="auto", dedupe_key=key,
            ))
            n += 1
        db.add(FloodExtractionRun(story_id=sid, event_key=event_key, extractor=extractor, facts=n))
        await db.commit()
        stored += n
        read += 1
    return {"stories_read": read, "facts_stored": stored, "geocoded": geocoded}


async def facts(db: AsyncSession, event_key: str = EVENT_KEY, days: int = 14,
                fact_type: Optional[str] = None, status: str = "auto,verified") -> list[dict[str, Any]]:
    stmt = select(FloodFact).where(FloodFact.event_key == event_key,
                                   FloodFact.created_at > datetime.now(timezone.utc) - timedelta(days=days),
                                   FloodFact.status.in_([s.strip() for s in status.split(",") if s.strip()]))
    if fact_type:
        stmt = stmt.where(FloodFact.fact_type == fact_type)
    stmt = stmt.order_by(FloodFact.published_at.desc().nullslast(), FloodFact.created_at.desc())
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": str(r.id), "fact_type": r.fact_type, "subject": r.subject, "subject_code": r.subject_code,
            "place_text": r.place_text, "district": r.district, "lat": r.place_lat, "lng": r.place_lng,
            "place_confidence": r.place_confidence, "figure": r.figure, "unit": r.unit, "quote": r.quote,
            "language": r.language, "outlet": r.outlet, "url": r.story_url,
            "published_at": r.published_at.isoformat() if r.published_at else None,
            "extractor": r.extractor, "confidence": r.confidence, "status": r.status,
            "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None, "reviewer": r.reviewer,
            "review_note": r.review_note, "review_reason": r.review_reason,
        }
        for r in rows
    ]
