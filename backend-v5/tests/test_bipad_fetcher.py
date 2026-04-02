import asyncio

from app.ingestion.bipad_fetcher import BIPADFetcher
from app.models.disaster import BIPAD_HAZARD_MAP, HazardType


def test_bipad_hazard_map_covers_recent_warning_types():
    assert BIPAD_HAZARD_MAP[12] == HazardType.FOREST_FIRE
    assert BIPAD_HAZARD_MAP[14] == HazardType.HEAVY_RAINFALL
    assert BIPAD_HAZARD_MAP[24] == HazardType.WINDSTORM
    assert BIPAD_HAZARD_MAP[37] == HazardType.POLLUTION


def test_parse_realtime_alert_normalizes_flood_warning():
    fetcher = BIPADFetcher()
    alert = fetcher._parse_realtime_alert({
        "id": 43007,
        "title": "Flood warning at Shailyashikhar-2, Darchula",
        "description": "Basin:Mahakali\nWarning level:2.75\nWater level:100007.179688",
        "referenceType": "river",
        "createdOn": "2026-03-16T14:35:12.497925+05:45",
        "startedOn": "2026-03-16T14:20:00+05:45",
        "expireOn": "2026-03-16T14:45:06.376379+05:45",
        "point": {"type": "Point", "coordinates": [80.0, 29.0]},
        "source": "dhm",
    })

    assert alert is not None
    assert alert.alert_type == "flood"
    assert alert.alert_level == "high"
    assert alert.location_name == "Shailyashikhar-2"
    assert alert.district == "Darchula"


def test_parse_realtime_alert_normalizes_pollution_alert():
    fetcher = BIPADFetcher()
    alert = fetcher._parse_realtime_alert({
        "id": 42936,
        "title": "Pollution Alert at Falgunanda-3, Panchthar",
        "description": "AQI value is greater than 150",
        "referenceType": "pollution",
        "createdOn": "2026-03-12T20:09:07.753058+05:45",
        "startedOn": "2026-03-12T19:42:00.010000+05:45",
        "point": {"type": "Point", "coordinates": [87.0, 27.0]},
        "source": "doe",
    })

    assert alert is not None
    assert alert.alert_type == "pollution"
    assert alert.alert_level == "high"
    assert alert.location_name == "Falgunanda-3"
    assert alert.district == "Panchthar"


def test_fetch_alerts_uses_large_alert_window_for_pollution_rows(monkeypatch):
    class FakeResponse:
        def __init__(self, payload):
            self.status_code = 200
            self.payload = payload

        def json(self):
            return self.payload

    class FakeRequestsGet:
        def __init__(self):
            self.calls = 0
            self.params = []

        def __call__(self, _endpoint, params=None, timeout=None):
            self.calls += 1
            self.params.append(params)
            results = [
                {
                    "id": 43007,
                    "title": "Flood warning at Shailyashikhar-2, Darchula",
                    "description": "Basin:Mahakali",
                    "referenceType": "river",
                    "createdOn": "2026-03-16T14:35:12.497925+05:45",
                    "startedOn": "2026-03-16T14:20:00+05:45",
                },
            ]
            if self.calls >= 2:
                results.append({
                    "id": 42936,
                    "title": "Pollution Alert at Falgunanda-3, Panchthar",
                    "description": "AQI value is greater than 150",
                    "referenceType": "pollution",
                    "createdOn": "2026-03-12T20:09:07.753058+05:45",
                    "startedOn": "2026-03-12T19:42:00.010000+05:45",
                })
            results.append({
                "id": 89,
                "title": "Pollution Alert at Old Site",
                "description": "AQI value is greater than 150",
                "referenceType": "pollution",
                "createdOn": "2020-01-23T18:14:34.332719+05:45",
                "startedOn": "2020-01-23T18:14:34.332719+05:45",
            })
            return FakeResponse({
                "count": 300,
                "results": results,
            })

    fetcher = BIPADFetcher()
    fetcher._semaphore = asyncio.Semaphore(1)
    fake_get = FakeRequestsGet()
    monkeypatch.setattr("app.ingestion.bipad_fetcher.requests.get", fake_get)

    result = asyncio.run(fetcher.fetch_alerts(limit=10, days_back=7))

    assert result.success is True
    assert fake_get.calls == 2
    assert fake_get.params == [
        {"limit": 300, "ordering": "-createdOn"},
        {"limit": 300, "ordering": "-createdOn"},
    ]
    assert result.alerts[0].bipad_id == 43007
    assert any(alert.bipad_id == 42936 and alert.alert_type == "pollution" for alert in result.alerts)
