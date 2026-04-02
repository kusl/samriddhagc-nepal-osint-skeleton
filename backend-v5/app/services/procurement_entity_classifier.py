"""Heuristic classification for procurement procuring entities."""

from __future__ import annotations

import re
from typing import Iterable, Sequence

from sqlalchemy import or_


ENTITY_BUCKET_LABELS = {
    "ministry": "Ministry",
    "security_agency": "Security Agency",
    "constitutional_body": "Constitutional Body",
    "provincial_government": "Provincial Government",
    "local_government": "Local Government",
    "department_or_office": "Department / Office",
    "organization": "Organization",
    "other": "Other",
}


_BUCKET_PATTERNS: dict[str, tuple[str, ...]] = {
    "security_agency": (
        "nepal police",
        "police office",
        "police headquarters",
        "armed police",
        "armed police force",
        "apf",
        "nepal army",
        "army",
        "military",
        "national investigation department",
        "prison office",
        "prison management",
        "कारागार",
        "प्रहरी",
        "सशस्त्र",
        "नेपाली सेना",
        "रक्षा",
    ),
    "ministry": (
        "ministry of",
        "ministry ",
        " mantralaya",
        " मन्त्रालय",
    ),
    "constitutional_body": (
        "election commission",
        "public service commission",
        "commission for the investigation of abuse of authority",
        "office of the auditor general",
        "supreme court",
        "high court",
        "constitutional council",
        "निर्वाचन आयोग",
        "लोक सेवा आयोग",
        "अख्तियार",
        "महालेखा परीक्षक",
        "सर्वोच्च अदालत",
        "उच्च अदालत",
    ),
    "provincial_government": (
        "province government",
        "province ministry",
        "provincial ministry",
        "प्रदेश सरकार",
        "प्रदेश मन्त्रालय",
        "pradesh",
    ),
    "local_government": (
        "metropolitan city",
        "sub metropolitan city",
        "municipality",
        "rural municipality",
        "ward office",
        "gaunpalika",
        "nagarpalika",
        "महानगरपालिका",
        "उपमहानगरपालिका",
        "नगरपालिका",
        "गाउँपालिका",
        "वडा कार्यालय",
    ),
    "department_or_office": (
        "department of",
        "department ",
        "office of",
        "district administration office",
        "division office",
        "directorate",
        "project office",
        "implementation unit",
        "training center",
        "hospital",
        "camp office",
        "customs office",
        "revenue office",
        "court",
        "airport office",
        "development project",
        "कार्यलय",
        "कार्यालय",
        "विभाग",
        "निर्देशनालय",
        "आयोजना",
        "परियोजना",
        "अस्पताल",
    ),
    "organization": (
        "authority",
        "board",
        "corporation",
        "committee",
        "council",
        "academy",
        "university",
        "campus",
        "institute",
        "fund",
        "bank",
        "company limited",
        "ltd",
        "secretariat",
        "center",
        "centre",
        "mission",
        "trust",
        "foundation",
        "association",
        "federation",
        "society",
        "hospital development committee",
        "प्राधिकरण",
        "बोर्ड",
        "निगम",
        "समिति",
        "परिषद",
        "अकादमी",
        "विश्वविद्यालय",
        "कोष",
        "बैंक",
        "कम्पनी",
        "सचिवालय",
        "केन्द्र",
        "केंद्र",
        "प्रतिष्ठान",
        "संघ",
        "महासंघ",
        "समाज",
    ),
}


