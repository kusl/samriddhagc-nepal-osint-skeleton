import { memo, useMemo, useState } from 'react';
import { ArrowUpRight, Newspaper } from 'lucide-react';
import { Widget } from '../Widget';
import { useStories } from '../../../api/hooks';
import { WidgetEmpty, WidgetError, WidgetSkeleton, formatTimeAgo } from './shared';

const TIME_WINDOWS = [
  { label: '24H', hours: 24 },
  { label: '72H', hours: 72 },
  { label: '7D', hours: 168 },
] as const;

export const EconomicNewsWidget = memo(function EconomicNewsWidget() {
  const [hours, setHours] = useState<24 | 72 | 168>(72);
  const limit = hours === 168 ? 500 : hours === 72 ? 180 : 120;
  const { data, isLoading, isError, refetch } = useStories({
    hours,
    limit,
    storyType: 'economic',
  });

  const stories = useMemo(() => {
    const items = data || [];
    const seen = new Set<string>();
    return items.filter((story) => {
      const rawHeadline = (story.canonical_headline || story.canonical_headline_ne || '').toLowerCase();
      const normalizedHeadline = rawHeadline
        .replace(/गङ्ग/g, 'गंग')
        .replace(/[^\w\u0900-\u097F\s]/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
      const key = `${story.cluster_id || 'solo'}::${normalizedHeadline}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [data]);
  const uniqueSources = new Set(stories.map((story) => story.source_name).filter(Boolean)).size;
  const uniqueDistricts = new Set(
    stories.flatMap((story) => story.districts_affected || []).filter(Boolean),
  ).size;
  const leadStory = stories[0];
  const leadLocation = leadStory?.display_location || leadStory?.districts_affected?.[0] || leadStory?.provinces_affected?.[0];
  const showInitialLoading = isLoading && typeof data === 'undefined';
  const metricCards = [
    {
      label: 'Story Volume',
      value: `${stories.length}`,
      meta: `Across the last ${hours === 168 ? '7 days' : hours === 72 ? '72 hours' : '24 hours'}`,
      accent: '#f59e0b',
    },
    {
      label: 'Source Spread',
      value: `${uniqueSources}`,
      meta: uniqueSources === 1 ? '1 outlet currently represented' : `${uniqueSources} outlets represented`,
      accent: '#38bdf8',
    },
    {
      label: 'Geographic Spread',
      value: `${uniqueDistricts}`,
      meta: leadLocation ? `Latest lead: ${leadLocation}` : 'No verified district tag on the latest lead',
      accent: '#34d399',
    },
  ];

  return (
    <Widget
      id="economic-news"
      icon={<Newspaper size={14} />}
      badge={stories.length ? `${stories.length} STORIES` : 'LIVE'}
    >
      <div
        style={{
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          background: 'var(--bg-surface)',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            padding: '10px 12px 0',
            borderBottom: '1px solid var(--border-subtle)',
            background: 'var(--bg-surface)',
          }}
        >
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: 1,
              background: 'rgba(255,255,255,0.06)',
              border: '1px solid var(--border-subtle)',
            }}
          >
            {metricCards.map((card) => (
              <div key={card.label} style={{ padding: '10px 12px', minHeight: 74, background: 'rgba(13,16,22,0.75)' }}>
                <div style={{ marginBottom: 8 }}>
                  <span style={{ fontSize: 8, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                    {card.label}
                  </span>
                </div>
                {showInitialLoading ? (
                  <>
                    <div
                      style={{
                        height: 18,
                        width: 44,
                        borderRadius: 6,
                        marginBottom: 8,
                        background: 'linear-gradient(90deg, rgba(255,255,255,0.06), rgba(255,255,255,0.12), rgba(255,255,255,0.06))',
                        backgroundSize: '200% 100%',
                        animation: 'widget-shimmer 1.8s ease-in-out infinite',
                      }}
                    />
                    <div
                      style={{
                        height: 10,
                        width: '78%',
                        borderRadius: 6,
                        background: 'linear-gradient(90deg, rgba(255,255,255,0.05), rgba(255,255,255,0.09), rgba(255,255,255,0.05))',
                        backgroundSize: '200% 100%',
                        animation: 'widget-shimmer 1.8s ease-in-out infinite',
                      }}
                    />
                  </>
                ) : (
                  <>
                    <div style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 16,
                      lineHeight: 1.15,
                      color: card.accent,
                      marginBottom: 5,
                    }}>
                      {card.value}
                    </div>
                    <div style={{ fontSize: 9, color: 'var(--text-disabled)', lineHeight: 1.35 }}>
                      {card.meta}
                    </div>
                  </>
                )}
              </div>
            ))}
            <div style={{ padding: '10px 12px', minHeight: 74, background: 'rgba(13,16,22,0.75)', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', gap: 10 }}>
              <div>
                <div style={{ marginBottom: 8 }}>
                  <span style={{ fontSize: 8, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                    Time Window
                  </span>
                </div>
                <div style={{ fontSize: 9, color: 'var(--text-disabled)', lineHeight: 1.35 }}>
                  Narrow or widen the feed without leaving the summary strip.
                </div>
              </div>
              <div
                style={{
                  display: 'inline-flex',
                  alignSelf: 'flex-start',
                  gap: '3px',
                  background: 'rgba(255,255,255,0.04)',
                  borderRadius: '999px',
                  padding: '3px',
                  border: '1px solid var(--border-subtle)',
                }}
              >
                {TIME_WINDOWS.map((option) => {
                  const active = option.hours === hours;
                  return (
                    <button
                      key={option.hours}
                      onClick={() => setHours(option.hours)}
                      style={{
                        padding: '5px 10px',
                        fontSize: '9px',
                        fontWeight: 600,
                        border: 'none',
                        borderRadius: '999px',
                        cursor: 'pointer',
                        transition: 'all 0.15s ease',
                        background: active ? 'rgba(59,130,246,0.18)' : 'transparent',
                        color: active ? '#93c5fd' : 'var(--text-muted)',
                        fontFamily: 'var(--font-mono)',
                        letterSpacing: '0.06em',
                      }}
                    >
                      {option.label}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        </div>

        {showInitialLoading ? (
          <WidgetSkeleton />
        ) : isError ? (
          <WidgetError message="Failed to load economic news" onRetry={() => refetch()} />
        ) : stories.length === 0 ? (
          <WidgetEmpty message="No economic stories found right now" />
        ) : (
          <div style={{ flex: 1, overflowY: 'auto', padding: '10px 12px 12px' }}>
            {stories.map((story) => {
              const location = story.display_location || story.districts_affected?.[0] || story.provinces_affected?.[0];
              const headline = story.canonical_headline || story.canonical_headline_ne || 'Untitled story';
              const localHeadline = story.canonical_headline_ne && story.canonical_headline_ne !== headline
                ? story.canonical_headline_ne
                : null;
              const synopsis = story.summary || story.summary_ne;
              const sourceCount = story.source_count || 0;

              return (
                <div
                  key={story.id}
                  style={{
                    padding: '9px 12px',
                    marginBottom: 6,
                    border: '1px solid var(--border-subtle)',
                    background: 'var(--bg-surface)',
                    display: 'flex',
                    gap: 10,
                    alignItems: 'flex-start',
                  }}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginBottom: 5 }}>
                      {story.is_verified ? (
                        <span style={{
                          fontSize: 8,
                          fontWeight: 700,
                          color: '#86efac',
                          background: 'rgba(34,197,94,0.12)',
                          border: '1px solid rgba(34,197,94,0.28)',
                          padding: '2px 6px',
                          borderRadius: 999,
                          textTransform: 'uppercase',
                          letterSpacing: '0.06em',
                        }}>
                          Verified
                        </span>
                      ) : null}
                      {sourceCount > 1 ? (
                        <span style={{
                          fontSize: 8,
                          color: 'var(--accent-primary)',
                          background: 'rgba(59,130,246,0.12)',
                          border: '1px solid rgba(59,130,246,0.24)',
                          padding: '2px 6px',
                          borderRadius: 999,
                          letterSpacing: '0.04em',
                        }}>
                          {sourceCount} sources
                        </span>
                      ) : null}
                    </div>
                    <div
                      style={{
                        fontSize: 10,
                        fontWeight: 600,
                        lineHeight: 1.35,
                        color: 'var(--text-primary)',
                        marginBottom: localHeadline || synopsis ? 4 : 6,
                      }}
                    >
                      {headline}
                    </div>
                    {localHeadline ? (
                      <div style={{ fontSize: 8, color: 'var(--text-muted)', lineHeight: 1.35, marginBottom: synopsis ? 4 : 6 }}>
                        {localHeadline}
                      </div>
                    ) : null}
                    {synopsis ? (
                      <div
                        style={{
                          fontSize: 9,
                          color: 'var(--text-secondary)',
                          lineHeight: 1.35,
                          marginBottom: 6,
                          display: '-webkit-box',
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: 'vertical',
                          overflow: 'hidden',
                        }}
                      >
                        {synopsis}
                      </div>
                    ) : null}
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                        flexWrap: 'wrap',
                        fontSize: 8,
                        color: 'var(--text-muted)',
                      }}
                    >
                      <span style={{ fontFamily: 'var(--font-mono)' }}>{story.source_name || 'Source'}</span>
                      {location ? (
                        <span style={{
                          padding: '2px 6px',
                          borderRadius: 999,
                          background: 'rgba(255,255,255,0.04)',
                          border: '1px solid var(--border-subtle)',
                          color: 'var(--text-secondary)',
                        }}>
                          {location}
                        </span>
                      ) : null}
                      <span>{formatTimeAgo(story.last_updated_at || story.first_reported_at)}</span>
                    </div>
                  </div>
                  <a
                    href={story.url}
                    target="_blank"
                    rel="noreferrer"
                    style={{
                      color: 'var(--text-secondary)',
                      padding: '6px',
                      border: '1px solid var(--border-subtle)',
                      background: 'rgba(255,255,255,0.03)',
                      flexShrink: 0,
                      borderRadius: 6,
                      display: 'inline-flex',
                    }}
                    title="Open source"
                  >
                    <ArrowUpRight size={12} />
                  </a>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </Widget>
  );
});
