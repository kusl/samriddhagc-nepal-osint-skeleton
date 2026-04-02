import { memo } from 'react';
import { Landmark, RefreshCw } from 'lucide-react';
import { Widget } from '../Widget';
import { useProcurementWidgetSummary } from '../../../api/hooks';
import { WidgetEmpty, WidgetError, WidgetSkeleton } from './shared';

function formatCompactNpr(value: number | null | undefined): string {
  if (!value) return 'Nrs 0';
  const abs = Math.abs(value);
  if (abs >= 1_000_000_000_000) return `Nrs ${(value / 1_000_000_000_000).toFixed(2).replace(/\.00$/, '')}T`;
  if (abs >= 1_000_000_000) return `Nrs ${(value / 1_000_000_000).toFixed(2).replace(/\.00$/, '')}B`;
  if (abs >= 1_000_000) return `Nrs ${(value / 1_000_000).toFixed(2).replace(/\.00$/, '')}M`;
  if (abs >= 1_000) return `Nrs ${(value / 1_000).toFixed(1).replace(/\.0$/, '')}K`;
  return `Nrs ${Math.round(value).toLocaleString('en-US')}`;
}

export const PublicSpendingWidget = memo(function PublicSpendingWidget() {
  const summaryQuery = useProcurementWidgetSummary({ per_page: 10 });

  const summary = summaryQuery.data;
  const stats = summary?.stats;
  const topEntities = summary?.top_entities || [];
  const topBucket = (stats?.by_entity_bucket || []).slice().sort((a, b) => (b.total_value || 0) - (a.total_value || 0))[0];

  return (
    <Widget
      id="public-spending"
      icon={<Landmark size={14} />}
      badge={stats?.total_contracts ? `${stats.total_contracts} AWARDS` : 'LIVE'}
      actions={
        <button
          className="widget-action"
          title="Refresh public spending"
          onClick={() => {
            summaryQuery.refetch();
          }}
        >
          <RefreshCw size={12} />
        </button>
      }
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
        {summaryQuery.isLoading ? (
          <WidgetSkeleton />
        ) : summaryQuery.isError ? (
          <WidgetError
            message="Failed to load public spending"
            onRetry={() => {
              summaryQuery.refetch();
            }}
          />
        ) : !stats ? (
          <WidgetEmpty message="No public spending data available" />
        ) : (
          <>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
                gap: 1,
                background: 'var(--border-subtle)',
                borderBottom: '1px solid var(--border-subtle)',
              }}
            >
              {[
                { label: 'Tracked Value', value: formatCompactNpr(stats.total_value_npr), meta: 'Procurement awards' },
                { label: 'Awards', value: `${stats.total_contracts}`, meta: 'Bolpatra contracts' },
                { label: 'Lead Bucket', value: topBucket?.label || 'None', meta: topBucket ? formatCompactNpr(topBucket.total_value) : 'No bucket', compact: true },
              ].map((card) => (
                <div key={card.label} style={{ background: 'var(--bg-surface)', padding: '10px 11px', minHeight: 80 }}>
                  <div style={{ fontSize: 9, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 7 }}>
                    {card.label}
                  </div>
                  <div
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: card.compact ? 13 : 18,
                      lineHeight: 1.18,
                      color: 'var(--text-primary)',
                      marginBottom: 6,
                      wordBreak: 'break-word',
                    }}
                  >
                    {card.value}
                  </div>
                  <div style={{ fontSize: 9, color: 'var(--text-disabled)', lineHeight: 1.3 }}>{card.meta}</div>
                </div>
              ))}
            </div>

            <div style={{ flex: 1, overflowY: 'auto' }}>
              {topEntities.length === 0 ? (
                <WidgetEmpty message="No spending entities ranked yet" />
              ) : (
                topEntities.map((entity, index) => (
                  <div
                    key={`${entity.procuring_entity}-${index}`}
                    style={{
                      padding: '11px 13px',
                      borderBottom: '1px solid var(--border-subtle)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 12,
                    }}
                  >
                    <div
                      style={{
                        width: 18,
                        color: 'var(--text-muted)',
                        fontFamily: 'var(--font-mono)',
                        fontSize: 10,
                        flexShrink: 0,
                      }}
                    >
                      {index + 1}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 12, color: 'var(--text-primary)', marginBottom: 4 }}>
                        {entity.procuring_entity}
                      </div>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                        {entity.entity_bucket_label} • {entity.contract_count} awards
                      </div>
                    </div>
                    <div
                      style={{
                        fontSize: 12,
                        fontFamily: 'var(--font-mono)',
                        color: 'var(--text-primary)',
                        flexShrink: 0,
                      }}
                    >
                      {formatCompactNpr(entity.total_value)}
                    </div>
                  </div>
                ))
              )}
            </div>
          </>
        )}
      </div>
    </Widget>
  );
});
