from datetime import datetime, timezone
from uuid import uuid4

from app.api.v1.analytics import _build_story_tracker_fallback_entries


def test_story_tracker_fallback_entries_are_built_from_cluster_rows():
    cluster_id = uuid4()
    now = datetime.now(timezone.utc)

    entries = _build_story_tracker_fallback_entries([
        {
            "cluster_id": cluster_id,
            "headline": "Coalition dispute widens after cabinet reshuffle",
            "category": "political",
            "severity": "high",
            "story_count": 4,
            "source_count": 3,
            "first_published": now,
            "last_updated": now,
            "bluf": "Cabinet changes triggered a broader coalition dispute.",
            "development_stage": "developing",
            "urgency_score": 47.5,
            "primary_district": "Kathmandu",
            "primary_province": "Bagmati",
            "primary_municipality": None,
            "main_entities": ["KP Sharma Oli", "Cabinet"],
        }
    ])

    assert len(entries) == 1

    entry = entries[0]
    assert entry.label == "Coalition dispute widens after cabinet reshuffle"
    assert entry.direction == "rising"
    assert entry.cluster_count == 1
    assert entry.momentum_score == 47.5
    assert entry.lead_regions == ["Kathmandu", "Bagmati"]
    assert entry.lead_entities == ["KP Sharma Oli", "Cabinet"]
    assert len(entry.clusters) == 1
    assert entry.clusters[0].cluster_id == cluster_id
    assert entry.clusters[0].similarity_score == 1.0
