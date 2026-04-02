import { memo } from 'react';
import { Landmark, RefreshCw } from 'lucide-react';
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

export const NrbBankingLiquidityWidget = memo(function NrbBankingLiquidityWidget() {
  const { data, isLoading, isError, refetch } = useNepalDebtClock();

  const cards = data
    ? [
        { label: 'Broad Money Growth', value: formatPercent(data.broad_money_growth_pct), meta: data.broad_money_growth_label || 'Latest NRB release' },
        { label: 'Private Credit Growth', value: formatPercent(data.private_sector_credit_growth_pct), meta: data.private_sector_credit_growth_label || 'Latest NRB release' },
        { label: 'Deposit Rate', value: formatPercent(data.weighted_deposit_rate_pct), meta: data.weighted_deposit_rate_label || 'Latest NRB release' },
        { label: 'Credit Rate', value: formatPercent(data.weighted_credit_rate_pct), meta: data.weighted_credit_rate_label || 'Latest NRB release' },
        { label: 'Interbank Rate', value: formatPercent(data.interbank_rate_pct), meta: data.interbank_rate_label || 'Latest NRB release' },
        {
          label: 'Banking Network',
          value:
            data.total_financial_institutions != null || data.total_bfi_branches != null
              ? `${formatInteger(data.total_financial_institutions)} FI • ${formatInteger(data.licensed_bfis)} BFI`
              : 'N/A',
          meta:
            data.total_bfi_branches != null
              ? `${formatInteger(data.total_bfi_branches)} branches`
              : data.total_bfi_branches_label || 'Latest NRB release',
        },
      ]
    : [];

  return (
    <Widget
      id="nrb-banking"
      icon={<Landmark size={14} />}
      badge="NRB"
      actions={
        <button className="widget-action" title="Refresh banking and liquidity" onClick={() => refetch()}>
          <RefreshCw size={12} />
        </button>
      }
    >
      {isLoading ? (
        <WidgetSkeleton />
      ) : isError ? (
        <WidgetError message="Failed to load NRB banking data" onRetry={() => refetch()} />
      ) : cards.length === 0 ? (
        <WidgetEmpty message="No NRB banking data available" />
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
              Banking and liquidity
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
              <div key={card.label} style={{ background: 'var(--bg-surface)', padding: '12px', minHeight: 78 }}>
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
                    fontSize: 18,
                    lineHeight: 1.1,
                    color: 'var(--text-primary)',
                    marginBottom: 7,
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
