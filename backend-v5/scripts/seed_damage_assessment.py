"""Seed damage assessment data for testing.

Creates a sample assessment for the GenZ Protest at Singha Durbar, September 8, 2025.
"""
import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Add parent to path for imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import AsyncSessionLocal as async_session_factory
from app.models.damage_assessment import (
    DamageAssessment,
    DamageZone,
    DamageEvidence,
    DamageType,
    SeverityLevel,
    AssessmentStatus,
    EvidenceSourceType,
    VerificationStatus,
)
from app.models.user import User


async def seed_genz_protest_assessment():
    """Seed the GenZ Protest Singha Durbar assessment."""

    async with async_session_factory() as db:
        # Check if already exists
        existing = await db.execute(
            select(DamageAssessment).where(
                DamageAssessment.event_name == "GenZ Protest - Singha Durbar"
            )
        )
        if existing.scalar_one_or_none():
            print("Assessment already exists, skipping...")
            return

        # Get dev user for created_by
        user_result = await db.execute(
            select(User).where(User.email == "dev@narada.dev")
        )
        user = user_result.scalar_one_or_none()

        # Singha Durbar coordinates (Government secretariat, Kathmandu)
        # Coordinates: 27.7005, 85.3227 (approx center)
        # Bounding box around the complex
        bbox = [85.318, 27.697, 85.328, 27.705]  # [min_lng, min_lat, max_lng, max_lat]
        center_lat = 27.701
        center_lng = 85.323

        # Create the assessment
        assessment = DamageAssessment(
            id=uuid4(),
            event_name="GenZ Protest - Singha Durbar",
            event_description=(
                "Widespread protests led by youth activists (GenZ movement) demanding "
                "government accountability and reform. Protests centered on Singha Durbar "
                "(central secretariat) resulted in clashes and damage to government property. "
                "Multiple buildings affected, vehicles burned, and infrastructure damaged."
            ),
            event_type=DamageType.CIVIL_UNREST.value,
            event_date=datetime(2025, 9, 8, 10, 0, 0, tzinfo=timezone.utc),
            bbox=bbox,
            districts=["Kathmandu"],
            center_lat=center_lat,
            center_lng=center_lng,
            baseline_start=datetime(2025, 8, 8, 0, 0, 0, tzinfo=timezone.utc),
            baseline_end=datetime(2025, 9, 7, 23, 59, 59, tzinfo=timezone.utc),
            post_event_start=datetime(2025, 9, 8, 0, 0, 0, tzinfo=timezone.utc),
            post_event_end=datetime(2025, 9, 23, 23, 59, 59, tzinfo=timezone.utc),
            # Simulated analysis results
            total_area_km2=0.35,
            damaged_area_km2=0.12,
            damage_percentage=34.3,
            critical_area_km2=0.03,
            severe_area_km2=0.04,
            moderate_area_km2=0.03,
            minor_area_km2=0.02,
            affected_population=15000,
            displaced_estimate=500,
            buildings_affected=12,
            roads_damaged_km=0.8,
            bridges_affected=0,
            utilities_disrupted=3,
            infrastructure_details={
                "roads": [
                    {"name": "Singha Durbar Road", "status": "partially_blocked", "damage_km": 0.3},
                    {"name": "Ramshah Path", "status": "damaged", "damage_km": 0.5},
                ],
                "utilities": [
                    {"type": "power", "status": "disrupted", "areas": ["Singha Durbar Complex"]},
                    {"type": "telecom", "status": "degraded", "areas": ["Central Kathmandu"]},
                ]
            },
            status=AssessmentStatus.COMPLETED.value,
            confidence_score=0.78,
            baseline_images_count=18,
            post_images_count=12,
            key_findings=[
                "Main secretariat building shows 65% structural damage to east wing",
                "3 government vehicles completely destroyed by fire",
                "Perimeter wall breached in 4 locations",
                "Significant debris scattered across 0.12 km² area",
                "Water supply disrupted due to damaged main pipeline",
            ],
            tags=["protest", "civil_unrest", "government", "kathmandu", "2025", "genz"],
            created_by_id=user.id if user else None,
        )

        db.add(assessment)
        await db.flush()

        # Add damage zones
        zones = [
            DamageZone(
                id=uuid4(),
                assessment_id=assessment.id,
                zone_name="Main Secretariat East Wing",
                zone_type="building",
                geometry={
                    "type": "Polygon",
                    "coordinates": [[[85.322, 27.700], [85.324, 27.700], [85.324, 27.702], [85.322, 27.702], [85.322, 27.700]]]
                },
                centroid_lat=27.701,
                centroid_lng=85.323,
                area_km2=0.008,
                severity=SeverityLevel.CRITICAL.value,
                damage_percentage=65.0,
                confidence=0.85,
                land_use="government",
                building_type="administrative",
                estimated_population=0,
                satellite_detected=True,
                ground_verified=True,
                verification_notes="Confirmed by ground reports and aerial footage",
            ),
            DamageZone(
                id=uuid4(),
                assessment_id=assessment.id,
                zone_name="Main Gate / Vehicle Parking",
                zone_type="infrastructure",
                geometry={
                    "type": "Polygon",
                    "coordinates": [[[85.320, 27.699], [85.322, 27.699], [85.322, 27.700], [85.320, 27.700], [85.320, 27.699]]]
                },
                centroid_lat=27.6995,
                centroid_lng=85.321,
                area_km2=0.004,
                severity=SeverityLevel.SEVERE.value,
                damage_percentage=80.0,
                confidence=0.90,
                land_use="government",
                satellite_detected=True,
                ground_verified=True,
                verification_notes="Multiple vehicles burned, gate destroyed",
            ),
            DamageZone(
                id=uuid4(),
                assessment_id=assessment.id,
                zone_name="Perimeter Wall Section A",
                zone_type="infrastructure",
                geometry={
                    "type": "Polygon",
                    "coordinates": [[[85.318, 27.698], [85.320, 27.698], [85.320, 27.699], [85.318, 27.699], [85.318, 27.698]]]
                },
                centroid_lat=27.6985,
                centroid_lng=85.319,
                area_km2=0.002,
                severity=SeverityLevel.MODERATE.value,
                damage_percentage=40.0,
                confidence=0.75,
                satellite_detected=True,
                ground_verified=False,
            ),
        ]

        for zone in zones:
            db.add(zone)

        await db.flush()

        # Add evidence
        evidence_items = [
            DamageEvidence(
                id=uuid4(),
                assessment_id=assessment.id,
                zone_id=zones[0].id,
                source_type=EvidenceSourceType.SATELLITE.value,
                evidence_type="analysis",
                title="Sentinel-1 SAR Change Detection",
                excerpt="PWTT analysis shows significant backscatter decrease (-4.2 dB) indicating structural damage",
                timestamp=datetime(2025, 9, 10, 9, 30, 0, tzinfo=timezone.utc),
                confidence=0.85,
                verification_status=VerificationStatus.VERIFIED.value,
                auto_linked=False,
            ),
            DamageEvidence(
                id=uuid4(),
                assessment_id=assessment.id,
                zone_id=zones[1].id,
                source_type=EvidenceSourceType.STORY.value,
                evidence_type="text",
                source_name="Kathmandu Post",
                title="Vehicles burned at Singha Durbar during protests",
                excerpt="At least 5 government vehicles were set ablaze by protesters near the main gate...",
                source_url="https://kathmandupost.com/national/2025/09/08/vehicles-burned-singha-durbar",
                timestamp=datetime(2025, 9, 8, 14, 30, 0, tzinfo=timezone.utc),
                confidence=0.80,
                verification_status=VerificationStatus.VERIFIED.value,
                auto_linked=True,
                link_confidence=0.88,
            ),
            DamageEvidence(
                id=uuid4(),
                assessment_id=assessment.id,
                source_type=EvidenceSourceType.SOCIAL_MEDIA.value,
                evidence_type="video",
                source_name="Twitter/X",
                title="Live footage of protest at Singha Durbar",
                excerpt="Video shows large crowd breaching perimeter, smoke visible from multiple locations",
                timestamp=datetime(2025, 9, 8, 11, 15, 0, tzinfo=timezone.utc),
                confidence=0.70,
                verification_status=VerificationStatus.VERIFIED.value,
                auto_linked=True,
                link_confidence=0.72,
            ),
            DamageEvidence(
                id=uuid4(),
                assessment_id=assessment.id,
                source_type=EvidenceSourceType.GOVERNMENT.value,
                evidence_type="report",
                source_name="Ministry of Home Affairs",
                title="Official damage assessment report",
                excerpt="Preliminary assessment estimates NPR 500 million in damages to government property",
                timestamp=datetime(2025, 9, 12, 10, 0, 0, tzinfo=timezone.utc),
                confidence=0.95,
                verification_status=VerificationStatus.VERIFIED.value,
                auto_linked=False,
            ),
        ]

        for evidence in evidence_items:
            db.add(evidence)

        await db.commit()
        print(f"✓ Created assessment: {assessment.event_name}")
        print(f"  - ID: {assessment.id}")
        print(f"  - Zones: {len(zones)}")
        print(f"  - Evidence: {len(evidence_items)}")


if __name__ == "__main__":
    asyncio.run(seed_genz_protest_assessment())
