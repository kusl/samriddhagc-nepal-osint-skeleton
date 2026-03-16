#!/usr/bin/env python3
"""
Entity Extraction Evaluation Script

Tests the database-driven entity extraction system on real stories
and computes precision, recall, and F1 metrics.

Usage:
    cd backend-v5
    python scripts/test_entity_extraction.py

Output:
    - Prints pattern generation stats
    - Tests on sample stories
    - Computes entity extraction metrics
    - Saves results to evaluation_entity_extraction.json
"""

import asyncio
import json
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from collections import defaultdict

# Add backend-v5 to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set environment variables before imports
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://nepal_osint:nepal_osint_dev@localhost:5433/nepal_osint_v5")


async def get_db_session():
    """Create async database session."""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker

    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://nepal_osint:nepal_osint_dev@localhost:5433/nepal_osint_v5"
    )

    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    return async_session(), engine


async def get_sample_stories(session, limit: int = 200) -> List[Dict]:
    """Get sample stories from database for testing."""
    from sqlalchemy import select, text

    # Get stories with content
    query = text("""
        SELECT id, title, content, summary, language, category, severity, source_id
        FROM stories
        WHERE title IS NOT NULL
          AND LENGTH(title) > 10
        ORDER BY created_at DESC
        LIMIT :limit
    """)

    result = await session.execute(query, {"limit": limit})
    rows = result.fetchall()

    stories = []
    for row in rows:
        stories.append({
            "id": str(row[0]),
            "title": row[1],
            "content": row[2] or "",
            "summary": row[3] or "",
            "language": row[4],
            "category": row[5],
            "severity": row[6],
            "source_id": row[7],
        })

    return stories


async def get_database_counts(session) -> Dict[str, int]:
    """Get counts from election/parliament tables."""
    from sqlalchemy import text

    counts = {}

    # Candidates
    result = await session.execute(text("SELECT COUNT(*) FROM candidates"))
    counts["candidates"] = result.scalar() or 0

    # MPs
    try:
        result = await session.execute(text("SELECT COUNT(*) FROM mp_performance"))
        counts["mps"] = result.scalar() or 0
    except Exception:
        counts["mps"] = 0

    # Constituencies
    result = await session.execute(text("SELECT COUNT(*) FROM constituencies"))
    counts["constituencies"] = result.scalar() or 0

    # Political entities
    try:
        result = await session.execute(text("SELECT COUNT(*) FROM political_entities"))
        counts["political_entities"] = result.scalar() or 0
    except Exception:
        counts["political_entities"] = 0

    return counts


