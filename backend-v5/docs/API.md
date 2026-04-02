# Nepal OSINT v5 - API Reference

Complete API documentation for the Nepal OSINT v5 backend.

## Base URL

```
http://localhost:8001
```

## Authentication

Currently no authentication required (development mode).

---

## Stories Endpoints

### GET /api/v1/stories

Paginated list of stories with filtering.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | int | 1 | Page number |
| `page_size` | int | 20 | Items per page (max: 100) |
| `source_id` | string | - | Filter by source |
| `nepal_only` | bool | true | Only Nepal-relevant stories |
| `from_date` | datetime | - | Start date filter |
| `to_date` | datetime | - | End date filter |
| `category` | string | - | Filter by category |
| `severity` | string | - | Filter by severity |

**Response:**

```json
{
  "items": [
    {
      "id": "uuid",
      "source_id": "tkp",
      "source_name": "The Kathmandu Post",
      "title": "Story headline",
      "url": "https://...",
      "summary": "Story summary",
      "category": "political",
      "severity": "medium",
      "nepal_relevance": "NEPAL_DOMESTIC",
      "relevance_score": 0.85,
      "published_at": "2026-01-27T10:00:00Z",
      "created_at": "2026-01-27T10:05:00Z"
    }
  ],
  "total": 150,
  "page": 1,
  "page_size": 20,
  "pages": 8
}
```

### GET /api/v1/stories/{id}

Get single story by ID.

**Response:**

```json
{
  "id": "uuid",
  "source_id": "tkp",
  "source_name": "The Kathmandu Post",
  "title": "Story headline",
  "url": "https://...",
  "summary": "Story summary",
  "content": "Full article content...",
  "category": "political",
  "severity": "medium",
  "nepal_relevance": "NEPAL_DOMESTIC",
  "relevance_score": 0.85,
  "relevance_triggers": ["nepal", "kathmandu", "parliament"],
  "cluster_id": "uuid-or-null",
  "published_at": "2026-01-27T10:00:00Z",
  "created_at": "2026-01-27T10:05:00Z"
}
```

---

## Analytics Endpoints

### GET /api/v1/analytics/aggregated-news

Get clustered/aggregated news for StoriesWidget.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `hours` | int | 72 | Time window (1-168) |
| `category` | string | - | Filter: political, economic, security, disaster, social |
| `severity` | string | - | Filter: critical, high, medium, low |

**Response:**

```json
{
  "clusters": [
    {
      "id": "uuid",
      "headline": "Parliament passes new budget amid opposition boycott",
      "summary": "Multiple sources reporting...",
      "category": "political",
      "severity": "medium",
      "story_count": 5,
      "source_count": 4,
      "sources": ["Kathmandu Post", "Republica", "Online Khabar", "Himalayan Times"],
      "first_published": "2026-01-27T08:00:00Z",
      "last_updated": "2026-01-27T12:00:00Z",
      "stories": [
        {
          "id": "uuid",
          "source_id": "tkp",
          "source_name": "The Kathmandu Post",
          "title": "Budget passed in parliament",
          "summary": "The annual budget...",
          "url": "https://kathmandupost.com/...",
          "published_at": "2026-01-27T12:00:00Z"
        }
      ]
    }
  ],
  "unclustered_count": 12,
  "total_stories": 69
}
```

### GET /api/v1/analytics/consolidated-stories

Get individual stories (not clustered) for alternative view.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `hours` | int | 72 | Time window (1-168) |
| `limit` | int | 100 | Max stories (1-500) |
| `story_type` | string | - | Filter by category |
| `severity` | string | - | Filter by severity |
| `category` | string | - | Alias for story_type |

**Response:**

```json
[
  {
    "id": "uuid",
    "source_id": "tkp",
    "source_name": "The Kathmandu Post",
    "canonical_headline": "Story title",
    "canonical_headline_ne": null,
    "summary": "Summary text",
    "summary_ne": null,
    "url": "https://...",
    "story_type": "political",
    "severity": "medium",
    "nepal_relevance": "NEPAL_DOMESTIC",
    "source_count": 1,
    "first_reported_at": "2026-01-27T10:00:00Z",
    "last_updated_at": "2026-01-27T10:05:00Z",
    "districts_affected": [],
    "is_verified": false,
    "confidence_score": 0.85,
    "cluster_id": null
  }
]
```

### GET /api/v1/analytics/summary

Get KPI metrics for dashboard header.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `hours` | int | 72 | Time window (1-720) |

**Response:**

