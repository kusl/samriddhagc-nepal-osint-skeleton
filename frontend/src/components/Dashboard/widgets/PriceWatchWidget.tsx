import { memo, useMemo } from 'react';
import { Coins, Fuel, RefreshCw } from 'lucide-react';
import { Widget } from '../Widget';
import { useMarketSummary } from '../../../api/hooks';
import { WidgetError, WidgetSkeleton } from './shared';

function formatValue(value: number, kind: 'npr' | 'points' | 'tola' | 'litre'): string {
  if (kind === 'points') {
    return value.toLocaleString('en-NP', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  if (kind === 'tola') {
    return `Nrs ${value.toLocaleString('en-NP', { maximumFractionDigits: 0 })}`;
  }
  if (kind === 'litre') {
    return `Nrs ${value.toFixed(2)}`;
  }
  return value.toFixed(2);
}

function formatChange(value: number): string {
  const prefix = value >= 0 ? '+' : '';
  return `${prefix}${value.toFixed(2)}%`;
}

function compactTimestamp(value: string | null | undefined): string {
  if (!value) return 'Awaiting refresh';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Awaiting refresh';
  return `Updated ${date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}`;
}

export const PriceWatchWidget = memo(function PriceWatchWidget() {
  const { data, isLoading, isError, refetch } = useMarketSummary();

  const cards = useMemo(() => {
    return [
      {
        label: 'Gold',
        value: data?.gold ? formatValue(data.gold.value, 'tola') : '--',
        change: data?.gold ? formatChange(data.gold.change) : '--',
        accent: '#f59e0b',
        meta: 'per tola',
      },
      {
        label: 'Silver',
        value: data?.silver ? formatValue(data.silver.value, 'tola') : '--',
        change: data?.silver ? formatChange(data.silver.change) : '--',
        accent: '#cbd5e1',
        meta: 'per tola',
      },
      {
        label: 'Petrol',
        value: data?.petrol ? formatValue(data.petrol.value, 'litre') : '--',
        change: data?.petrol ? formatChange(data.petrol.change) : '--',
        accent: '#fb923c',
        meta: data?.petrol?.data_date ? `NOC · ${new Date(data.petrol.data_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}` : 'Nepal Oil Corporation',
      },
      {
        label: 'Diesel',
        value: data?.diesel ? formatValue(data.diesel.value, 'litre') : '--',
        change: data?.diesel ? formatChange(data.diesel.change) : '--',
        accent: '#38bdf8',
        meta: data?.diesel?.data_date ? `NOC · ${new Date(data.diesel.data_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}` : 'Nepal Oil Corporation',
      },
      {
        label: 'USD / NPR',
        value: data?.usd_npr ? formatValue(data.usd_npr.value, 'npr') : '--',
        change: data?.usd_npr ? formatChange(data.usd_npr.change) : '--',
        accent: '#34d399',
        meta: 'NRB forex',
      },
      {
        label: 'NEPSE',
        value: data?.nepse ? formatValue(data.nepse.value, 'points') : '--',
        change: data?.nepse ? formatChange(data.nepse.change) : '--',
        accent: '#60a5fa',
        meta: 'daily close',
      },
    ];
  }, [data]);

  return (
    <Widget
      id="price-watch"
      icon={<Coins size={14} />}
      badge={compactTimestamp(data?.updated_at)}
      actions={
        <button className="widget-action" title="Refresh prices" onClick={() => refetch()}>
          <RefreshCw size={12} />
        </button>
      }
    >
      {isLoading ? (
        <WidgetSkeleton />
      ) : isError ? (
        <WidgetError message="Failed to load price watch" onRetry={() => refetch()} />
      ) : (
        <div
          style={{
            height: '100%',
            display: 'grid',
            gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
            gap: 1,
            background: 'var(--border-subtle)',
          }}
        >
          {cards.map((card) => {
            const positive = card.change.startsWith('+');
            return (
              <div
                key={card.label}
                style={{
                  background: 'var(--bg-surface)',
                  padding: '10px 11px',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  minHeight: 74,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                  <span
                    style={{
                      fontSize: 9,
                      color: 'var(--text-muted)',
                      textTransform: 'uppercase',
                      letterSpacing: '0.08em',
                    }}
                  >
                    {card.label}
                  </span>
                  {card.label === 'Petrol' || card.label === 'Diesel' ? <Fuel size={11} color={card.accent} /> : null}
                </div>
                <div
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 16,
                    lineHeight: 1.15,
                    color: card.accent,
                    marginBottom: 5,
                  }}
                >
                  {card.value}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                  <span style={{ fontSize: 9, color: 'var(--text-disabled)' }}>{card.meta}</span>
                  <span
                    style={{
                      fontSize: 10,
                      fontFamily: 'var(--font-mono)',
                      color: positive ? 'var(--status-low)' : 'var(--status-critical)',
                    }}
                  >
                    {card.change}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Widget>
  );
});
