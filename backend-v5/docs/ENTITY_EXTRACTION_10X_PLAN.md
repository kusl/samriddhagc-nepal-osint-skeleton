# 10x Entity Extraction Improvement Plan

**Goal:** Leverage election database (candidates, constituencies, parties) and parliament data (MPs, committees, ministries) to achieve 10x more accurate, precise entity extraction with low false positives.

---

## Executive Summary

| Metric | Current State | Target State | Method |
|--------|--------------|--------------|--------|
| **Entity Recall** | ~60% | ~95% | Database-driven pattern generation |
| **Entity Precision** | ~70% | ~92% | Context validation + confidence scoring |
| **False Positive Rate** | ~15% | <3% | Strict boundary detection + disambiguation |
| **Name Resolution** | Basic aliases | Full canonical linking | Cross-lingual entity resolution |
| **Coverage** | ~200 entities | ~3000+ entities | Auto-generated from DB |

---

## Data Sources Analysis

### 1. Election Database (`election.py`)
| Table | Fields | Entity Count (Est.) |
|-------|--------|---------------------|
| `Candidate` | name_en, name_ne, party, party_ne | ~2,500 per election |
| `Constituency` | name_en, name_ne, district, province | 165 x 3 elections |
| `Election` | year_bs, year_ad | 3 elections (2074, 2079, 2082) |

**Key Fields for Entity Extraction:**
- `name_en`: English candidate names ("Ram Bahadur Thapa")
- `name_ne`: Nepali candidate names ("राम बहादुर थापा")
- `party`: English party ("Nepali Congress")
- `party_ne`: Nepali party ("नेपाली काँग्रेस")
- `constituency.district`: District names
- `constituency.province`: Province names

### 2. Parliament Database (`parliament.py`)
| Table | Fields | Entity Count (Est.) |
|-------|--------|---------------------|
| `MPPerformance` | name_en, name_ne, party, constituency, ministry_portfolio | ~275 MPs |
| `ParliamentCommittee` | name_en, name_ne | ~50 committees |
| `ParliamentBill` | title_en, title_ne, ministry | ~500+ bills |

**Key Fields for Entity Extraction:**
- `is_minister`: Flag for current ministers
- `ministry_portfolio`: Ministry names
- `is_former_pm`: Former Prime Ministers
- Committee names (English/Nepali)

### 3. Political Entity KB (`political_entity.py`)
| Field | Purpose |
|-------|---------|
| `canonical_id` | Unique identifier for entity resolution |
| `aliases` | JSONB list of all name variations |
| `entity_type` | person, party, organization, institution |
| `role` | Current position/title |

---

## Architecture: Database-Driven Entity Extraction

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Database-Driven Entity Extraction Pipeline                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐                    │
│  │   Election   │   │  Parliament  │   │  Political   │                    │
│  │   Database   │   │   Database   │   │  Entity KB   │                    │
│  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘                    │
│         │                  │                  │                            │
│         └─────────┬────────┴─────────┬────────┘                            │
│                   │                  │                                      │
│                   ▼                  ▼                                      │
│         ┌─────────────────┐  ┌──────────────────┐                          │
│         │  Entity Index   │  │  Alias Expansion │                          │
│         │   Generator     │  │     Service      │                          │
│         └────────┬────────┘  └────────┬─────────┘                          │
│                  │                    │                                     │
│                  └────────┬───────────┘                                     │
│                           ▼                                                 │
│         ┌─────────────────────────────────────────┐                        │
│         │        Trie-Based Entity Matcher        │                        │
│         │    (Aho-Corasick Multi-Pattern Match)   │                        │
│         └────────────────────┬────────────────────┘                        │
│                              │                                              │
│                              ▼                                              │
│         ┌─────────────────────────────────────────┐                        │
│         │       Context Validator & Scorer        │                        │
│         │    - Boundary validation                │                        │
│         │    - Part-of-speech context             │                        │
│         │    - Confidence scoring                 │                        │
│         └────────────────────┬────────────────────┘                        │
│                              │                                              │
│                              ▼                                              │
│         ┌─────────────────────────────────────────┐                        │
│         │      Entity Disambiguation Layer        │                        │
│         │    - Name collision resolution          │                        │
│         │    - Cross-reference with context       │                        │
│         │    - Canonical ID assignment            │                        │
│         └────────────────────┬────────────────────┘                        │
│                              │                                              │
│                              ▼                                              │
│         ┌─────────────────────────────────────────┐                        │
│         │         Canonical Entity Output         │                        │
│         │    - Linked to PoliticalEntity KB       │                        │
│         │    - Confidence score 0.0-1.0           │                        │
│         │    - Entity type classification         │                        │
│         └─────────────────────────────────────────┘                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Entity Index Generator (Priority: Critical)

