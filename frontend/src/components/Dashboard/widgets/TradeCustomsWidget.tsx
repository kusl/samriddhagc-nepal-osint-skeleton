import { memo, useMemo, useState } from 'react';
import { ArrowDownRight, ArrowUpRight, BusFront, RefreshCw, Search } from 'lucide-react';
import { Widget } from '../Widget';
import { useBorderCrossingStatus } from '../../../api/hooks';
import { WidgetEmpty, WidgetError, WidgetSkeleton } from './shared';

function formatCompactNprThousands(value: number): string {
  const npr = value * 1_000;
  const abs = Math.abs(npr);
  if (abs >= 1_000_000_000) return `Nrs ${(npr / 1_000_000_000).toFixed(2).replace(/\.00$/, '')}B`;
  if (abs >= 1_000_000) return `Nrs ${(npr / 1_000_000).toFixed(2).replace(/\.00$/, '')}M`;
  if (abs >= 1_000) return `Nrs ${(npr / 1_000).toFixed(1).replace(/\.0$/, '')}K`;
  return `Nrs ${Math.round(npr).toLocaleString('en-US')}`;
}

function formatDelta(current: number, previous: number): string {
  if (!previous) return 'New';
  const change = ((current - previous) / previous) * 100;
  const prefix = change >= 0 ? '+' : '';
  return `${prefix}${change.toFixed(1)}%`;
}

export const TradeCustomsWidget = memo(function TradeCustomsWidget() {
  const { data, isLoading, isError, refetch } = useBorderCrossingStatus();
  const [search, setSearch] = useState('');

  const items = useMemo(
    () =>
      (data?.items || [])
        .filter((item) => item.status !== 'NO_DATA')
        .sort((a, b) => b.current_month_value_npr_thousands - a.current_month_value_npr_thousands),
    [data?.items],
  );

  const filteredItems = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return items;
    return items.filter((item) => {
      const haystack = [
        item.name,
        item.route,
        ...(item.customs_offices || []),
      ]
        .join(' ')
        .toLowerCase();
      return haystack.includes(needle);
    });
  }, [items, search]);

  const operationalCount = items.filter((item) => item.is_operational).length;
  const totalValue = items.reduce((sum, item) => sum + item.current_month_value_npr_thousands, 0);
  const leadRoute = filteredItems[0] || items[0];

  return (
    <Widget
      id="trade-customs"
      icon={<BusFront size={14} />}
      badge={data?.period?.upto_month || 'CUSTOMS'}
      actions={
        <button className="widget-action" title="Refresh trade and customs" onClick={() => refetch()}>
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
        {isLoading ? (
          <WidgetSkeleton />
        ) : isError ? (
          <WidgetError message="Failed to load trade and customs" onRetry={() => refetch()} />
        ) : items.length === 0 ? (
          <WidgetEmpty message="No customs flow available yet" />
        ) : (
          <>
            <div
              style={{
                padding: '10px 12px',
                borderBottom: '1px solid var(--border-subtle)',
                background: 'var(--bg-surface)',
              }}
            >
              <label
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  border: '1px solid var(--border-subtle)',
                  background: 'var(--bg-canvas)',
                  padding: '8px 10px',
                }}
              >
                <Search size={13} style={{ color: 'var(--text-muted)' }} />
                <input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search customs office or route..."
                  style={{
                    flex: 1,
                    minWidth: 0,
                    border: 0,
                    outline: 0,
                    background: 'transparent',
                    color: 'var(--text-primary)',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 11,
                  }}
                />
                <span
                  style={{
                    fontSize: 9,
                    color: 'var(--text-disabled)',
                    fontFamily: 'var(--font-mono)',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {filteredItems.length} shown
                </span>
              </label>
            </div>

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
                { label: 'Operational', value: `${operationalCount}`, meta: `${items.length} tracked routes` },
                { label: 'Trade Value', value: formatCompactNprThousands(totalValue), meta: data?.period?.fiscal_year_bs || 'Current period' },
                { label: 'Lead Crossing', value: leadRoute?.name || 'None', meta: leadRoute?.route || 'No route', compact: true },
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
              {filteredItems.map((item) => {
                const positive = item.current_month_value_npr_thousands >= item.previous_month_value_npr_thousands;
                return (
                  <div
                    key={item.id}
                    style={{
                      padding: '11px 13px',
                      borderBottom: '1px solid var(--border-subtle)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 12,
                    }}
                  >
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 12, color: 'var(--text-primary)', marginBottom: 4 }}>
                        {item.name}
                      </div>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                        {item.route}
                      </div>
                    </div>
                    <div style={{ textAlign: 'right', flexShrink: 0 }}>
                      <div
                        style={{
                          fontSize: 12,
                          color: 'var(--text-primary)',
                          fontFamily: 'var(--font-mono)',
                          marginBottom: 4,
                        }}
                      >
                        {formatCompactNprThousands(item.current_month_value_npr_thousands)}
                      </div>
                      <div
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 4,
                          fontSize: 10,
                          color: positive ? 'var(--status-low)' : 'var(--status-high)',
                          fontFamily: 'var(--font-mono)',
                        }}
                      >
                        {positive ? <ArrowUpRight size={11} /> : <ArrowDownRight size={11} />}
                        {formatDelta(item.current_month_value_npr_thousands, item.previous_month_value_npr_thousands)}
                      </div>
                    </div>
                  </div>
                );
              })}

              {filteredItems.length === 0 ? (
                <div
                  style={{
                    padding: '18px 14px',
                    color: 'var(--text-muted)',
                    fontSize: 11,
                    fontFamily: 'var(--font-mono)',
                  }}
                >
                  No customs routes match that search.
                </div>
              ) : null}
            </div>
          </>
        )}
      </div>
    </Widget>
  );
});
