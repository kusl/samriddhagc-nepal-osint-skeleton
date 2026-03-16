# Backend Integration Plan - Nepal OSINT v5

> **Purpose**: This document serves as the single source of truth for integrating the frontend dashboard with the backend API. Follow this guide to ensure modular, maintainable code with no duplication.

---

## 1. Architecture Overview

### Current Stack
```
Frontend (React + Vite)          Backend (FastAPI)
├── src/                         ├── app/
│   ├── api/        ──────────►  │   ├── api/v1/     (36+ endpoints)
│   ├── stores/                  │   ├── services/   (71 services)
│   ├── components/Dashboard/    │   ├── models/     (42 models)
│   └── hooks/                   │   └── core/
└── Port: 5174                   └── Port: 8000
```

### Deployment Target: Cloudflare
- **Frontend**: Cloudflare Pages (static build)
- **Backend**: Cloudflare Tunnel → Docker container
- **Database**: PostgreSQL + Neo4j + Redis (self-hosted or managed)

---

## 2. Widget-to-API Mapping

Each dashboard widget maps to specific backend endpoints:

| Widget | API Endpoint | Data Model | Priority |
|--------|--------------|------------|----------|
| **map** | `/api/v1/map-events`, `/api/v1/geo/districts` | MapEvent, DistrictMetrics | P0 |
| **kpi** | `/api/v1/analytics/summary` | AnalyticsSummary | P0 |
| **stories** | `/api/v1/stories?limit=10` | Story[] | P0 |
| **weather** | External: OpenWeather API | WeatherData | P1 |
| **disasters** | `/api/v1/disaster-alerts/active` | DisasterAlert[] | P0 |
| **elections** | `/api/v1/elections/summary` | ElectionSummary | P1 |
| **market** | External: Nepal Rastra Bank API | MarketData | P2 |
| **entities** | `/api/v1/entities?is_key_actor=true` | Entity[] | P1 |
| **briefing** | `/api/v1/analytics/executive-summary` | ExecutiveSummary | P1 |
| **social** | `/api/v1/stories?source_type=social` | Story[] | P2 |
| **govt** | `/api/v1/stories?source_type=government` | Story[] | P2 |
| **threats** | `/api/v1/analytics/threat-matrix` | ThreatMatrix | P0 |
| **rivers** | `/api/v1/disaster-alerts?type=flood` | RiverLevel[] | P1 |
| **seismic** | `/api/v1/disaster-alerts?type=earthquake` | SeismicEvent[] | P1 |
| **infra** | `/api/v1/analytics/infrastructure` | InfraStatus | P2 |
| **contacts** | Static data (no API needed) | EmergencyContact[] | P3 |
| **news** | `/api/v1/stories?source_type=news` | Story[] | P1 |
| **aqi** | External: IQAir API or govt data | AQIData | P2 |
| **power** | External: NEA API (if available) | PowerStatus | P3 |
| **borders** | Static + manual updates | BorderStatus[] | P3 |
| **rumors** | `/api/v1/stories?is_rumor=true` | RumorCheck[] | P2 |

**Priority Legend**: P0 = Must have, P1 = Should have, P2 = Nice to have, P3 = Static/Manual

---

## 3. Code Architecture Principles

### 3.1 API Layer Structure
```
src/api/
├── client.ts           # Axios instance with interceptors (EXISTING)
├── types.ts            # Shared API response types (NEW)
├── hooks/              # React Query hooks (NEW)
│   ├── useStories.ts
│   ├── useAnalytics.ts
│   ├── useDisasters.ts
│   ├── useElections.ts
│   └── useEntities.ts
└── endpoints/          # Endpoint definitions (REFACTOR existing)
    ├── analytics.ts
    ├── stories.ts
    ├── disasters.ts
    └── ...
```

### 3.2 No Duplication Rules
1. **Single fetch function per endpoint** - Never duplicate API calls
2. **Shared types** - All API types in `src/types/api.ts`
3. **Centralized error handling** - In `client.ts` interceptors
4. **React Query for caching** - No manual caching logic in components
5. **Widget data hooks** - Each widget uses a dedicated hook

### 3.3 Widget Component Pattern
```typescript
// GOOD: Modular widget with hook
export function StoriesWidget() {
  const { data, isLoading, error } = useStories({ limit: 5 });

  if (isLoading) return <WidgetSkeleton />;
  if (error) return <WidgetError error={error} />;

  return (
    <Widget id="stories">
      {data.map(story => <StoryItem key={story.id} story={story} />)}
    </Widget>
  );
}

// BAD: Inline fetching, duplicated logic
export function StoriesWidget() {
  const [data, setData] = useState([]);
  useEffect(() => {
    fetch('/api/v1/stories')  // NO! Use the hook
      .then(r => r.json())
      .then(setData);
  }, []);
  // ...
}
```