### 1.1 Auto-Generate Entity Index from Database

**File:** `backend-v5/app/services/nlp/entity_index_generator.py`

```python
"""
Entity Index Generator - Auto-populates entity patterns from database.
Runs on startup and periodically to sync with latest election/parliament data.
"""

class EntityIndexGenerator:
    """
    Generates entity recognition patterns from:
    - Election candidates (name_en, name_ne, party, party_ne)
    - Parliament MPs (name_en, name_ne, constituency)
    - Political entities KB (canonical with aliases)
    - Constituencies (165 districts, 7 provinces)
    """

    async def generate_person_patterns(self, session: AsyncSession) -> Dict[str, EntityPattern]:
        """
        Generate patterns for all political persons.

        Returns:
            Dict mapping pattern text to EntityPattern with:
            - canonical_id: unique identifier
            - entity_type: PERSON
            - confidence: base confidence (0.7-1.0)
            - context_hints: party, constituency, role
        """
        patterns = {}

        # 1. Election candidates
        candidates = await session.execute(
            select(Candidate).options(selectinload(Candidate.constituency))
        )
        for candidate in candidates.scalars():
            # Primary name (English)
            patterns[candidate.name_en.lower()] = EntityPattern(
                canonical_id=f"candidate_{candidate.external_id}",
                entity_type="PERSON",
                confidence=0.9,
                context_hints={
                    "party": candidate.party,
                    "constituency": candidate.constituency.name_en,
                    "district": candidate.constituency.district,
                }
            )
            # Nepali name
            if candidate.name_ne:
                patterns[candidate.name_ne] = EntityPattern(
                    canonical_id=f"candidate_{candidate.external_id}",
                    entity_type="PERSON",
                    confidence=0.95,  # Higher for Nepali (more specific)
                    context_hints={...}
                )

        # 2. Parliament MPs
        mps = await session.execute(select(MPPerformance))
        for mp in mps.scalars():
            patterns[mp.name_en.lower()] = EntityPattern(
                canonical_id=f"mp_{mp.mp_id}",
                entity_type="PERSON",
                confidence=0.92,
                context_hints={
                    "party": mp.party,
                    "role": "minister" if mp.is_minister else "mp",
                    "ministry": mp.ministry_portfolio,
                }
            )
            # ... Nepali name

        # 3. Political Entities KB (highest priority)
        entities = await session.execute(
            select(PoliticalEntity).where(PoliticalEntity.entity_type == EntityType.PERSON)
        )
        for entity in entities.scalars():
            # All aliases get high confidence
            for name in entity.all_names:
                patterns[name.lower()] = EntityPattern(
                    canonical_id=entity.canonical_id,
                    entity_type="PERSON",
                    confidence=0.98,  # Highest for curated KB
                    context_hints={"party": entity.party, "role": entity.role}
                )

        return patterns

    async def generate_organization_patterns(self, session: AsyncSession) -> Dict[str, EntityPattern]:
        """Generate patterns for parties, committees, ministries."""
        patterns = {}

        # Political parties (from candidates)
        parties = await session.execute(
            select(Candidate.party, Candidate.party_ne).distinct()
        )
        for party_en, party_ne in parties:
            canonical = self._party_to_canonical(party_en)
            patterns[party_en.lower()] = EntityPattern(
                canonical_id=canonical,
                entity_type="ORGANIZATION",
                confidence=0.95,
            )
            if party_ne:
                patterns[party_ne] = EntityPattern(
                    canonical_id=canonical,
                    entity_type="ORGANIZATION",
                    confidence=0.98,
                )

        # Parliament committees
        committees = await session.execute(select(ParliamentCommittee))
        for committee in committees.scalars():
            patterns[committee.name_en.lower()] = EntityPattern(
                canonical_id=f"committee_{committee.external_id}",
                entity_type="ORGANIZATION",
                confidence=0.9,
            )

        # Ministries (from MP portfolios)
        ministries = await session.execute(
            select(MPPerformance.ministry_portfolio).where(
                MPPerformance.ministry_portfolio.isnot(None)
            ).distinct()
        )
        for (ministry,) in ministries:
            patterns[ministry.lower()] = EntityPattern(
                canonical_id=f"ministry_{self._slugify(ministry)}",
                entity_type="ORGANIZATION",
                confidence=0.88,
            )

        return patterns

    async def generate_location_patterns(self, session: AsyncSession) -> Dict[str, EntityPattern]:
        """Generate patterns for constituencies, districts, provinces."""
        patterns = {}

        # All 165 constituencies
        constituencies = await session.execute(select(Constituency))
        for const in constituencies.scalars():
            # English name
            patterns[const.name_en.lower()] = EntityPattern(
                canonical_id=f"constituency_{const.constituency_code}",
                entity_type="LOCATION",
                confidence=0.92,
                context_hints={"district": const.district, "province_id": const.province_id}
            )
            # Nepali name
            if const.name_ne:
                patterns[const.name_ne] = EntityPattern(
                    canonical_id=f"constituency_{const.constituency_code}",
                    entity_type="LOCATION",
                    confidence=0.95,
                )
            # District (avoid duplicates)
            if const.district.lower() not in patterns:
                patterns[const.district.lower()] = EntityPattern(
                    canonical_id=f"district_{self._slugify(const.district)}",
                    entity_type="LOCATION",
                    confidence=0.85,
                )

        return patterns
```

