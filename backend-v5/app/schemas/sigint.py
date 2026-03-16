from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SignalSourceItem(BaseModel):
    source_type: str
    id: str
    title: Optional[str] = None
    source_name: Optional[str] = None
    author: Optional[str] = None
    similarity: Optional[float] = None
    published_at: Optional[str] = None


class SignalResponse(BaseModel):
    signal_type: str
    title: str
    severity: str
    confidence: float
    summary: str
    sources: list[SignalSourceItem] = []
    tags: list[str] = []
    first_seen: Optional[str] = None
    source_count: int = 0


class SignalListResponse(BaseModel):
    signals: list[SignalResponse]
    period_hours: int
    generated_at: str
    total: int


class ConvergenceItem(BaseModel):
    cluster_id: str
    title: str
    sources: list[str] = []
    source_count: int = 0
    avg_similarity: float = 0.0
    max_similarity: float = 0.0
    first_seen: Optional[str] = None


class ConvergenceResponse(BaseModel):
    clusters: list[ConvergenceItem]
    period_hours: int
    generated_at: str
    total_pairs: int
    total_clusters: int


class NovelSignalItem(BaseModel):
    source_type: str
    id: str
    title: str
    source_name: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[str] = None
    max_similarity_to_past: float = 0.0


class NovelSignalResponse(BaseModel):
    signals: list[NovelSignalItem]
    period_hours: int
    lookback_hours: int
    generated_at: str
    total: int


class TopicIntensityItem(BaseModel):
    seed_query: str
    count: int
    intensity: str


class TopicCategoryHeatmap(BaseModel):
    category: str
    topics: list[TopicIntensityItem]
    max_intensity: str = "NONE"
    total_matches: int = 0


class TopicHeatmapResponse(BaseModel):
    categories: list[TopicCategoryHeatmap]
    period_hours: int
    generated_at: str


class BriefingSummary(BaseModel):
    economic_topline: Optional[str] = None
    security_topline: Optional[str] = None
    convergence_topline: Optional[str] = None
    novel_topline: Optional[str] = None
    overall_assessment: Optional[str] = None


class SIGINTBriefingResponse(BaseModel):
    generated_at: str
    period_hours: int
    economic_signals: list[SignalResponse]
    security_signals: list[SignalResponse]
    cross_source_convergence: list[ConvergenceItem]
    novel_signals: list[NovelSignalItem]
    topic_heatmap: list[TopicCategoryHeatmap]
    summary: BriefingSummary

