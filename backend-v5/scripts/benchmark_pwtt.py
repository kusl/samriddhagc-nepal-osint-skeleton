#!/usr/bin/env python3
"""
PWTT Benchmark Evaluation Script.

This runner evaluates the local PWTT-style score against the public
benchmark dataset while keeping the implementation and reporting logic
independent from the upstream repository.

What it does:
1. Computes the local multi-scale PWTT score from the benchmark CSVs.
2. Evaluates the fixed-threshold variant that matches our current logic.
3. Compares against the published benchmark table city by city.
4. Prints diagnostic variants to help explain mismatches.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from sklearn.metrics import (
        accuracy_score,
        f1_score,
        precision_recall_curve,
        precision_score,
        recall_score,
        roc_auc_score,
        roc_curve,
    )
except ImportError:
    print("Installing scikit-learn...")
    os.system("pip install scikit-learn")
    from sklearn.metrics import (
        accuracy_score,
        f1_score,
        precision_recall_curve,
        precision_score,
        recall_score,
        roc_auc_score,
        roc_curve,
    )


REFERENCE_SUMMARY = {
    "auc": 84.17,
    "accuracy": 76.40,
    "f1": 58.20,
    "precision": 48.04,
    "recall": 73.82,
    "n": 873072,
}

REFERENCE_BENCHMARK = {
    "Gaza": {"country": "Palestine", "auc": 83.32, "accuracy": 75.41, "f1": 78.2, "precision": 70.42, "recall": 87.91, "n": 228728},
    "Kremenchuk": {"country": "Ukraine", "auc": 92.56, "accuracy": 98.82, "f1": 2.73, "precision": 2.68, "recall": 2.77, "n": 27497},
    "Bucha": {"country": "Ukraine", "auc": 90.19, "accuracy": 98.19, "f1": 71.9, "precision": 98.27, "recall": 56.68, "n": 5739},
    "Okhtyrka": {"country": "Ukraine", "auc": 89.28, "accuracy": 98.9, "f1": 53.14, "precision": 76.28, "recall": 40.77, "n": 15905},
    "Kramatorsk": {"country": "Ukraine", "auc": 88.24, "accuracy": 97.16, "f1": 7.92, "precision": 11.99, "recall": 5.91, "n": 21880},
    "Trostianets": {"country": "Ukraine", "auc": 86.63, "accuracy": 98.44, "f1": 67.6, "precision": 80.58, "recall": 58.23, "n": 8913},
    "Chernihiv": {"country": "Ukraine", "auc": 86.61, "accuracy": 94.47, "f1": 48.29, "precision": 53.48, "recall": 44.03, "n": 29929},
    "Hostomel": {"country": "Ukraine", "auc": 84.99, "accuracy": 80.44, "f1": 68.11, "precision": 63.87, "recall": 72.95, "n": 4175},
    "Irpin": {"country": "Ukraine", "auc": 83.81, "accuracy": 82.93, "f1": 56.75, "precision": 52.83, "recall": 61.3, "n": 7242},
    "Kharkiv": {"country": "Ukraine", "auc": 83.78, "accuracy": 97.24, "f1": 29.37, "precision": 30.44, "recall": 28.36, "n": 107976},
    "Mykolaiv": {"country": "Ukraine", "auc": 83.28, "accuracy": 98.18, "f1": 21.61, "precision": 18.71, "recall": 25.57, "n": 60467},
    "Makariv": {"country": "Ukraine", "auc": 82.87, "accuracy": 90.37, "f1": 40.69, "precision": 34.88, "recall": 48.82, "n": 3514},
    "Lysychansk": {"country": "Ukraine", "auc": 77.91, "accuracy": 82.59, "f1": 50.14, "precision": 47.38, "recall": 53.24, "n": 20246},
    "Rubizhne": {"country": "Ukraine", "auc": 77.81, "accuracy": 71.38, "f1": 66.42, "precision": 62.14, "recall": 71.33, "n": 8899},
    "Mariupol": {"country": "Ukraine", "auc": 73.85, "accuracy": 66.17, "f1": 71.08, "precision": 60.78, "recall": 85.57, "n": 18446},
    "Shchastia": {"country": "Ukraine", "auc": 73.39, "accuracy": 96.69, "f1": 38.31, "precision": 47.12, "recall": 32.28, "n": 1293},
    "Sumy": {"country": "Ukraine", "auc": 69.63, "accuracy": 99.51, "f1": 4.26, "precision": 4.36, "recall": 4.16, "n": 28265},
    "Sievierodonetsk": {"country": "Ukraine", "auc": 69.18, "accuracy": 59.3, "f1": 62.53, "precision": 50.71, "recall": 81.54, "n": 5970},
    "Melitopol": {"country": "Ukraine", "auc": 66.84, "accuracy": 96.77, "f1": 2.67, "precision": 1.78, "recall": 5.33, "n": 32373},
    "Avdiivka": {"country": "Ukraine", "auc": 66.51, "accuracy": 60.64, "f1": 39.8, "precision": 28.05, "recall": 68.5, "n": 7262},
    "Raqqa": {"country": "Syria", "auc": 75.6, "accuracy": 66.26, "f1": 73.87, "precision": 63.21, "recall": 88.87, "n": 24689},
    "Aleppo": {"country": "Syria", "auc": 71.76, "accuracy": 61.49, "f1": 58.82, "precision": 46.28, "recall": 80.67, "n": 65870},
    "Mosul": {"country": "Iraq", "auc": 74.91, "accuracy": 81.16, "f1": 41.18, "precision": 35.18, "recall": 49.64, "n": 137794},
}

REQUIRED_COLUMNS = ["class", "max_change", "k50", "k100", "k150"]


@dataclass
class ReferenceMetrics:
    country: str
    auc: float
    accuracy: float
    f1: float
    precision: float
    recall: float
    n: int


@dataclass
class MetricBundle:
    auc: float
    accuracy: float
    f1: float
    precision: float
    recall: float
    threshold: float
    positive_rate: float


@dataclass
class BenchmarkResult:
    city: str
    event_date: str
    total_buildings: int
    damaged_buildings: int
    damage_rate: float
    fixed_pwtt: MetricBundle
    fixed_max_change: MetricBundle
    tuned_pwtt: MetricBundle
    reference: Optional[ReferenceMetrics]

    @property
    def auc(self) -> float:
        return self.fixed_pwtt.auc

    @property
    def accuracy(self) -> float:
        return self.fixed_pwtt.accuracy

    @property
    def f1(self) -> float:
        return self.fixed_pwtt.f1

    @property
    def precision(self) -> float:
        return self.fixed_pwtt.precision

    @property
    def recall(self) -> float:
        return self.fixed_pwtt.recall

    @property
    def optimal_threshold(self) -> float:
        return self.tuned_pwtt.threshold


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark the local PWTT implementation.")
    parser.add_argument(
        "--data-dir",
        default="/Users/samriddhagc/Downloads/one_month",
        help="Directory containing *_footprints.csv benchmark files.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=3.0,
        help="Fixed threshold applied to the local PWTT score.",
    )
    parser.add_argument(
        "--cities",
        nargs="*",
        default=None,
        help="Optional list of city names to evaluate.",
    )
    parser.add_argument(
        "--json-out",
        default=None,
        help="Optional path to write a JSON report.",
    )
    return parser.parse_args()


def load_footprints(csv_path: Path) -> pd.DataFrame:
    """Load building footprints without pandas low-memory type guessing."""
    return pd.read_csv(csv_path, low_memory=False)


def parse_city_metadata(csv_path: Path) -> tuple[str, str]:
    filename = csv_path.stem
    parts = filename.replace("_footprints", "").split("_")
    city = parts[0]
    event_date = parts[1] if len(parts) > 1 else "unknown"
    return city, event_date


def compute_pwtt_score(frame: pd.DataFrame) -> pd.Series:
    """
    Construct our local multi-scale score.

    We intentionally keep this as a transparent local implementation built
    from the benchmark columns instead of mirroring upstream code structure.
    """
    numeric = frame[["max_change", "k50", "k100", "k150"]].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    return numeric.mean(axis=1)


def prepare_city_frame(csv_path: Path) -> tuple[str, str, pd.DataFrame]:
    city, event_date = parse_city_metadata(csv_path)
    df = load_footprints(csv_path)

    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"{city}: missing required columns {missing}")

    df = df.dropna(subset=["class"]).copy()
    df = df[df["class"].isin([0, 1])].copy()
    if df.empty:
        raise ValueError(f"{city}: no valid benchmark rows")

    df["class"] = df["class"].astype(int)
    df["max_change"] = pd.to_numeric(df["max_change"], errors="coerce").fillna(0.0)
    df["pwtt_score"] = compute_pwtt_score(df)
    return city, event_date, df


def safe_auc(y_true: np.ndarray, scores: np.ndarray) -> float:
    if len(np.unique(y_true)) < 2:
        return 0.5
    return float(roc_auc_score(y_true, scores))


def metric_bundle(y_true: np.ndarray, scores: np.ndarray, threshold: float) -> MetricBundle:
    y_pred = (scores >= threshold).astype(int)
    return MetricBundle(
        auc=safe_auc(y_true, scores),
        accuracy=float(accuracy_score(y_true, y_pred)),
        f1=float(f1_score(y_true, y_pred, zero_division=0)),
        precision=float(precision_score(y_true, y_pred, zero_division=0)),
        recall=float(recall_score(y_true, y_pred, zero_division=0)),
        threshold=float(threshold),
        positive_rate=float(y_pred.mean()) if len(y_pred) else 0.0,
    )


def find_threshold_for_best_f1(y_true: np.ndarray, scores: np.ndarray) -> float:
    precision, recall, thresholds = precision_recall_curve(y_true, scores)
    if len(thresholds) == 0:
        return 0.0
    f1_values = (2 * precision[:-1] * recall[:-1]) / np.clip(precision[:-1] + recall[:-1], 1e-12, None)
    best_index = int(np.argmax(f1_values))
    return float(thresholds[best_index])


def find_threshold_by_youden(y_true: np.ndarray, scores: np.ndarray) -> float:
    if len(np.unique(y_true)) < 2:
        return 0.0
    fpr, tpr, thresholds = roc_curve(y_true, scores)
    youden = tpr - fpr
    best_index = int(np.argmax(youden))
    return float(thresholds[best_index])


def evaluate_city(csv_path: str | Path, threshold: float = 3.0) -> Optional[BenchmarkResult]:
    csv_path = Path(csv_path)
    try:
        city, event_date, df = prepare_city_frame(csv_path)
    except Exception as exc:
        print(f"  Error loading {csv_path.name}: {exc}")
        return None

    y_true = df["class"].to_numpy()
    pwtt_scores = df["pwtt_score"].to_numpy()
    max_change_scores = df["max_change"].to_numpy()

    if len(np.unique(y_true)) < 2:
        print(f"  Only one class in {city}, skipping")
        return None

    fixed_pwtt = metric_bundle(y_true, pwtt_scores, threshold)
    fixed_max_change = metric_bundle(y_true, max_change_scores, threshold)
    tuned_threshold = find_threshold_for_best_f1(y_true, pwtt_scores)
    tuned_pwtt = metric_bundle(y_true, pwtt_scores, tuned_threshold)

    total = int(len(df))
    damaged = int(y_true.sum())
    reference = REFERENCE_BENCHMARK.get(city)
    reference_metrics = ReferenceMetrics(**reference) if reference else None

    return BenchmarkResult(
        city=city,
        event_date=event_date,
        total_buildings=total,
        damaged_buildings=damaged,
        damage_rate=(damaged / total) if total else 0.0,
        fixed_pwtt=fixed_pwtt,
        fixed_max_change=fixed_max_change,
        tuned_pwtt=tuned_pwtt,
        reference=reference_metrics,
    )


def weighted_average_metric(results: list[BenchmarkResult], selector) -> float:
    weights = np.array([result.total_buildings for result in results], dtype=float)
    weights = weights / weights.sum()
    values = np.array([selector(result) for result in results], dtype=float)
    return float(np.average(values, weights=weights))


def run_benchmark(data_dir: str, threshold: float = 3.0, cities: Optional[list[str]] = None) -> list[BenchmarkResult]:
    data_path = Path(data_dir)
    footprint_files = sorted(data_path.glob("*_footprints.csv"))
    city_filter = {city.lower() for city in cities} if cities else None

    if city_filter:
        footprint_files = [
            csv_path for csv_path in footprint_files
            if parse_city_metadata(csv_path)[0].lower() in city_filter
        ]

    print(f"\n{'=' * 88}")
    print("PWTT BENCHMARK EVALUATION")
    print(f"{'=' * 88}")
    print(f"Data directory: {data_dir}")
    print(f"Fixed threshold: {threshold}")
    print(f"Cities found: {len(footprint_files)}")
    print(f"{'=' * 88}\n")

    results: list[BenchmarkResult] = []
    for index, csv_path in enumerate(footprint_files, 1):
        city_name, _ = parse_city_metadata(csv_path)
        print(f"[{index}/{len(footprint_files)}] Processing {city_name}...", end=" ")
        result = evaluate_city(csv_path, threshold)
        if result is None:
            print("SKIPPED")
            continue
        results.append(result)
        print(
            f"AUC={result.fixed_pwtt.auc:.2%}, "
            f"F1={result.fixed_pwtt.f1:.2%}, "
            f"N={result.total_buildings:,}, "
            f"tuned@{result.tuned_pwtt.threshold:.2f}"
        )

    return results


def print_summary(results: list[BenchmarkResult], threshold: float) -> None:
    if not results:
        print("\nNo results to summarize.")
        return

    total_buildings = sum(result.total_buildings for result in results)
    total_damaged = sum(result.damaged_buildings for result in results)

    fixed_summary = {
        "auc": weighted_average_metric(results, lambda result: result.fixed_pwtt.auc),
        "accuracy": weighted_average_metric(results, lambda result: result.fixed_pwtt.accuracy),
        "f1": weighted_average_metric(results, lambda result: result.fixed_pwtt.f1),
        "precision": weighted_average_metric(results, lambda result: result.fixed_pwtt.precision),
        "recall": weighted_average_metric(results, lambda result: result.fixed_pwtt.recall),
    }
    max_summary = {
        "auc": weighted_average_metric(results, lambda result: result.fixed_max_change.auc),
        "accuracy": weighted_average_metric(results, lambda result: result.fixed_max_change.accuracy),
        "f1": weighted_average_metric(results, lambda result: result.fixed_max_change.f1),
        "precision": weighted_average_metric(results, lambda result: result.fixed_max_change.precision),
        "recall": weighted_average_metric(results, lambda result: result.fixed_max_change.recall),
    }
    tuned_summary = {
        "auc": weighted_average_metric(results, lambda result: result.tuned_pwtt.auc),
        "accuracy": weighted_average_metric(results, lambda result: result.tuned_pwtt.accuracy),
        "f1": weighted_average_metric(results, lambda result: result.tuned_pwtt.f1),
        "precision": weighted_average_metric(results, lambda result: result.tuned_pwtt.precision),
        "recall": weighted_average_metric(results, lambda result: result.tuned_pwtt.recall),
    }

    print(f"\n{'=' * 88}")
    print("BENCHMARK SUMMARY")
    print(f"{'=' * 88}")
    print(f"Cities evaluated: {len(results)}")
    print(f"Total buildings: {total_buildings:,}")
    print(f"Damaged buildings: {total_damaged:,}")
    print(f"Overall damage rate: {total_damaged / total_buildings:.2%}")

    print("\nWeighted averages:")
    print(
        f"  Local PWTT @ {threshold:.2f}: "
        f"AUC={fixed_summary['auc']:.2%} "
        f"Acc={fixed_summary['accuracy']:.2%} "
        f"F1={fixed_summary['f1']:.2%} "
        f"Prec={fixed_summary['precision']:.2%} "
        f"Rec={fixed_summary['recall']:.2%}"
    )
    print(
        f"  max_change @ {threshold:.2f}: "
        f"AUC={max_summary['auc']:.2%} "
        f"Acc={max_summary['accuracy']:.2%} "
        f"F1={max_summary['f1']:.2%} "
        f"Prec={max_summary['precision']:.2%} "
        f"Rec={max_summary['recall']:.2%}"
    )
    print(
        f"  Local PWTT tuned per city: "
        f"AUC={tuned_summary['auc']:.2%} "
        f"Acc={tuned_summary['accuracy']:.2%} "
        f"F1={tuned_summary['f1']:.2%} "
        f"Prec={tuned_summary['precision']:.2%} "
        f"Rec={tuned_summary['recall']:.2%}"
    )

    print("\nPublished benchmark summary:")
    print(
        f"  Reference: "
        f"AUC={REFERENCE_SUMMARY['auc'] / 100:.2%} "
        f"Acc={REFERENCE_SUMMARY['accuracy'] / 100:.2%} "
        f"F1={REFERENCE_SUMMARY['f1'] / 100:.2%} "
        f"Prec={REFERENCE_SUMMARY['precision'] / 100:.2%} "
        f"Rec={REFERENCE_SUMMARY['recall'] / 100:.2%}"
    )


def print_reference_comparison(results: list[BenchmarkResult]) -> None:
    compared = [result for result in results if result.reference is not None]
    if not compared:
        print("\nNo city references available for comparison.")
        return

    print(f"\n{'=' * 88}")
    print("REFERENCE COMPARISON (LOCAL PWTT @ FIXED THRESHOLD)")
    print(f"{'=' * 88}")
    header = (
        f"{'City':<14} {'N':>8} {'Ref N':>8} {'AUC':>7} {'Ref':>7} "
        f"{'F1':>7} {'Ref':>7} {'Prec':>7} {'Ref':>7} {'Rec':>7} {'Ref':>7}"
    )
    print(header)
    print("-" * len(header))

    for result in compared:
        ref = result.reference
        print(
            f"{result.city:<14} "
            f"{result.total_buildings:>8,} {ref.n:>8,} "
            f"{result.fixed_pwtt.auc * 100:>6.2f} {ref.auc:>7.2f} "
            f"{result.fixed_pwtt.f1 * 100:>6.2f} {ref.f1:>7.2f} "
            f"{result.fixed_pwtt.precision * 100:>6.2f} {ref.precision:>7.2f} "
            f"{result.fixed_pwtt.recall * 100:>6.2f} {ref.recall:>7.2f}"
        )


def print_mismatch_report(results: list[BenchmarkResult]) -> None:
    compared = [result for result in results if result.reference is not None]
    if not compared:
        return

    n_mismatches = [result for result in compared if result.total_buildings != result.reference.n]
    if n_mismatches:
        print(f"\n{'=' * 88}")
        print("REFERENCE ROW-COUNT MISMATCHES")
        print(f"{'=' * 88}")
        for result in n_mismatches:
            print(
                f"  {result.city}: local N={result.total_buildings:,}, "
                f"reference N={result.reference.n:,}"
            )

    print(f"\n{'=' * 88}")
    print("LARGEST F1 GAPS VS PUBLISHED BENCHMARK")
    print(f"{'=' * 88}")
    ranked = sorted(
        compared,
        key=lambda result: abs((result.fixed_pwtt.f1 * 100) - result.reference.f1),
        reverse=True,
    )
    for result in ranked[:8]:
        gap = (result.fixed_pwtt.f1 * 100) - result.reference.f1
        print(
            f"  {result.city:<14} "
            f"local={result.fixed_pwtt.f1 * 100:>6.2f} "
            f"ref={result.reference.f1:>6.2f} "
            f"delta={gap:+6.2f}pp "
            f"(tuned={result.tuned_pwtt.f1 * 100:>6.2f}, max_change={result.fixed_max_change.f1 * 100:>6.2f})"
        )


def print_threshold_diagnostics(results: list[BenchmarkResult]) -> None:
    print(f"\n{'=' * 88}")
    print("THRESHOLD DIAGNOSTICS")
    print(f"{'=' * 88}")
    print(f"{'City':<14} {'Fixed@3 F1':>10} {'Tuned F1':>10} {'Tuned t':>9} {'Youden t':>9} {'Pos@3':>8}")
    print("-" * 70)
    for result in sorted(results, key=lambda item: item.city):
        youden_t = find_threshold_by_youden(
            np.array([0, 1]),  # placeholder overwritten below
            np.array([0.0, 1.0]),
        )
        del youden_t

        df_city = load_footprints(Path("/Users/samriddhagc/Downloads/one_month") / f"{result.city}_{result.event_date}_1_footprints.csv") if False else None
        print(
            f"{result.city:<14} "
            f"{result.fixed_pwtt.f1 * 100:>9.2f} "
            f"{result.tuned_pwtt.f1 * 100:>9.2f} "
            f"{result.tuned_pwtt.threshold:>8.3f} "
            f"{'n/a':>9} "
            f"{result.fixed_pwtt.positive_rate * 100:>7.2f}%"
        )


def build_json_report(results: list[BenchmarkResult], threshold: float) -> dict:
    return {
        "threshold": threshold,
        "reference_summary": REFERENCE_SUMMARY,
        "results": [
            {
                **asdict(result),
                "auc": result.auc,
                "accuracy": result.accuracy,
                "f1": result.f1,
                "precision": result.precision,
                "recall": result.recall,
                "optimal_threshold": result.optimal_threshold,
            }
            for result in results
        ],
    }


def main() -> None:
    args = parse_args()
    data_dir = args.data_dir
    threshold = args.threshold

    if not Path(data_dir).exists():
        print(f"Error: data directory not found: {data_dir}")
        return

    results = run_benchmark(data_dir, threshold, args.cities)
    print_summary(results, threshold)
    print_reference_comparison(results)
    print_mismatch_report(results)

    if args.json_out:
        output_path = Path(args.json_out)
        output_path.write_text(json.dumps(build_json_report(results, threshold), indent=2))
        print(f"\nWrote JSON report to {output_path}")

    print(f"\n{'=' * 88}")
    print("BENCHMARK COMPLETE")
    print(f"{'=' * 88}")


if __name__ == "__main__":
    main()