### 1.2 Pattern Statistics (Estimated)

| Category | English Patterns | Nepali Patterns | Total |
|----------|-----------------|-----------------|-------|
| Candidates (2082 election) | ~2,500 | ~2,500 | ~5,000 |
| MPs (current) | ~275 | ~275 | ~550 |
| Political Entities KB | ~200 | ~200 | ~400 |
| Parties | ~50 | ~50 | ~100 |
| Constituencies | ~165 | ~165 | ~330 |
| Districts | ~77 | ~77 | ~154 |
| Committees | ~50 | ~50 | ~100 |
| **Total** | **~3,300** | **~3,300** | **~6,600** |

---

## Phase 2: Aho-Corasick Multi-Pattern Matcher (Priority: High)

### 2.1 Why Aho-Corasick?

Current approach: Linear scan with regex for each pattern → O(n × m) where n = text length, m = patterns
Aho-Corasick: Single pass automaton → O(n + k) where k = number of matches

**Performance improvement: 100x-1000x for large pattern sets**

### 2.2 Implementation

**File:** `backend-v5/app/services/nlp/aho_corasick_matcher.py`

```python
"""
Aho-Corasick automaton for efficient multi-pattern matching.
Handles 6,600+ patterns in single text pass.
"""
import ahocorasick
from typing import List, Tuple, Dict
from dataclasses import dataclass

@dataclass
class EntityMatch:
    """Raw match before validation."""
    text: str
    start: int
    end: int
    pattern: EntityPattern
    raw_confidence: float

class AhoCorasickEntityMatcher:
    """
    High-performance entity matcher using Aho-Corasick automaton.

    Characteristics:
    - Single pass through text regardless of pattern count
    - Memory-efficient trie structure
    - Handles overlapping matches
    - Supports both English (case-insensitive) and Nepali (case-sensitive)
    """

    def __init__(self):
        self._automaton_en: Optional[ahocorasick.Automaton] = None
        self._automaton_ne: Optional[ahocorasick.Automaton] = None
        self._patterns: Dict[str, EntityPattern] = {}
        self._built = False

    def build_from_patterns(self, patterns: Dict[str, EntityPattern]):
        """
        Build automaton from entity patterns.

        Separates English (ASCII) and Nepali (Devanagari) patterns
        for optimal matching.
        """
        self._automaton_en = ahocorasick.Automaton()
        self._automaton_ne = ahocorasick.Automaton()

        for pattern_text, pattern in patterns.items():
            self._patterns[pattern_text] = pattern

            if self._is_devanagari(pattern_text):
                # Nepali: exact match (no lowercasing)
                self._automaton_ne.add_word(pattern_text, (pattern_text, pattern))
            else:
                # English: case-insensitive
                self._automaton_en.add_word(pattern_text.lower(), (pattern_text, pattern))

        self._automaton_en.make_automaton()
        self._automaton_ne.make_automaton()
        self._built = True

    def find_all_matches(self, text: str) -> List[EntityMatch]:
        """
        Find all entity matches in text.

        Returns list of EntityMatch with:
        - text: matched substring
        - start/end: character positions
        - pattern: EntityPattern with canonical_id, type, confidence
        """
        if not self._built:
            raise RuntimeError("Automaton not built. Call build_from_patterns first.")

        matches = []

        # English matching (case-insensitive)
        text_lower = text.lower()
        for end_idx, (pattern_text, pattern) in self._automaton_en.iter(text_lower):
            start_idx = end_idx - len(pattern_text) + 1
            matches.append(EntityMatch(
                text=text[start_idx:end_idx + 1],  # Original case
                start=start_idx,
                end=end_idx + 1,
                pattern=pattern,
                raw_confidence=pattern.confidence,
            ))

        # Nepali matching (exact)
        for end_idx, (pattern_text, pattern) in self._automaton_ne.iter(text):
            start_idx = end_idx - len(pattern_text) + 1
            matches.append(EntityMatch(
                text=text[start_idx:end_idx + 1],
                start=start_idx,
                end=end_idx + 1,
                pattern=pattern,
                raw_confidence=pattern.confidence,
            ))

        return matches

    def _is_devanagari(self, text: str) -> bool:
        """Check if text contains Devanagari characters."""
        return any('\u0900' <= c <= '\u097F' for c in text)
```

