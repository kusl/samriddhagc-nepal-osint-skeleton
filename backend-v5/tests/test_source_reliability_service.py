from types import SimpleNamespace

from app.models.annotation import SourceReliability
from app.services.source_reliability_service import SourceReliabilityScoringService


def test_provisional_sources_are_capped_below_a():
    assert SourceReliabilityScoringService.map_reliability_letter(0.93, provisional=False) == "A"
    assert SourceReliabilityScoringService.map_reliability_letter(0.93, provisional=True) == "B"


def test_restore_automated_rating_restores_saved_profile():
    source = SourceReliability(
        source_id="demo",
        source_name="Demo",
        source_type="rss",
        reliability_rating="D",
        credibility_rating=4,
        confidence_score=55,
        notes="Manual override",
        automation_metrics={
            "automated_rating": {
                "reliability_rating": "B",
                "credibility_rating": 2,
                "confidence_score": 83,
                "notes": "Automated profile restored",
            }
        },
    )

    SourceReliabilityScoringService.restore_automated_rating(source)

    assert source.reliability_rating == "B"
    assert source.credibility_rating == 2
    assert source.confidence_score == 83
    assert source.notes == "Automated profile restored"


def test_story_signal_estimator_rewards_corroborated_primary_reporting():
    corroborated_story = SimpleNamespace(
        title="Ministry press release confirms budget decision",
        summary="The ministry published a notice and transcript with quoted officials.",
        content='The ministry press release included a transcript, court filing references, and "official" quotes.',
        source_count=4,
        story_count=6,
        confidence_level="well_corroborated",
    )
    pickup_story = SimpleNamespace(
        title="Huge chaos! What happened next?",
        summary="According to reports, the viral story spread online.",
        content="As reported by agency sources, the article was reposted without documents.",
        source_count=1,
        story_count=1,
        confidence_level="single_source",
    )

    corroborated = SourceReliabilityScoringService.estimate_story_signals(corroborated_story, "rss")
    pickup = SourceReliabilityScoringService.estimate_story_signals(pickup_story, "wire")

    assert corroborated["corroboration_strength"] > pickup["corroboration_strength"]
    assert corroborated["evidence_quality"] > pickup["evidence_quality"]
    assert corroborated["primary_proximity"] > pickup["primary_proximity"]
    assert corroborated["aggregation_penalty"] < pickup["aggregation_penalty"]
