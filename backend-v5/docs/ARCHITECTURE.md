# Nepal OSINT v5 - Architecture Documentation

## Data Flow

### 1. RSS Ingestion Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         RSS INGESTION FLOW                               │
└─────────────────────────────────────────────────────────────────────────┘

sources.yaml (28 feeds)
        │
        ▼
┌─────────────────────┐
│   APScheduler       │  Every 5 min (priority 1) / 15 min (priority 2)
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│   rss_fetcher.py    │  Async fetch with aiohttp + feedparser
│   - Semaphore: 10   │  Max concurrent requests
│   - Timeout: 30s    │
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│   deduplicator.py   │  SHA-256 hash of normalized URL
│   - Remove tracking │  utm_*, fbclid, etc.
│   - Lowercase host  │
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│ relevance_service   │  Nepal classification
│ - NEPAL_DOMESTIC    │  From Nepal source OR contains Nepal markers
│ - NEPAL_NEIGHBOR    │  India/China with Nepal connection
│ - INTERNATIONAL     │  Not relevant (filtered out)
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│ severity_service    │  Severity grading
│ - critical          │  death, bomb, earthquake
│ - high              │  injured, arrest, flood
│ - medium            │  domestic + high relevance
│ - low               │  everything else
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│   PostgreSQL        │  stories table
│   - Insert new      │
│   - Skip duplicates │  (ON CONFLICT external_id)
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│ WebSocket Broadcast │  If Nepal-relevant
│   news_manager      │  {"type": "new_story", ...}
└─────────────────────┘
```

### 2. Story Clustering Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        CLUSTERING FLOW                                   │
└─────────────────────────────────────────────────────────────────────────┘

APScheduler (every 30 min)
        │
        ▼
┌─────────────────────┐
│  Get stories        │  Last 72 hours, Nepal-only
│  from PostgreSQL    │  Unclustered + existing clusters
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│  Blocking Rules     │  blocking.py
│  - Same category?   │  Different category → never cluster
│  - Time proximity?  │  > 48h apart → never cluster
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│ Similarity Scoring  │  similarity_engine.py
│ - Title similarity  │  difflib.SequenceMatcher (0.0-1.0)
│ - Entity overlap    │  Jaccard similarity of keywords
│ - Category bonus    │  +0.2 if same category
│ - Time bonus        │  Closer = higher score
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│ Build Similarity    │  Only pairs with score >= 0.6
│ Graph               │  Edges: (story_a, story_b, score)
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│   Union-Find        │  clustering_service.py
│   - find(x)         │  Path compression
│   - union(x, y)     │  Union by rank
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│ Create/Update       │  story_clusters table
│ Clusters            │  - headline: most recent story
│                     │  - category: most common
│                     │  - severity: highest
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│ Update stories      │  Set cluster_id FK
│ cluster_id          │
└─────────────────────┘
```

### 3. API Request Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        API REQUEST FLOW                                  │
└─────────────────────────────────────────────────────────────────────────┘

Frontend Request
        │
        ▼
