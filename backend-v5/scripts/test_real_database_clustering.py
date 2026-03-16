#!/usr/bin/env python3
"""
Test Palantir-grade clustering on REAL database stories.

This script:
1. Fetches recent stories from the database
2. Runs hybrid semantic clustering
3. Computes corroboration metrics for each cluster
4. Displays "Story backed by N sources" output
5. Computes intelligence scores
"""

import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict

# Add backend-v5 to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set environment variables
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://nepal_osint:nepal_osint_dev@localhost:5433/nepal_osint_v5")


async def main():
    print("\n" + "=" * 70)
    print("PALANTIR-GRADE CLUSTERING - REAL DATABASE TEST")
    print("=" * 70)

    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import select, text, func

    database_url = os.environ.get("DATABASE_URL")
    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # ============================================================
        # 1. Check database status
        # ============================================================
        print("\n1. DATABASE STATUS")
        print("-" * 50)

        # Count stories
        result = await session.execute(text("SELECT COUNT(*) FROM stories"))
        story_count = result.scalar()
        print(f"   Total stories: {story_count:,}")

        # Count recent stories (last 72 hours)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=72)
        result = await session.execute(
            text("SELECT COUNT(*) FROM stories WHERE published_at >= :cutoff"),
            {"cutoff": cutoff}
        )
        recent_count = result.scalar()
        print(f"   Stories in last 72h: {recent_count:,}")

        # Count existing clusters
        result = await session.execute(text("SELECT COUNT(*) FROM story_clusters"))
        cluster_count = result.scalar()
        print(f"   Existing clusters: {cluster_count:,}")

        # Count stories with embeddings
        result = await session.execute(text("SELECT COUNT(*) FROM story_embeddings"))
        embedding_count = result.scalar()
        print(f"   Stories with embeddings: {embedding_count:,}")

        # ============================================================
        # 2. Run hybrid clustering
        # ============================================================
        print("\n2. RUNNING HYBRID CLUSTERING")
        print("-" * 50)

        from app.services.clustering.clustering_service import ClusteringService

        clustering_service = ClusteringService(
            db=session,
            use_hybrid_semantic=True,
            use_llm_validation=False,  # Skip LLM for faster testing
        )

        start_time = datetime.now()
        stats = await clustering_service.cluster_stories(
            hours=72,
            min_cluster_size=2,
        )
        elapsed = (datetime.now() - start_time).total_seconds()

        print(f"   Clustering completed in {elapsed:.1f}s")
        print(f"   Stories processed: {stats['stories_processed']}")
        print(f"   Candidate pairs: {stats.get('candidate_pairs', 0)}")
        print(f"   Edges created: {stats['edges_created']}")
        print(f"   Clusters created: {stats['clusters_created']}")
        print(f"   Clusters updated: {stats['clusters_updated']}")
        print(f"   Stories clustered: {stats['stories_clustered']}")
        print(f"   Stories unclustered: {stats['stories_unclustered']}")
        print(f"   Cross-lingual pairs: {stats.get('cross_lingual_pairs', 0)}")
        print(f"   Embeddings loaded: {stats.get('embeddings_loaded', 0)}")

        # ============================================================
        # 3. Fetch clusters and compute corroboration
        # ============================================================
        print("\n3. CORROBORATION ANALYSIS")
        print("-" * 50)

        from app.models.story_cluster import StoryCluster
        from app.models.story import Story
        from app.services.corroboration.corroboration_service import CorroborationService
        from app.services.intelligence.intelligence_scorer import IntelligenceScorer

        corr_service = CorroborationService(db=session)
        intel_scorer = IntelligenceScorer()

        # Fetch recent clusters with stories
        result = await session.execute(
            select(StoryCluster)
            .where(StoryCluster.first_published >= cutoff)
            .order_by(StoryCluster.story_count.desc())
            .limit(20)
        )
        clusters = result.scalars().all()

        print(f"\n   Found {len(clusters)} clusters in last 72h\n")

        if not clusters:
            print("   No clusters found. Try running with more stories.")
            await session.close()
            await engine.dispose()
            return

        # Process each cluster
        cluster_results = []

        for i, cluster in enumerate(clusters[:10]):  # Top 10
            # Fetch stories for this cluster
            result = await session.execute(
                select(Story).where(Story.cluster_id == cluster.id)
            )
            stories = list(result.scalars().all())

            # Compute corroboration
            corr = corr_service.compute_corroboration(stories)

            # Compute intelligence score
            intel = intel_scorer.score(cluster, corr)

            # Update cluster with corroboration data
            cluster.unique_sources = corr.unique_sources
            cluster.diversity_score = corr.diversity_score
            cluster.confidence_level = corr.confidence_level
            cluster.languages = corr.languages
            cluster.cross_lingual_match = corr.cross_lingual
            cluster.intelligence_score = intel.overall_score
            cluster.actionability = intel.actionability

            cluster_results.append({
                'cluster': cluster,
                'corr': corr,
                'intel': intel,
                'stories': stories,
            })

        # Commit updates
        await session.commit()

        # ============================================================
        # 4. Display results - "Story backed by N sources"
        # ============================================================
        print("\n4. CLUSTER RESULTS - 'STORY BACKED BY N SOURCES'")
        print("=" * 70)

        for i, result in enumerate(cluster_results):
            cluster = result['cluster']
            corr = result['corr']
            intel = result['intel']
            stories = result['stories']

            print(f"\n{'─' * 70}")
            print(f"CLUSTER #{i+1}: {cluster.headline[:60]}...")
            print(f"{'─' * 70}")

            # The key metric: "Backed by N sources"
            print(f"\n   📰 BACKED BY {corr.source_count} SOURCE{'S' if corr.source_count > 1 else ''}")
            print(f"   Sources: {', '.join(corr.unique_sources[:5])}")
            if len(corr.unique_sources) > 5:
                print(f"            ... and {len(corr.unique_sources) - 5} more")

            # Confidence level with emoji
            confidence_emoji = {
                "single_source": "⚠️",
                "corroborated": "✓",
                "well_corroborated": "✓✓",
                "highly_corroborated": "✓✓✓",
            }
            print(f"\n   {confidence_emoji.get(corr.confidence_level, '?')} Confidence: {corr.confidence_level.replace('_', ' ').title()}")
            print(f"   📊 Diversity Score: {corr.diversity_score:.2f} (Simpson Index)")

            # Cross-lingual
            if corr.cross_lingual:
                print(f"   🌐 Cross-lingual: {', '.join(corr.languages)}")

            # Intelligence score
            action_emoji = {"immediate": "🚨", "monitor": "👁️", "archive": "📁"}
            print(f"\n   🧠 Intelligence Score: {intel.overall_score:.1f}/100")
            print(f"   {action_emoji.get(intel.actionability, '?')} Actionability: {intel.actionability.upper()}")
            print(f"   💡 {intel.reasoning}")

            # Show confirmation chain (first 3)
            if corr.confirmation_chain:
                print(f"\n   📜 Confirmation Chain:")
                for entry in corr.confirmation_chain[:3]:
                    ts = entry.timestamp[:16] if entry.timestamp else "?"
                    lang = f" [{entry.language}]" if entry.language else ""
                    print(f"      • {ts} | {entry.source}{lang}")
                    print(f"        \"{entry.snippet[:50]}...\"")

            # Category and severity
            print(f"\n   Category: {cluster.category or 'N/A'} | Severity: {cluster.severity or 'N/A'}")
            print(f"   Stories: {cluster.story_count}")

        # ============================================================
        # 5. Summary statistics
        # ============================================================
        print("\n" + "=" * 70)
        print("5. SUMMARY STATISTICS")
        print("=" * 70)

        # Confidence level distribution
        confidence_dist = defaultdict(int)
        for r in cluster_results:
            confidence_dist[r['corr'].confidence_level] += 1

        print("\n   Confidence Distribution:")
        for level in ["single_source", "corroborated", "well_corroborated", "highly_corroborated"]:
            count = confidence_dist.get(level, 0)
            bar = "█" * count
            print(f"      {level:25s}: {count:3d} {bar}")

        # Actionability distribution
        action_dist = defaultdict(int)
        for r in cluster_results:
            action_dist[r['intel'].actionability] += 1

        print("\n   Actionability Distribution:")
        for action in ["immediate", "monitor", "archive"]:
            count = action_dist.get(action, 0)
            bar = "█" * count
            print(f"      {action:12s}: {count:3d} {bar}")

        # Cross-lingual stats
        cross_lingual_count = sum(1 for r in cluster_results if r['corr'].cross_lingual)
        print(f"\n   Cross-lingual clusters: {cross_lingual_count}/{len(cluster_results)}")

        # Average metrics
        avg_sources = sum(r['corr'].source_count for r in cluster_results) / len(cluster_results)
        avg_diversity = sum(r['corr'].diversity_score for r in cluster_results) / len(cluster_results)
        avg_intel = sum(r['intel'].overall_score for r in cluster_results) / len(cluster_results)

        print(f"\n   Average sources per cluster: {avg_sources:.1f}")
        print(f"   Average diversity score: {avg_diversity:.2f}")
        print(f"   Average intelligence score: {avg_intel:.1f}/100")

        # ============================================================
        # 6. Show a specific example with all details
        # ============================================================
        if cluster_results:
            best = max(cluster_results, key=lambda r: r['corr'].source_count)
            print("\n" + "=" * 70)
            print("6. BEST CORROBORATED STORY EXAMPLE")
            print("=" * 70)

            print(f"\n   Headline: {best['cluster'].headline[:70]}...")
            print(f"\n   Backed by {best['corr'].source_count} sources:")
            for i, source in enumerate(best['corr'].unique_sources):
                print(f"      {i+1}. {source}")

            print(f"\n   Individual story headlines:")
            for i, story in enumerate(best['stories'][:5]):
                lang_tag = f" [{story.language}]" if hasattr(story, 'language') and story.language else ""
                print(f"      {i+1}. {story.title[:60]}...{lang_tag}")

        print("\n" + "=" * 70)
        print("TEST COMPLETE")
        print("=" * 70)

        await session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
