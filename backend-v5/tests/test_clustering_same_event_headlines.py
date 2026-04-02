from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.services.clustering.clustering_service import ClusteringService, ClusterCandidate
from app.services.clustering.blocking import BlockingRules, HierarchicalBlocker
from app.services.clustering.feature_extractor import get_feature_extractor
from app.services.clustering.similarity_engine import HybridSimilarityScore


def _candidate(title: str, hours_ago: int = 0) -> ClusterCandidate:
    extractor = get_feature_extractor()
    published_at = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return ClusterCandidate(
        id=uuid4(),
        title=title,
        summary=None,
        content=None,
        category="disaster",
        severity="critical",
        source_id="test",
        published_at=published_at,
        language="ne",
        features=extractor.extract(title=title, story_id=str(uuid4()), published_at=published_at),
        embedding=None,
    )


def test_same_event_headline_score_detects_palpa_tipper_rewrites():
    story1 = _candidate("पाल्पामा टिपर दुर्घटना : मृतकको सङ्ख्या चार पुग्यो", hours_ago=1)
    story2 = _candidate("पाल्पा टिपर दुर्घटना : चालकसहित चारको मृत्यु", hours_ago=2)

    score = ClusteringService._compute_same_event_headline_score(story1, story2)

    assert score >= 0.78


def test_force_merge_accepts_near_duplicate_disaster_titles_without_strong_semantics():
    service = ClusteringService(db=None)
    story1 = _candidate("पाल्पामा टिपर दुर्घटना, चार जनाको मृत्यु", hours_ago=1)
    story2 = _candidate("पाल्पामा भएको टिपर दुर्घटनामा ज्यान गुमाउनेको संख्या ४ पुग्यो", hours_ago=2)
    similarity = HybridSimilarityScore(
        overall=0.58,
        semantic=0.41,
        lexical=0.54,
        structural=0.57,
        entity_overlap=0.42,
        geo_similarity=1.0,
        temporal_proximity=0.96,
    )

    assert service._should_force_merge_high_precision_pair(story1, story2, similarity) is True


def test_feature_extractor_normalizes_nepali_districts_to_canonical_location_fields():
    extractor = get_feature_extractor()

    features = extractor.extract(
        title="पाल्पामा टिपर दुर्घटना हुँदा ४ जनाको मृत्यु",
        summary=None,
        content=None,
        story_id=str(uuid4()),
        published_at=datetime.now(timezone.utc),
    )

    assert "palpa" in features.districts
    assert features.title_district == "palpa"
    assert features.primary_province == "lumbini"


def test_feature_extractor_normalizes_nepali_city_mentions():
    extractor = get_feature_extractor()

    features = extractor.extract(
        title="काठमाडौं महानगरपालिकाले नयाँ ट्राफिक योजना लागू गर्‍यो",
        summary=None,
        content=None,
        story_id=str(uuid4()),
        published_at=datetime.now(timezone.utc),
    )

    assert "kathmandu" in features.municipalities
    assert features.primary_municipality == "kathmandu"
    assert features.primary_province == "bagmati"


def test_feature_extractor_does_not_match_gorkhapatra_as_gorkha():
    extractor = get_feature_extractor()

    features = extractor.extract(
        title="कार्यस्थलमा अधिक तापको मापदण्ड लागु",
        summary="गोरखापत्र समाचारदाता काठमाडौँ, चैत १८ गते । सरकारले मापदण्ड स्वीकृत गरेको छ ।",
        content=None,
        story_id=str(uuid4()),
        published_at=datetime.now(timezone.utc),
    )

    assert "gorkha" not in features.districts
    assert features.title_district is None


def test_same_event_headline_score_handles_city_vs_district_rewrites():
    story1 = _candidate("एमाले अध्यक्ष केपी शर्मा ओलीको रिहाईको माग गर्दै धनुषामा प्रदर्शन", hours_ago=1)
    story2 = _candidate("ओली पक्राउको विरोधमा सडकमा उत्रिएको जनकपुर", hours_ago=2)

    score = ClusteringService._compute_same_event_headline_score(story1, story2)

    assert score >= 0.35


def test_blocker_generates_candidate_pairs_for_city_vs_district_same_event():
    now = datetime.now(timezone.utc)
    story1 = _candidate("जनकपुरधामको गंगासागरमा अतिक्रमण हटाउन चल्यो डोजर", hours_ago=1)
    story2 = _candidate("गङ्गासागर क्षेत्रबाट अतिक्रमित संरचना हटाउने अभियान तीव्र", hours_ago=2)

    blocker = HierarchicalBlocker()
    pairs = blocker.get_candidate_pairs([
        (story1.id, story1.features, "social", now),
        (story2.id, story2.features, "political", now - timedelta(hours=1)),
    ])

    normalized_pair = tuple(sorted((story1.id, story2.id), key=str))
    assert normalized_pair in pairs


def test_openai_pair_check_allows_same_entity_same_location_political_rewrites():
    service = ClusteringService(db=None)
    service.openai_runtime.api_key = "test"
    service.openai_runtime.settings.openai_clustering_enabled = True
    story1 = _candidate("एमाले अध्यक्ष केपी शर्मा ओलीको रिहाईको माग गर्दै धनुषामा प्रदर्शन", hours_ago=1)
    story2 = _candidate("ओली पक्राउको विरोधमा सडकमा उत्रिएको जनकपुर", hours_ago=2)
    similarity = HybridSimilarityScore(
        overall=0.44,
        semantic=0.31,
        lexical=0.29,
        structural=0.52,
        entity_overlap=0.60,
        geo_similarity=0.70,
        temporal_proximity=0.95,
    )

    assert service._should_run_openai_pair_check(story1, story2, similarity) is True


def test_blocking_rules_allow_social_political_same_event_when_geo_overlaps():
    story1 = _candidate("जनकपुरधामको गंगासागरमा अतिक्रमण हटाउन चल्यो डोजर", hours_ago=1)
    story2 = _candidate("गङ्गासागर क्षेत्रबाट अतिक्रमित संरचना हटाउने अभियान तीव्र", hours_ago=2)

    blocked, reason = BlockingRules().should_block_with_features(
        story1.features,
        story2.features,
        "social",
        "political",
        story1.published_at,
        story2.published_at,
    )

    assert blocked is False, reason