┌─────────────────────┐
│   FastAPI Router    │  /api/v1/*
│   - CORS validation │
│   - Path routing    │
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│   Pydantic Schema   │  Query parameter validation
│   - Type checking   │
│   - Default values  │
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│   Repository Layer  │  StoryRepository, StoryClusterRepository
│   - SQL queries     │  SQLAlchemy async
│   - Eager loading   │  selectinload for relationships
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│  Response Schema    │  Pydantic models
│  - from_attributes  │  ORM model → dict conversion
│  - Field aliasing   │  Internal → external naming
└─────────────────────┘
        │
        ▼
JSON Response
```

## Design Decisions

### Why No ML/LLM for Classification?

1. **Speed**: Rules-based classification is instant vs. API calls
2. **Cost**: No inference costs, runs entirely locally
3. **Predictability**: Deterministic results, easy to debug
4. **Simplicity**: No model versioning, no GPU requirements

**Trade-off**: Less nuanced classification, may miss edge cases. Acceptable for v5 MVP.

### Why Union-Find for Clustering?

1. **O(α(n)) amortized**: Near-constant time per operation
2. **No external deps**: Pure Python, no scikit-learn/numpy
3. **Incremental**: Can add new stories without full re-cluster
4. **Simple**: ~50 lines of code vs. complex ML pipelines

**Trade-off**: Less sophisticated than hierarchical or density-based clustering.

### Why WebSocket over Polling?

1. **Real-time**: Stories appear instantly on ingest
2. **Efficiency**: No wasted requests when no new stories
3. **Scalability**: Connection manager handles multiple clients
4. **Modern UX**: Live feed experience

### Why Separate Ports (8001 vs 8000)?

- **v5 on 8001**: Allows running alongside legacy v3 during migration
- **PostgreSQL 5433**: Avoids conflict with any existing PostgreSQL
- **Redis 6380**: Avoids conflict with existing Redis instances

## Component Responsibilities

### Services Layer

| Service | Responsibility |
|---------|---------------|
| `RelevanceService` | Nepal classification + 5-category assignment |
| `SeverityService` | 4-level severity grading based on keywords |
| `IngestionService` | RSS fetching, dedup, classification, DB insert, WS broadcast |
| `ClusteringService` | Union-Find clustering, cluster creation/update |

### Repository Layer

| Repository | Responsibility |
|------------|---------------|
| `StoryRepository` | Story CRUD, filtering, pagination, aggregations |
| `StoryClusterRepository` | Cluster CRUD, cluster listing with stories |

### API Layer

| Router | Responsibility |
|--------|---------------|
| `stories.py` | Individual story endpoints |
| `analytics.py` | Dashboard widget data (aggregated, summary, threat-matrix) |
| `ingest.py` | Manual ingestion control |
| `websocket.py` | Real-time news feed |

## Database Indexes

```sql
-- Deduplication (unique constraint)
CREATE UNIQUE INDEX idx_stories_external_id ON stories(external_id);

-- Common query patterns
CREATE INDEX idx_stories_source_published ON stories(source_id, published_at);
CREATE INDEX idx_stories_relevance_published ON stories(nepal_relevance, published_at);
CREATE INDEX idx_stories_category_published ON stories(category, published_at);
CREATE INDEX idx_stories_severity_published ON stories(severity, published_at);
CREATE INDEX idx_stories_cluster_id ON stories(cluster_id);
CREATE INDEX idx_stories_created ON stories(created_at);

-- Cluster queries
CREATE INDEX idx_clusters_category_severity ON story_clusters(category, severity);
CREATE INDEX idx_clusters_created ON story_clusters(created_at);
```

## Error Handling Strategy

1. **RSS Fetch Errors**: Log and skip, don't fail entire batch
2. **Classification Errors**: Default to INTERNATIONAL/low severity
3. **Clustering Errors**: Skip story, continue with others
4. **WebSocket Errors**: Disconnect client, log error
5. **Database Errors**: Raise to API layer, return 500

## Scaling Considerations

### Current Limits (Single Server)

- ~1000 stories/hour ingestion capacity
- ~100 concurrent WebSocket connections
- ~72 hours clustering window

### Future Scaling Options

1. **Redis Pub/Sub**: Multiple backend instances
2. **Celery Workers**: Distributed ingestion
3. **Read Replicas**: Scale read traffic
4. **CDN**: Cache analytics responses

## Configuration Files

### sources.yaml Structure

```yaml
sources:
  - id: string        # Unique identifier
    name: string      # Display name
    url: string       # RSS feed URL
    language: en|ne   # Content language
    priority: 1|2|3   # Polling frequency tier
    enabled: bool     # Active/inactive toggle
```

### relevance_rules.yaml Structure

```yaml
# Sources that are automatically NEPAL_DOMESTIC
nepal_sources:
  - tkp
  - himalayan

# Keywords that trigger Nepal relevance
nepal_markers:
  # Country
  - nepal
  - nepali
  # Cities
  - kathmandu
  - pokhara
  # Politicians
  - oli
  - prachanda
  # Parties
  - congress
  - uml

# Patterns that exclude stories (unless Nepal marker present)
exclusion_patterns:
  - bollywood
  - ipl.*cricket

# Keywords for NEPAL_NEIGHBOR classification
neighbor_keywords:
  - india.*nepal
  - china.*nepal
  - border.*dispute
```

## Frontend Integration Points

| Widget | API Endpoint | Refresh |
|--------|-------------|---------|
| StoriesWidget | GET /analytics/aggregated-news | 5 min (React Query) |
| NewsFeedWidget | WS /ws/news | Real-time |
| KPIWidget | GET /analytics/summary | 5 min |
| ThreatsWidget | GET /analytics/threat-matrix | 5 min |

## Monitoring Points

| Metric | Source | Alert Threshold |
|--------|--------|-----------------|
| Stories/hour | PostgreSQL count | < 5 (sources down?) |
| WebSocket connections | news_manager.connection_count | > 1000 |
| Clustering time | Scheduler logs | > 5 min |
| API latency | FastAPI middleware | > 2s |
