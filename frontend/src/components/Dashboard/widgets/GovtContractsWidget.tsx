import { memo, useMemo, useState } from 'react';
import { Briefcase, Building2, Landmark, RefreshCw, Search, Shield } from 'lucide-react';
import { Widget } from '../Widget';
import { useProcurementWidgetSummary } from '../../../api/hooks/useProcurement';

const FILTER_GROUP_STYLE = {
  display: 'flex',
  gap: '2px',
  background: 'var(--bg-tertiary)',
  borderRadius: '4px',
  padding: '2px',
} as const;

const FILTER_BUTTON_STYLE = {
  padding: '2px 6px',
  fontSize: '9px',
  fontWeight: 500,
  border: 'none',
  borderRadius: '3px',
  cursor: 'pointer',
  transition: 'all 0.15s ease',
  fontFamily: 'var(--font-mono)',
} as const;

const ENTITY_FILTER_PRIORITY = [
  'all',
  'ministry',
  'organization',
  'security_agency',
  'local_government',
  'department_or_office',
] as const;

function formatCompactNpr(value: number | null | undefined): string {
  if (!value) return 'Nrs 0';
  const abs = Math.abs(value);
  if (abs >= 1_000_000_000_000) return `Nrs ${(value / 1_000_000_000_000).toFixed(2).replace(/\.00$/, '')}T`;
  if (abs >= 1_000_000_000) return `Nrs ${(value / 1_000_000_000).toFixed(2).replace(/\.00$/, '')}B`;
  if (abs >= 1_000_000) return `Nrs ${(value / 1_000_000).toFixed(2).replace(/\.00$/, '')}M`;
  if (abs >= 1_000) return `Nrs ${(value / 1_000).toFixed(1).replace(/\.0$/, '')}K`;
  return `Nrs ${Math.round(value).toLocaleString('en-US')}`;
}

