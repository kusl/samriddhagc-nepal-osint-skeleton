from types import SimpleNamespace

from app.services.parliament_scorer import PerformanceScorer


def test_participation_uses_available_attendance_sources_only():
    scorer = PerformanceScorer(db=None)
    mp = SimpleNamespace(session_attendance_pct=100.0, committee_attendance_pct=None)

    score = scorer._calc_participation(mp)

    assert score == 100.0


def test_participation_blends_session_and_committee_when_both_exist():
    scorer = PerformanceScorer(db=None)
    mp = SimpleNamespace(session_attendance_pct=100.0, committee_attendance_pct=50.0)

    score = scorer._calc_participation(mp)

    assert round(score, 2) == 85.0
