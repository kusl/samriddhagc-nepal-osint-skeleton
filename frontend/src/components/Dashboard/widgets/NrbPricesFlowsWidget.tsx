import { memo } from 'react';
import { BarChart3, RefreshCw } from 'lucide-react';
import { Widget } from '../Widget';
import { useNepalDebtClock } from '../../../api/hooks';
import { WidgetEmpty, WidgetError, WidgetSkeleton } from './shared';

function formatPercent(value: number | null | undefined): string {
  if (value == null) return 'N/A';
  return `${value.toFixed(2)}%`;
}

function formatCompactBillionNpr(value: number | null | undefined): string {
  if (value == null) return 'N/A';
  if (value >= 1_000) {
    return `Nrs ${(value / 1_000).toFixed(2).replace(/\.00$/, '')}T`;
  }
  return `Nrs ${value.toLocaleString('en-US', { maximumFractionDigits: 0 })}B`;
}

export const NrbPricesFlowsWidget = memo(function NrbPricesFlowsWidget() {
  const { data, isLoading, isError, refetch } = useNepalDebtClock();

  const cards = data
    ? [
        { label: 'Inflation', value: formatPercent(data.inflation_pct), meta: data.inflation_label || 'Latest NRB release' },
        { label: 'Food Inflation', value: formatPercent(data.food_inflation_pct), meta: data.food_inflation_label || 'Latest NRB release' },
        { label: 'Non-food Inflation', value: formatPercent(data.non_food_inflation_pct), meta: data.non_food_inflation_label || 'Latest NRB release' },
        { label: 'Remittance Inflow', value: formatCompactBillionNpr(data.remittance_inflow_billion_npr), meta: data.remittance_inflow_label || 'Latest NRB release' },
        { label: 'BOP Surplus', value: formatCompactBillionNpr(data.bop_surplus_billion_npr), meta: data.bop_surplus_label || 'Latest NRB release' },
        { label: 'GDP Growth', value: formatPercent(data.gdp_growth_pct), meta: data.growth_label || 'Latest IMF projection' },
      ]
    : [];

  return (
    <Widget
      id="nrb-prices"
      icon={<BarChart3 size={14} />}
      badge="NRB"
      actions={
        <button className="widget-action" title="Refresh NRB prices and flows" onClick={() => refetch()}>
          <RefreshCw size={12} />
        </button>
      }
    >
      {isLoading ? (
        <WidgetSkeleton />
      ) : isError ? (
        <WidgetError message="Failed to load NRB prices and flows" onRetry={() => refetch()} />
      ) : cards.length === 0 ? (
        <WidgetEmpty message="No NRB prices and flows available" />
      ) : (
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
              padding: '10px 12px',
              borderBottom: '1px solid var(--border-subtle)',
            }}
          >
            <span
              style={{
                fontSize: 9,
                color: 'var(--text-muted)',
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
              }}
            >
              Prices and external flows
            </span>
          </div>

          <div
            style={{
              flex: 1,
              display: 'grid',
              gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
              gridAutoRows: '1fr',
              gap: 1,
              background: 'var(--border-subtle)',
            }}
          >
            {cards.map((card) => (
              <div key={card.label} style={{ background: 'var(--bg-surface)', padding: '12px', minHeight: 88 }}>
                <div
                  style={{
                    fontSize: 9,
                    color: 'var(--text-muted)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.08em',
                    marginBottom: 8,
                  }}
                >
                  {card.label}
                </div>
                <div
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 19,
                    lineHeight: 1.1,
                    color: 'var(--text-primary)',
                    marginBottom: 8,
                  }}
                >
                  {card.value}
                </div>
                <div
                  style={{
                    fontSize: 9,
                    color: 'var(--text-disabled)',
                    lineHeight: 1.35,
                    display: '-webkit-box',
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: 'vertical',
                    overflow: 'hidden',
                  }}
                >
                  {card.meta}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </Widget>
  );
});
