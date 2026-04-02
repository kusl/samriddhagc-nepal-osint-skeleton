from datetime import date, datetime

from app.services.cabinet_action_service import CabinetActionService


def test_extract_pdf_items_expected_count_and_sections():
    service = CabinetActionService(db=None)  # type: ignore[arg-type]
    items = service._extract_pdf_items("/Users/samriddhagc/Downloads/१००-क्रियाकलापहरू-Final.pdf")

    assert len(items) == 100
    assert items[0].item_number == 1
    assert items[0].section_key == "shared-commitments"
    assert items[42].item_number == 43
    assert items[42].section_key == "good-governance-anticorruption"
    assert items[99].item_number == 100
    assert items[99].section_key == "strategic-social-security"


def test_parse_deadline_variants_from_source_language():
    service = CabinetActionService(db=None)  # type: ignore[arg-type]

    day_deadline = service._parse_deadline("मन्त्रालयले 15 दिनभित्र कार्ययोजना पेश गर्ने")
    assert day_deadline[1] == "days"
    assert day_deadline[2] == 15.0
    assert isinstance(day_deadline[3], date)

    week_deadline = service._parse_deadline("सम्बन्धित निकायले एक हप्ताभित्र विवरण अद्यावधिक गर्ने")
    assert week_deadline[1] == "weeks"
    assert week_deadline[2] == 1.0

    month_deadline = service._parse_deadline("समिति गठन गरी तीन महिनाभित्र प्रतिवेदन पेश गर्ने")
    assert month_deadline[1] == "months"
    assert month_deadline[2] == 3.0

    immediate_deadline = service._parse_deadline("सम्बन्धित निकायले तत्काल कार्यान्वयन गर्ने")
    assert immediate_deadline[1] == "immediate"
    assert immediate_deadline[2] == 0.0


def test_completed_signal_maps_late_status_against_due_date():
    due_date = date(2026, 4, 1)
    event_date = datetime(2026, 4, 4)
    assert (
        CabinetActionService._map_signal_to_status(
            "completed",
            due_date=due_date,
            event_date=event_date,
        )
        == "completed_late"
    )