---

## 4. Implementation Phases

### Phase 1: Core Infrastructure (Day 1) ✅ COMPLETE
- [x] Set up React Query provider (`src/lib/queryClient.ts`, `src/main.tsx`)
- [x] Create base API hooks pattern (`src/api/hooks/`)
- [x] Add loading/error states to Widget component (`src/components/Dashboard/widgets/shared.tsx`)
- [x] Connect KPI widget to `/analytics/summary` + `/analytics/threat-matrix`
- [x] Connect Stories widget to `/analytics/consolidated-stories`
- [x] Connect Threats widget to `/analytics/threat-matrix`
- [x] Connect Disasters widget to `/disaster-alerts/stats` + `/disaster-alerts/active`

### Phase 2: Critical Widgets (Day 1-2)
- [ ] Map widget with live events
- [ ] Disasters widget with BIPAD data
- [ ] Real-time WebSocket connection

### Phase 3: Secondary Widgets (Day 2-3)
- [ ] Elections widget
- [ ] Entities widget (key actors)
- [ ] Briefing widget (executive summary)
- [ ] News/Social/Govt feeds

### Phase 4: External APIs (Day 3-4)
- [ ] Weather widget (OpenWeather)
- [ ] Rivers/Seismic (BIPAD integration)
- [ ] AQI widget
- [ ] Market data

### Phase 5: Polish & Deploy (Day 4-5)
- [ ] Error boundaries on all widgets
- [ ] Skeleton loaders
- [ ] Production build optimization
- [ ] Cloudflare deployment

---

## 5. Cloudflare Deployment Setup

### Frontend (Cloudflare Pages)
```bash
# Build command
npm run build

# Output directory
dist

# Environment variables
VITE_API_URL=https://api.yourdomain.com
```

### Backend (Cloudflare Tunnel)
```yaml
# cloudflared config
tunnel: nepal-osint
credentials-file: /root/.cloudflared/credentials.json

ingress:
  - hostname: api.yourdomain.com
    service: http://localhost:8000
  - service: http_status:404
```

### Required Environment Variables
```env
# Frontend (.env.production)
VITE_API_URL=https://api.yourdomain.com
VITE_WS_URL=wss://api.yourdomain.com/ws

# Backend (.env)
CORS_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
NEO4J_URI=bolt://...
ANTHROPIC_API_KEY=sk-ant-...
```

---

## 6. File Naming Conventions

```
# Hooks: use{Resource}.ts
useStories.ts, useAnalytics.ts, useDisasters.ts

# Components: {Name}.tsx (PascalCase)
StoriesWidget.tsx, MapWidget.tsx, KPIWidget.tsx

# Types: {name}.types.ts or in api.ts
story.types.ts, analytics.types.ts

# API endpoints: {resource}.ts (camelCase)
stories.ts, analytics.ts, disasters.ts
```

---

## 7. Error Handling Strategy

```typescript
// Global error handler in client.ts
api.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.status === 401) {
      // Redirect to login
    }
    if (error.response?.status >= 500) {
      // Log to error service
    }
    return Promise.reject(error);
  }
);

// Widget-level error boundary
<ErrorBoundary fallback={<WidgetError />}>
  <StoriesWidget />
</ErrorBoundary>
```

---

## 8. Data Refresh Strategy

| Data Type | Refresh Method | Interval |
|-----------|----------------|----------|
| KPIs | React Query refetch | 30 seconds |
| Stories | React Query + WebSocket | 60 seconds + push |
| Threats | React Query | 5 minutes |
| Map Events | WebSocket | Real-time |
| Weather | React Query | 30 minutes |
| Elections | React Query | 5 minutes |

---

## 9. Type Safety Checklist

- [ ] All API responses have TypeScript interfaces
- [ ] No `any` types in widget components
- [ ] Zod validation for external API responses
- [ ] Strict null checks enabled

---

## 10. Testing Strategy

```
# Unit tests for hooks
src/api/hooks/__tests__/useStories.test.ts

# Integration tests for widgets
src/components/Dashboard/widgets/__tests__/StoriesWidget.test.tsx

# E2E tests for critical flows
cypress/e2e/dashboard.cy.ts
```

---

## Reminder Notes

**DO NOT:**
- Duplicate API fetch logic
- Add inline styles (use CSS classes)
- Create one-off utility functions
- Skip error handling
- Hardcode API URLs

**ALWAYS:**
- Use React Query hooks
- Follow the Widget component pattern
- Add TypeScript types
- Handle loading/error states
- Keep widgets under 100 lines

---

*Last Updated: 2026-01-27*
*Version: 1.0.0*