_SEARCH_ALIAS_GROUPS: dict[str, tuple[str, ...]] = {
    "nepal_police": (
        "nepal police",
        "police headquarters",
        "police office",
        "nepal prahari",
        "नेपाल प्रहरी",
    ),
    "armed_police": (
        "armed police force",
        "armed police",
        "apf",
        "sashastra prahari",
        "सशस्त्र प्रहरी",
    ),
    "nepal_army": (
        "nepal army",
        "army headquarters",
        "nepal sena",
        "nepali sena",
        "नेपाल सेना",
        "नेपाली सेना",
    ),
    "ministry_of_home_affairs": (
        "ministry of home affairs",
        "home ministry",
        "griha mantralaya",
        "गृह मन्त्रालय",
    ),
    "ministry_of_defence": (
        "ministry of defence",
        "ministry of defense",
        "defence ministry",
        "defense ministry",
        "raksha mantralaya",
        "रक्षा मन्त्रालय",
    ),
    "ministry_of_finance": (
        "ministry of finance",
        "finance ministry",
        "artha mantralaya",
        "अर्थ मन्त्रालय",
    ),
    "ministry_of_health": (
        "ministry of health",
        "ministry of health and population",
        "health ministry",
        "swasthya mantralaya",
        "स्वास्थ्य मन्त्रालय",
        "स्वास्थ्य तथा जनसंख्या मन्त्रालय",
    ),
}

_SEARCH_STOPWORDS = {
    "nepal",
    "nepali",
    "ministry",
    "department",
    "office",
    "authority",
    "board",
    "committee",
    "city",
    "municipality",
    "government",
    "public",
}


def _normalize_entity_name(value: str | None) -> str:
    if not value:
        return ""
    normalized = re.sub(r"\s+", " ", value).strip().lower()
    return normalized


def _matches_any(normalized_name: str, patterns: Iterable[str]) -> bool:
    return any(pattern in normalized_name for pattern in patterns)


def expand_procurement_search_terms(value: str | None) -> list[str]:
    """Expand a user search into bilingual / alias-aware search terms."""
    normalized = _normalize_entity_name(value)
    if not normalized:
        return []

    expanded: list[str] = [normalized]
    alias_matched = False

    for aliases in _SEARCH_ALIAS_GROUPS.values():
        if _matches_any(normalized, aliases):
            alias_matched = True
            expanded.extend(aliases)

    # Keep useful fragments only for generic search text, not known alias groups.
    if not alias_matched and " " in normalized:
        expanded.extend(
            token
            for token in normalized.split(" ")
            if len(token) >= 4 and token not in _SEARCH_STOPWORDS
        )

    # Security / ministry bucket hints for common short forms.
    if normalized in {"army", "sena", "police", "prahari", "apf"}:
        for aliases in _SEARCH_ALIAS_GROUPS.values():
            if normalized in aliases:
                expanded.extend(aliases)

    deduped: list[str] = []
    seen: set[str] = set()
    for term in expanded:
        candidate = _normalize_entity_name(term)
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        deduped.append(candidate)
    return deduped


def build_smart_text_condition(columns: Sequence, value: str | None):
    """Build alias-aware ilike matching across one or more columns."""
    terms = expand_procurement_search_terms(value)
    if not terms:
        return None
    return or_(
        *[
            column.ilike(f"%{term}%")
            for column in columns
            for term in terms
        ]
    )


def classify_procurement_entity(entity_name: str | None) -> dict[str, str]:
    """Classify one procuring entity into a UI-friendly bucket."""
    normalized = _normalize_entity_name(entity_name)

    for bucket in (
        "security_agency",
        "ministry",
        "constitutional_body",
        "provincial_government",
        "local_government",
        "department_or_office",
        "organization",
    ):
        if _matches_any(normalized, _BUCKET_PATTERNS[bucket]):
            return {
                "entity_bucket": bucket,
                "entity_bucket_label": ENTITY_BUCKET_LABELS[bucket],
            }

    return {
        "entity_bucket": "other",
        "entity_bucket_label": ENTITY_BUCKET_LABELS["other"],
    }


def build_entity_bucket_condition(column, entity_bucket: str):
    """Build a SQLAlchemy condition for an entity bucket."""
    bucket = (entity_bucket or "").strip().lower()
    if not bucket:
        return None

    if bucket not in ENTITY_BUCKET_LABELS:
        return None

    if bucket == "other":
        exclusion_conditions = []
        for patterns in _BUCKET_PATTERNS.values():
            exclusion_conditions.extend(column.ilike(f"%{pattern}%") for pattern in patterns)
        return ~or_(*exclusion_conditions) if exclusion_conditions else None

    patterns = _BUCKET_PATTERNS.get(bucket, ())
    if not patterns:
        return None
    return or_(*(column.ilike(f"%{pattern}%") for pattern in patterns))