### 2.3 Dependencies

Add to `requirements.txt`:
```
pyahocorasick>=2.0.0
```

---

## Phase 3: Context Validation & False Positive Reduction (Priority: Critical)

### 3.1 Word Boundary Validation

**Problem:** "Ram" matches inside "Ramesh", "Congress" matches inside "Congressional"

```python
class BoundaryValidator:
    """
    Validates entity matches respect word boundaries.
    Critical for reducing false positives.
    """

    # Nepali word boundary characters
    NEPALI_BOUNDARIES = set(' ।,;:!?\n\t()[]{}""''')

    # English word boundary (non-alphanumeric)
    ENGLISH_BOUNDARY_PATTERN = re.compile(r'\b')

    def is_valid_boundary(self, text: str, match: EntityMatch) -> bool:
        """
        Check if match has valid word boundaries.

        Rules:
        - English: must be surrounded by non-alphanumeric or string edges
        - Nepali: must be surrounded by spaces, punctuation, or string edges
        """
        start, end = match.start, match.end
        matched_text = match.text

        if self._is_devanagari(matched_text):
            return self._check_nepali_boundary(text, start, end)
        else:
            return self._check_english_boundary(text, start, end)

    def _check_english_boundary(self, text: str, start: int, end: int) -> bool:
        """English boundary: alphanumeric edges must be at word boundary."""
        # Check left boundary
        if start > 0:
            left_char = text[start - 1]
            if left_char.isalnum():
                return False

        # Check right boundary
        if end < len(text):
            right_char = text[end]
            if right_char.isalnum():
                return False

        return True

    def _check_nepali_boundary(self, text: str, start: int, end: int) -> bool:
        """Nepali boundary: spaces or punctuation."""
        # Check left boundary
        if start > 0:
            left_char = text[start - 1]
            if left_char not in self.NEPALI_BOUNDARIES and '\u0900' <= left_char <= '\u097F':
                return False

        # Check right boundary
        if end < len(text):
            right_char = text[end]
            if right_char not in self.NEPALI_BOUNDARIES and '\u0900' <= right_char <= '\u097F':
                return False

        return True
```

### 3.2 Context-Based Confidence Scoring

