"""Cabinet 100-day action tracker service."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import logging
from pathlib import Path
import re
from typing import Any, Optional
from uuid import UUID

from PyPDF2 import PdfReader
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models.announcement import GovtAnnouncement
from app.models.cabinet_action import (
    CabinetActionEvidence,
    CabinetActionItem,
    CabinetActionMilestone,
    CabinetActionProgram,
    CabinetActionPromiseLink,
    CabinetActionReview,
)
from app.models.promise import ManifestoPromise
from app.models.story import Story
from app.services.editorial_control_service import EditorialControlService
from app.services.openai_runtime import OpenAIUsageLimitExceeded, get_openai_runtime
from app.utils.nepali_date import ad_to_bs, bs_to_ad

logger = logging.getLogger(__name__)

DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
ITEM_START_RE = re.compile(r"^\s*(\d{1,3})\.\s*(.+)?$")
SUBITEM_RE = re.compile(r"(?:^|\s)([कखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसह])\)\s*")
SPACE_RE = re.compile(r"\s+")
DEADLINE_DAY_RE = re.compile(r"(\d+)\s*(?:र्दन|दिन)(?:\s*(?:मभि|भित्र|मा|भित्रै))?")
DEADLINE_HOUR_RE = re.compile(r"(\d+)\s*(?:िण्टा|घन्टा)(?:\s*(?:मभि|भित्र|मा|भित्रै))?")
MONTH_RE = re.compile(r"(एक|दुई|तीन|चार|पाँच|छ|सात|आठ|नौ|दश|11|12|\d+)\s*(?:मवहना|महिना|महीना)")
WEEK_RE = re.compile(r"(एक|दुई|तीन|चार|पाँच|छ|सात|आठ|नौ|दश|1|2|3|4|5|6|7)\s*(?:हप्ता|हप्ता)")

TRACKABLE_STATUSES = {
    "not_started",
    "announced",
    "implementation_started",
    "partially_completed",
    "completed_on_time",
    "completed_late",
    "overdue",
    "cannot_verify",
}
COMPLETED_STATUSES = {"completed_on_time", "completed_late"}

TRUSTED_NEWS_TOKENS = (
    "ekantipur", "kathmandu post", "kathmandupost", "the kathmandu post",
    "republica", "my republica", "himalayan", "onlinekhabar", "setopati",
    "nagarik", "ratopati", "khabarhub", "kantipur tv", "kantipurtv",
    "risingnepal", "the rising nepal",
)

SECTION_RANGES: tuple[tuple[int, int, str, str, str], ...] = (
    (1, 8, "shared-commitments", "साझा प्रमिबद्धिा, समरवय र जनववश्वास", "Shared Commitments, Coordination and Public Trust"),
    (9, 19, "administrative-restructuring", "प्रशासमनक सुधार, पुनसंरचना र ममिव्यवयिा", "Administrative Reform, Restructuring and Fiscal Restraint"),
    (20, 27, "public-service-grievance", "सावयजमनक सेवा प्रवाह र गुनासो व्यवस्थापन", "Public Service Delivery and Grievance Management"),
    (28, 42, "digital-governance", "मडन्त्जटल शासन र डेटा गभर्नेन्स िथा सञ्चार", "Digital Governance, Data Governance and Communications"),
    (43, 47, "good-governance-anticorruption", "सुशासन, पारदर्शिता र भ्रष्टाचार नियन्त्रण", "Good Governance, Transparency and Anti-Corruption"),
    (48, 52, "procurement-project-reform", "सावयजमनक खररद र पररयोजना व्यवस्थापन सुधार", "Public Procurement and Project Management Reform"),
    (53, 73, "investment-private-sector-tourism", "लगानी, उद्योर्, मनजी क्षेि प्रवर्द्धन िथा पययटन", "Investment, Industry, Private Sector Promotion and Tourism"),
    (74, 77, "energy-water", "ऊजाय िथा जलस्रोि", "Energy and Water Resources"),
    (78, 84, "revenue-reform", "राजस्व सुधार", "Revenue Reform"),
    (85, 89, "health-education-human-development", "स्वास््य, न्त्शक्षा र मानव ववकास", "Health, Education and Human Development"),
    (90, 92, "agriculture-land-infrastructure", "कृवष, भूमम, पूवायधार र आधारभूि सेवा", "Agriculture, Land, Infrastructure and Basic Services"),
    (93, 100, "strategic-social-security", "अरय रणनीमिक िथा सामान्त्जक सुरक्षा सम्बरधी मनर्ययहरू", "Other Strategic and Social Security Decisions"),
)


@dataclass
class ParsedMilestone:
    milestone_order: int
    source_text_ne: str
    deadline_text_ne: Optional[str]
    deadline_kind: Optional[str]
    deadline_value: Optional[float]
    due_date_ad: Optional[date]
    due_date_bs: Optional[str]


@dataclass
class ParsedItem:
    item_number: int
    source_text_ne: str
    source_pdf_page: int
    section_key: str
    section_title_ne: str
    section_title_en: str
    deadline_text_ne: Optional[str]
    deadline_kind: Optional[str]
    deadline_value: Optional[float]
    due_date_ad: Optional[date]
    due_date_bs: Optional[str]
    milestones: list[ParsedMilestone] = field(default_factory=list)


@dataclass
class ActionSource:
    kind: str
    source_id: str
    title: str
    summary: str
    source_name: str
    source_url: str
    published_at: datetime
    is_official: bool
    source_story_id: Optional[str] = None
    source_announcement_id: Optional[str] = None


class CabinetActionService:
    """PDF seeding, public feed, and automation for cabinet actions."""

    PROGRAM_KEY = "balen-cabinet-100-day-2082-chaitra-13"
    PROGRAM_WINDOW_DAYS = 100
    PROGRAM_TITLE_NE = "नेपाल सरकार, मन्त्रिपरिषद्को मिति २०८२ चैत्र १३ को बैठकबाट स्वीकृत शासकीय सुधार सम्बन्धी एक सय कार्यसूचीहरू"
    PROGRAM_TITLE_EN = "Balen Government 100-Day Cabinet Action Programme"
    APPROVAL_DATE_BS = "2082-12-13"

    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()
        self.openai = get_openai_runtime()
        self.control_service = EditorialControlService(db)

    @staticmethod
    def _clean_text(value: str) -> str:
        value = (value or "").replace("\u00a0", " ")
        return SPACE_RE.sub(" ", value).strip()

    @classmethod
    def _normalize_for_match(cls, value: str) -> str:
        value = (value or "").translate(DEVANAGARI_DIGITS).lower()
        value = re.sub(r"[^0-9a-z\u0900-\u097f]+", " ", value)
        return cls._clean_text(value)

    @classmethod
    def _tokenize(cls, value: str) -> set[str]:
        return {
            token
            for token in cls._normalize_for_match(value).split()
            if len(token) > 1 and token not in {"the", "and", "for", "with", "from", "this", "that", "government"}
        }

    @staticmethod
    def _stable_hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @classmethod
    def _normalize_source_url(cls, value: Optional[str]) -> str:
        return cls._clean_text((value or "").strip().rstrip("/")).lower()

    @classmethod
    def _evidence_identity_key(
        cls,
        *,
        source_kind: Optional[str],
        source_title: Optional[str],
        source_name: Optional[str],
        source_url: Optional[str],
        source_story_id: Optional[str],
        source_announcement_id: Optional[str],
        milestone_id: Optional[UUID] = None,
    ) -> tuple[str, ...]:
        milestone_key = str(milestone_id) if milestone_id else "item"
        if source_announcement_id:
            return ("announcement", source_announcement_id, milestone_key)
        if source_story_id:
            return ("story", source_story_id, milestone_key)
        normalized_url = cls._normalize_source_url(source_url)
        if normalized_url:
            return ("url", normalized_url, milestone_key)
        return (
            "text",
            cls._normalize_for_match(source_kind or ""),
            cls._normalize_for_match(source_name or ""),
            cls._normalize_for_match(source_title or ""),
            milestone_key,
        )

    @classmethod
    def _evidence_identity_for_entry(cls, entry: CabinetActionEvidence) -> tuple[str, ...]:
        return cls._evidence_identity_key(
            source_kind=entry.source_kind,
            source_title=entry.source_title,
            source_name=entry.source_name,
            source_url=entry.source_url,
            source_story_id=entry.source_story_id,
            source_announcement_id=entry.source_announcement_id,
            milestone_id=entry.milestone_id,
        )

    @classmethod
    def _evidence_sort_score(cls, entry: CabinetActionEvidence) -> tuple[Any, ...]:
        note = cls._clean_text(entry.evidence_note_en or "")
        published_ts = entry.published_at.timestamp() if entry.published_at else 0.0
        created_ts = entry.created_at.timestamp() if entry.created_at else 0.0
        return (
            1 if entry.is_official else 0,
            1 if entry.is_applied else 0,
            1 if entry.is_public else 0,
            1 if note else 0,
            len(note),
            float(entry.confidence or 0.0),
            published_ts,
            created_ts,
        )

    @classmethod
    def _dedupe_evidence_entries(cls, entries: list[CabinetActionEvidence]) -> list[CabinetActionEvidence]:
        best_by_key: dict[tuple[str, ...], CabinetActionEvidence] = {}
        for entry in sorted(entries, key=cls._evidence_sort_score, reverse=True):
            key = cls._evidence_identity_for_entry(entry)
            if key not in best_by_key:
                best_by_key[key] = entry
        return sorted(
            best_by_key.values(),
            key=lambda entry: (
                1 if entry.is_official else 0,
                entry.published_at or datetime.min.replace(tzinfo=timezone.utc),
                entry.created_at or datetime.min.replace(tzinfo=timezone.utc),
            ),
            reverse=True,
        )

    @classmethod
    def _section_for_item(cls, item_number: int) -> tuple[str, str, str]:
        for start, end, key, title_ne, title_en in SECTION_RANGES:
            if start <= item_number <= end:
                return key, title_ne, title_en
        return "uncategorized", "", ""

    @staticmethod
    def _number_from_word(value: str) -> Optional[int]:
        mapping = {
            "एक": 1,
            "दुई": 2,
            "तीन": 3,
            "चार": 4,
            "पाँच": 5,
            "छ": 6,
            "सात": 7,
            "आठ": 8,
            "नौ": 9,
            "दश": 10,
        }
        value = value.strip()
        if value.isdigit():
            return int(value)
        return mapping.get(value)

    def _parse_deadline(self, text_ne: str) -> tuple[Optional[str], Optional[str], Optional[float], Optional[date], Optional[str]]:
        normalized = self._normalize_for_match(text_ne)
        approval_ad = bs_to_ad(self.APPROVAL_DATE_BS)
        approval_date = approval_ad.date() if approval_ad else None

        for match in DEADLINE_HOUR_RE.finditer(normalized):
            value = int(match.group(1))
            due_ad = approval_date + timedelta(days=value / 24) if approval_date else None
            return match.group(0), "hours", float(value), due_ad, ad_to_bs(datetime.combine(due_ad, datetime.min.time())) if due_ad else None

        for match in DEADLINE_DAY_RE.finditer(normalized):
            value = int(match.group(1))
            due_ad = approval_date + timedelta(days=value) if approval_date else None
            return match.group(0), "days", float(value), due_ad, ad_to_bs(datetime.combine(due_ad, datetime.min.time())) if due_ad else None

        for match in WEEK_RE.finditer(normalized):
            count = self._number_from_word(match.group(1)) or 1
            due_ad = approval_date + timedelta(days=count * 7) if approval_date else None
            return match.group(0), "weeks", float(count), due_ad, ad_to_bs(datetime.combine(due_ad, datetime.min.time())) if due_ad else None

        for match in MONTH_RE.finditer(normalized):
            count = self._number_from_word(match.group(1)) or 1
            due_ad = approval_date + timedelta(days=count * 30) if approval_date else None
            return match.group(0), "months", float(count), due_ad, ad_to_bs(datetime.combine(due_ad, datetime.min.time())) if due_ad else None

        if "ित्काल" in normalized or "तत्काल" in normalized:
            due_ad = approval_date + timedelta(days=self.PROGRAM_WINDOW_DAYS) if approval_date else None
            return "तत्काल", "program_window", float(self.PROGRAM_WINDOW_DAYS), due_ad, ad_to_bs(datetime.combine(due_ad, datetime.min.time())) if due_ad else None

        due_ad = approval_date + timedelta(days=self.PROGRAM_WINDOW_DAYS) if approval_date else None
        return None, "program_window", float(self.PROGRAM_WINDOW_DAYS), due_ad, ad_to_bs(datetime.combine(due_ad, datetime.min.time())) if due_ad else None

    def _split_milestones(self, text_ne: str) -> list[str]:
        matches = list(SUBITEM_RE.finditer(text_ne))
        if len(matches) < 2:
            return []
        parts: list[str] = []
        for index, match in enumerate(matches):
            start = match.start(1)
            end = matches[index + 1].start(1) if index + 1 < len(matches) else len(text_ne)
            snippet = self._clean_text(text_ne[start:end])
            if snippet:
                parts.append(snippet)
        return parts

    def _extract_pdf_items(self, pdf_path: str) -> list[ParsedItem]:
        reader = PdfReader(pdf_path)
        items: list[ParsedItem] = []
        current_number: Optional[int] = None
        current_lines: list[str] = []
        current_page = 1

        for page_index, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text() or ""
            for raw_line in page_text.splitlines():
                line = self._clean_text(raw_line)
                if not line:
                    continue
                if line == str(page_index):
                    continue
                normalized = line.translate(DEVANAGARI_DIGITS)
                match = ITEM_START_RE.match(normalized)
                if match:
                    item_number = int(match.group(1))
                    if 1 <= item_number <= 100:
                        if current_number is not None:
                            items.append(self._build_parsed_item(current_number, current_lines, current_page))
                        current_number = item_number
                        current_page = page_index
                        current_lines = [self._clean_text(match.group(2) or "")]
                        continue
                if current_number is None:
                    continue
                if any(anchor in line for anchor in (
                    "साझा प्रमिबद्धिा",
                    "प्रशासमनक सुधार",
                    "सावयजमनक सेवा प्रवाह",
                    "मडन्त्जटल शासन",
                    "सुशासन",
                    "सावयजमनक खररद",
                    "लर्ानी",
                    "ऊजाय िथा जलस्रोि",
                    "राजस्व सुधार",
                    "स्वास््य",
                    "कृवष",
                    "अरय रणनीमिक",
                )):
                    continue
                current_lines.append(line)

        if current_number is not None:
            items.append(self._build_parsed_item(current_number, current_lines, current_page))

        if len(items) != 100:
            raise ValueError(f"Expected 100 cabinet action items, parsed {len(items)}")
        return items

    def _build_parsed_item(self, item_number: int, lines: list[str], page: int) -> ParsedItem:
        source_text_ne = self._clean_text(" ".join(part for part in lines if part))
        section_key, section_title_ne, section_title_en = self._section_for_item(item_number)
        deadline_text_ne, deadline_kind, deadline_value, due_date_ad, due_date_bs = self._parse_deadline(source_text_ne)
        milestone_texts = self._split_milestones(source_text_ne)
        milestones: list[ParsedMilestone] = []
        if milestone_texts:
            for milestone_order, milestone_text in enumerate(milestone_texts, start=1):
                m_deadline_text, m_deadline_kind, m_deadline_value, m_due_date_ad, m_due_date_bs = self._parse_deadline(milestone_text)
                milestones.append(
                    ParsedMilestone(
                        milestone_order=milestone_order,
                        source_text_ne=milestone_text,
                        deadline_text_ne=m_deadline_text,
                        deadline_kind=m_deadline_kind,
                        deadline_value=m_deadline_value,
                        due_date_ad=m_due_date_ad,
                        due_date_bs=m_due_date_bs,
                    )
                )
        return ParsedItem(
            item_number=item_number,
            source_text_ne=source_text_ne,
            source_pdf_page=page,
            section_key=section_key,
            section_title_ne=section_title_ne,
            section_title_en=section_title_en,
            deadline_text_ne=deadline_text_ne,
            deadline_kind=deadline_kind,
            deadline_value=deadline_value,
            due_date_ad=due_date_ad,
            due_date_bs=due_date_bs,
            milestones=milestones,
        )

    async def _translate_seed_item(self, parsed: ParsedItem) -> dict[str, Any]:
        if not self.openai.available:
            fallback = {
                "title_en": f"Cabinet Action {parsed.item_number}",
                "summary_en": "Source-grounded Nepali action item seeded without OpenAI translation.",
                "lead_institution": None,
                "supporting_institutions": [],
                "action_type": "Cabinet Action",
                "trackability_class": "milestone_based" if parsed.milestones else "directly_trackable",
                "milestones": [
                    {
                        "milestone_order": milestone.milestone_order,
                        "title_en": f"Milestone {milestone.milestone_order}",
                        "summary_en": "Source-grounded milestone seeded without OpenAI translation.",
                    }
                    for milestone in parsed.milestones
                ],
            }
            return self._normalize_seed_translation(parsed, fallback)

        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "title_en": {"type": "string"},
                "summary_en": {"type": "string"},
                "lead_institution": {"type": "string"},
                "supporting_institutions": {"type": "array", "items": {"type": "string"}},
                "action_type": {"type": "string"},
                "trackability_class": {
                    "type": "string",
                    "enum": ["directly_trackable", "milestone_based", "declaratory_contextual"],
                },
                "milestones": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "milestone_order": {"type": "integer"},
                            "title_en": {"type": "string"},
                            "summary_en": {"type": "string"},
                        },
                        "required": ["milestone_order", "title_en", "summary_en"],
                    },
                },
            },
            "required": [
                "title_en",
                "summary_en",
                "lead_institution",
                "supporting_institutions",
                "action_type",
                "trackability_class",
                "milestones",
            ],
        }
        prompt_lines = [
            "You are structuring one item from the Balen government 100-day cabinet action programme.",
            "Use only the Nepali source text below. Do not invent obligations.",
            "Return concise English only for all fields.",
            f"Item number: {parsed.item_number}",
            f"Section: {parsed.section_title_en}",
            f"Source text (Nepali): {parsed.source_text_ne}",
        ]
        if parsed.deadline_text_ne:
            prompt_lines.append(f"Deadline phrase: {parsed.deadline_text_ne}")
        if parsed.milestones:
            prompt_lines.append("Milestones extracted from the source text:")
            for milestone in parsed.milestones:
                prompt_lines.append(
                    f"- Order {milestone.milestone_order}: {milestone.source_text_ne}"
                )

        translated = await self.openai.json_completion(
            system_prompt=(
                "You convert Nepal government source material into structured English tracking records. "
                "Be faithful to the text, concise, and conservative."
            ),
            user_prompt="\n".join(prompt_lines),
            schema_name="cabinet_action_seed",
            schema=schema,
            model=self.settings.openai_clustering_model,
            max_completion_tokens=420,
            prompt_char_limit=5500,
            temperature=0.0,
            cache_scope=f"cabinet-action-seed:{parsed.item_number}:{self._stable_hash(parsed.source_text_ne)}",
            usage_bucket="cabinet_action",
        )
        return self._normalize_seed_translation(parsed, translated)

    @staticmethod
    def _normalize_seed_translation(parsed: ParsedItem, translated: dict[str, Any]) -> dict[str, Any]:
        text_ne = parsed.source_text_ne or ""
        title = str(translated.get("title_en") or "")
        summary = str(translated.get("summary_en") or "")

        if "जेन-जी" in text_ne or "जेन जी" in text_ne:
            title = re.sub(r"\bJan-G\b", "Gen Z", title, flags=re.IGNORECASE)
            title = re.sub(r"\bJan Andolan\b", "Gen Z movement", title, flags=re.IGNORECASE)
            summary = re.sub(r"\bJan-G\b", "Gen Z", summary, flags=re.IGNORECASE)
            summary = re.sub(r"\bJan Andolan\b", "Gen Z movement", summary, flags=re.IGNORECASE)
            translated["title_en"] = title
            translated["summary_en"] = summary

        return translated

    @staticmethod
    def _status_for_seed(trackability_class: str) -> str:
        return "announced"

    @staticmethod
    def _resolve_public_trackability(trackability_class: Optional[str]) -> str:
        return trackability_class or "directly_trackable"

    @classmethod
    def _resolve_public_status(
        cls,
        *,
        trackability_class: Optional[str],
        status: Optional[str],
        due_date_ad: Optional[date],
    ) -> str:
        return status or "announced"

    @staticmethod
    def _effective_audit_fields(item: CabinetActionItem) -> dict[str, Any]:
        review = item.review
        use_review = bool(review and review.workflow_status not in {"rejected", "superseded"})
        return {
            "trackability_class": review.final_trackability_class if use_review and review.final_trackability_class else item.trackability_class,
            "status": review.final_status if use_review and review.final_status else item.status,
        }

    async def seed_from_pdf(
        self,
        *,
        pdf_path: str,
        program_key: str | None = None,
        auto_approve: bool = True,
    ) -> dict[str, Any]:
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        approval_dt = bs_to_ad(self.APPROVAL_DATE_BS)
        if approval_dt is None:
            raise RuntimeError("Unable to convert cabinet approval date from BS to AD")

        parsed_items = self._extract_pdf_items(str(path))
        source_hash = self._stable_hash(path.read_bytes().hex())

        program = (
            await self.db.execute(
                select(CabinetActionProgram).where(
                    CabinetActionProgram.program_key == (program_key or self.PROGRAM_KEY)
                )
            )
        ).scalar_one_or_none()
        if program is None:
            program = CabinetActionProgram(
                program_key=program_key or self.PROGRAM_KEY,
                title_ne=self.PROGRAM_TITLE_NE,
                title_en=self.PROGRAM_TITLE_EN,
                source_pdf_name=path.name,
                source_pdf_path=str(path),
                source_pdf_hash=source_hash,
                approval_date_bs=self.APPROVAL_DATE_BS,
                approval_date_ad=approval_dt.date(),
            )
            self.db.add(program)
            await self.db.flush()
        else:
            program.source_pdf_name = path.name
            program.source_pdf_path = str(path)
            program.source_pdf_hash = source_hash

        existing_rows = (
            await self.db.execute(
                select(CabinetActionItem)
                .options(
                    selectinload(CabinetActionItem.milestones),
                    selectinload(CabinetActionItem.review),
                )
                .where(CabinetActionItem.program_id == program.id)
            )
        ).scalars().all()
        existing_by_number = {row.item_number: row for row in existing_rows}

        created = 0
        updated = 0
        for parsed in parsed_items:
            translated = await self._translate_seed_item(parsed)
            item = existing_by_number.get(parsed.item_number)
            is_new_item = item is None
            if item is None:
                item = CabinetActionItem(program_id=program.id, item_number=parsed.item_number)
                self.db.add(item)
                created += 1
            else:
                updated += 1

            trackability_class = translated.get("trackability_class") or ("milestone_based" if parsed.milestones else "directly_trackable")
            item.section_key = parsed.section_key
            item.section_title_ne = parsed.section_title_ne
            item.section_title_en = parsed.section_title_en
            item.source_text_ne = parsed.source_text_ne
            item.title_en = translated.get("title_en") or f"Cabinet Action {parsed.item_number}"
            item.summary_en = translated.get("summary_en") or item.title_en
            item.lead_institution = translated.get("lead_institution") or None
            item.supporting_institutions = translated.get("supporting_institutions") or []
            item.action_type = translated.get("action_type") or "Cabinet Action"
            item.trackability_class = trackability_class
            item.deadline_text_ne = parsed.deadline_text_ne
            item.deadline_kind = parsed.deadline_kind
            item.deadline_value = parsed.deadline_value
            item.due_date_bs = parsed.due_date_bs
            item.due_date_ad = parsed.due_date_ad
            item.status = self._status_for_seed(trackability_class)
            item.evidence_strength = "source_document"
            item.is_public = True
            item.last_checked_at = datetime.now(timezone.utc)
            item.source_pdf_page = parsed.source_pdf_page
            item.raw_seed_payload = {
                "source_pdf_name": path.name,
                "parsed_deadline_text": parsed.deadline_text_ne,
                "parsed_deadline_kind": parsed.deadline_kind,
                "parsed_deadline_value": parsed.deadline_value,
                "translated": translated,
            }

            if item.id is None:
                await self.db.flush()

            translated_milestones = {
                milestone.get("milestone_order"): milestone
                for milestone in translated.get("milestones", [])
                if isinstance(milestone, dict)
            }
            existing_milestones = (
                {}
                if is_new_item
                else {milestone.milestone_order: milestone for milestone in item.milestones}
            )
            milestone_override_payloads: list[dict[str, Any]] = []
            for parsed_milestone in parsed.milestones:
                milestone = existing_milestones.get(parsed_milestone.milestone_order)
                if milestone is None:
                    milestone = CabinetActionMilestone(item_id=item.id, milestone_order=parsed_milestone.milestone_order)
                    self.db.add(milestone)
                translated_milestone = translated_milestones.get(parsed_milestone.milestone_order, {})
                milestone.source_text_ne = parsed_milestone.source_text_ne
                milestone.title_en = translated_milestone.get("title_en") or f"Milestone {parsed_milestone.milestone_order}"
                milestone.summary_en = translated_milestone.get("summary_en") or milestone.title_en
                milestone.deadline_text_ne = parsed_milestone.deadline_text_ne
                milestone.deadline_kind = parsed_milestone.deadline_kind
                milestone.deadline_value = parsed_milestone.deadline_value
                milestone.due_date_bs = parsed_milestone.due_date_bs
                milestone.due_date_ad = parsed_milestone.due_date_ad
                milestone.status = self._status_for_seed(trackability_class)
                milestone.evidence_strength = "source_document"
                milestone.is_public = True
                milestone.last_checked_at = datetime.now(timezone.utc)
                milestone.raw_seed_payload = translated_milestone
                milestone_override_payloads.append(
                    {
                        "milestone_order": milestone.milestone_order,
                        "title_en": milestone.title_en,
                        "summary_en": milestone.summary_en,
                        "status": milestone.status,
                    }
                )

            review = None if is_new_item else item.review
            if review is None:
                review = CabinetActionReview(cabinet_action_item_id=item.id)
                self.db.add(review)
                item.review = review
            review.workflow_status = "approved" if auto_approve else "draft"
            review.final_section_key = parsed.section_key
            review.final_section_title_en = parsed.section_title_en
            review.final_title_en = item.title_en
            review.final_summary_en = item.summary_en
            review.final_lead_institution = item.lead_institution
            review.final_supporting_institutions = item.supporting_institutions
            review.final_action_type = item.action_type
            review.final_trackability_class = item.trackability_class
            review.final_status = item.status
            review.final_evidence_note = "Seeded from the canonical cabinet PDF approved on 2082 Chaitra 13."
            review.final_confidence = 1.0 if auto_approve else None
            review.final_is_public = True
            review.milestone_overrides = sorted(
                milestone_override_payloads,
                key=lambda entry: entry["milestone_order"],
            )
            if auto_approve:
                review.approved_at = datetime.now(timezone.utc)
                review.reviewer_note = "Auto-approved from canonical cabinet source document seed."

        await self.db.commit()
        return {
            "program_id": str(program.id),
            "program_key": program.program_key,
            "created": created,
            "updated": updated,
            "total_items": len(parsed_items),
        }

    @classmethod
    def _is_trusted_story(cls, story: Story) -> bool:
        blob = " ".join(
            part for part in [story.source_id or "", story.source_name or "", story.url or ""]
            if part
        ).lower()
        return any(token in blob for token in TRUSTED_NEWS_TOKENS)

    async def _list_recent_sources(self, since: datetime) -> list[ActionSource]:
        sources: list[ActionSource] = []
        official_rows = (
            await self.db.execute(
                select(GovtAnnouncement)
                .where(or_(GovtAnnouncement.published_at >= since, GovtAnnouncement.created_at >= since))
                .order_by(GovtAnnouncement.published_at.desc().nullslast(), GovtAnnouncement.created_at.desc())
                .limit(120)
            )
        ).scalars().all()
        for row in official_rows:
            sources.append(
                ActionSource(
                    kind="announcement",
                    source_id=str(row.id),
                    title=row.title or "",
                    summary=self._clean_text((row.content or "")[:500]),
                    source_name=row.source_name or "",
                    source_url=row.url or "",
                    published_at=row.published_at or row.created_at or datetime.now(timezone.utc),
                    is_official=True,
                    source_announcement_id=str(row.id),
                )
            )

        story_rows = (
            await self.db.execute(
                select(Story)
                .where(
                    or_(Story.published_at >= since, Story.created_at >= since),
                    or_(Story.nepal_relevance.is_(None), Story.nepal_relevance != "INTERNATIONAL"),
                )
                .order_by(Story.published_at.desc().nullslast(), Story.created_at.desc())
                .limit(220)
            )
        ).scalars().all()
        for row in story_rows:
            if not self._is_trusted_story(row):
                continue
            sources.append(
                ActionSource(
                    kind="story",
                    source_id=str(row.id),
                    title=row.title or "",
                    summary=self._clean_text((row.summary or "")[:400]),
                    source_name=row.source_name or row.source_id or "",
                    source_url=row.url or "",
                    published_at=row.published_at or row.created_at or datetime.now(timezone.utc),
                    is_official=False,
                    source_story_id=str(row.id),
                )
            )
        return sources

    def _shortlist_items(self, source: ActionSource, items: list[CabinetActionItem], limit: int = 5) -> list[CabinetActionItem]:
        source_tokens = self._tokenize(f"{source.title} {source.summary}")
        scored: list[tuple[int, CabinetActionItem]] = []
        for item in items:
            blob = " ".join(
                filter(
                    None,
                    [
                        item.title_en,
                        item.summary_en,
                        item.source_text_ne,
                        item.lead_institution,
                        " ".join(item.supporting_institutions or []),
                    ],
                )
            )
            overlap = len(source_tokens & self._tokenize(blob))
            if overlap <= 0:
                continue
            scored.append((overlap, item))
        scored.sort(key=lambda pair: (pair[0], -(pair[1].item_number or 0)), reverse=True)
        return [item for _, item in scored[:limit]]

    async def _extract_evidence_mapping(self, source: ActionSource, candidates: list[CabinetActionItem]) -> dict[str, Any]:
        if not self.openai.available:
            return {
                "matched_item_numbers": [],
                "matched_milestones": [],
                "status_signal": "no_match",
                "evidence_note_en": "",
                "confidence": 0.0,
                "should_apply": False,
                "why_not_applied": "OpenAI unavailable",
            }

        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "matched_item_numbers": {"type": "array", "items": {"type": "integer"}},
                "matched_milestones": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "item_number": {"type": "integer"},
                            "milestone_order": {"type": "integer"},
                        },
                        "required": ["item_number", "milestone_order"],
                    },
                },
                "status_signal": {
                    "type": "string",
                    "enum": [
                        "announcement",
                        "implementation_started",
                        "partial",
                        "completed",
                        "cannot_verify",
                        "no_match",
                    ],
                },
                "evidence_note_en": {"type": "string"},
                "confidence": {"type": "number"},
                "should_apply": {"type": "boolean"},
                "why_not_applied": {"type": "string"},
            },
            "required": [
                "matched_item_numbers",
                "matched_milestones",
                "status_signal",
                "evidence_note_en",
                "confidence",
                "should_apply",
                "why_not_applied",
            ],
        }
        lines = [
            "Map this evidence to the Balen government 100-day cabinet action tracker.",
            "Use only the shortlist below. Do not invent new cabinet obligations.",
            "If the source is only commentary, reaction, or unrelated reporting, return no_match.",
            f"Source title: {source.title}",
            f"Source summary: {source.summary}",
            f"Source name: {source.source_name}",
            f"Official source: {'yes' if source.is_official else 'no'}",
            "Candidate cabinet action items:",
        ]
        for item in candidates:
            lines.append(
                f"- Item {item.item_number}: {item.title_en} | Lead: {item.lead_institution or 'Unknown'} | Summary: {item.summary_en}"
            )
            for milestone in sorted(item.milestones, key=lambda entry: entry.milestone_order):
                lines.append(f"  - Milestone {milestone.milestone_order}: {milestone.title_en} | {milestone.summary_en}")

        return await self.openai.json_completion(
            system_prompt=(
                "You map source evidence to an existing Nepal cabinet action tracker. "
                "Return strict JSON only. Be conservative and do not over-match."
            ),
            user_prompt="\n".join(lines),
            schema_name="cabinet_action_evidence_mapping",
            schema=schema,
            model=self.settings.openai_clustering_model,
            max_completion_tokens=260,
            prompt_char_limit=6000,
            temperature=0.0,
            cache_scope=f"cabinet-action-evidence:{source.kind}:{source.source_id}:{self._stable_hash(source.title + source.summary)}",
            usage_bucket="cabinet_action",
        )

    @staticmethod
    def _map_signal_to_status(signal: str, *, due_date: Optional[date], event_date: Optional[datetime]) -> str:
        if signal == "announcement":
            return "announced"
        if signal == "implementation_started":
            return "implementation_started"
        if signal == "partial":
            return "partially_completed"
        if signal == "cannot_verify":
            return "cannot_verify"
        if signal == "completed":
            if due_date and event_date and event_date.date() > due_date:
                return "completed_late"
            return "completed_on_time"
        return "announced"

    async def _ensure_program(self) -> CabinetActionProgram | None:
        return (
            await self.db.execute(
                select(CabinetActionProgram).where(CabinetActionProgram.program_key == self.PROGRAM_KEY)
            )
        ).scalar_one_or_none()

    async def _sync_promise_links(self, item: CabinetActionItem, promise_codes: list[str]) -> None:
        existing = {link.manifesto_promise_id: link for link in item.promise_links}
        rows = (
            await self.db.execute(
                select(ManifestoPromise).where(ManifestoPromise.promise_id.in_(promise_codes))
            )
        ).scalars().all()
        desired_ids = {row.id for row in rows}
        for link_id, link in list(existing.items()):
            if link_id not in desired_ids:
                await self.db.delete(link)
        for row in rows:
            if row.id in existing:
                continue
            self.db.add(CabinetActionPromiseLink(item_id=item.id, manifesto_promise_id=row.id))

    async def _apply_evidence(self, item: CabinetActionItem, mapping: dict[str, Any], source: ActionSource) -> None:
        milestone_targets = {
            (entry["item_number"], entry["milestone_order"])
            for entry in mapping.get("matched_milestones", [])
            if isinstance(entry, dict)
        }
        applied_status = self._map_signal_to_status(mapping["status_signal"], due_date=item.due_date_ad, event_date=source.published_at)
        incoming_key = self._evidence_identity_key(
            source_kind=source.kind,
            source_title=source.title,
            source_name=source.source_name,
            source_url=source.source_url,
            source_story_id=source.source_story_id,
            source_announcement_id=source.source_announcement_id,
        )
        should_apply = bool(source.is_official and (mapping.get("should_apply") or False))
        incoming_confidence = float(mapping.get("confidence") or 0.0)
        incoming_note = self._clean_text(str(mapping.get("evidence_note_en") or ""))
        existing_evidence = next(
            (
                entry
                for entry in item.evidence_entries
                if self._evidence_identity_for_entry(entry) == incoming_key
            ),
            None,
        )

        if existing_evidence is None:
            evidence = CabinetActionEvidence(
                item_id=item.id,
                source_kind=source.kind,
                source_title=source.title,
                source_name=source.source_name,
                source_url=source.source_url,
                published_at=source.published_at,
                source_story_id=source.source_story_id,
                source_announcement_id=source.source_announcement_id,
                is_official=source.is_official,
                extracted_status=applied_status,
                evidence_note_en=incoming_note or None,
                confidence=incoming_confidence,
                is_public=should_apply,
                is_applied=should_apply,
                raw_model_payload=mapping,
            )
            self.db.add(evidence)
            item.evidence_entries.append(evidence)
        else:
            evidence = existing_evidence
            evidence.source_kind = evidence.source_kind or source.kind
            evidence.source_title = evidence.source_title or source.title
            evidence.source_name = evidence.source_name or source.source_name
            evidence.source_url = evidence.source_url or source.source_url
            evidence.source_story_id = evidence.source_story_id or source.source_story_id
            evidence.source_announcement_id = evidence.source_announcement_id or source.source_announcement_id
            evidence.is_official = bool(evidence.is_official or source.is_official)
            evidence.extracted_status = evidence.extracted_status or applied_status
            if source.published_at and (evidence.published_at is None or source.published_at > evidence.published_at):
                evidence.published_at = source.published_at
            existing_note = self._clean_text(evidence.evidence_note_en or "")
            if incoming_note and len(incoming_note) >= len(existing_note):
                evidence.evidence_note_en = incoming_note
            evidence.confidence = max(float(evidence.confidence or 0.0), incoming_confidence)
            evidence.is_public = bool(evidence.is_public or should_apply)
            evidence.is_applied = bool(evidence.is_applied or should_apply)
            evidence.raw_model_payload = mapping

        if source.is_official and mapping.get("should_apply") and incoming_confidence >= 0.9:
            item.status = applied_status
            item.evidence_strength = "official"
            item.last_checked_at = datetime.now(timezone.utc)
            for milestone in item.milestones:
                if (item.item_number, milestone.milestone_order) not in milestone_targets:
                    continue
                milestone.status = self._map_signal_to_status(
                    mapping["status_signal"],
                    due_date=milestone.due_date_ad,
                    event_date=source.published_at,
                )
                milestone.evidence_strength = "official"
                milestone.last_checked_at = datetime.now(timezone.utc)
        else:
            review = item.review or CabinetActionReview(cabinet_action_item_id=item.id)
            if item.review is None:
                self.db.add(review)
                item.review = review
            review.workflow_status = "needs_correction"
            review.final_evidence_note = mapping.get("evidence_note_en") or review.final_evidence_note
            review.final_confidence = float(mapping.get("confidence") or 0.0)
            review.reviewer_note = mapping.get("why_not_applied") or "Automation proposed an evidence match that requires review."

    async def _recompute_deadlines(self) -> None:
        today = datetime.now(timezone.utc).date()
        rows = (
            await self.db.execute(
                select(CabinetActionItem).options(selectinload(CabinetActionItem.milestones))
            )
        ).scalars().all()
        for item in rows:
            if item.status == "declaratory_non_scored":
                item.status = "announced"
            for milestone in item.milestones:
                if milestone.status == "declaratory_non_scored":
                    milestone.status = "announced"
                if milestone.due_date_ad and milestone.status not in COMPLETED_STATUSES and milestone.due_date_ad < today:
                    milestone.status = "overdue"
            if item.milestones:
                statuses = {milestone.status for milestone in item.milestones}
                if statuses and statuses <= COMPLETED_STATUSES:
                    item.status = "completed_late" if "completed_late" in statuses else "completed_on_time"
                elif "overdue" in statuses:
                    item.status = "overdue"
                elif "partially_completed" in statuses:
                    item.status = "partially_completed"
                elif "implementation_started" in statuses:
                    item.status = "implementation_started"
            elif item.trackability_class != "declaratory_contextual" and item.due_date_ad and item.status not in COMPLETED_STATUSES and item.due_date_ad < today:
                item.status = "overdue"

    async def run_tracking(self, *, force: bool = False, max_candidates: int = 40) -> dict[str, Any]:
        if not force and not await self.control_service.is_enabled("cabinet_action_tracking"):
            return {"status": "paused", "processed": 0, "matched": 0, "applied": 0, "queued": 0}

        program = await self._ensure_program()
        if program is None:
            raise RuntimeError("Cabinet action program has not been seeded yet")

        control = await self.control_service.get_control("cabinet_action_tracking")
        base_since = control.last_success_at or (datetime.now(timezone.utc) - timedelta(hours=24))
        since = base_since - timedelta(hours=12)
        sources = (await self._list_recent_sources(since))[: max(max_candidates * 3, 120)]
        items = (
            await self.db.execute(
                select(CabinetActionItem)
                .options(
                    selectinload(CabinetActionItem.milestones),
                    selectinload(CabinetActionItem.review),
                    selectinload(CabinetActionItem.evidence_entries),
                )
                .where(CabinetActionItem.program_id == program.id)
            )
        ).scalars().all()
        stats = {"status": "ok", "processed": 0, "matched": 0, "applied": 0, "queued": 0}
        for source in sources:
            shortlist = self._shortlist_items(source, items)
            if not shortlist:
                continue
            stats["processed"] += 1
            try:
                mapping = await self._extract_evidence_mapping(source, shortlist)
            except OpenAIUsageLimitExceeded:
                raise
            except Exception:
                logger.warning("Cabinet action evidence mapping failed for %s", source.source_id, exc_info=True)
                await self.db.rollback()
                continue

            matched_numbers = [
                int(number)
                for number in mapping.get("matched_item_numbers", [])
                if isinstance(number, int)
            ]
            if not matched_numbers or mapping.get("status_signal") == "no_match":
                continue

            matched_items = [item for item in items if item.item_number in matched_numbers]
            if not matched_items:
                continue

            stats["matched"] += len(matched_items)
            try:
                for item in matched_items:
                    await self._apply_evidence(item, mapping, source)
                await self.db.commit()
            except OpenAIUsageLimitExceeded:
                raise
            except Exception:
                logger.warning(
                    "Cabinet action evidence persistence failed for %s",
                    source.source_id,
                    exc_info=True,
                )
                await self.db.rollback()
                continue

            if source.is_official and mapping.get("should_apply") and float(mapping.get("confidence") or 0.0) >= 0.9:
                stats["applied"] += len(matched_items)
            else:
                stats["queued"] += len(matched_items)

        await self._recompute_deadlines()
        await self.db.commit()
        return stats

    @staticmethod
    def _effective_fields(item: CabinetActionItem) -> dict[str, Any]:
        review = item.review
        use_review = bool(review and review.workflow_status == "approved")
        return {
            "section_key": review.final_section_key if use_review and review.final_section_key else item.section_key,
            "section_title_en": review.final_section_title_en if use_review and review.final_section_title_en else item.section_title_en,
            "title_en": review.final_title_en if use_review and review.final_title_en else item.title_en,
            "summary_en": review.final_summary_en if use_review and review.final_summary_en else item.summary_en,
            "lead_institution": review.final_lead_institution if use_review and review.final_lead_institution else item.lead_institution,
            "supporting_institutions": review.final_supporting_institutions if use_review and review.final_supporting_institutions is not None else item.supporting_institutions,
            "action_type": review.final_action_type if use_review and review.final_action_type else item.action_type,
            "trackability_class": review.final_trackability_class if use_review and review.final_trackability_class else item.trackability_class,
            "status": review.final_status if use_review and review.final_status else item.status,
            "evidence_note": review.final_evidence_note if use_review and review.final_evidence_note else None,
            "confidence": review.final_confidence if use_review and review.final_confidence is not None else None,
            "is_public": review.final_is_public if use_review and review.final_is_public is not None else item.is_public,
            "manifesto_promise_ids": review.final_manifesto_promise_ids if use_review and review.final_manifesto_promise_ids is not None else None,
        }

    def serialize_public_item(self, item: CabinetActionItem, *, include_source: bool = False) -> dict[str, Any]:
        effective = self._effective_fields(item)
        audit = self._effective_audit_fields(item)
        public_trackability = self._resolve_public_trackability(audit["trackability_class"])
        public_status = self._resolve_public_status(
            trackability_class=audit["trackability_class"],
            status=audit["status"],
            due_date_ad=item.due_date_ad,
        )
        promises = [link.manifesto_promise.promise_id for link in item.promise_links if link.manifesto_promise]
        payload = {
            "id": str(item.id),
            "itemNumber": item.item_number,
            "sectionKey": effective["section_key"],
            "sectionTitle": effective["section_title_en"],
            "title": effective["title_en"],
            "summary": effective["summary_en"],
            "leadInstitution": effective["lead_institution"],
            "supportingInstitutions": effective["supporting_institutions"] or [],
            "actionType": effective["action_type"],
            "trackabilityClass": public_trackability,
            "deadlineTextNe": item.deadline_text_ne,
            "dueDateBs": item.due_date_bs,
            "dueDateAd": item.due_date_ad,
            "status": public_status,
            "evidenceNote": effective["evidence_note"],
            "sourcePdfPage": item.source_pdf_page,
            "relatedManifestoPromises": promises,
            "milestoneCount": len(item.milestones),
        }
        if include_source:
            evidence_entries = self._dedupe_evidence_entries(list(item.evidence_entries))
            payload["sourceTextNe"] = item.source_text_ne
            payload["milestones"] = [
                {
                    "id": str(milestone.id),
                    "milestoneOrder": milestone.milestone_order,
                    "title": milestone.title_en,
                    "summary": milestone.summary_en,
                    "sourceTextNe": milestone.source_text_ne,
                    "deadlineTextNe": milestone.deadline_text_ne,
                    "dueDateBs": milestone.due_date_bs,
                    "dueDateAd": milestone.due_date_ad,
                    "status": milestone.status,
                    "evidenceStrength": milestone.evidence_strength,
                }
                for milestone in sorted(item.milestones, key=lambda entry: entry.milestone_order)
                if milestone.is_public
            ]
            payload["evidence"] = [
                {
                    "id": str(entry.id),
                    "sourceKind": entry.source_kind,
                    "sourceTitle": entry.source_title,
                    "sourceName": entry.source_name,
                    "sourceUrl": entry.source_url,
                    "publishedAt": entry.published_at,
                    "isOfficial": entry.is_official,
                    "status": entry.extracted_status,
                    "note": entry.evidence_note_en,
                    "confidence": entry.confidence,
                }
                for entry in evidence_entries
                if entry.is_public or include_source
            ]
        return payload

    def serialize_editorial_item(self, item: CabinetActionItem) -> dict[str, Any]:
        review = item.review
        effective = self._effective_fields(item)
        return {
            "item_id": str(item.id),
            "program_id": str(item.program_id),
            "item_number": item.item_number,
            "source_pdf_page": item.source_pdf_page,
            "raw": {
                "section_key": item.section_key,
                "section_title_ne": item.section_title_ne,
                "section_title_en": item.section_title_en,
                "source_text_ne": item.source_text_ne,
                "title_en": item.title_en,
                "summary_en": item.summary_en,
                "lead_institution": item.lead_institution,
                "supporting_institutions": item.supporting_institutions,
                "action_type": item.action_type,
                "trackability_class": item.trackability_class,
                "deadline_text_ne": item.deadline_text_ne,
                "deadline_kind": item.deadline_kind,
                "deadline_value": item.deadline_value,
                "due_date_bs": item.due_date_bs,
                "due_date_ad": item.due_date_ad,
                "status": item.status,
                "evidence_strength": item.evidence_strength,
                "is_public": item.is_public,
                "last_checked_at": item.last_checked_at,
                "raw_seed_payload": item.raw_seed_payload,
            },
            "review": {
                "workflow_status": review.workflow_status if review else "draft",
                "final_section_key": review.final_section_key if review else None,
                "final_section_title_en": review.final_section_title_en if review else None,
                "final_title_en": review.final_title_en if review else None,
                "final_summary_en": review.final_summary_en if review else None,
                "final_lead_institution": review.final_lead_institution if review else None,
                "final_supporting_institutions": review.final_supporting_institutions if review else None,
                "final_action_type": review.final_action_type if review else None,
                "final_trackability_class": review.final_trackability_class if review else None,
                "final_status": review.final_status if review else None,
                "final_evidence_note": review.final_evidence_note if review else None,
                "final_confidence": review.final_confidence if review else None,
                "final_is_public": review.final_is_public if review else None,
                "final_manifesto_promise_ids": review.final_manifesto_promise_ids if review else None,
                "milestone_overrides": review.milestone_overrides if review else None,
                "reviewer_note": review.reviewer_note if review else None,
                "approved_at": review.approved_at if review else None,
                "rejected_at": review.rejected_at if review else None,
                "rejection_reason": review.rejection_reason if review else None,
                "needs_rerun": review.needs_rerun if review else False,
                "rerun_requested_at": review.rerun_requested_at if review else None,
            },
            "effective": effective,
            "milestones": [
                {
                    "id": str(milestone.id),
                    "milestone_order": milestone.milestone_order,
                    "source_text_ne": milestone.source_text_ne,
                    "title_en": milestone.title_en,
                    "summary_en": milestone.summary_en,
                    "deadline_text_ne": milestone.deadline_text_ne,
                    "due_date_bs": milestone.due_date_bs,
                    "due_date_ad": milestone.due_date_ad,
                    "status": milestone.status,
                    "evidence_strength": milestone.evidence_strength,
                }
                for milestone in sorted(item.milestones, key=lambda entry: entry.milestone_order)
            ],
            "evidence": [
                {
                    "id": str(entry.id),
                    "source_kind": entry.source_kind,
                    "source_title": entry.source_title,
                    "source_name": entry.source_name,
                    "source_url": entry.source_url,
                    "published_at": entry.published_at,
                    "is_official": entry.is_official,
                    "extracted_status": entry.extracted_status,
                    "evidence_note_en": entry.evidence_note_en,
                    "confidence": entry.confidence,
                    "is_public": entry.is_public,
                    "is_applied": entry.is_applied,
                }
                for entry in item.evidence_entries
            ],
            "manifesto_links": [
                {
                    "id": str(link.id),
                    "promise_id": link.manifesto_promise.promise_id,
                    "category": link.manifesto_promise.category,
                    "title": link.manifesto_promise.title,
                }
                for link in item.promise_links
                if link.manifesto_promise
            ],
        }

    async def list_public(
        self,
        *,
        limit: int = 100,
        section_key: Optional[str] = None,
        status: Optional[str] = None,
        lead_institution: Optional[str] = None,
        trackability_class: Optional[str] = None,
        due_bucket: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(CabinetActionItem)
            .join(CabinetActionReview, CabinetActionReview.cabinet_action_item_id == CabinetActionItem.id)
            .options(
                selectinload(CabinetActionItem.review),
                selectinload(CabinetActionItem.milestones),
                selectinload(CabinetActionItem.evidence_entries),
                selectinload(CabinetActionItem.promise_links).selectinload(CabinetActionPromiseLink.manifesto_promise),
            )
            .where(
                CabinetActionReview.workflow_status.notin_(["rejected", "superseded"]),
                CabinetActionItem.is_public.is_(True),
            )
            .order_by(CabinetActionItem.item_number.asc())
        )
        if section_key:
            stmt = stmt.where(CabinetActionItem.section_key == section_key)
        if status:
            stmt = stmt.where(CabinetActionItem.status == status)
        if lead_institution:
            stmt = stmt.where(CabinetActionItem.lead_institution == lead_institution)
        if trackability_class:
            stmt = stmt.where(CabinetActionItem.trackability_class == trackability_class)
        today = datetime.now(timezone.utc).date()
        if due_bucket == "due_soon":
            stmt = stmt.where(
                CabinetActionItem.due_date_ad.is_not(None),
                CabinetActionItem.due_date_ad >= today,
                CabinetActionItem.due_date_ad <= today + timedelta(days=7),
                CabinetActionItem.status.notin_(COMPLETED_STATUSES),
            )
        elif due_bucket == "overdue":
            stmt = stmt.where(CabinetActionItem.status == "overdue")

        rows = (await self.db.execute(stmt.limit(limit))).scalars().all()
        return [self.serialize_public_item(item) for item in rows]

    async def get_public_item(self, item_id: UUID) -> Optional[dict[str, Any]]:
        item = (
            await self.db.execute(
                select(CabinetActionItem)
                .join(CabinetActionReview, CabinetActionReview.cabinet_action_item_id == CabinetActionItem.id)
                .options(
                    selectinload(CabinetActionItem.review),
                    selectinload(CabinetActionItem.milestones),
                    selectinload(CabinetActionItem.evidence_entries),
                    selectinload(CabinetActionItem.promise_links).selectinload(CabinetActionPromiseLink.manifesto_promise),
                )
                .where(
                    CabinetActionItem.id == item_id,
                    CabinetActionReview.workflow_status.notin_(["rejected", "superseded"]),
                )
            )
        ).scalar_one_or_none()
        return self.serialize_public_item(item, include_source=True) if item else None

    async def list_public_summary(self) -> dict[str, Any]:
        items = await self.list_public(limit=500)
        scored = list(items)
        total_actions = len(items)
        total_scored = len(scored)
        not_started = sum(1 for item in scored if item["status"] == "not_started")
        announced = sum(1 for item in scored if item["status"] == "announced")
        implementation_started = sum(1 for item in scored if item["status"] == "implementation_started")
        partially_completed = sum(1 for item in scored if item["status"] == "partially_completed")
        completed_on_time = sum(1 for item in scored if item["status"] == "completed_on_time")
        completed_late = sum(1 for item in scored if item["status"] == "completed_late")
        overdue = sum(1 for item in scored if item["status"] == "overdue")
        cannot_verify = sum(1 for item in scored if item["status"] == "cannot_verify")
        declaratory_non_scored = sum(1 for item in scored if item["status"] == "declaratory_non_scored")
        started = implementation_started + partially_completed
        underway = not_started + announced + started
        non_scored = declaratory_non_scored
        return {
            "total_actions": total_actions,
            "total_scored_actions": total_scored,
            "not_started": not_started,
            "announced": announced,
            "implementation_started": implementation_started,
            "partially_completed": partially_completed,
            "completed_on_time": completed_on_time,
            "completed_late": completed_late,
            "overdue": overdue,
            "started": started,
            "cannot_verify": cannot_verify,
            "declaratory_non_scored": declaratory_non_scored,
            "underway": underway,
            "non_scored": non_scored,
            "completion_rate": round(((completed_on_time + completed_late) / total_scored) * 100, 1) if total_scored else 0.0,
            "on_time_rate": round((completed_on_time / total_scored) * 100, 1) if total_scored else 0.0,
        }

    async def list_by_manifesto_promise(self, promise_code: str) -> list[dict[str, Any]]:
        rows = (
            await self.db.execute(
                select(CabinetActionItem)
                .join(CabinetActionPromiseLink, CabinetActionPromiseLink.item_id == CabinetActionItem.id)
                .join(ManifestoPromise, ManifestoPromise.id == CabinetActionPromiseLink.manifesto_promise_id)
                .join(CabinetActionReview, CabinetActionReview.cabinet_action_item_id == CabinetActionItem.id)
                .options(selectinload(CabinetActionItem.review), selectinload(CabinetActionItem.milestones))
                .where(
                    ManifestoPromise.promise_id == promise_code,
                    CabinetActionReview.workflow_status.notin_(["rejected", "superseded"]),
                )
                .order_by(CabinetActionItem.item_number.asc())
            )
        ).scalars().all()
        return [self.serialize_public_item(item) for item in rows]

    async def list_inbox(
        self,
        *,
        workflow_statuses: Optional[list[str]] = None,
        page: int = 1,
        per_page: int = 40,
    ) -> dict[str, Any]:
        stmt = (
            select(CabinetActionItem)
            .outerjoin(CabinetActionReview, CabinetActionReview.cabinet_action_item_id == CabinetActionItem.id)
            .options(
                selectinload(CabinetActionItem.review),
                selectinload(CabinetActionItem.milestones),
                selectinload(CabinetActionItem.evidence_entries),
                selectinload(CabinetActionItem.promise_links).selectinload(CabinetActionPromiseLink.manifesto_promise),
            )
            .order_by(
                case(
                    (CabinetActionReview.workflow_status.in_(["draft", "needs_correction"]), 0),
                    (CabinetActionReview.workflow_status == "approved", 1),
                    (CabinetActionReview.workflow_status == "superseded", 2),
                    else_=3,
                ),
                CabinetActionItem.item_number.asc(),
            )
        )
        count_stmt = (
            select(func.count(CabinetActionItem.id))
            .select_from(CabinetActionItem)
            .outerjoin(CabinetActionReview, CabinetActionReview.cabinet_action_item_id == CabinetActionItem.id)
        )
        if workflow_statuses:
            stmt = stmt.where(CabinetActionReview.workflow_status.in_(workflow_statuses))
            count_stmt = count_stmt.where(CabinetActionReview.workflow_status.in_(workflow_statuses))

        total = int((await self.db.execute(count_stmt)).scalar() or 0)
        rows = (
            await self.db.execute(stmt.offset((page - 1) * per_page).limit(per_page))
        ).scalars().all()
        return {
            "items": [self.serialize_editorial_item(item) for item in rows],
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": (total + per_page - 1) // per_page if per_page else 0,
        }

    async def get_item(self, item_id: UUID) -> CabinetActionItem | None:
        return (
            await self.db.execute(
                select(CabinetActionItem)
                .options(
                    selectinload(CabinetActionItem.review),
                    selectinload(CabinetActionItem.milestones),
                    selectinload(CabinetActionItem.evidence_entries),
                    selectinload(CabinetActionItem.promise_links).selectinload(CabinetActionPromiseLink.manifesto_promise),
                )
                .where(CabinetActionItem.id == item_id)
            )
        ).scalar_one_or_none()
