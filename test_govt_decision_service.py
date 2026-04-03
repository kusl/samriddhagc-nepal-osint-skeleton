from datetime import datetime, timezone

from app.services.govt_decision_service import GovtDecisionService


def test_candidate_gate_accepts_real_decision_language():
    text = (
        "The cabinet decided to implement the Karki Commission report and instructed the Home Ministry "
        "to form a study committee for security recommendations."
    )
    assert GovtDecisionService._is_candidate_text(text) is True


def test_candidate_gate_rejects_speech_only_language():
    text = (
        "The prime minister addressed party workers and said the government would work in the public interest "
        "during a rally in Kathmandu."
    )
    assert GovtDecisionService._is_candidate_text(text) is False


def test_candidate_gate_rejects_generic_office_assumption_story():
    text = (
        "The minister assumed office at Singha Durbar after taking the oath and met ministry staff after the ceremony."
    )
    assert GovtDecisionService._is_candidate_text(text) is False


def test_event_key_extracts_actor_action_and_bucket():
    event_key, actor, action = GovtDecisionService._build_event_key(
        title="Finance Ministry orders repeal process for 15 laws",
        summary="The ministry instructed officials to begin repeal and reform work.",
        published_at=datetime(2026, 3, 27, 12, 0, tzinfo=timezone.utc),
    )
    assert actor == "finance_ministry"
    assert action == "ordered"
    assert event_key.startswith("finance_ministry:ordered:20260327:")


def test_public_item_match_collapses_betting_shutdown_rewrites():
    left = {
        "title": "Directive to Close Online Betting Apps and Websites within 24 Hours",
        "office": "Ministry of Communication and Information Technology",
        "implementingMinistry": "Ministry of Communication and Information Technology",
        "decisionType": "Administrative Order",
        "decision": "The ministry instructed the regulator to shut down betting applications within 24 hours.",
        "publishedAt": datetime(2026, 3, 29, 10, 0, tzinfo=timezone.utc),
    }
    right = {
        "title": "Government decides to shut down betting apps and websites within 24 hours",
        "office": "Cabinet",
        "implementingMinistry": "Ministry of Communication and Information Technology",
        "decisionType": "Cabinet Decision",
        "decision": "The government decided to shut down betting apps and related websites within 24 hours.",
        "publishedAt": datetime(2026, 3, 30, 9, 0, tzinfo=timezone.utc),
    }
    assert GovtDecisionService._public_items_match(left, right) is True


def test_public_item_match_collapses_duplicate_court_treatment_orders():
    left = {
        "title": "Court orders government to arrange treatment for former PM Oli",
        "office": "Kathmandu District Court",
        "implementingMinistry": None,
        "decisionType": "Administrative Order",
        "decision": "The court ordered the government to ensure treatment for KP Sharma Oli.",
        "publishedAt": datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc),
    }
    right = {
        "title": "Court Orders Effective Treatment for UML Chairman KP Oli",
        "office": "District Court Kathmandu",
        "implementingMinistry": None,
        "decisionType": "Administrative Order",
        "decision": "The District Court Kathmandu ordered effective treatment arrangements for KP Oli in custody.",
        "publishedAt": datetime(2026, 3, 28, 14, 0, tzinfo=timezone.utc),
    }
    assert GovtDecisionService._public_items_match(left, right) is True