```python
class ContextScorer:
    """
    Adjusts confidence based on surrounding context.
    Uses context hints from EntityPattern to boost/penalize.
    """

    # Context boost keywords
    PERSON_CONTEXT_BOOST = {
        "minister", "mp", "member", "leader", "chairman", "president",
        "मन्त्री", "सांसद", "नेता", "अध्यक्ष", "सभापति",
    }

    PARTY_CONTEXT_BOOST = {
        "party", "congress", "communist", "socialist", "coalition",
        "पार्टी", "काँग्रेस", "कम्युनिष्ट", "समाजवादी", "गठबन्धन",
    }

    LOCATION_CONTEXT_BOOST = {
        "district", "province", "constituency", "election",
        "जिल्ला", "प्रदेश", "निर्वाचन क्षेत्र", "चुनाव",
    }

    def score_with_context(
        self,
        match: EntityMatch,
        text: str,
        window: int = 50
    ) -> float:
        """
        Score match based on surrounding context.

        Args:
            match: Entity match with raw confidence
            text: Full text
            window: Characters to look before/after match

        Returns:
            Adjusted confidence (0.0 - 1.0)
        """
        confidence = match.raw_confidence

        # Extract context window
        start = max(0, match.start - window)
        end = min(len(text), match.end + window)
        context = text[start:end].lower()

        # Boost based on entity type context
        entity_type = match.pattern.entity_type

        if entity_type == "PERSON":
            if any(kw in context for kw in self.PERSON_CONTEXT_BOOST):
                confidence = min(1.0, confidence + 0.1)
            # Check if party mentioned nearby (confirms person)
            if match.pattern.context_hints.get("party"):
                party = match.pattern.context_hints["party"].lower()
                if party in context:
                    confidence = min(1.0, confidence + 0.15)

        elif entity_type == "ORGANIZATION":
            if any(kw in context for kw in self.PARTY_CONTEXT_BOOST):
                confidence = min(1.0, confidence + 0.1)

        elif entity_type == "LOCATION":
            if any(kw in context for kw in self.LOCATION_CONTEXT_BOOST):
                confidence = min(1.0, confidence + 0.1)

        # Penalize very short matches (high false positive risk)
        if len(match.text) < 4:
            confidence *= 0.7

        return confidence
```

### 3.3 Overlap Resolution

```python
class OverlapResolver:
    """
    Resolves overlapping entity matches.
    Prefers: longer matches > higher confidence > earlier position
    """

    def resolve_overlaps(self, matches: List[EntityMatch]) -> List[EntityMatch]:
        """
        Remove overlapping matches, keeping best candidates.

        Strategy:
        1. Sort by (start, -length, -confidence)
        2. Greedy selection: take non-overlapping with best score
        """
        if not matches:
            return []

        # Sort: earlier start, then longer, then higher confidence
        sorted_matches = sorted(
            matches,
            key=lambda m: (m.start, -(m.end - m.start), -m.raw_confidence)
        )

        selected = []
        last_end = -1

        for match in sorted_matches:
            if match.start >= last_end:
                selected.append(match)
                last_end = match.end
            elif (match.end - match.start) > (selected[-1].end - selected[-1].start):
                # Longer match takes precedence even if overlapping
                selected[-1] = match
                last_end = match.end

        return selected
```

---

## Phase 4: Entity Disambiguation (Priority: High)

### 4.1 Name Collision Resolution

**Problem:** "Ram Thapa" could match multiple candidates with same name

```python
class EntityDisambiguator:
    """
    Resolves ambiguous entity matches using context clues.
    """

    async def disambiguate(
        self,
        match: EntityMatch,
        text: str,
        session: AsyncSession,
    ) -> Tuple[str, float]:
        """
        Resolve ambiguous entity to canonical ID.

        Returns:
            (canonical_id, confidence)
        """
        # If pattern has unique canonical_id, use it
        if match.pattern.canonical_id:
            return match.pattern.canonical_id, match.raw_confidence

        # Find all entities matching this name
        candidates = await self._find_candidates(match.text, session)

        if len(candidates) == 1:
            return candidates[0].canonical_id, match.raw_confidence

        if len(candidates) == 0:
            # New/unknown entity
            return f"unknown_{self._slugify(match.text)}", match.raw_confidence * 0.5

        # Multiple candidates - disambiguate by context
        return await self._disambiguate_by_context(match, text, candidates)

    async def _disambiguate_by_context(
        self,
        match: EntityMatch,
        text: str,
        candidates: List[PoliticalEntity],
    ) -> Tuple[str, float]:
        """
        Use context clues to pick best candidate.

        Context signals:
        - Party mentioned nearby
        - Constituency mentioned nearby
        - Role/title mentioned nearby
        """
        text_lower = text.lower()
        scores = {}

        for candidate in candidates:
            score = 0.0

            # Party match
            if candidate.party and candidate.party.lower() in text_lower:
                score += 0.4

            # Role match
            if candidate.role and candidate.role.lower() in text_lower:
                score += 0.3

            # Recent mention (temporal relevance)
            if candidate.last_mentioned_at:
                days_ago = (datetime.utcnow() - candidate.last_mentioned_at).days
                if days_ago < 7:
                    score += 0.2
                elif days_ago < 30:
                    score += 0.1

            scores[candidate.canonical_id] = score

        if not scores:
            # No context signals - return most mentioned
            best = max(candidates, key=lambda c: c.total_mentions)
            return best.canonical_id, match.raw_confidence * 0.6

        best_id = max(scores, key=scores.get)
        confidence = match.raw_confidence * (0.7 + scores[best_id] * 0.3)

        return best_id, min(confidence, 1.0)
```

