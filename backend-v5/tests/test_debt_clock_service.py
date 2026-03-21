from app.services.debt_clock_service import DebtClockService


SAMPLE_HTML = """
<html>
  <body>
    <div class="sub">Updated: <time id="updated-at" datetime="2026-03-20">March 20, 2026</time> - Data from IMF/World Bank/ECB</div>
    <script>
      window.__DC__ = {
        country: "Nepal",
        currency: "NPR",
        snapshot_year: 2024,
        population: 29136808,
        gdp_usd: 42914268286.71,
        gdp_lcy: 5738781077697.48,
        debt_gdp_pct: 44.278,
        debt_usd: 19001579711.99,
        debt_lcy: 2541017485582.89,
        interest_year_usd: 570047391.36,
        interest_year_lcy: 76230524567.49,
        flow_per_second_lcy: 2415.5995566041147,
        fx_usd_per_lcy: 0.00747794134428439,
        inflation_pct: 7.11476,
        inflation_year: 2023,
        gdp_growth_pct: 3.665374,
        gdp_growth_year: 2024,
        unemployment_pct: 10.706,
        unemployment_year: 2024,
        budget_balance_pct: -4.002867,
        budget_balance_year: 2021,
        series: { debt_gdp: {"2024":42.952} }
      };
    </script>
  </body>
</html>
"""


def test_parse_html_extracts_nepal_summary():
    summary = DebtClockService.parse_html(SAMPLE_HTML)

    assert summary["country"] == "Nepal"
    assert summary["currency_code"] == "NPR"
    assert summary["updated_at"] == "2026-03-20"
    assert summary["updated_label"] == "March 20, 2026"
    assert summary["snapshot_year"] == 2024
    assert summary["population"] == 29136808
    assert summary["population_year"] == 2024
    assert round(summary["debt_gdp_pct"], 2) == 44.28
    assert round(summary["debt_nominal_npr"]) == 2541017485583
    assert round(summary["interest_per_year_npr"]) == 76230524567
    assert round(summary["debt_per_citizen_npr"]) == 87210


PDMO_TEXT = """
GOVERNMENT DEBT STATISTICS
For the month of Magh 2082 (Mid-February, 2026)
PUBLIC DEBT MANAGEMENT OFFICE
Disbursement/
New IssuedRepayment
A. External Debt 140,582.36        3,781.65            2,676.09       (9,296.82)    150,984.74      52.81          24.72
BDomestic Debt 126,822.41        21,766.69          13,676.00     134,913.10      47.19          22.09
267,404.77        25,548.34          16,352.09     (9,296.82)    285,897.84      100.00       46.81
4Total Interset Payment          10,853.30         4,013.53 6,839.77     36.98           0.66%
"""


NRB_TEXT = """
March 11, 2026
Based on Seven Months' Data (Ending Mid-February) of 2025/26
The y-o-y consumer price inflation stood at 3.25 percent in mid-February 2026 compared to 4.16 percent a year ago.
Nepal Government’s expenditure amounted to Rs. 801.37 billion, and revenue mobilization amounted to Rs. 665.02 billion.
"""


def test_parse_pdmo_pdf_extracts_latest_debt_stats(monkeypatch):
    monkeypatch.setattr(DebtClockService, "_extract_pdf_text", staticmethod(lambda _pdf: PDMO_TEXT))

    payload = DebtClockService.parse_pdmo_pdf(b"fake-pdf")

    assert payload["period_label"] == "Magh 2082 (Mid-February, 2026)"
    assert payload["total_debt_crore"] == 285897.84
    assert payload["debt_gdp_pct"] == 46.81
    assert payload["external_debt_crore"] == 150984.74
    assert payload["domestic_debt_crore"] == 134913.10
    assert payload["annual_interest_crore"] == 10853.30


def test_parse_nrb_pdf_extracts_inflation_and_fiscal_flow(monkeypatch):
    monkeypatch.setattr(DebtClockService, "_extract_pdf_text", staticmethod(lambda _pdf: NRB_TEXT))

    payload = DebtClockService.parse_nrb_pdf(b"fake-pdf")

    assert payload["inflation_pct"] == 3.25
    assert payload["inflation_year"] == 2026
    assert payload["expenditure_billion"] == 801.37
    assert payload["revenue_billion"] == 665.02
    assert payload["fiscal_year"] == 2026


def test_parse_world_bank_indicator_extracts_latest_point():
    payload = [
        {"lastupdated": "2026-02-24"},
        [
            {
                "indicator": {"id": "SL.UEM.TOTL.ZS", "value": "Unemployment, total (% of total labor force) (modeled ILO estimate)"},
                "date": "2025",
                "value": 10.465,
            }
        ],
    ]

    point = DebtClockService.parse_world_bank_indicator(payload)

    assert point["value"] == 10.465
    assert point["year"] == 2025
    assert point["last_updated"] == "2026-02-24"


def test_parse_imf_indicator_prefers_current_year(monkeypatch):
    class FrozenDatetime:
        @classmethod
        def now(cls, tz=None):
            from datetime import datetime
            return datetime(2026, 3, 20, tzinfo=tz)

    monkeypatch.setattr("app.services.debt_clock_service.datetime", FrozenDatetime)

    payload = {
        "values": {
            "NGDP_RPCH": {
                "NPL": {
                    "2025": 4.9,
                    "2026": 5.2,
                    "2027": 5.0,
                }
            }
        }
    }

    point = DebtClockService.parse_imf_indicator(payload, indicator="NGDP_RPCH")

    assert point["value"] == 5.2
    assert point["year"] == 2026
