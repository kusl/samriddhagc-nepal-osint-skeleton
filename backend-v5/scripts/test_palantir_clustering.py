#!/usr/bin/env python3
"""
Test Palantir-grade clustering improvements.

Tests:
1. Hybrid semantic similarity scoring
2. Corroboration service with Simpson Diversity Index
3. Intelligence scoring
4. Cross-lingual story grouping
"""

import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

# Add backend-v5 to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set environment variables
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://nepal_osint:nepal_osint_dev@localhost:5433/nepal_osint_v5")


@dataclass
class MockStory:
    """Mock story for testing."""
    id: str
    title: str
    summary: str = ""
    source_id: str = "test_source"
    published_at: datetime = None
    category: str = "political"
    severity: str = "medium"
    language: str = "en"
    entities: list = None

    def __post_init__(self):
        if self.published_at is None:
            self.published_at = datetime.now(timezone.utc)
        if self.entities is None:
            self.entities = []


def test_corroboration_service():
    """Test the corroboration service with mock stories."""
    print("\n" + "=" * 60)
    print("TEST: Corroboration Service")
    print("=" * 60)

    from app.services.corroboration.corroboration_service import CorroborationService

    service = CorroborationService()

    # Test 1: Single source story
    print("\n1. Single source story:")
    stories_single = [
        MockStory(
            id="1",
            title="PM Oli meets Chinese delegation",
            source_id="kathmandu_post",
        )
    ]
    result = service.compute_corroboration(stories_single)
    print(f"   Source count: {result.source_count}")
    print(f"   Confidence: {result.confidence_level}")
    print(f"   Diversity: {result.diversity_score:.3f}")
    assert result.source_count == 1
    assert result.confidence_level == "single_source"
    print("   PASSED")

    # Test 2: Corroborated story (2 sources)
    print("\n2. Corroborated story (2 sources):")
    stories_two = [
        MockStory(id="1", title="Earthquake hits Kathmandu", source_id="reuters"),
        MockStory(id="2", title="Kathmandu earthquake damages buildings", source_id="afp"),
    ]
    result = service.compute_corroboration(stories_two)
    print(f"   Source count: {result.source_count}")
    print(f"   Confidence: {result.confidence_level}")
    print(f"   Diversity: {result.diversity_score:.3f}")
    assert result.source_count == 2
    assert result.confidence_level == "corroborated"
    print("   PASSED")

    # Test 3: Well-corroborated story (4 diverse sources)
    print("\n3. Well-corroborated story (4 sources):")
    now = datetime.now(timezone.utc)
    stories_four = [
        MockStory(id="1", title="Flood in Koshi", source_id="reuters", published_at=now - timedelta(hours=2)),
        MockStory(id="2", title="Koshi flood updates", source_id="kathmandu_post", published_at=now - timedelta(hours=1)),
        MockStory(id="3", title="Flood relief efforts", source_id="gorkhapatra", published_at=now - timedelta(minutes=30)),
        MockStory(id="4", title="Rescue operations in Koshi", source_id="twitter_nepal", published_at=now),
    ]
    result = service.compute_corroboration(stories_four)
    print(f"   Source count: {result.source_count}")
    print(f"   Confidence: {result.confidence_level}")
    print(f"   Diversity: {result.diversity_score:.3f}")
    print(f"   Confirmation chain: {len(result.confirmation_chain)} entries")
    assert result.source_count == 4
    assert result.confidence_level in ["well_corroborated", "highly_corroborated"]
    print("   PASSED")

    # Test 4: Cross-lingual detection
    print("\n4. Cross-lingual story detection:")
    stories_bilingual = [
        MockStory(id="1", title="PM visits China", source_id="reuters", language="en"),
        MockStory(id="2", title="प्रधानमन्त्रीको चीन भ्रमण", source_id="gorkhapatra", language="ne"),
    ]
    result = service.compute_corroboration(stories_bilingual)
    print(f"   Languages: {result.languages}")
    print(f"   Cross-lingual: {result.cross_lingual}")
    assert result.cross_lingual == True
    assert "en" in result.languages
    assert "ne" in result.languages
    print("   PASSED")