### 4.2 Cross-Lingual Linking

```python
class CrossLingualLinker:
    """
    Links English and Nepali mentions to same canonical entity.
    """

    def __init__(self):
        self._en_to_canonical: Dict[str, str] = {}
        self._ne_to_canonical: Dict[str, str] = {}

    async def build_index(self, session: AsyncSession):
        """Build cross-lingual index from database."""

        # From candidates
        candidates = await session.execute(select(Candidate))
        for c in candidates.scalars():
            canonical = f"candidate_{c.external_id}"
            self._en_to_canonical[c.name_en.lower()] = canonical
            if c.name_ne:
                self._ne_to_canonical[c.name_ne] = canonical

        # From political entities (highest priority)
        entities = await session.execute(select(PoliticalEntity))
        for e in entities.scalars():
            self._en_to_canonical[e.name_en.lower()] = e.canonical_id
            if e.name_ne:
                self._ne_to_canonical[e.name_ne] = e.canonical_id
            if e.aliases:
                for alias in e.aliases:
                    if self._is_devanagari(alias):
                        self._ne_to_canonical[alias] = e.canonical_id
                    else:
                        self._en_to_canonical[alias.lower()] = e.canonical_id

    def get_canonical(self, text: str) -> Optional[str]:
        """Get canonical ID for text (English or Nepali)."""
        if self._is_devanagari(text):
            return self._ne_to_canonical.get(text)
        else:
            return self._en_to_canonical.get(text.lower())
```

---

## Phase 5: Integration & API (Priority: Medium)

### 5.1 Unified Entity Extractor

**File:** `backend-v5/app/services/nlp/database_entity_extractor.py`

