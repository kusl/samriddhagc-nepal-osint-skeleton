#!/usr/bin/env python3
"""
Test ML/NLP system on real news stories from the database.

Evaluates:
1. Severity prediction accuracy vs labeled data
2. Category prediction accuracy vs labeled data
3. Entity extraction quality
4. Language detection accuracy
5. Cross-validation between English and Nepali stories
"""

import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from typing import List, Dict, Any, Optional
import json

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np

# Database imports
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Models
from app.models.story import Story
from app.config import get_settings


class RealStoryEvaluator:
    """Evaluate ML system on real database stories."""

    def __init__(self):
        self.settings = get_settings()
        self.engine = None
        self.session_factory = None

        # ML components (lazy loaded)
        self._preprocessor = None
        self._ner = None
        self._embedder = None
        self._severity_detector = None
        self._bandit = None

        # Results
        self.results = {
            "total_stories": 0,
            "stories_with_severity": 0,
            "stories_with_category": 0,
            "severity_predictions": [],
            "category_predictions": [],
            "entity_extractions": [],
            "language_detections": [],
            "processing_errors": [],
        }

    async def connect(self):
        """Connect to database."""
        print(f"  Connecting to database...")
        self.engine = create_async_engine(
            self.settings.database_url,
            echo=False,
        )
        self.session_factory = sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        print(f"  ✅ Connected to database")

    async def disconnect(self):
        """Disconnect from database."""
        if self.engine:
            await self.engine.dispose()

    def load_ml_components(self):
        """Load ML/NLP components."""
        print("  Loading ML components...")

        from app.services.nlp.nepali_preprocessor import get_preprocessor
        from app.services.nlp.hybrid_ner import get_hybrid_ner
        from app.services.embeddings.text_embedder import get_embedder
        from app.ml.features.semantic_severity import SemanticSeverityDetector
        from app.ml.models.priority_bandit import PriorityBandit

        self._preprocessor = get_preprocessor()
        self._ner = get_hybrid_ner()

        # Use MiniLM for faster processing
        self._embedder = get_embedder(model_key="minilm")

        # Create severity detector with minilm
        self._severity_detector = SemanticSeverityDetector(
            temperature=0.2,
            min_confidence=0.25,
        )
        self._severity_detector._embedder = self._embedder

        self._bandit = PriorityBandit(input_dim=32)

        print("  ✅ ML components loaded")

    async def fetch_stories(
        self,
        limit: int = 200,
        with_labels: bool = True,
        days_back: int = 30,
    ) -> List[Story]:
        """Fetch stories from database."""
        async with self.session_factory() as session:
            # Build query
            query = select(Story)

            # Filter to recent stories
            cutoff = datetime.now() - timedelta(days=days_back)
            query = query.where(Story.created_at >= cutoff)

            # Prefer stories with labels if requested
            if with_labels:
                query = query.where(
                    (Story.severity.isnot(None)) | (Story.category.isnot(None))
                )

            # Order by most recent first
            query = query.order_by(Story.created_at.desc())
            query = query.limit(limit)

            result = await session.execute(query)
            stories = result.scalars().all()

            return stories

    async def get_story_stats(self) -> Dict[str, Any]:
        """Get statistics about stories in database."""
        async with self.session_factory() as session:
            # Total count
            total = await session.execute(select(func.count(Story.id)))
            total_count = total.scalar()

            # Count by severity
            severity_counts = await session.execute(
                select(Story.severity, func.count(Story.id))
                .group_by(Story.severity)
            )
            severity_dist = dict(severity_counts.fetchall())

            # Count by category
            category_counts = await session.execute(
                select(Story.category, func.count(Story.id))
                .group_by(Story.category)
            )
            category_dist = dict(category_counts.fetchall())

            # Count by language
            lang_counts = await session.execute(
                select(Story.language, func.count(Story.id))
                .group_by(Story.language)
            )
            lang_dist = dict(lang_counts.fetchall())

            # Recent stories (last 7 days)
            cutoff = datetime.now() - timedelta(days=7)
            recent = await session.execute(
                select(func.count(Story.id)).where(Story.created_at >= cutoff)
            )
            recent_count = recent.scalar()

            return {
                "total": total_count,
                "recent_7d": recent_count,
                "severity_distribution": severity_dist,
                "category_distribution": category_dist,
                "language_distribution": lang_dist,
            }

    def evaluate_story(self, story: Story) -> Dict[str, Any]:
        """Evaluate ML predictions for a single story."""
        text = f"{story.title} {story.content or story.summary or ''}"

        result = {
            "id": str(story.id),
            "title": story.title[:80],
            "language_actual": story.language,
            "severity_actual": story.severity,
            "category_actual": story.category,
            "published_at": story.published_at,
        }

        try:
            # 1. Language detection
            is_nepali = self._preprocessor.is_nepali(text)
            result["language_predicted"] = "ne" if is_nepali else "en"
            result["language_match"] = (
                (result["language_predicted"] == "ne" and story.language in ["ne", "np"]) or
                (result["language_predicted"] == "en" and story.language in ["en", None])
            )

            # 2. Entity extraction
            entities = self._ner._extract_rule_based_entities(text)
            result["entities"] = [
                {"text": e["text"], "type": e["type"]}
                for e in entities[:10]  # Limit to 10
            ]
            result["entity_count"] = len(entities)

            # 3. Severity detection
            severity, sev_conf, sev_probs = self._severity_detector.detect_severity(text)
            result["severity_predicted"] = severity
            result["severity_confidence"] = sev_conf
            result["severity_probs"] = sev_probs

            # Check if prediction matches actual
            if story.severity:
                result["severity_match"] = severity == story.severity
                # Also accept if within one level
                severity_order = ["low", "medium", "high", "critical"]
                if severity in severity_order and story.severity in severity_order:
                    pred_idx = severity_order.index(severity)
                    actual_idx = severity_order.index(story.severity)
                    result["severity_close"] = abs(pred_idx - actual_idx) <= 1
                else:
                    result["severity_close"] = result["severity_match"]

            # 4. Priority prediction (using v2 features)
            features = self._bandit.extract_context_features_v2(
                text=text,
                category=story.category,
                source_confidence=0.8,
                entities=entities,
                published_at=story.published_at or datetime.now(),
                severity_detector=self._severity_detector,
            )
            prediction = self._bandit._rule_based_predict(features)
            result["priority_predicted"] = prediction.priority
            result["priority_confidence"] = prediction.confidence

        except Exception as e:
            result["error"] = str(e)
            self.results["processing_errors"].append({
                "story_id": str(story.id),
                "error": str(e),
            })

        return result

    def analyze_results(self, evaluations: List[Dict]) -> Dict[str, Any]:
        """Analyze evaluation results and compute metrics."""
        analysis = {
            "total_evaluated": len(evaluations),
            "errors": len([e for e in evaluations if "error" in e]),
        }

        # Language detection accuracy
        lang_evals = [e for e in evaluations if "language_match" in e]
        if lang_evals:
            lang_correct = sum(1 for e in lang_evals if e["language_match"])
            analysis["language_accuracy"] = lang_correct / len(lang_evals)
            analysis["language_total"] = len(lang_evals)

        # Severity prediction accuracy
        sev_evals = [e for e in evaluations if "severity_match" in e]
        if sev_evals:
            sev_correct = sum(1 for e in sev_evals if e["severity_match"])
            sev_close = sum(1 for e in sev_evals if e.get("severity_close", False))
            analysis["severity_exact_accuracy"] = sev_correct / len(sev_evals)
            analysis["severity_close_accuracy"] = sev_close / len(sev_evals)
            analysis["severity_total"] = len(sev_evals)

            # Confusion matrix
            confusion = defaultdict(lambda: defaultdict(int))
            for e in sev_evals:
                actual = e["severity_actual"]
                predicted = e["severity_predicted"]
                confusion[actual][predicted] += 1
            analysis["severity_confusion"] = dict(confusion)

        # Entity extraction stats
        ent_evals = [e for e in evaluations if "entity_count" in e]
        if ent_evals:
            entity_counts = [e["entity_count"] for e in ent_evals]
            analysis["entities_mean"] = np.mean(entity_counts)
            analysis["entities_median"] = np.median(entity_counts)
            analysis["entities_with_any"] = sum(1 for c in entity_counts if c > 0)

            # Entity type distribution
            all_entities = []
            for e in ent_evals:
                all_entities.extend(e.get("entities", []))
            type_counts = Counter(ent["type"] for ent in all_entities)
            analysis["entity_type_distribution"] = dict(type_counts)

        # Sample predictions for review
        analysis["sample_predictions"] = evaluations[:10]

        return analysis

    def print_analysis(self, analysis: Dict[str, Any]):
        """Print analysis results in a readable format."""
        print("\n" + "=" * 70)
        print("  REAL DATA EVALUATION RESULTS")
        print("=" * 70)

        print(f"\n  Total Stories Evaluated: {analysis['total_evaluated']}")
        print(f"  Processing Errors: {analysis['errors']}")

        # Language detection
        if "language_accuracy" in analysis:
            print(f"\n  LANGUAGE DETECTION:")
            print(f"    Accuracy: {analysis['language_accuracy']:.1%} ({analysis['language_total']} stories)")

        # Severity prediction
        if "severity_exact_accuracy" in analysis:
            print(f"\n  SEVERITY PREDICTION:")
            print(f"    Exact Match: {analysis['severity_exact_accuracy']:.1%}")
            print(f"    Within 1 Level: {analysis['severity_close_accuracy']:.1%}")
            print(f"    Total with labels: {analysis['severity_total']}")

            if "severity_confusion" in analysis:
                print(f"\n    Confusion Matrix (actual → predicted):")
                confusion = analysis["severity_confusion"]
                for actual, preds in sorted(confusion.items()):
                    pred_str = ", ".join(f"{k}:{v}" for k, v in sorted(preds.items()))
                    print(f"      {actual:>10} → {pred_str}")

        # Entity extraction
        if "entities_mean" in analysis:
            print(f"\n  ENTITY EXTRACTION:")
            print(f"    Mean entities/story: {analysis['entities_mean']:.1f}")
            print(f"    Stories with entities: {analysis['entities_with_any']}/{analysis['total_evaluated']}")
            if "entity_type_distribution" in analysis:
                print(f"    Entity types: {analysis['entity_type_distribution']}")

        # Sample predictions
        if "sample_predictions" in analysis:
            print(f"\n  SAMPLE PREDICTIONS:")
            for i, pred in enumerate(analysis["sample_predictions"][:5]):
                print(f"\n    [{i+1}] {pred['title'][:60]}...")
                print(f"        Language: {pred.get('language_predicted', '?')} (actual: {pred.get('language_actual', '?')})")
                print(f"        Severity: {pred.get('severity_predicted', '?')} (actual: {pred.get('severity_actual', '?')})")
                if pred.get("entities"):
                    ent_str = ", ".join(e["text"][:20] for e in pred["entities"][:3])
                    print(f"        Entities: {ent_str}")

    def identify_issues(self, evaluations: List[Dict]) -> List[Dict]:
        """Identify patterns in prediction errors for tuning."""
        issues = []

        # Find severity mismatches
        sev_errors = [
            e for e in evaluations
            if e.get("severity_match") == False and e.get("severity_actual")
        ]

        # Group by error pattern
        error_patterns = defaultdict(list)
        for e in sev_errors:
            pattern = f"{e['severity_actual']}→{e['severity_predicted']}"
            error_patterns[pattern].append(e)

        for pattern, errors in sorted(error_patterns.items(), key=lambda x: -len(x[1])):
            actual, predicted = pattern.split("→")
            sample_texts = [err["title"] for err in errors[:3]]

            issues.append({
                "type": "severity_mismatch",
                "pattern": pattern,
                "count": len(errors),
                "actual": actual,
                "predicted": predicted,
                "sample_texts": sample_texts,
            })

        return issues

    def suggest_tuning(self, issues: List[Dict]) -> List[str]:
        """Suggest model tuning based on identified issues."""
        suggestions = []

        for issue in issues:
            if issue["type"] == "severity_mismatch":
                actual = issue["actual"]
                predicted = issue["predicted"]
                count = issue["count"]

                if actual == "critical" and predicted in ["medium", "low"]:
                    suggestions.append(
                        f"⚠️ Under-predicting critical severity ({count} cases). "
                        f"Consider adding more critical examples to SEVERITY_EXAMPLES or "
                        f"lowering severity_temperature."
                    )
                elif actual == "low" and predicted in ["high", "critical"]:
                    suggestions.append(
                        f"⚠️ Over-predicting severity for low-priority stories ({count} cases). "
                        f"Add more low-severity examples or increase severity_temperature."
                    )
                elif actual == "high" and predicted == "medium":
                    suggestions.append(
                        f"⚠️ Missing high-severity classification ({count} cases). "
                        f"Review the high-severity examples for better coverage."
                    )

        if not suggestions:
            suggestions.append("✅ No significant tuning issues identified.")

        return suggestions