```json
{
  "stories": 69,
  "events": 0,
  "entities": 0,
  "active_alerts": 0,
  "sources_breakdown": {
    "tkp": 15,
    "republica": 12,
    "onlinekhabar_en": 10,
    "himalayan": 8
  },
  "hourly_trend": [
    { "hour": "2026-01-27T00:00:00Z", "count": 5 },
    { "hour": "2026-01-27T01:00:00Z", "count": 3 }
  ],
  "time_range_hours": 72
}
```

### GET /api/v1/analytics/threat-matrix

Get threat levels by category for ThreatsWidget.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `hours` | int | 24 | Time window (1-168) |

**Response:**

```json
{
  "matrix": [
    {
      "category": "political",
      "level": "elevated",
      "trend": "stable",
      "event_count": 15,
      "top_event": "Parliament session adjourned amid protests",
      "severity_breakdown": {
        "critical": 0,
        "high": 3,
        "medium": 7,
        "low": 5
      }
    },
    {
      "category": "disaster",
      "level": "guarded",
      "trend": "stable",
      "event_count": 4,
      "top_event": "Minor earthquake recorded in Gorkha",
      "severity_breakdown": {
        "critical": 0,
        "high": 1,
        "medium": 2,
        "low": 1
      }
    }
  ],
  "overall_threat_level": "ELEVATED",
  "last_updated": "2026-01-27T12:00:00Z"
}
```

**Threat Level Calculation:**

```
score = critical*4 + high*3 + medium*2 + low*1

score > 20  → critical
score > 10  → elevated
score > 5   → guarded
else        → low
```

---

## Ingestion Endpoints

### POST /api/v1/ingest/trigger

Manually trigger RSS ingestion.

**Response:**

```json
{
  "status": "started",
  "message": "Ingestion triggered"
}
```

### GET /api/v1/ingest/status

Get ingestion status.

**Response:**

```json
{
  "last_run": "2026-01-27T11:45:00Z",
  "next_run": "2026-01-27T12:00:00Z",
  "stories_ingested_last_run": 5,
  "active_sources": 28
}
```

---

## WebSocket Endpoints

### WS /ws/news

Real-time news feed WebSocket.

**Connection:**

```javascript
const ws = new WebSocket('ws://localhost:8001/ws/news');

ws.onopen = () => {
  console.log('Connected');
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);

  switch (message.type) {
    case 'initial_stories':
      // Array of recent stories (last 1 hour)
      console.log('Initial stories:', message.data);
      break;

    case 'new_story':
      // Single new story just ingested
      console.log('New story:', message.data);
      break;

    case 'heartbeat':
      // Keep-alive (every 30s)
      console.log('Heartbeat:', message.timestamp);
      break;
  }
};

// Send ping to keep connection alive
ws.send('ping');
// Receives: {"type":"pong"}
```

**Message Format - initial_stories:**

```json
{
  "type": "initial_stories",
  "timestamp": "2026-01-27T12:00:00Z",
  "data": [
    {
      "id": "uuid",
      "title": "Story title",
      "url": "https://...",
      "summary": "Summary",
      "source_id": "tkp",
      "source_name": "The Kathmandu Post",
      "category": "political",
      "severity": "medium",
      "published_at": "2026-01-27T11:30:00Z",
      "created_at": "2026-01-27T11:35:00Z"
    }
  ]
}
```

**Message Format - new_story:**

```json
{
  "type": "new_story",
  "timestamp": "2026-01-27T12:05:00Z",
  "data": {
    "id": "uuid",
    "title": "Breaking: New development in...",
    "url": "https://...",
    "summary": "Summary",
    "source_id": "onlinekhabar_en",
    "source_name": "Online Khabar",
    "category": "security",
    "severity": "high",
    "published_at": "2026-01-27T12:04:00Z",
    "created_at": "2026-01-27T12:05:00Z"
  }
}
```

### GET /ws/status

Get WebSocket connection statistics.

**Response:**

```json
{
  "active_connections": 3,
  "status": "healthy"
}
```

---

## Health Endpoints

### GET /

Root endpoint with service info.

**Response:**

```json
{
  "name": "Nepal OSINT v5",
  "version": "5.0.0",
  "status": "operational"
}
```

### GET /health

Health check.

**Response:**

```json
{
  "status": "healthy"
}
```

---

## Error Responses

All endpoints return consistent error format:

```json
{
  "detail": "Error message here"
}
```

**HTTP Status Codes:**

| Code | Description |
|------|-------------|
| 200 | Success |
| 400 | Bad Request (invalid parameters) |
| 404 | Not Found |
| 422 | Validation Error |
| 500 | Internal Server Error |

---

## Rate Limits

Currently no rate limits in development mode.

---

## CORS

Allowed origins:
- `http://localhost:5173`
- `http://localhost:5174`
- `http://127.0.0.1:5173`
- `http://127.0.0.1:5174`

All methods and headers allowed.
