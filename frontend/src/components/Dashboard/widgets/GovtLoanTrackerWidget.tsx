import { memo, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Landmark, RefreshCw } from 'lucide-react';
import { Widget } from '../Widget';
import { useNepalDebtClock } from '../../../api/hooks';

type CurrencyMode = 'npr' | 'usd';

const NPR_PREFIX = 'Nrs';

function formatInteger(value: number, locale: string = 'en-US'): string {
  return Math.round(value).toLocaleString(locale);
}

function formatCurrencyValue(value: number, currency: CurrencyMode): string {
  if (currency === 'usd') {
    return `$${formatInteger(value, 'en-US')}`;
  }
  return `${NPR_PREFIX} ${formatInteger(value, 'en-NP')}`;
}

function formatCurrencyNumberOnly(value: number, currency: CurrencyMode): string {
  if (currency === 'usd') {
    return formatInteger(value, 'en-US');
  }
  return formatInteger(value, 'en-NP');
}

function formatCompactCurrencyValue(value: number, currency: CurrencyMode): string {
  const absValue = Math.abs(value);
  if (absValue < 1_000_000) {
    if (currency === 'usd') {
      return `$${value.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
    }
    return `${NPR_PREFIX} ${value.toLocaleString('en-NP', { maximumFractionDigits: 0 })}`;
  }

  const suffixes = [
    { threshold: 1_000_000_000_000, suffix: 'T' },
    { threshold: 1_000_000_000, suffix: 'B' },
    { threshold: 1_000_000, suffix: 'M' },
  ];

  for (const { threshold, suffix } of suffixes) {
    if (absValue >= threshold) {
      const compact = (value / threshold).toLocaleString('en-US', {
        minimumFractionDigits: 0,
        maximumFractionDigits: 2,
      });
      if (currency === 'usd') {
        return `$${compact}${suffix}`;
      }
      return `${NPR_PREFIX} ${compact}${suffix}`;
    }
  }

  if (currency === 'usd') {
    return `$${value.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
  }
  return `${NPR_PREFIX} ${value.toLocaleString('en-NP', { maximumFractionDigits: 0 })}`;
}

function formatPercent(value: number | null | undefined): string {
  if (value == null) {
    return 'N/A';
  }
  return `${value.toFixed(2)}%`;
}

function formatYearMeta(prefix: string, year: number | null | undefined): string {
  if (!year) {
    return prefix;
  }
  return `${prefix}: ${year}`;
}

function LoadingState() {
  return (
    <div style={{ height: '100%', padding: 14 }}>
      <div
        style={{
          height: '100%',
          border: '1px solid var(--border-subtle)',
          background: 'linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.01))',
          animation: 'pulse 1.5s infinite',
        }}
      />
    </div>
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <div
      style={{
        height: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 24,
      }}
    >
      <div style={{ textAlign: 'center', maxWidth: 320 }}>
        <AlertTriangle size={32} style={{ color: 'var(--status-warning)', marginBottom: 10 }} />
        <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 6 }}>
          Debt clock unavailable
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.6, marginBottom: 14 }}>
          The live Nepal debt snapshot could not be loaded right now.
        </div>
        <button
          onClick={onRetry}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            padding: '7px 12px',
            border: '1px solid var(--border-subtle)',
            background: 'var(--bg-tertiary)',
            color: 'var(--text-primary)',
            fontSize: 11,
            cursor: 'pointer',
          }}
        >
          <RefreshCw size={12} />
          Retry
        </button>
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  meta,
  accent,
  featured = false,
}: {
  label: string;
  value: string;
  meta: string;
  accent?: string;
  featured?: boolean;
}) {
  const valueLength = value.length;
  const valueFontSize = featured
    ? valueLength > 20 ? 18 : valueLength > 14 ? 21 : 24
    : valueLength > 20 ? 15 : valueLength > 14 ? 17 : 19;

  return (
    <div
      style={{
        border: '1px solid var(--border-subtle)',
        background: 'linear-gradient(180deg, rgba(255,255,255,0.025), rgba(255,255,255,0.01))',
        padding: featured ? '12px 13px 11px' : '10px 11px 9px',
        minHeight: featured ? 94 : 84,
        boxShadow: accent ? `inset 0 1px 0 ${accent}22` : 'inset 0 1px 0 rgba(255,255,255,0.04)',
      }}
    >
      <div
        style={{
          fontSize: 8,
          color: 'var(--text-muted)',
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          marginBottom: 8,
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: valueFontSize,
          lineHeight: featured ? 1 : 1.05,
          fontWeight: 700,
          color: accent || 'var(--text-primary)',
          wordBreak: 'break-word',
          letterSpacing: featured ? '-0.035em' : '-0.02em',
          marginBottom: 6,
        }}
      >
        {value}
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
        {meta}
      </div>
    </div>
  );
}

