#!/usr/bin/env python3
"""Debug why rule-based finds more entities than database extractor."""

import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://nepal_osint:nepal_osint_dev@localhost:5433/nepal_osint_v5")


async def main():
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import text

    database_url = os.environ.get("DATABASE_URL")
    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    session = async_session()

    async with session:
        # Initialize extractors
        from app.services.nlp.database_entity_extractor import DatabaseEntityExtractor
        from app.services.nlp.hybrid_ner import HybridNER

        db_extractor = DatabaseEntityExtractor()
        await db_extractor.initialize(session)

        rule_ner = HybridNER(use_transformer=False)

        # Get 10 sample stories
        query = text("""
            SELECT id, title, language FROM stories
            WHERE title IS NOT NULL AND LENGTH(title) > 10
            ORDER BY RANDOM()
            LIMIT 10
        """)
        result = await session.execute(query)
        stories = result.fetchall()

        print("=" * 70)
        print("ENTITY EXTRACTION COMPARISON")
        print("=" * 70)

        for story_id, title, lang in stories:
            print(f"\n{'=' * 70}")
            print(f"TITLE ({lang}): {title[:80]}")
            print("-" * 70)

            # Database extraction
            db_entities = await db_extractor.extract(title, min_confidence=0.3, session=session)
            db_canonicals = {e.canonical_id: e for e in db_entities}

            print(f"\nDATABASE EXTRACTOR ({len(db_entities)} entities):")
            for e in db_entities:
                print(f"  - {e.text} -> {e.canonical_id} ({e.entity_type}, {e.confidence:.2f}, {e.source})")

            # Rule-based extraction
            rule_entities = rule_ner.extract_entities(title)
            rule_canonicals = {e.get("canonical_id"): e for e in rule_entities if e.get("canonical_id")}

            print(f"\nRULE-BASED NER ({len(rule_entities)} entities):")
            for e in rule_entities:
                print(f"  - {e.get('text')} -> {e.get('canonical_id')} ({e.get('type')}, {e.get('confidence'):.2f})")

            # Differences
            db_only = set(db_canonicals.keys()) - set(rule_canonicals.keys())
            rule_only = set(rule_canonicals.keys()) - set(db_canonicals.keys())

            if db_only:
                print(f"\n  DB ONLY: {db_only}")
            if rule_only:
                print(f"\n  RULE ONLY: {rule_only}")

        await session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