function formatAwardDate(
  value: string | null,
  options?: { fiscalYear?: string | null; fetchedAt?: string | null },
): string {
  if (!value) {
    if (options?.fiscalYear) {
      return `FY ${options.fiscalYear}`;
    }
    if (options?.fetchedAt) {
      const fetched = new Date(options.fetchedAt);
      if (!Number.isNaN(fetched.getTime())) {
        return `Fetched ${fetched.toLocaleDateString('en-US', {
          month: 'short',
          day: 'numeric',
          year: 'numeric',
        })}`;
      }
    }
    return 'Award date unavailable';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

function normalizeBucketCount(bucket: { count?: number; contract_count?: number }): number {
  return bucket.count ?? bucket.contract_count ?? 0;
}

function compactProcurementType(value: string): string {
  return value.length > 20 ? value.replace('Quotation', 'Quote') : value;
}

function bucketIcon(bucket: string) {
  switch (bucket) {
    case 'ministry':
      return <Landmark size={12} />;
    case 'security_agency':
      return <Shield size={12} />;
    default:
      return <Building2 size={12} />;
  }
}

export const GovtContractsWidget = memo(function GovtContractsWidget() {
  const [entityBucket, setEntityBucket] = useState<string>('all');
  const [procurementType, setProcurementType] = useState<string>('all');
  const [search, setSearch] = useState('');

  const trimmedSearch = search.trim();

  const summaryQuery = useProcurementWidgetSummary({
    ...(entityBucket !== 'all' ? { entity_bucket: entityBucket } : {}),
    ...(procurementType !== 'all' ? { procurement_type: procurementType } : {}),
    ...(trimmedSearch ? { search: trimmedSearch } : {}),
    per_page: 20,
  });
  const summary = summaryQuery.data;

  const bucketFilters = useMemo(() => {
    const apiBuckets = summary?.entity_buckets || [];
    const apiMap = new Map(apiBuckets.map((bucket) => [bucket.bucket, bucket]));
    return ENTITY_FILTER_PRIORITY.filter((bucket) => bucket === 'all' || apiMap.has(bucket)).map((bucket) => {
      if (bucket === 'all') {
        return {
          bucket: 'all',
          label: 'All',
          count: summary?.stats.total_contracts || 0,
        };
      }
      const item = apiMap.get(bucket)!;
      return {
        bucket,
        label: item.label,
        count: normalizeBucketCount(item),
      };
    });
  }, [summary?.entity_buckets, summary?.stats.total_contracts]);

  const procurementTypes = useMemo(() => {
    const types = (summary?.stats.by_procurement_type || [])
      .slice()
      .sort((a, b) => b.count - a.count)
      .map((item) => item.type);
    return ['all', ...types];
  }, [summary?.stats.by_procurement_type]);

  const summaryCards = summary?.cards || [];
  const isLoading = summaryQuery.isLoading;
  const hasError = summaryQuery.isError;
  const contracts = summary?.contracts || [];
  const hasResolvedData = Boolean(summary);
  const showInitialLoading = isLoading && !hasResolvedData;
  const showRefreshing = !showInitialLoading && summaryQuery.isFetching;

  return (
    <Widget
      id="govt-contracts"
      icon={<Briefcase size={14} />}
      badge={summary?.stats.total_contracts ? `${summary.stats.total_contracts} CONTRACTS` : 'LIVE'}
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
            padding: '8px 12px',
            display: 'flex',
            gap: 6,
            alignItems: 'center',
            flexWrap: 'wrap',
            borderBottom: '1px solid var(--border-subtle)',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              border: '1px solid var(--border-subtle)',
              background: 'rgba(255,255,255,0.02)',
              padding: '0 10px',
              height: 32,
              minWidth: 180,
              flex: '1 1 180px',
            }}
          >
            <Search size={14} color="var(--text-muted)" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search project or entity..."
              style={{
                flex: 1,
                background: 'transparent',
                border: 'none',
                outline: 'none',
                color: 'var(--text-primary)',
                fontSize: 11,
                fontFamily: 'var(--font-mono)',
              }}
            />
          </div>

          <button
            onClick={() => {
              summaryQuery.refetch();
            }}
            className="widget-action"
            title="Refresh contracts"
          >
            <RefreshCw size={12} />
          </button>

          {showRefreshing ? (
            <div
              style={{
                fontSize: 9,
                color: 'var(--text-disabled)',
                fontFamily: 'var(--font-mono)',
                padding: '0 2px',
              }}
            >
              Refreshing...
            </div>
          ) : null}
        </div>

        <div
          style={{
            padding: '7px 12px',
            display: 'flex',
            gap: 6,
            flexWrap: 'wrap',
            alignItems: 'center',
            borderBottom: '1px solid var(--border-subtle)',
          }}
        >
          <div style={{ ...FILTER_GROUP_STYLE, flexWrap: 'wrap' }}>
            {bucketFilters.map((bucket) => {
              const active = bucket.bucket === entityBucket;
              return (
                <button
                  key={bucket.bucket}
                  onClick={() => setEntityBucket(bucket.bucket)}
                  style={{
                    ...FILTER_BUTTON_STYLE,
                    background: active ? 'var(--bg-secondary)' : 'transparent',
                    color: active ? 'var(--text-primary)' : 'var(--text-muted)',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 5,
                  }}
                >
                  {bucket.bucket !== 'all' ? bucketIcon(bucket.bucket) : null}
                  <span>{bucket.label}</span>
                  <span style={{ color: 'var(--text-disabled)' }}>{bucket.count}</span>
                </button>
              );
            })}
          </div>

          <div
            style={{
              width: '1px',
              height: '16px',
              background: 'var(--border-subtle)',
              flexShrink: 0,
            }}
          />

          <div style={{ ...FILTER_GROUP_STYLE, flexWrap: 'wrap' }}>
            {procurementTypes.map((type) => {
              const active = procurementType === type;
              return (
                <button
                  key={type}
                  onClick={() => setProcurementType(type)}
                  style={{
                    ...FILTER_BUTTON_STYLE,
                    background: active ? 'var(--bg-secondary)' : 'transparent',
                    color: active ? 'var(--text-primary)' : 'var(--text-muted)',
                  }}
                >
                  {type === 'all' ? 'All types' : compactProcurementType(type)}
                </button>
              );
            })}
          </div>
        </div>

        <div
          style={{
            padding: '7px 12px',
            borderBottom: '1px solid var(--border-subtle)',
            display: 'grid',
            gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
            gap: 6,
          }}
        >
          {summaryCards.map((item) => (
            <div
              key={item.label}
              style={{
                border: '1px solid var(--border-subtle)',
                background: 'rgba(255,255,255,0.02)',
                padding: '7px 9px',
                minWidth: 0,
              }}
            >
              <div
                style={{
                  fontSize: 8,
                  color: 'var(--text-muted)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.08em',
                  marginBottom: 5,
                }}
              >
                {item.label}
              </div>
              <div
                style={{
                  fontFamily: item.compact ? 'var(--font-sans)' : 'var(--font-mono)',
                  fontSize: item.compact ? 12 : 15,
                  lineHeight: 1.15,
                  fontWeight: 700,
                  color: 'var(--text-primary)',
                  marginBottom: 4,
                  whiteSpace: item.compact ? 'nowrap' : 'normal',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
                title={item.value}
              >
                {item.value}
              </div>
              <div style={{ fontSize: 9, color: 'var(--text-disabled)', lineHeight: 1.25 }}>
                {item.meta}
              </div>
            </div>
          ))}
        </div>

        <div style={{ flex: 1, overflow: 'auto' }}>
          {showInitialLoading ? (
            <div style={{ padding: 12, color: 'var(--text-muted)', fontSize: 11 }}>Loading contract data...</div>
          ) : hasError ? (
            <div style={{ padding: 12, color: 'var(--status-critical)', fontSize: 11 }}>
              Failed to load contract data
            </div>
          ) : contracts.length === 0 ? (
            <div style={{ padding: 12, color: 'var(--text-muted)', fontSize: 11 }}>
              No contracts found for this filter.
            </div>
          ) : (
            contracts.map((contract) => (
              <div
                key={contract.id}
                style={{
                  padding: '9px 12px',
                  borderBottom: '1px solid var(--border-subtle)',
                  display: 'flex',
                  gap: 10,
                  alignItems: 'flex-start',
                }}
              >
                <div
                  style={{
                    width: 4,
                    alignSelf: 'stretch',
                    background:
                      contract.entity_bucket === 'security_agency'
                        ? '#ef4444'
                        : contract.entity_bucket === 'ministry'
                          ? '#60a5fa'
                          : '#f59e0b',
                    borderRadius: 999,
                    opacity: 0.9,
                    flexShrink: 0,
                  }}
                />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginBottom: 5 }}>
                    <span
                      style={{
                        padding: '2px 6px',
                        border: '1px solid var(--border-subtle)',
                        background: 'rgba(255,255,255,0.04)',
                        fontSize: 8,
                        textTransform: 'uppercase',
                        letterSpacing: '0.08em',
                        color: 'var(--text-secondary)',
                      }}
                    >
                      {contract.entity_bucket_label}
                    </span>
                    <span
                      style={{
                        padding: '2px 6px',
                        border: '1px solid rgba(45,114,210,0.25)',
                        background: 'rgba(45,114,210,0.12)',
                        fontSize: 8,
                        textTransform: 'uppercase',
                        letterSpacing: '0.08em',
                        color: '#60a5fa',
                      }}
                    >
                      {compactProcurementType(contract.procurement_type)}
                    </span>
                  </div>
                  <div
                    style={{
                      fontSize: 12,
                      fontWeight: 700,
                      color: 'var(--text-primary)',
                      lineHeight: 1.35,
                      marginBottom: 4,
                    }}
                  >
                    {contract.project_name}
                  </div>
                  <div
                    style={{
                      fontSize: 10,
                      color: 'var(--text-muted)',
                      lineHeight: 1.4,
                      display: '-webkit-box',
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: 'vertical',
                      overflow: 'hidden',
                      marginBottom: 6,
                    }}
                  >
                    {contract.procuring_entity}
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', fontSize: 9, color: 'var(--text-disabled)' }}>
                    <span>{contract.contractor_name || 'Contractor not listed'}</span>
                    {contract.district ? <span>• {contract.district}</span> : null}
                    {contract.fiscal_year_bs ? <span>• FY {contract.fiscal_year_bs}</span> : null}
                  </div>
                </div>

                <div style={{ minWidth: 108, textAlign: 'right', flexShrink: 0 }}>
                  <div
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 14,
                      lineHeight: 1.1,
                      fontWeight: 700,
                      color: 'var(--text-primary)',
                      marginBottom: 4,
                    }}
                  >
                    {formatCompactNpr(contract.contract_amount_npr)}
                  </div>
                  <div style={{ fontSize: 9, color: 'var(--text-disabled)', marginBottom: 5 }}>
                    {formatAwardDate(contract.contract_award_date, {
                      fiscalYear: contract.fiscal_year_bs,
                      fetchedAt: contract.fetched_at,
                    })}
                  </div>
                  {contract.source_url ? (
                    <a
                      href={contract.source_url}
                      target="_blank"
                      rel="noreferrer"
                      style={{
                        color: 'var(--accent-primary)',
                        textDecoration: 'none',
                        fontSize: 9,
                      }}
                    >
                      Source
                    </a>
                  ) : null}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </Widget>
  );
});
