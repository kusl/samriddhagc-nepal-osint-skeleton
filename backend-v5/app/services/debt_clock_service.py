"""Debt clock data ingestion for Nepal-specific official and fallback sources."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
from datetime import datetime, timezone
from io import BytesIO
from typing import Any
from urllib.parse import unquote

import httpx
import requests
from PyPDF2 import PdfReader
from redis.asyncio import Redis

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class DebtClockService:
    """Fetch and cache Nepal debt clock data."""

    SOURCE_URL = "https://debtclock.io/nepal"
    PDMO_MONTHLY_URL = "https://pdmo.gov.np/pages/monthlyrepo/"
    NRB_MACRO_ARCHIVE_URL = "https://www.nrb.org.np/red/"
    WORLD_BANK_INDICATOR_URL = (
        "https://api.worldbank.org/v2/country/NPL/indicator/{indicator}?format=json&per_page=5&mrnev=1"
    )
    IMF_DATAMAPPER_URL = "https://www.imf.org/external/datamapper/api/v1/{indicator}/NPL"
    CACHE_KEY = "debt-clock:nepal:summary"
    SECONDS_PER_YEAR = 365 * 24 * 60 * 60

    IMF_REAL_GDP_GROWTH_INDICATOR = "NGDP_RPCH"
    WORLD_BANK_POPULATION_INDICATOR = "SP.POP.TOTL"
    WORLD_BANK_UNEMPLOYMENT_INDICATOR = "SL.UEM.TOTL.ZS"

    _TIME_TAG_RE = re.compile(
        r'<time id="updated-at" datetime="(?P<iso>[^"]+)">(?P<label>[^<]+)</time>',
        re.IGNORECASE,
    )
    _DC_BLOCK_RE = re.compile(
        r"window\.__DC__\s*=\s*\{(?P<body>.*?)}\s*;\s*</script>",
        re.IGNORECASE | re.DOTALL,
    )
    _PDF_HREF_RE = re.compile(r'href="(?P<url>[^"]+\.pdf)"', re.IGNORECASE)
    _NRB_REPORT_LINK_RE = re.compile(
        r'href="(?P<url>https://www\.nrb\.org\.np/red/current-macroeconomic-and-financial-situation-english[^"]+/?)"',
        re.IGNORECASE,
    )
    _PDMO_PERIOD_RE = re.compile(
        r"For the month of\s+(?P<label>.+?)\s+PUBLIC DEBT MANAGEMENT OFFICE",
        re.IGNORECASE | re.DOTALL,
    )
    _PDMO_TOTALS_RE = re.compile(
        r"A\.\s*External Debt\s+[\d,]+\.\d+\s+[\d,]+\.\d+\s+[\d,]+\.\d+\s+\([\d,]+\.\d+\)\s+"
        r"(?P<external>[\d,]+\.\d+)\s+52\.81\s+[\d,]+\.\d+\s+"
        r"BDomestic Debt\s+[\d,]+\.\d+\s+[\d,]+\.\d+\s+[\d,]+\.\d+\s+"
        r"(?P<domestic>[\d,]+\.\d+)\s+47\.19\s+[\d,]+\.\d+\s+"
        r"[\d,]+\.\d+\s+[\d,]+\.\d+\s+[\d,]+\.\d+\s+\([\d,]+\.\d+\)\s+"
        r"(?P<total>[\d,]+\.\d+)\s+100\.00\s+(?P<ratio>[\d,]+\.\d+)",
        re.IGNORECASE | re.DOTALL,
    )
    _PDMO_INTEREST_RE = re.compile(
        r"Total Interset Payment\s+(?P<annual>[\d,]+\.\d+)\s+(?P<paid>[\d,]+\.\d+)\s+(?P<remaining>[\d,]+\.\d+)",
        re.IGNORECASE,
    )
    _NRB_PERIOD_RE = re.compile(
        r"Based on\s+(?P<label>.+?)(?:\n|The y-o-y|The y/y|The y-o- y)",
        re.IGNORECASE | re.DOTALL,
    )
    _NRB_INFLATION_RE = re.compile(
        r"inflation stood at\s+(?P<inflation>\d+\.\d+)\s+percent in\s+(?P<period>mid-[A-Za-z]+\s+\d{4})",
        re.IGNORECASE,
    )
    _NRB_FISCAL_RE = re.compile(
        r"expenditure\s+amounted to\s+Rs\.\s*(?P<expenditure>\d+\.\d+)\s+billion,\s+and\s+revenue mobilization "
        r"amounted to\s+Rs\.\s*(?P<revenue>\d+\.\d+)\s+billion",
        re.IGNORECASE,
    )

    def __init__(self, redis: Redis):
        self.redis = redis

    async def get_nepal_summary(self, *, force_refresh: bool = False) -> dict[str, Any]:
        """Return cached or freshly fetched Nepal debt clock summary."""
        if not force_refresh:
            cached = await self.redis.get(self.CACHE_KEY)
            if cached:
                return json.loads(cached)

        try:
            summary = await self._fetch_and_parse()
        except Exception:
            logger.exception("Failed to refresh Nepal debt clock data")
            cached = await self.redis.get(self.CACHE_KEY)
            if cached:
                return json.loads(cached)
            raise

        await self.redis.set(self.CACHE_KEY, json.dumps(summary), ex=settings.debt_clock_cache_ttl_seconds)
        return summary

    async def _fetch_and_parse(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            fallback_response = await client.get(
                self.SOURCE_URL,
                headers={
                    "User-Agent": "NepalOSINT/1.0 (+https://nepalosint.com)",
                    "Accept": "text/html,application/xhtml+xml",
                },
            )
            fallback_response.raise_for_status()
            fallback_summary = self.parse_html(fallback_response.text)
            pdmo_payload, nrb_payload, population_point, unemployment_point, imf_growth_point = await asyncio.gather(
                self._safe_fetch("PDMO debt report", self._fetch_latest_pdmo_payload(client)),
                self._safe_fetch("NRB macro report", self._fetch_nrb_payload(client)),
                self._safe_fetch(
                    "World Bank population",
                    self._fetch_world_bank_indicator(client, self.WORLD_BANK_POPULATION_INDICATOR),
                ),
                self._safe_fetch(
                    "World Bank unemployment",
                    self._fetch_world_bank_indicator(client, self.WORLD_BANK_UNEMPLOYMENT_INDICATOR),
                ),
                self._safe_fetch(
                    "IMF real GDP growth",
                    self._fetch_imf_indicator(client, self.IMF_REAL_GDP_GROWTH_INDICATOR),
                ),
            )
            return self._build_official_summary(
                fallback_summary=fallback_summary,
                pdmo_payload=pdmo_payload,
                nrb_payload=nrb_payload,
                population_point=population_point,
                unemployment_point=unemployment_point,
                imf_growth_point=imf_growth_point,
            )

    async def _safe_fetch(self, label: str, coro):
        try:
            return await coro
        except Exception:
            logger.exception("Failed to refresh %s", label)
            return None

    def _build_official_summary(
        self,
        *,
        fallback_summary: dict[str, Any],
        pdmo_payload: dict[str, Any] | None,
        nrb_payload: dict[str, Any] | None,
        population_point: dict[str, Any] | None,
        unemployment_point: dict[str, Any] | None,
        imf_growth_point: dict[str, Any] | None,
    ) -> dict[str, Any]:
        fx_usd_per_lcy = fallback_summary.get("fx_usd_per_lcy") or 0.0
        fetched_at = datetime.now(timezone.utc).isoformat()
        current_year = datetime.now(timezone.utc).year

        population = (
            int(round(population_point["value"]))
            if population_point and population_point.get("value") is not None
            else fallback_summary["population"]
        )

        total_debt_npr = pdmo_payload["total_debt_crore"] * 10_000_000 if pdmo_payload else fallback_summary["debt_nominal_npr"]
        external_debt_npr = pdmo_payload["external_debt_crore"] * 10_000_000 if pdmo_payload else fallback_summary.get("external_debt_npr")
        domestic_debt_npr = pdmo_payload["domestic_debt_crore"] * 10_000_000 if pdmo_payload else fallback_summary.get("domestic_debt_npr")
        debt_gdp_pct = pdmo_payload["debt_gdp_pct"] if pdmo_payload else fallback_summary["debt_gdp_pct"]
        gdp_nominal_npr = total_debt_npr / (debt_gdp_pct / 100.0) if debt_gdp_pct else fallback_summary["gdp_nominal_npr"]
        debt_now_usd = total_debt_npr * fx_usd_per_lcy if fx_usd_per_lcy else fallback_summary["debt_now_usd"]
        gdp_nominal_usd = gdp_nominal_npr * fx_usd_per_lcy if fx_usd_per_lcy else fallback_summary["gdp_nominal_usd"]

        interest_per_year_npr = (
            pdmo_payload.get("annual_interest_crore", 0.0) * 10_000_000 if pdmo_payload else 0.0
        ) or fallback_summary["interest_per_year_npr"]
        interest_per_year_usd = interest_per_year_npr * fx_usd_per_lcy if fx_usd_per_lcy else fallback_summary["interest_per_year_usd"]
        flow_per_second_npr = interest_per_year_npr / self.SECONDS_PER_YEAR if interest_per_year_npr else fallback_summary["flow_per_second_npr"]
        flow_per_second_usd = flow_per_second_npr * fx_usd_per_lcy if fx_usd_per_lcy else fallback_summary["flow_per_second_usd"]
        debt_per_citizen_npr = total_debt_npr / population if population else fallback_summary["debt_per_citizen_npr"]
        debt_per_citizen_usd = debt_now_usd / population if population else fallback_summary["debt_per_citizen_usd"]

        budget_balance_pct = fallback_summary.get("budget_balance_pct")
        if nrb_payload and nrb_payload.get("revenue_billion") is not None and nrb_payload.get("expenditure_billion") is not None and gdp_nominal_npr:
            fiscal_balance_npr = (nrb_payload["revenue_billion"] - nrb_payload["expenditure_billion"]) * 1_000_000_000
            budget_balance_pct = fiscal_balance_npr / gdp_nominal_npr * 100.0

        growth_pct = imf_growth_point["value"] if imf_growth_point and imf_growth_point.get("value") is not None else fallback_summary.get("gdp_growth_pct")
        growth_year = imf_growth_point["year"] if imf_growth_point else fallback_summary.get("gdp_growth_year")
        unemployment_pct = (
            unemployment_point["value"]
            if unemployment_point and unemployment_point.get("value") is not None
            else fallback_summary.get("unemployment_pct")
        )
        unemployment_year = unemployment_point["year"] if unemployment_point else fallback_summary.get("unemployment_year")

        debt_as_of_label = pdmo_payload["period_label"] if pdmo_payload else fallback_summary.get("debt_as_of_label")
        updated_label = f"Debt as of {debt_as_of_label}" if debt_as_of_label else fallback_summary["updated_label"]

        return {
            **fallback_summary,
            "source_label": "PDMO / NRB / IMF / World Bank",
            "updated_at": fetched_at,
            "updated_label": updated_label,
            "snapshot_year": current_year,
            "debt_now_npr": total_debt_npr,
            "debt_now_usd": debt_now_usd,
            "debt_nominal_npr": total_debt_npr,
            "debt_nominal_usd": debt_now_usd,
            "debt_gdp_pct": debt_gdp_pct,
            "gdp_nominal_npr": gdp_nominal_npr,
            "gdp_nominal_usd": gdp_nominal_usd,
            "population": population,
            "population_year": population_point["year"] if population_point else fallback_summary.get("population_year"),
            "interest_per_year_npr": interest_per_year_npr,
            "interest_per_year_usd": interest_per_year_usd,
            "flow_per_second_npr": flow_per_second_npr,
            "flow_per_second_usd": flow_per_second_usd,
            "debt_per_citizen_npr": debt_per_citizen_npr,
            "debt_per_citizen_usd": debt_per_citizen_usd,
            "inflation_pct": nrb_payload.get("inflation_pct") if nrb_payload and nrb_payload.get("inflation_pct") is not None else fallback_summary.get("inflation_pct"),
            "inflation_year": nrb_payload.get("inflation_year") if nrb_payload and nrb_payload.get("inflation_year") is not None else fallback_summary.get("inflation_year"),
            "gdp_growth_pct": growth_pct,
            "gdp_growth_year": growth_year,
            "unemployment_pct": unemployment_pct,
            "unemployment_year": unemployment_year,
            "budget_balance_pct": budget_balance_pct,
            "budget_balance_year": nrb_payload.get("fiscal_year") if nrb_payload and nrb_payload.get("fiscal_year") is not None else fallback_summary.get("budget_balance_year"),
            "debt_as_of_label": debt_as_of_label,
            "debt_ratio_label": f"PDMO public debt ratio as of {debt_as_of_label}" if debt_as_of_label else fallback_summary.get("debt_ratio_label"),
            "gdp_nominal_label": (
                f"Implied from PDMO debt stock and debt/GDP ratio as of {debt_as_of_label}"
                if debt_as_of_label
                else fallback_summary.get("gdp_nominal_label")
            ),
            "population_label": population_point["label"] if population_point else fallback_summary.get("population_label"),
            "interest_label": (
                f"PDMO annual interest allocation as of {debt_as_of_label}"
                if debt_as_of_label
                else fallback_summary.get("interest_label")
            ),
            "inflation_label": nrb_payload.get("inflation_label") if nrb_payload else fallback_summary.get("inflation_label"),
            "growth_label": imf_growth_point["label"] if imf_growth_point else fallback_summary.get("growth_label"),
            "budget_balance_label": nrb_payload.get("fiscal_label") if nrb_payload else fallback_summary.get("budget_balance_label"),
            "unemployment_label": unemployment_point["label"] if unemployment_point else fallback_summary.get("unemployment_label"),
            "methodology_note": (
                "Debt stock and debt ratio use the latest PDMO monthly report. Inflation and fiscal flow use NRB's"
                " latest current macro report. Population and unemployment use World Bank API series. Real GDP"
                " growth uses IMF DataMapper. The summary is refreshed on a low-frequency scheduler and cached in Redis."
            ),
            "domestic_debt_npr": domestic_debt_npr,
            "external_debt_npr": external_debt_npr,
            "fetched_at": fetched_at,
        }

    async def _fetch_latest_pdmo_payload(self, client: httpx.AsyncClient) -> dict[str, Any]:
        response = await client.get(
            self.PDMO_MONTHLY_URL,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/xhtml+xml"},
        )
        response.raise_for_status()
        latest_pdf_url = self._extract_latest_pdmo_pdf_url(response.text)
        pdf_response = await client.get(
            latest_pdf_url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/pdf,*/*",
                "Referer": self.PDMO_MONTHLY_URL,
            },
        )
        pdf_response.raise_for_status()
        return self.parse_pdmo_pdf(pdf_response.content)

    async def _fetch_nrb_payload(self, client: httpx.AsyncClient) -> dict[str, Any]:
        listing_response = await client.get(
            self.NRB_MACRO_ARCHIVE_URL,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/xhtml+xml"},
        )
        listing_response.raise_for_status()
        latest_report_url = self._extract_latest_nrb_report_url(listing_response.text)

        response = await client.get(
            latest_report_url,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/pdf,*/*"},
        )
        response.raise_for_status()
        return self.parse_nrb_pdf(response.content)

    async def _fetch_world_bank_indicator(self, client: httpx.AsyncClient, indicator: str) -> dict[str, Any]:
        response = await client.get(
            self.WORLD_BANK_INDICATOR_URL.format(indicator=indicator),
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
        )
        response.raise_for_status()
        return self.parse_world_bank_indicator(response.json())

    async def _fetch_imf_indicator(self, client: httpx.AsyncClient, indicator: str) -> dict[str, Any]:
        del client  # IMF blocks httpx on this endpoint more aggressively than stdlib requests.
        payload = await asyncio.to_thread(self._load_json_via_urllib, self.IMF_DATAMAPPER_URL.format(indicator=indicator))
        return self.parse_imf_indicator(payload, indicator=indicator)

    @classmethod
    def parse_pdmo_pdf(cls, pdf_bytes: bytes) -> dict[str, Any]:
        text = cls._extract_pdf_text(pdf_bytes)
        period_match = cls._PDMO_PERIOD_RE.search(text)
        totals_match = cls._PDMO_TOTALS_RE.search(text)
        interest_match = cls._PDMO_INTEREST_RE.search(text)

        if not period_match or not totals_match:
            raise ValueError("Unable to parse latest PDMO debt statistics PDF")

        return {
            "period_label": cls._normalize_whitespace(period_match.group("label")),
            "external_debt_crore": cls._parse_number(totals_match.group("external")),
            "domestic_debt_crore": cls._parse_number(totals_match.group("domestic")),
            "total_debt_crore": cls._parse_number(totals_match.group("total")),
            "debt_gdp_pct": cls._parse_number(totals_match.group("ratio")),
            "annual_interest_crore": cls._parse_number(interest_match.group("annual")) if interest_match else 0.0,
        }

    @classmethod
    def parse_nrb_pdf(cls, pdf_bytes: bytes) -> dict[str, Any]:
        text = cls._extract_pdf_text(pdf_bytes)
        period_match = cls._NRB_PERIOD_RE.search(text)
        inflation_match = cls._NRB_INFLATION_RE.search(text)
        fiscal_match = cls._NRB_FISCAL_RE.search(text)
        inflation_year = cls._extract_year(inflation_match.group("period")) if inflation_match else None
        period_label = cls._normalize_whitespace(period_match.group("label")) if period_match else None

        return {
            "inflation_pct": cls._parse_number(inflation_match.group("inflation")) if inflation_match else None,
            "inflation_year": inflation_year,
            "inflation_label": f"NRB y/y CPI, {inflation_match.group('period')}" if inflation_match else None,
            "expenditure_billion": cls._parse_number(fiscal_match.group("expenditure")) if fiscal_match else None,
            "revenue_billion": cls._parse_number(fiscal_match.group("revenue")) if fiscal_match else None,
            "fiscal_label": f"NRB {period_label}" if fiscal_match and period_label else None,
            "fiscal_year": inflation_year,
        }

    @classmethod
    def parse_world_bank_indicator(cls, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
            raise ValueError("Unexpected World Bank indicator payload")

        metadata = payload[0] or {}
        point = payload[1][0]
        value = point.get("value")
        if value is None:
            raise ValueError("World Bank indicator payload did not include a value")

        year = int(point["date"])
        indicator_label = point.get("indicator", {}).get("value") or "World Bank indicator"
        return {
            "value": float(value),
            "year": year,
            "label": f"{indicator_label}, {year}",
            "last_updated": metadata.get("lastupdated"),
        }

    @classmethod
    def parse_imf_indicator(cls, payload: dict[str, Any], *, indicator: str) -> dict[str, Any]:
        values = payload.get("values", {})
        series = values.get(indicator, {}).get("NPL", {})
        if not series:
            raise ValueError("Unexpected IMF DataMapper payload")

        year_points = {int(year): float(value) for year, value in series.items() if value is not None}
        if not year_points:
            raise ValueError("IMF DataMapper payload did not include a usable value")

        current_year = datetime.now(timezone.utc).year
        eligible_years = [year for year in year_points if year <= current_year]
        selected_year = max(eligible_years) if eligible_years else max(year_points)
        label = "IMF DataMapper real GDP growth"
        if selected_year >= current_year:
            label = f"{label} projection, {selected_year}"
        else:
            label = f"{label}, {selected_year}"

        return {
            "value": year_points[selected_year],
            "year": selected_year,
            "label": label,
        }

    @classmethod
    def parse_html(cls, html: str) -> dict[str, Any]:
        """Parse the fallback DebtClock HTML into a normalized summary payload."""
        dc_match = cls._DC_BLOCK_RE.search(html)
        if not dc_match:
            raise ValueError("DebtClock payload not found in HTML")
        dc_body = dc_match.group("body")

        updated_match = cls._TIME_TAG_RE.search(html)
        updated_at = updated_match.group("iso") if updated_match else datetime.now(timezone.utc).date().isoformat()
        updated_label = updated_match.group("label").strip() if updated_match else updated_at

        country = cls._extract_string(dc_body, "country") or "Nepal"
        currency = cls._extract_string(dc_body, "currency") or "NPR"
        snapshot_year = cls._extract_int(dc_body, "snapshot_year")
        population = cls._extract_int(dc_body, "population") or 0
        debt_lcy = cls._extract_float(dc_body, "debt_lcy") or 0.0
        debt_usd = cls._extract_float(dc_body, "debt_usd") or 0.0
        gdp_lcy = cls._extract_float(dc_body, "gdp_lcy") or 0.0
        gdp_usd = cls._extract_float(dc_body, "gdp_usd") or 0.0
        interest_year_lcy = cls._extract_float(dc_body, "interest_year_lcy") or 0.0
        interest_year_usd = cls._extract_float(dc_body, "interest_year_usd") or 0.0
        flow_per_second_lcy = cls._extract_float(dc_body, "flow_per_second_lcy") or 0.0
        fx_usd_per_lcy = cls._extract_float(dc_body, "fx_usd_per_lcy") or 0.0
        debt_gdp_pct = cls._extract_float(dc_body, "debt_gdp_pct") or 0.0
        inflation_pct = cls._extract_float(dc_body, "inflation_pct")
        gdp_growth_pct = cls._extract_float(dc_body, "gdp_growth_pct")
        unemployment_pct = cls._extract_float(dc_body, "unemployment_pct")
        budget_balance_pct = cls._extract_float(dc_body, "budget_balance_pct")

        debt_per_citizen_npr = debt_lcy / population if population else 0.0
        debt_per_citizen_usd = debt_usd / population if population else 0.0
        flow_per_second_usd = flow_per_second_lcy * fx_usd_per_lcy if fx_usd_per_lcy else 0.0

        return {
            "country": country,
            "flag": "🇳🇵",
            "currency_code": currency,
            "source_label": "IMF/World Bank/ECB",
            "updated_at": updated_at,
            "updated_label": updated_label,
            "snapshot_year": snapshot_year,
            "debt_now_npr": debt_lcy,
            "debt_now_usd": debt_usd,
            "debt_nominal_npr": debt_lcy,
            "debt_nominal_usd": debt_usd,
            "debt_gdp_pct": debt_gdp_pct,
            "gdp_nominal_npr": gdp_lcy,
            "gdp_nominal_usd": gdp_usd,
            "population": population,
            "population_year": snapshot_year,
            "interest_per_year_npr": interest_year_lcy,
            "interest_per_year_usd": interest_year_usd,
            "flow_per_second_npr": flow_per_second_lcy,
            "flow_per_second_usd": flow_per_second_usd,
            "debt_per_citizen_npr": debt_per_citizen_npr,
            "debt_per_citizen_usd": debt_per_citizen_usd,
            "inflation_pct": inflation_pct,
            "inflation_year": cls._extract_int(dc_body, "inflation_year"),
            "gdp_growth_pct": gdp_growth_pct,
            "gdp_growth_year": cls._extract_int(dc_body, "gdp_growth_year"),
            "unemployment_pct": unemployment_pct,
            "unemployment_year": cls._extract_int(dc_body, "unemployment_year"),
            "budget_balance_pct": budget_balance_pct,
            "budget_balance_year": cls._extract_int(dc_body, "budget_balance_year"),
            "debt_as_of_label": updated_label,
            "debt_ratio_label": None,
            "gdp_nominal_label": None,
            "population_label": None,
            "interest_label": None,
            "inflation_label": None,
            "growth_label": None,
            "budget_balance_label": None,
            "unemployment_label": None,
            "methodology_note": None,
            "domestic_debt_npr": None,
            "external_debt_npr": None,
            "fx_usd_per_lcy": fx_usd_per_lcy,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    def _extract_latest_pdmo_pdf_url(cls, html: str) -> str:
        candidates = []
        for match in cls._PDF_HREF_RE.finditer(html):
            url = match.group("url")
            decoded = unquote(url)
            if "Debt" in decoded:
                candidates.append(url)

        if not candidates:
            raise ValueError("No debt statistics PDF links found on PDMO monthly repo page")

        return candidates[0]

    @classmethod
    def _extract_latest_nrb_report_url(cls, html: str) -> str:
        match = cls._NRB_REPORT_LINK_RE.search(html)
        if not match:
            raise ValueError("No NRB macro report links found on archive page")
        return match.group("url")

    @staticmethod
    def _extract_pdf_text(pdf_bytes: bytes) -> str:
        reader = PdfReader(BytesIO(pdf_bytes))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    @staticmethod
    def _normalize_whitespace(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _parse_number(raw: str) -> float:
        return float(raw.replace(",", "").strip())

    @staticmethod
    def _load_json_via_urllib(url: str) -> Any:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _extract_year(raw: str | None) -> int | None:
        if not raw:
            return None
        match = re.search(r"(20\d{2})", raw)
        return int(match.group(1)) if match else None

    @staticmethod
    def _extract_string(body: str, key: str) -> str | None:
        match = re.search(rf"\b{re.escape(key)}\s*:\s*\"([^\"]*)\"", body)
        return match.group(1) if match else None

    @staticmethod
    def _extract_float(body: str, key: str) -> float | None:
        match = re.search(rf"\b{re.escape(key)}\s*:\s*(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", body)
        return float(match.group(1)) if match else None

    @classmethod
    def _extract_int(cls, body: str, key: str) -> int | None:
        value = cls._extract_float(body, key)
        return int(value) if value is not None and not math.isnan(value) else None