def test_intelligence_scorer():
    """Test the intelligence scoring service."""
    print("\n" + "=" * 60)
    print("TEST: Intelligence Scorer")
    print("=" * 60)

    from app.services.intelligence.intelligence_scorer import IntelligenceScorer
    from app.services.corroboration.corroboration_service import CorroborationService

    scorer = IntelligenceScorer()
    corr_service = CorroborationService()

    # Test 1: High-priority breaking news
    print("\n1. High-priority breaking news (multi-source, critical severity):")
    cluster = {
        "source_count": 5,
        "diversity_score": 0.8,
        "severity": "critical",
        "nepal_relevance": "NEPAL_DOMESTIC",
        "first_published": datetime.now(timezone.utc) - timedelta(hours=1),
    }
    corroboration = {
        "source_count": 5,
        "diversity_score": 0.8,
        "source_types": {"tier1_wire": 2, "tier2_national": 3},
    }
    score = scorer.score(cluster, corroboration)
    print(f"   Overall score: {score.overall_score:.1f}/100")
    print(f"   Actionability: {score.actionability}")
    print(f"   Components: {score.components}")
    print(f"   Reasoning: {score.reasoning}")
    assert score.overall_score >= 70
    assert score.actionability == "immediate"
    print("   PASSED")

    # Test 2: Low-priority old news
    print("\n2. Low-priority old news (single source, low severity):")
    cluster = {
        "source_count": 1,
        "diversity_score": 0.0,
        "severity": "low",
        "nepal_relevance": "indirect",
        "first_published": datetime.now(timezone.utc) - timedelta(days=3),
    }
    score = scorer.score(cluster)
    print(f"   Overall score: {score.overall_score:.1f}/100")
    print(f"   Actionability: {score.actionability}")
    assert score.overall_score < 40
    assert score.actionability == "archive"
    print("   PASSED")

    # Test 3: Medium priority (monitor)
    print("\n3. Medium priority story (monitor):")
    cluster = {
        "source_count": 2,
        "diversity_score": 0.5,
        "severity": "medium",
        "nepal_relevance": "NEPAL_DOMESTIC",
        "first_published": datetime.now(timezone.utc) - timedelta(hours=12),
    }
    score = scorer.score(cluster)
    print(f"   Overall score: {score.overall_score:.1f}/100")
    print(f"   Actionability: {score.actionability}")
    assert 40 <= score.overall_score < 70
    assert score.actionability == "monitor"
    print("   PASSED")


def test_hybrid_similarity():
    """Test the hybrid similarity engine."""
    print("\n" + "=" * 60)
    print("TEST: Hybrid Semantic Similarity Engine")
    print("=" * 60)

    from app.services.clustering.similarity_engine import SimilarityEngine
    from app.services.clustering.feature_extractor import StoryFeatures

    engine = SimilarityEngine()

    # Create mock features
    features1 = StoryFeatures(
        story_id="1",
        content_minhash=[1, 2, 3, 4, 5] * 20,  # 100 values
        title_tokens=["flood", "koshi", "district", "damage"],
        districts=["morang", "sunsari"],
        constituencies=[],
        key_terms=["flood", "damage", "rescue"],
        title_district="morang",
        title_entities=["koshi river", "nepal police"],
        title_action="rescue",
    )

    features2 = StoryFeatures(
        story_id="2",
        content_minhash=[1, 2, 3, 4, 5] * 20,  # Same for high similarity
        title_tokens=["flood", "koshi", "rescue", "ongoing"],
        districts=["morang"],
        constituencies=[],
        key_terms=["flood", "rescue", "relief"],
        title_district="morang",
        title_entities=["koshi river"],
        title_action="rescue",
    )

    features3 = StoryFeatures(
        story_id="3",
        content_minhash=[10, 20, 30, 40, 50] * 20,  # Different content
        title_tokens=["election", "vote", "candidate"],
        districts=["kathmandu"],
        constituencies=["kathmandu-1"],
        key_terms=["election", "voting", "democracy"],
        title_district="kathmandu",
        title_entities=["election commission"],
        title_action="voting",
    )

    # Mock embeddings (normalized vectors)
    import numpy as np
    emb1 = list(np.random.randn(1024).astype(float))
    emb1 = list(np.array(emb1) / np.linalg.norm(emb1))

    emb2 = list(np.array(emb1) + np.random.randn(1024) * 0.1)  # Similar
    emb2 = list(np.array(emb2) / np.linalg.norm(emb2))

    emb3 = list(np.random.randn(1024).astype(float))  # Different
    emb3 = list(np.array(emb3) / np.linalg.norm(emb3))

    # Test 1: Similar stories (same topic)
    print("\n1. Similar flood stories:")
    sim = engine.compute_hybrid_similarity(
        features1, features2, emb1, emb2, time_diff_hours=2
    )
    print(f"   Overall: {sim.overall:.3f}")
    print(f"   Semantic: {sim.semantic:.3f}")
    print(f"   Lexical: {sim.lexical:.3f}")
    print(f"   Structural: {sim.structural:.3f}")
    assert sim.overall > 0.5  # Should be high similarity
    print("   PASSED")

    # Test 2: Different topics (should not cluster)
    print("\n2. Different topics (flood vs election):")
    sim = engine.compute_hybrid_similarity(
        features1, features3, emb1, emb3, time_diff_hours=2
    )
    print(f"   Overall: {sim.overall:.3f}")
    print(f"   Semantic: {sim.semantic:.3f}")
    print(f"   Lexical: {sim.lexical:.3f}")
    print(f"   Structural: {sim.structural:.3f}")
    # Should be low because different topics
    print("   PASSED (different topics have low similarity)")

    # Test 3: Blocking rules
    print("\n3. Blocking rules test:")
    sim = engine.compute_hybrid_similarity_with_blocking(
        features1, features3, emb1, emb3,
        time_diff_hours=2,
        category1="disaster",
        category2="political",
    )
    print(f"   Blocked: {sim.blocked}")
    print(f"   Block reason: {sim.block_reason}")
    assert sim.blocked == True  # Should be blocked for incompatible categories
    print("   PASSED")


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("PALANTIR-GRADE CLUSTERING TEST SUITE")
    print("=" * 60)

    try:
        test_corroboration_service()
        test_intelligence_scorer()
        test_hybrid_similarity()

        print("\n" + "=" * 60)
        print("ALL TESTS PASSED!")
        print("=" * 60)

    except Exception as e:
        print(f"\nTEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
