from dataclasses import dataclass
from uuid import uuid4

from app.api.v1.alerts import _filter_stories_by_districts as filter_alert_stories
from app.api.v1.analytics import _filter_stories_by_districts as filter_analytics_stories
from app.api.v1.map import get_coordinates_for_province, normalize_province_name
from app.schemas.analytics import ConsolidatedStoryResponse


@dataclass
class _StoryStub:
    title: str
    districts: list[str] | None = None
    provinces: list[str] | None = None


def test_analytics_filter_includes_province_only_story():
    stories = [
        _StoryStub(title="Province update", districts=None, provinces=["Gandaki"]),
        _StoryStub(title="Kathmandu notice", districts=["Kathmandu"], provinces=["Bagmati"]),
    ]

    filtered = filter_analytics_stories(stories, ["Kaski", "Myagdi"])
    assert len(filtered) == 1
    assert filtered[0].provinces == ["Gandaki"]


def test_analytics_filter_does_not_use_title_only_province_fallback():
    stories = [
        _StoryStub(title="Gandaki ministers congratulate the new cabinet", districts=None, provinces=None),
        _StoryStub(title="Pokhara airport update", districts=["Kaski"], provinces=["Gandaki"]),
    ]

    filtered = filter_analytics_stories(stories, ["Kaski", "Myagdi"])
    assert len(filtered) == 1
    assert filtered[0].title == "Pokhara airport update"


def test_alert_filter_matches_district_variants_with_underscores():
    stories = [
        _StoryStub(title="Nawalparasi update", districts=["Nawalparasi_East"], provinces=["Gandaki"]),
    ]

    filtered = filter_alert_stories(stories, ["Nawalparasi East"])
    assert len(filtered) == 1


def test_map_province_normalization_and_coordinates():
    assert normalize_province_name(4) == "Gandaki"
    assert normalize_province_name("gandaki") == "Gandaki"
    assert get_coordinates_for_province("gandaki") is not None


def test_consolidated_story_response_preserves_geography():
    class _Story:
        id = uuid4()
        source_id = "source"
        source_name = "Source"
        title = "Pokhara update"
        summary = "Summary"
        url = "https://example.com/story"
        category = "security"
        categories = ["security"]
        severity = "medium"
        nepal_relevance = "NEPAL_DOMESTIC"
        published_at = None
        created_at = None
        districts = ["Kaski"]
        provinces = ["Gandaki"]
        relevance_score = 0.8
        cluster_id = None
        features = type(
            "_Features",
            (),
            {
                "geo_confidence": 0.8,
                "title_district": "kaski",
                "primary_municipality": "pokhara",
            },
        )()

    response = ConsolidatedStoryResponse.from_story(_Story())
    assert response.districts_affected == ["Kaski"]
    assert response.provinces_affected == ["Gandaki"]
    assert response.location_verified is True
    assert response.display_location == "Kaski"


def test_consolidated_story_response_suppresses_weak_geo_and_falls_back_to_kathmandu_for_politics():
    class _Story:
        id = uuid4()
        source_id = "gandaki_ratopati"
        source_name = "Ratopati Gandaki"
        title = "गृहमन्त्रीद्वारा एमाले कार्यकर्ताबाट दुर्व्यवहारमा परेका वृद्धसँग भेट"
        summary = "Political update"
        url = "https://example.com/story"
        category = "political"
        categories = ["politics"]
        severity = "medium"
        nepal_relevance = "NEPAL_DOMESTIC"
        published_at = None
        created_at = None
        districts = ["Kaski"]
        provinces = ["Gandaki"]
        relevance_score = 0.8
        cluster_id = None
        features = type(
            "_Features",
            (),
            {
                "geo_confidence": 0.2,
                "title_district": None,
                "primary_municipality": None,
            },
        )()

    response = ConsolidatedStoryResponse.from_story(_Story())
    assert response.districts_affected == []
    assert response.provinces_affected == []
    assert response.location_verified is False
    assert response.display_location == "Kathmandu"


def test_consolidated_story_response_does_not_treat_gorkhapatra_as_gorkha():
    class _Story:
        id = uuid4()
        source_id = "gorkhapatra"
        source_name = "Gorkhapatra"
        title = "कार्यस्थलमा अधिक तापको मापदण्ड लागु"
        summary = "गोरखापत्र समाचारदाता काठमाडौँ, चैत १८ गते । सरकारले श्रमिकको स्वास्थ्य र सुरक्षालाई ध्यानमा राखेर मापदण्ड स्वीकृत गरेको छ ।"
        content = None
        url = "https://example.com/story"
        category = "security"
        categories = ["security"]
        severity = "medium"
        nepal_relevance = "NEPAL_DOMESTIC"
        published_at = None
        created_at = None
        districts = ["Gorkha"]
        provinces = ["Gandaki"]
        relevance_score = 0.8
        cluster_id = None
        features = type(
            "_Features",
            (),
            {
                "geo_confidence": 0.8,
                "title_district": "gorkha",
                "primary_municipality": None,
            },
        )()

    response = ConsolidatedStoryResponse.from_story(_Story())
    assert response.districts_affected == []
    assert response.provinces_affected == []
    assert response.location_verified is False
    assert response.display_location == "Kathmandu"


def test_consolidated_story_response_does_not_lazy_load_features():
    class _Story:
        id = uuid4()
        source_id = "source"
        source_name = "Source"
        title = "Economic update"
        summary = "Kathmandu trade update"
        content = None
        url = "https://example.com/story"
        category = "economic"
        categories = ["economy"]
        severity = "medium"
        nepal_relevance = "NEPAL_DOMESTIC"
        published_at = None
        created_at = None
        districts = ["Kathmandu"]
        provinces = ["Bagmati"]
        relevance_score = 0.8
        cluster_id = None

        @property
        def features(self):
            raise AssertionError("features lazy load should not be triggered")

    response = ConsolidatedStoryResponse.from_story(_Story())
    assert response.districts_affected == ["Kathmandu"]
    assert response.provinces_affected == []
    assert response.display_location == "Kathmandu"