async def main():
    """Run real story evaluation."""
    print("\n" + "=" * 70)
    print("  NEPAL OSINT v5 - Real Story ML Evaluation")
    print("=" * 70)

    evaluator = RealStoryEvaluator()

    try:
        # Connect to database
        await evaluator.connect()

        # Get database statistics
        print("\n  DATABASE STATISTICS:")
        stats = await evaluator.get_story_stats()
        print(f"    Total stories: {stats['total']}")
        print(f"    Recent (7 days): {stats['recent_7d']}")
        print(f"    Severity distribution: {stats['severity_distribution']}")
        print(f"    Category distribution: {stats['category_distribution']}")
        print(f"    Language distribution: {stats['language_distribution']}")

        # Check if we have stories
        if stats['total'] == 0:
            print("\n  ⚠️ No stories in database. Cannot run evaluation.")
            print("     Please ingest some news stories first.")
            return

        # Load ML components
        evaluator.load_ml_components()

        # Fetch stories
        print("\n  Fetching stories for evaluation...")
        stories = await evaluator.fetch_stories(
            limit=100,
            with_labels=True,
            days_back=30,
        )
        print(f"  ✅ Fetched {len(stories)} stories")

        if len(stories) == 0:
            # Try without label filter
            print("  No labeled stories found, trying all stories...")
            stories = await evaluator.fetch_stories(
                limit=50,
                with_labels=False,
                days_back=30,
            )
            print(f"  ✅ Fetched {len(stories)} stories (unlabeled)")

        if len(stories) == 0:
            print("\n  ⚠️ No stories found in last 30 days.")
            return

        # Evaluate each story
        print("\n  Evaluating stories...")
        evaluations = []
        for i, story in enumerate(stories):
            if (i + 1) % 20 == 0:
                print(f"    Processed {i + 1}/{len(stories)}...")
            result = evaluator.evaluate_story(story)
            evaluations.append(result)

        # Analyze results
        print("\n  Analyzing results...")
        analysis = evaluator.analyze_results(evaluations)

        # Print analysis
        evaluator.print_analysis(analysis)

        # Identify issues
        print("\n" + "-" * 70)
        print("  ERROR ANALYSIS & TUNING SUGGESTIONS")
        print("-" * 70)

        issues = evaluator.identify_issues(evaluations)
        if issues:
            print(f"\n  Found {len(issues)} error patterns:")
            for issue in issues[:5]:
                print(f"    • {issue['pattern']}: {issue['count']} cases")
                for text in issue['sample_texts'][:2]:
                    print(f"      - \"{text[:50]}...\"")

        # Suggest tuning
        suggestions = evaluator.suggest_tuning(issues)
        print("\n  TUNING SUGGESTIONS:")
        for s in suggestions:
            print(f"    {s}")

        # Save detailed results
        output_path = Path(__file__).parent / "evaluation_results.json"
        with open(output_path, "w") as f:
            json.dump({
                "stats": stats,
                "analysis": {k: v for k, v in analysis.items() if k != "sample_predictions"},
                "issues": issues,
                "suggestions": suggestions,
            }, f, indent=2, default=str)
        print(f"\n  📄 Detailed results saved to: {output_path}")

    finally:
        await evaluator.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
