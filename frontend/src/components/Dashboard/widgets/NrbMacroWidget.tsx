import { memo } from 'react';
import { BarChart3, RefreshCw } from 'lucide-react';
import { Widget } from '../Widget';
import { useNepalDebtClock } from '../../../api/hooks';
import { WidgetEmpty, WidgetError, WidgetSkeleton } from './shared';

function formatPercent(value: number | null | undefined): string {
  if (value == null) return 'N/A';
  return `${value.toFixed(2)}%`;
}

function formatInteger(value: number | null | undefined): string {
  if (value == null) return 'N/A';
  return Math.round(value).toLocaleString('en-US');
}

function formatCompactBillionNpr(value: number | null | undefined): string {
  if (value == null) return 'N/A';
  if (value >= 1_000) {
    return `Nrs ${(value / 1_000).toFixed(2).replace(/\.00$/, '')}T`;
  }
  return `Nrs ${value.toLocaleString('en-US', { maximumFractionDigits: 0 })}B`;
}

export const NrbMacroWidget = memo(function NrbMacroWidget() {
  const { data, isLoading, isError, refetch } = useNepalDebtClock();

  const cards = data
    ? [
        {
          label: 'Inflation',
          value: formatPercent(data.inflation_pct),
          meta: data.inflation_label || `Latest year: ${data.inflation_year || 'N/A'}`,
        },
        {
          label: 'Food Inflation',
          value: formatPercent(data.food_inflation_pct),
          meta: data.food_inflation_label || 'Latest NRB release',
        },
        {
          label: 'Non-food Inflation',
          value: formatPercent(data.non_food_inflation_pct),
          meta: data.non_food_inflation_label || 'Latest NRB release',
        },
        {
          label: 'Broad Money Growth',
          value: formatPercent(data.broad_money_growth_pct),
          meta: data.broad_money_growth_label || 'Latest NRB release',
        },
        {
          label: 'Private Credit Growth',
          value: formatPercent(data.private_sector_credit_growth_pct),
          meta: data.private_sector_credit_growth_label || 'Latest NRB release',
        },
        {
          label: 'Remittance Inflow',
          value: formatCompactBillionNpr(data.remittance_inflow_billion_npr),
          meta: data.remittance_inflow_label || 'Latest NRB release',
        },
        {
          label: 'BOP Surplus',
          value: formatCompactBillionNpr(data.bop_surplus_billion_npr),
          meta: data.bop_surplus_label || 'Latest NRB release',
        },
        {
          label: 'Deposit Rate',
          value: formatPercent(data.weighted_deposit_rate_pct),
          meta: data.weighted_deposit_rate_label || 'Latest NRB release',
        },
        {
          label: 'Credit Rate',
          value: formatPercent(data.weighted_credit_rate_pct),
          meta: data.weighted_credit_rate_label || 'Latest NRB release',
        },
        {
          label: 'Interbank Rate',
          value: formatPercent(data.interbank_rate_pct),
          meta: data.interbank_rate_label || 'Latest NRB release',
        },
        {
          label: 'Financial Institutions',
          value: formatInteger(data.total_financial_institutions),
          meta: data.total_financial_institutions_label || 'Latest NRB release',
        },
        {
          label: 'Licensed BFIs',
          value: formatInteger(data.licensed_bfis),
          meta: data.licensed_bfis_label || 'Latest NRB release',
        },
        {
          label: 'Total Branches',
          value: formatInteger(data.total_bfi_branches),
          meta: data.total_bfi_branches_label || 'Latest NRB release',
        },
      ]
    : [];

  const sourceMeta = [
    data?.source_label || 'NRB / IMF / World Bank',
    data?.debt_as_of_label || data?.updated_label,
  ].filter(Boolean).join(' • ');

  return (
    <Widget
      id="nrb-macro"
      icon={<BarChart3 size={14} />}
      badge="LATEST"
      actions={
        <button className="widget-action" title="Refresh macro snapshot" onClick={() => refetch()}>
          <RefreshCw size={12} />
        </button>
      }
    >
      {isLoading ? (
        <WidgetSkeleton />
      ) : isError ? (
        <WidgetError message="Failed to load macro data" onRetry={() => refetch()} />
      ) : cards.length === 0 ? (
        <WidgetEmpty message="No macro snapshot available" />
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
              display: 'flex',
              flexWrap: 'wrap',
              gap: 8,
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
              Central bank snapshot
            </span>
            <span
              style={{
                fontSize: 9,
                color: 'var(--text-disabled)',
                fontFamily: 'var(--font-mono)',
              }}
            >
              {sourceMeta}
            </span>
          </div>

          <div
            style={{
              flex: 1,
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: 1,
              background: 'var(--border-subtle)',
              overflowY: 'auto',
            }}
          >
            {cards.map((card) => (
              <div
                key={card.label}
                style={{
                  background: 'var(--bg-surface)',
                  padding: '10px 11px',
                  minHeight: 78,
                }}
              >
                <div
                  style={{
                    fontSize: 9,
                    color: 'var(--text-muted)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.08em',
                    marginBottom: 7,
                  }}
                >
                  {card.label}
                </div>
                <div
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 15,
                    lineHeight: 1.15,
                    color: 'var(--text-primary)',
                    marginBottom: 6,
                    wordBreak: 'break-word',
                  }}
                >
                  {card.value}
                </div>
                <div
                  style={{
                    fontSize: 9,
                    color: 'var(--text-disabled)',
                    lineHeight: 1.3,
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
