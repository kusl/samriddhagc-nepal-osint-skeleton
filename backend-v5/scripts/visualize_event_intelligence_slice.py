#!/usr/bin/env python3
"""
Visualize event-intelligence clustering on a CSV slice of stories.

Expected columns:
- id
- title
- summary
- content
- category
- severity
- source_id
- published_at
- language
"""

import argparse
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.clustering.feature_extractor import get_feature_extractor
from app.services.clustering.similarity_engine import SimilarityEngine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Visualize event-intelligence clustering from CSV.")
    parser.add_argument("--input", required=True, help="Path to input CSV.")
    parser.add_argument("--output-prefix", required=True, help="Output prefix without extension.")
    return parser.parse_args()


def to_dt(value: str | None) -> datetime | None:
    if not value or value != value:
        return None
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime()


def union_find_cluster(edges, n):
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for a, b in edges:
        union(a, b)

    groups = defaultdict(list)
    for idx in range(n):
        groups[find(idx)].append(idx)
    return [members for members in groups.values() if len(members) >= 2]


def purity(rows, key):
    values = [row.get(key) for row in rows if row.get(key)]
    if not values:
        return None
    counts = Counter(values)
    return counts.most_common(1)[0][1] / len(values)


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_prefix = Path(args.output_prefix)
    output_prefix.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(input_path).fillna("")
    extractor = get_feature_extractor()
    engine = SimilarityEngine()

    rows = []
    points = []
    for _, row in df.iterrows():
        published_at = to_dt(row.get("published_at"))
        features = extractor.extract(
            title=row.get("title", ""),
            summary=row.get("summary", ""),
            content=row.get("content", ""),
            story_id=str(row.get("id", "")),
            published_at=published_at,
        )
        rows.append(
            {
                "id": row.get("id", ""),
                "title": row.get("title", ""),
                "summary": row.get("summary", ""),
                "content": row.get("content", ""),
                "category": row.get("category", "") or None,
                "severity": row.get("severity", "") or None,
                "source_id": row.get("source_id", "") or "",
                "language": row.get("language", "") or None,
                "published_at": published_at,
                "features": features,
                "province": features.primary_province or "unknown",
                "event_type": features.event_type or "unknown",
            }
        )
        signature = np.array(features.content_minhash[:32], dtype=float) if features.content_minhash else np.zeros(32)
        if signature.size:
            signature = np.log1p(signature)
        points.append(signature)

    if not rows:
        raise SystemExit("No rows loaded")

    points = np.vstack(points)
    pca = PCA(n_components=2)
    coords = pca.fit_transform(points)

    edges = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            a = rows[i]
            b = rows[j]
            if not a["published_at"] or not b["published_at"]:
                continue
            time_diff = abs((a["published_at"] - b["published_at"]).total_seconds()) / 3600.0
            if time_diff > 72:
                continue
            score = engine.compute_similarity_with_features(
                a["features"],
                b["features"],
                a["category"],
                b["category"],
                time_diff,
            )
            if (
                score.overall >= 0.55
                and score.title_similarity >= 0.25
                and (score.geo_similarity >= 0.25 or score.entity_overlap >= 0.14 or score.text_similarity >= 0.62)
            ):
                edges.append((i, j, score.overall))

    clusters = union_find_cluster([(a, b) for a, b, _ in edges], len(rows))
    cluster_id_map = {}
    for idx, members in enumerate(clusters, start=1):
        for member in members:
            cluster_id_map[member] = idx

    cluster_rows = [[rows[i] for i in members] for members in clusters]
    avg_category_purity = np.mean([purity(group, "category") for group in cluster_rows if purity(group, "category") is not None]) if cluster_rows else 0.0
    avg_province_purity = np.mean([purity(group, "province") for group in cluster_rows if purity(group, "province") is not None]) if cluster_rows else 0.0
    avg_event_purity = np.mean([purity(group, "event_type") for group in cluster_rows if purity(group, "event_type") is not None]) if cluster_rows else 0.0
    geo_known_share = sum(1 for row in rows if row["province"] != "unknown") / len(rows)
    event_known_share = sum(1 for row in rows if row["event_type"] != "unknown") / len(rows)
    clustered_share = len(cluster_id_map) / len(rows)

    fig, axes = plt.subplots(2, 3, figsize=(14, 9))
    province_colors = {}
    palette = plt.cm.get_cmap("tab10", 10)
    for idx, province in enumerate(sorted({row["province"] for row in rows})):
        province_colors[province] = palette(idx % 10)

    ax = axes[0, 0]
    for idx, row in enumerate(rows):
        ax.scatter(coords[idx, 0], coords[idx, 1], color=province_colors[row["province"]], s=18, alpha=0.85)
    ax.set_title("Recent Stories by Inferred Province")

    ax = axes[0, 1]
    ax.scatter(coords[:, 0], coords[:, 1], color="#cbd5e1", s=12, alpha=0.35)
    for a, b, _ in edges:
        ax.plot([coords[a, 0], coords[b, 0]], [coords[a, 1], coords[b, 1]], color="#94a3b8", alpha=0.2, linewidth=0.7)
    for idx, row in enumerate(rows):
        if idx in cluster_id_map:
            ax.scatter(coords[idx, 0], coords[idx, 1], color=palette(cluster_id_map[idx] % 10), s=28, alpha=0.95)
    ax.set_title("Event Clusters from Hybrid Scoring")

    ax = axes[0, 2]
    event_counts = Counter(row["event_type"] for row in rows)
    top_events = event_counts.most_common(8)
    ax.barh([item[0] for item in top_events], [item[1] for item in top_events], color="#60a5fa")
    ax.set_title("Detected Event Types")

    ax = axes[1, 0]
    cluster_sizes = [len(members) for members in clusters]
    if cluster_sizes:
        bins = np.arange(2, max(cluster_sizes) + 2) - 0.5
        ax.hist(cluster_sizes, bins=bins, color="#22c55e", edgecolor="#0f172a")
    ax.set_title("Cluster Size Distribution")

    ax = axes[1, 1]
    metrics = {
        "Category": avg_category_purity or 0.0,
        "Province": avg_province_purity or 0.0,
        "Event Type": avg_event_purity or 0.0,
        "Geo Known": geo_known_share,
        "Event Known": event_known_share,
        "Clustered": clustered_share,
    }
    ax.bar(list(metrics.keys()), list(metrics.values()), color=["#3b82f6", "#10b981", "#f59e0b", "#8b5cf6", "#ef4444", "#64748b"])
    ax.set_ylim(0, 1.05)
    ax.set_title("Operational Coherence Signals")
    ax.tick_params(axis="x", rotation=20)

    ax = axes[1, 2]
    ax.axis("off")
    ax.text(
        0.02,
        0.98,
        "\n".join(
            [
                f"Stories analyzed: {len(rows)}",
                f"Clusters found (>=2): {len(clusters)}",
                f"Stories in clusters: {len(cluster_id_map)}",
                f"Edges created: {len(edges)}",
                f"PCA variance (2D): {pca.explained_variance_ratio_.sum():.2%}",
                "",
                f"Avg category purity: {avg_category_purity:.2f}",
                f"Avg province purity: {avg_province_purity:.2f}",
                f"Avg event-type purity: {avg_event_purity:.2f}",
                f"Geo-known share: {geo_known_share:.2%}",
                f"Event-known share: {event_known_share:.2%}",
                "",
                "Read:",
                "operational signal is usable if province and event purity stay high",
            ]
        ),
        va="top",
        fontsize=11,
    )

    fig.suptitle("NepalOSINT Event-Intelligence Cluster Review", fontsize=18)
    fig.tight_layout()
    image_path = output_prefix.with_suffix(".png")
    fig.savefig(image_path, dpi=180, bbox_inches="tight")
    plt.close(fig)

    top_clusters = []
    for members in sorted(clusters, key=len, reverse=True)[:10]:
        group = [rows[i] for i in members]
        provinces = Counter(row["province"] for row in group if row["province"] != "unknown")
        event_types = Counter(row["event_type"] for row in group if row["event_type"] != "unknown")
        top_clusters.append(
            f"- size={len(group)} province={(provinces.most_common(1)[0][0] if provinces else 'unknown')} "
            f"event_type={(event_types.most_common(1)[0][0] if event_types else 'unknown')} lead=\"{group[0]['title'][:90]}\""
        )

    report_path = output_prefix.with_suffix(".md")
    report_path.write_text(
        "\n".join(
            [
                "# Event Cluster Review",
                "",
                f"- recent stories analyzed: {len(rows)}",
                f"- clusters found: {len(clusters)}",
                f"- stories in clusters: {len(cluster_id_map)}",
                f"- edges created: {len(edges)}",
                f"- average category purity: {avg_category_purity:.4f}",
                f"- average province purity: {avg_province_purity:.4f}",
                f"- average event-type purity: {avg_event_purity:.4f}",
                f"- geo-known share: {geo_known_share:.4f}",
                f"- event-known share: {event_known_share:.4f}",
                f"- clustered share: {clustered_share:.4f}",
                "",
                "## Top clusters",
                *top_clusters,
            ]
        ),
        encoding="utf-8",
    )

    print(image_path)
    print(report_path)


if __name__ == "__main__":
    main()