```python
"""
Database-Driven Entity Extractor - Production implementation.
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class ExtractedEntity:
    """Final extracted entity with full metadata."""
    text: str
    canonical_id: str
    entity_type: str  # PERSON, ORGANIZATION, LOCATION
    confidence: float
    start: int
    end: int
    metadata: Dict[str, Any]  # party, constituency, role, etc.

class DatabaseEntityExtractor:
    """
    Production entity extractor using database patterns.

    Features:
    - 6,600+ patterns from election/parliament database
    - Aho-Corasick O(n) matching
    - Context-based confidence scoring
    - Cross-lingual canonical resolution
    - False positive reduction via boundary validation
    """

    def __init__(self):
        self._index_generator = EntityIndexGenerator()
        self._matcher = AhoCorasickEntityMatcher()
        self._boundary_validator = BoundaryValidator()
        self._context_scorer = ContextScorer()
        self._overlap_resolver = OverlapResolver()
        self._disambiguator = EntityDisambiguator()
        self._cross_lingual = CrossLingualLinker()
        self._initialized = False

    async def initialize(self, session: AsyncSession):
        """
        Initialize entity extractor from database.
        Should be called on application startup.
        """
        if self._initialized:
            return

        # Generate patterns from database
        person_patterns = await self._index_generator.generate_person_patterns(session)
        org_patterns = await self._index_generator.generate_organization_patterns(session)
        loc_patterns = await self._index_generator.generate_location_patterns(session)

        all_patterns = {**person_patterns, **org_patterns, **loc_patterns}

        # Build Aho-Corasick automaton
        self._matcher.build_from_patterns(all_patterns)

        # Build cross-lingual index
        await self._cross_lingual.build_index(session)

        self._initialized = True
        logger.info(f"Entity extractor initialized with {len(all_patterns)} patterns")

    async def extract(
        self,
        text: str,
        min_confidence: float = 0.6,
        session: Optional[AsyncSession] = None,
    ) -> List[ExtractedEntity]:
        """
        Extract entities from text.

        Args:
            text: Input text (English or Nepali)
            min_confidence: Minimum confidence threshold
            session: Database session for disambiguation

        Returns:
            List of ExtractedEntity with canonical IDs
        """
        if not self._initialized:
            raise RuntimeError("Entity extractor not initialized")

        # Step 1: Find all pattern matches (O(n))
        raw_matches = self._matcher.find_all_matches(text)

        # Step 2: Validate word boundaries
        valid_matches = [
            m for m in raw_matches
            if self._boundary_validator.is_valid_boundary(text, m)
        ]

        # Step 3: Score with context
        for match in valid_matches:
            match.raw_confidence = self._context_scorer.score_with_context(match, text)

        # Step 4: Resolve overlaps
        non_overlapping = self._overlap_resolver.resolve_overlaps(valid_matches)

        # Step 5: Disambiguate and create final entities
        entities = []
        for match in non_overlapping:
            if match.raw_confidence < min_confidence:
                continue

            # Get canonical ID (with disambiguation if needed)
            if session:
                canonical_id, confidence = await self._disambiguator.disambiguate(
                    match, text, session
                )
            else:
                canonical_id = match.pattern.canonical_id
                confidence = match.raw_confidence

            entities.append(ExtractedEntity(
                text=match.text,
                canonical_id=canonical_id,
                entity_type=match.pattern.entity_type,
                confidence=confidence,
                start=match.start,
                end=match.end,
                metadata=match.pattern.context_hints or {},
            ))

        return entities

    async def refresh_patterns(self, session: AsyncSession):
        """
        Refresh patterns from database.
        Call when election/parliament data is updated.
        """
        self._initialized = False
        await self.initialize(session)
```

### 5.2 Integration with Existing Pipeline

**File:** Update `backend-v5/app/services/nlp/hybrid_ner.py`

```python
class HybridNER:
    """
    Updated to use DatabaseEntityExtractor as primary source.
    Falls back to transformer NER for unknown entities.
    """

    def __init__(self):
        self.db_extractor = DatabaseEntityExtractor()
        self.transformer_ner = TransformerNER()  # Fallback
        self._initialized = False

    async def initialize(self, session: AsyncSession):
        """Initialize database-driven extractor."""
        await self.db_extractor.initialize(session)
        self._initialized = True

    async def extract_entities(
        self,
        text: str,
        session: Optional[AsyncSession] = None,
    ) -> List[Dict[str, Any]]:
        """
        Extract entities using hybrid approach.

        Priority:
        1. Database patterns (high confidence, canonical IDs)
        2. Transformer NER (for unknown entities)
        """
        if not self._initialized:
            # Fallback to transformer-only
            return self.transformer_ner.extract_entities(text)

        # Primary: Database-driven extraction
        db_entities = await self.db_extractor.extract(text, session=session)

        # Convert to dict format
        entities = [
            {
                "text": e.text,
                "type": e.entity_type,
                "canonical_id": e.canonical_id,
                "confidence": e.confidence,
                "start": e.start,
                "end": e.end,
                "source": "database",
                "metadata": e.metadata,
            }
            for e in db_entities
        ]

        # Secondary: Transformer NER for gaps
        transformer_entities = self.transformer_ner.extract_entities(text)

        # Add transformer entities that don't overlap with DB entities
        db_spans = {(e["start"], e["end"]) for e in entities}
        for t_ent in transformer_entities:
            t_start, t_end = t_ent.get("start", 0), t_ent.get("end", 0)
            overlaps = any(
                not (t_end <= db_start or t_start >= db_end)
                for db_start, db_end in db_spans
            )
            if not overlaps:
                t_ent["source"] = "transformer"
                t_ent["confidence"] *= 0.8  # Slightly lower confidence
                entities.append(t_ent)

        return sorted(entities, key=lambda e: e.get("start", 0))
```

---

## Phase 6: Sync & Maintenance (Priority: Medium)

### 6.1 Periodic Refresh Job