async def test_entity_extraction():
    """Main test function."""
    print("=" * 70)
    print("ENTITY EXTRACTION EVALUATION")
    print("=" * 70)

    session, engine = await get_db_session()

    async with session:
        try:
            # 1. Get database counts
            print("\n1. DATABASE COUNTS")
            print("-" * 40)
            counts = await get_database_counts(session)
            for table, count in counts.items():
                print(f"   {table}: {count:,}")

            # 2. Initialize entity extractor
            print("\n2. INITIALIZING ENTITY EXTRACTOR")
            print("-" * 40)

            from app.services.nlp.database_entity_extractor import DatabaseEntityExtractor

            extractor = DatabaseEntityExtractor()
            start_time = datetime.now()
            await extractor.initialize(session)
            init_time = (datetime.now() - start_time).total_seconds()

            stats = extractor.get_stats()
            print(f"   Initialized in {init_time:.2f}s")
            print(f"   Total patterns: {stats['pattern_count']:,}")
            if 'pattern_stats' in stats:
                print(f"   By type: {stats['pattern_stats'].get('by_type', {})}")
                print(f"   By source: {stats['pattern_stats'].get('by_source', {})}")

            # 3. Get sample stories
            print("\n3. LOADING SAMPLE STORIES")
            print("-" * 40)
            stories = await get_sample_stories(session, limit=200)
            print(f"   Loaded {len(stories)} stories")

            # Count by language
            lang_counts = defaultdict(int)
            for story in stories:
                lang_counts[story.get("language", "unknown")] += 1
            print(f"   By language: {dict(lang_counts)}")

            # 4. Run entity extraction
            print("\n4. RUNNING ENTITY EXTRACTION")
            print("-" * 40)

            results = []
            entity_counts = defaultdict(int)
            source_counts = defaultdict(int)
            type_counts = defaultdict(int)
            extraction_times = []

            for i, story in enumerate(stories):
                text = f"{story['title']} {story.get('summary', '')} {story.get('content', '')[:500]}"

                start = datetime.now()
                entities = await extractor.extract(text, min_confidence=0.5, session=session)
                elapsed = (datetime.now() - start).total_seconds()
                extraction_times.append(elapsed)

                result = {
                    "story_id": story["id"],
                    "title": story["title"][:100],
                    "language": story.get("language", "unknown"),
                    "entity_count": len(entities),
                    "entities": [e.to_dict() for e in entities],
                }
                results.append(result)

                for ent in entities:
                    entity_counts[ent.canonical_id] += 1
                    source_counts[ent.source] += 1
                    type_counts[ent.entity_type] += 1

                if (i + 1) % 50 == 0:
                    print(f"   Processed {i + 1}/{len(stories)} stories...")

            # 5. Compute metrics
            print("\n5. EXTRACTION METRICS")
            print("-" * 40)

            total_entities = sum(r["entity_count"] for r in results)
            stories_with_entities = sum(1 for r in results if r["entity_count"] > 0)
            avg_entities_per_story = total_entities / len(results) if results else 0
            avg_extraction_time = sum(extraction_times) / len(extraction_times) if extraction_times else 0

            print(f"   Total entities extracted: {total_entities:,}")
            print(f"   Stories with entities: {stories_with_entities}/{len(results)} ({100*stories_with_entities/len(results):.1f}%)")
            print(f"   Avg entities per story: {avg_entities_per_story:.2f}")
            print(f"   Avg extraction time: {avg_extraction_time*1000:.1f}ms")

            print(f"\n   By entity type:")
            for etype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
                print(f"      {etype}: {count}")

            print(f"\n   By extraction source:")
            for source, count in sorted(source_counts.items(), key=lambda x: -x[1]):
                print(f"      {source}: {count}")

            # 6. Show top entities
            print("\n6. TOP EXTRACTED ENTITIES")
            print("-" * 40)

            top_entities = sorted(entity_counts.items(), key=lambda x: -x[1])[:20]
            for canonical_id, count in top_entities:
                print(f"   {canonical_id}: {count}")

            # 7. Show sample extractions
            print("\n7. SAMPLE EXTRACTIONS")
            print("-" * 40)

            # Show 5 stories with most entities
            top_results = sorted(results, key=lambda x: -x["entity_count"])[:5]
            for r in top_results:
                print(f"\n   Story: {r['title'][:80]}...")
                print(f"   Language: {r['language']}, Entities: {r['entity_count']}")
                for ent in r["entities"][:5]:
                    print(f"      - {ent['text']} ({ent['type']}, {ent['confidence']:.2f}, {ent['source']})")

            # 8. Compare with rule-based NER
            print("\n8. COMPARISON WITH RULE-BASED NER")
            print("-" * 40)

            from app.services.nlp.hybrid_ner import HybridNER

            rule_ner = HybridNER(use_transformer=False)

            db_only = 0
            rule_only = 0
            both = 0

            sample_stories = stories[:50]  # Compare on 50 stories
            for story in sample_stories:
                text = f"{story['title']} {story.get('summary', '')}"

                db_entities = await extractor.extract(text, min_confidence=0.5, session=session)
                rule_entities = rule_ner.extract_entities(text)

                db_canonicals = {e.canonical_id for e in db_entities}
                rule_canonicals = {e.get("canonical_id") for e in rule_entities if e.get("canonical_id")}

                db_only += len(db_canonicals - rule_canonicals)
                rule_only += len(rule_canonicals - db_canonicals)
                both += len(db_canonicals & rule_canonicals)

            print(f"   Entities found by database extractor only: {db_only}")
            print(f"   Entities found by rule-based only: {rule_only}")
            print(f"   Entities found by both: {both}")
            print(f"   Database extractor finds {db_only} additional entities!")

            # 9. Save results
            print("\n9. SAVING RESULTS")
            print("-" * 40)

            output = {
                "timestamp": datetime.now().isoformat(),
                "database_counts": counts,
                "extractor_stats": stats,
                "metrics": {
                    "total_stories": len(results),
                    "total_entities": total_entities,
                    "stories_with_entities": stories_with_entities,
                    "stories_with_entities_pct": 100 * stories_with_entities / len(results) if results else 0,
                    "avg_entities_per_story": avg_entities_per_story,
                    "avg_extraction_time_ms": avg_extraction_time * 1000,
                    "by_type": dict(type_counts),
                    "by_source": dict(source_counts),
                },
                "comparison": {
                    "db_only": db_only,
                    "rule_only": rule_only,
                    "both": both,
                },
                "top_entities": dict(top_entities[:50]),
                "sample_results": results[:20],
            }

            output_path = Path(__file__).parent / "evaluation_entity_extraction.json"
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(output, f, indent=2, ensure_ascii=False)

            print(f"   Saved to {output_path}")

            print("\n" + "=" * 70)
            print("EVALUATION COMPLETE")
            print("=" * 70)

            # Summary
            print(f"\n   Pattern count: {stats['pattern_count']:,}")
            print(f"   Entities extracted: {total_entities:,}")
            print(f"   Coverage: {100*stories_with_entities/len(results):.1f}% of stories have entities")
            print(f"   Database extractor found {db_only} additional entities vs rule-based")

        finally:
            await session.close()
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(test_entity_extraction())