export const GovtLoanTrackerWidget = memo(function GovtLoanTrackerWidget() {
  const [currency, setCurrency] = useState<CurrencyMode>('npr');
  const [now, setNow] = useState<number>(() => Date.now());
  const { data, isLoading, isError, refetch, isFetching } = useNepalDebtClock();

  useEffect(() => {
    const timer = window.setInterval(() => {
      setNow(Date.now());
    }, 250);
    return () => window.clearInterval(timer);
  }, []);

  const currentDebt = useMemo(() => {
    if (!data) {
      return 0;
    }

    const baseDebt = currency === 'usd' ? data.debt_now_usd : data.debt_now_npr;
    const flowPerSecond = currency === 'usd' ? data.flow_per_second_usd : data.flow_per_second_npr;
    const anchor = Date.parse(data.fetched_at || data.updated_at);

    if (Number.isNaN(anchor)) {
      return baseDebt;
    }

    const elapsedSeconds = Math.max(0, (now - anchor) / 1000);
    return baseDebt + elapsedSeconds * flowPerSecond;
  }, [currency, data, now]);

  const macroCards = useMemo(() => {
    if (!data) {
      return [];
    }

    return [
      {
        label: 'Debt As % Of GDP',
        value: formatPercent(data.debt_gdp_pct),
        meta: data.debt_ratio_label || `Latest year: ${data.snapshot_year || 'N/A'}`,
        accent: '#f59e0b',
        featured: true,
      },
      {
        label: 'External Debt',
        value: formatCompactCurrencyValue(
          currency === 'usd'
            ? (data.external_debt_npr || 0) * data.fx_usd_per_lcy
            : (data.external_debt_npr || 0),
          currency,
        ),
        meta: data.debt_as_of_label || 'Latest debt report',
        accent: '#60a5fa',
        featured: true,
      },
      {
        label: 'Domestic Debt',
        value: formatCompactCurrencyValue(
          currency === 'usd'
            ? (data.domestic_debt_npr || 0) * data.fx_usd_per_lcy
            : (data.domestic_debt_npr || 0),
          currency,
        ),
        meta: data.debt_as_of_label || 'Latest debt report',
        accent: '#34d399',
        featured: true,
      },
      {
        label: 'Debt Per Citizen',
        value: formatCompactCurrencyValue(
          currency === 'usd' ? data.debt_per_citizen_usd : data.debt_per_citizen_npr,
          currency,
        ),
        meta: data.population_label || 'Based on latest population',
      },
      {
        label: 'Per Second',
        value: formatCompactCurrencyValue(
          currency === 'usd' ? data.flow_per_second_usd : data.flow_per_second_npr,
          currency,
        ),
        meta: data.interest_label || formatYearMeta('Snapshot year', data.snapshot_year),
        accent: '#fb923c',
      },
      {
        label: 'GDP (Nominal)',
        value: formatCompactCurrencyValue(
          currency === 'usd' ? data.gdp_nominal_usd : data.gdp_nominal_npr,
          currency,
        ),
        meta: data.gdp_nominal_label || formatYearMeta('Latest year', data.snapshot_year),
        accent: '#93c5fd',
      },
      {
        label: 'Population',
        value: formatInteger(data.population, 'en-NP'),
        meta: data.population_label || formatYearMeta('Latest year', data.population_year),
      },
      {
        label: 'Inflation / Growth',
        value: `${formatPercent(data.inflation_pct)} / ${formatPercent(data.gdp_growth_pct)}`,
        meta: `${data.inflation_label || formatYearMeta('CPI', data.inflation_year)} · ${data.growth_label || formatYearMeta('Growth', data.gdp_growth_year)}`,
      },
      {
        label: 'Budget / Unemployment',
        value: `${formatPercent(data.budget_balance_pct)} / ${formatPercent(data.unemployment_pct)}`,
        meta: `${data.budget_balance_label || formatYearMeta('Budget', data.budget_balance_year)} · ${data.unemployment_label || formatYearMeta('Unemployment', data.unemployment_year)}`,
      },
    ];
  }, [currency, data]);

  if (isLoading) {
    return (
      <Widget id="govt-loan-tracker" icon={<Landmark size={14} />} badge="LIVE">
        <LoadingState />
      </Widget>
    );
  }

  if (isError || !data) {
    return (
      <Widget id="govt-loan-tracker" icon={<Landmark size={14} />}>
        <ErrorState onRetry={() => refetch()} />
      </Widget>
    );
  }

  return (
    <Widget
      id="govt-loan-tracker"
      icon={<Landmark size={14} />}
      badge="LIVE"
      actions={(
        <button
          onClick={() => refetch()}
          title="Refresh debt clock"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 24,
            height: 24,
            border: '1px solid var(--border-subtle)',
            background: 'var(--bg-tertiary)',
            color: 'var(--text-muted)',
            cursor: 'pointer',
          }}
        >
          <RefreshCw size={12} className={isFetching ? 'animate-spin' : ''} />
        </button>
      )}
    >
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div
          style={{
            padding: '13px 14px 12px',
            borderBottom: '1px solid var(--border-subtle)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
          }}
        >
          <div style={{ minWidth: 0, flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
              <span
                style={{
                  fontSize: 9,
                  color: 'var(--text-muted)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.1em',
                }}
              >
                Sovereign Snapshot
              </span>
              <span
                style={{
                  fontSize: 9,
                  color: 'var(--text-secondary)',
                  fontFamily: 'var(--font-mono)',
                  padding: '3px 7px',
                  border: '1px solid var(--border-subtle)',
                  background: 'rgba(255,255,255,0.03)',
                }}
              >
                {data.source_label}
              </span>
              <span
                style={{
                  fontSize: 9,
                  color: 'var(--text-disabled)',
                  fontFamily: 'var(--font-mono)',
                  padding: '3px 7px',
                  border: '1px solid var(--border-subtle)',
                  background: 'rgba(255,255,255,0.02)',
                }}
              >
                {data.debt_as_of_label || data.updated_label}
              </span>
            </div>
            <div style={{ fontSize: 10, color: 'var(--text-disabled)', lineHeight: 1.4 }}>
              Latest official macro releases, normalized into one Nepal sovereign snapshot.
            </div>
          </div>

          <div
            style={{
              display: 'inline-flex',
              background: 'var(--bg-tertiary)',
              border: '1px solid var(--border-subtle)',
              padding: 2,
              gap: 3,
              flexShrink: 0,
            }}
          >
            {(['npr', 'usd'] as CurrencyMode[]).map((option) => {
              const active = option === currency;
              return (
                <button
                  key={option}
                  onClick={() => setCurrency(option)}
                  style={{
                    padding: '6px 10px',
                    border: 'none',
                    background: active ? 'rgba(45,114,210,0.2)' : 'transparent',
                    color: active ? 'var(--text-primary)' : 'var(--text-muted)',
                    fontSize: 9,
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    letterSpacing: '0.06em',
                    cursor: 'pointer',
                    minWidth: 48,
                  }}
                >
                  {option}
                </button>
              );
            })}
          </div>
        </div>

        <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 14, overflow: 'auto' }}>
          <div
            style={{
              border: '1px solid var(--border-subtle)',
              background: 'linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01))',
              padding: '14px 16px 13px',
            }}
          >
            <div
              style={{
                fontSize: 8,
                color: 'var(--text-muted)',
                textTransform: 'uppercase',
                letterSpacing: '0.1em',
                marginBottom: 8,
              }}
            >
              Live Debt Clock
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 8 }}>
              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 12,
                  lineHeight: 1,
                  fontWeight: 700,
                  color: currency === 'usd' ? '#60a5fa' : '#f59e0b',
                  padding: '7px 10px',
                  border: '1px solid var(--border-subtle)',
                  background: 'rgba(255,255,255,0.03)',
                }}
              >
                {currency === 'usd' ? 'USD' : NPR_PREFIX}
              </span>
              <div
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 42,
                  fontWeight: 700,
                  lineHeight: 0.98,
                  color: 'var(--text-primary)',
                  letterSpacing: '-0.05em',
                  wordBreak: 'break-word',
                  minWidth: 0,
                  flex: 1,
                }}
              >
                {formatCurrencyNumberOnly(currentDebt, currency)}
              </div>
            </div>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
              gap: 10,
            }}
          >
            {macroCards.map((card) => (
              <StatCard
                key={card.label}
                label={card.label}
                value={card.value}
                meta={card.meta}
                accent={card.accent}
                featured={card.featured}
              />
            ))}
          </div>
        </div>
      </div>
    </Widget>
  );
});