**File:** `backend-v5/app/workers/tasks/entity_index_refresh.py`

```python
from celery import shared_task
from app.services.nlp.database_entity_extractor import DatabaseEntityExtractor

@shared_task
async def refresh_entity_index():
    """
    Refresh entity patterns from database.
    Run after election data imports or KB updates.
    """
    async with get_session() as session:
        extractor = DatabaseEntityExtractor()
        await extractor.refresh_patterns(session)

        logger.info("Entity index refreshed successfully")
        return {"status": "refreshed", "patterns": extractor.pattern_count}
```

### 6.2 Startup Initialization

**File:** Update `backend-v5/app/main.py`

```python
from app.services.nlp.hybrid_ner import HybridNER

# Global singleton
entity_extractor: Optional[HybridNER] = None

@app.on_event("startup")
async def startup():
    global entity_extractor

    # Initialize database-driven entity extractor
    async with get_session() as session:
        entity_extractor = HybridNER()
        await entity_extractor.initialize(session)
        logger.info("Entity extractor initialized on startup")
```

---

## Implementation Checklist

### Week 1: Core Infrastructure
- [ ] Create `entity_index_generator.py` with DB queries
- [ ] Implement `aho_corasick_matcher.py` with pyahocorasick
- [ ] Add boundary validation for English and Nepali
- [ ] Write unit tests for pattern matching

### Week 2: Validation & Scoring
- [ ] Implement `ContextScorer` with boost keywords
- [ ] Create `OverlapResolver` for conflict resolution
- [ ] Build `EntityDisambiguator` with context clues
- [ ] Add cross-lingual linking

### Week 3: Integration
- [ ] Create `DatabaseEntityExtractor` unified class
- [ ] Update `HybridNER` to use database extractor
- [ ] Add startup initialization in `main.py`
- [ ] Create refresh Celery task

### Week 4: Testing & Tuning
- [ ] Run on real stories from database
- [ ] Measure precision/recall/F1
- [ ] Tune confidence thresholds
- [ ] Document edge cases

---

## Expected Outcomes

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Pattern Count | ~200 | ~6,600 | 33x |
| Matching Speed | O(n×m) | O(n) | 100x |
| Person Recall | 60% | 95% | +58% |
| Person Precision | 70% | 92% | +31% |
| False Positive Rate | 15% | <3% | -80% |
| Cross-lingual | No | Yes | New |
| Canonical Linking | Partial | Full | Complete |

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Pattern explosion (memory) | Aho-Corasick is memory-efficient trie |
| Stale patterns | Periodic refresh job + manual trigger |
| Name collisions | Disambiguation by context + confidence penalty |
| Unicode issues | Separate English/Nepali automatons |
| Performance regression | O(n) guarantee regardless of pattern count |

---

## Dependencies

```txt
# requirements.txt additions
pyahocorasick>=2.0.0  # Aho-Corasick automaton
```

---

## Files to Create

| File | Priority | Description |
|------|----------|-------------|
| `app/services/nlp/entity_index_generator.py` | Critical | DB pattern generator |
| `app/services/nlp/aho_corasick_matcher.py` | Critical | Fast multi-pattern matcher |
| `app/services/nlp/boundary_validator.py` | Critical | Word boundary validation |
| `app/services/nlp/context_scorer.py` | High | Context-based scoring |
| `app/services/nlp/entity_disambiguator.py` | High | Name collision resolver |
| `app/services/nlp/database_entity_extractor.py` | High | Unified extractor |
| `app/workers/tasks/entity_index_refresh.py` | Medium | Celery refresh task |

---

## Conclusion

This plan transforms entity extraction from a static 200-pattern dictionary to a dynamic 6,600+ pattern system powered by the election and parliament databases. The Aho-Corasick algorithm ensures O(n) performance regardless of pattern count, while context-based scoring and disambiguation dramatically reduce false positives.

**Key innovations:**
1. **Database-driven patterns**: Auto-generated from 3 elections, 275 MPs, 165 constituencies
2. **O(n) matching**: 100x faster than current regex-based approach
3. **Cross-lingual resolution**: English and Nepali names link to same canonical entity
4. **Context disambiguation**: Uses party, constituency, role mentions to resolve name collisions
5. **Strict boundary validation**: Eliminates substring false positives
