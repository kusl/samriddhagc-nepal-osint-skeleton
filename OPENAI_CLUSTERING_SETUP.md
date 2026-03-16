# OpenAI Clustering And Story Products

This setup adds:

- OpenAI multilingual embeddings for Nepali/English event matching
- `gpt-5-mini` only for gray-zone event decisions
- separate event-level `Developing Stories`
- separate narrative-level `Story Tracker`

The implementation is designed to stay cheap:

- embeddings do most of the cross-lingual work
- `gpt-5-mini` is only used on ambiguous pairs
- `Developing Stories` stores/reuses cluster BLUFs
- `Story Tracker` persists slower-moving narratives in DB

## Environment Variables

Add these to your local `.env` when you are ready:

```env
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1

EMBEDDING_MODEL_KEY=openai-3-large
OPENAI_EMBEDDING_ENABLED=true
OPENAI_EMBEDDING_MODEL=text-embedding-3-large
OPENAI_EMBEDDING_DIMENSIONS=1024

OPENAI_CLUSTERING_ENABLED=true
OPENAI_CLUSTERING_MODEL=gpt-5-mini
OPENAI_CLUSTER_GRAY_ZONE_LOW=0.68
OPENAI_CLUSTER_GRAY_ZONE_HIGH=0.82

OPENAI_DEVELOPING_STORIES_ENABLED=true
OPENAI_STORY_TRACKER_ENABLED=true

OPENAI_CACHE_TTL_SECONDS=2592000
OPENAI_STORY_TRACKER_SIMILARITY_THRESHOLD=0.78
```

## Migration

Run:

```bash
cd backend-v5
alembic upgrade head
```

This creates:

- `story_narratives`
- `story_narrative_clusters`

## What Uses OpenAI

### Uses embeddings

- story-to-story semantic clustering
- Nepali-English cross-lingual candidate matching
- cluster-to-cluster similarity for narrative grouping

### Uses `gpt-5-mini`

- only ambiguous event pair validation in the clustering gray zone
- missing `Developing Stories` BLUF generation
- story-tracker narrative label/thesis generation
- ambiguous cluster-to-narrative grouping

### Does not use `gpt-5-mini`

- all pairwise comparisons
- every cluster on every run
- every frontend request

## API Endpoints

Existing:

- `GET /api/v1/analytics/cluster-timeline`
  - legacy shared cluster feed

New:

- `GET /api/v1/analytics/developing-stories`
  - event-level, fast-moving
- `GET /api/v1/analytics/story-tracker`
  - narrative-level, slower-moving
- `GET /api/v1/analytics/story-tracker?refresh=true`
  - force rebuild of persisted narratives

## Frontend Hooks

New hooks:

- `useDevelopingStories()`
- `useStoryTracker()`

The tracker widget now reads the narrative endpoint instead of the old cluster timeline.

## Cost Controls

To keep this under a tight monthly budget:

1. Keep `EMBEDDING_MODEL_KEY=openai-3-large` so clustering uses embeddings as the primary semantic layer.
2. Do not widen the gray zone unless you need more recall.
3. Keep `OPENAI_STORY_TRACKER_ENABLED=true` but refresh narratives on a slower cadence than clusters.
4. Avoid forcing `refresh=true` on every UI load.
5. Use embeddings once per story and reuse stored vectors.

## Rollback

To revert to the old local embedding stack and disable OpenAI:

```env
EMBEDDING_MODEL_KEY=e5-large
OPENAI_EMBEDDING_ENABLED=false
OPENAI_CLUSTERING_ENABLED=false
OPENAI_DEVELOPING_STORIES_ENABLED=false
OPENAI_STORY_TRACKER_ENABLED=false
```

The system will continue to run using the prior hybrid/local path.
