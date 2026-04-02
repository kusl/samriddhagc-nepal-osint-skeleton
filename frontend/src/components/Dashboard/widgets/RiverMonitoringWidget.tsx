import { memo, useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle, Droplets, Search, TrendingDown, TrendingUp, Waves } from 'lucide-react';
import { Widget } from '../Widget';
import { useRiverStations } from '../../../api/hooks';
import { WidgetSkeleton, WidgetError, WidgetEmpty, formatTimeAgo } from './shared';

const MIN_REASONABLE_WATER_LEVEL = -2;
const MAX_REASONABLE_WATER_LEVEL = 200;

const COMPACT_SEGMENT_STYLE = {
  padding: '3px 7px',
  fontSize: '9px',
  fontWeight: 600,
  fontFamily: 'var(--font-mono)',
  border: '1px solid var(--border-subtle)',
  cursor: 'pointer',
  lineHeight: 1.2,
  whiteSpace: 'nowrap' as const,
};

const TIME_OPTIONS = [
  { label: '24H', hours: 24 },
  { label: '48H', hours: 48 },
  { label: '72H', hours: 72 },
  { label: '7D', hours: 168 },
];

const STATUS_FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'danger', label: 'Danger' },
  { key: 'warning', label: 'Warning' },
  { key: 'safe', label: 'Safe' },
] as const;

type RiverStatusFilter = (typeof STATUS_FILTERS)[number]['key'];
type RiverDisplayStatus = 'danger' | 'warning' | 'safe';

type RiverViewItem = {
  id: string;
  title: string;
  basin: string | null;
  current_level: number | null;
  warning_level: number | null;
  danger_level: number | null;
  current_status: string | null;
  current_trend: string | null;
  reading_at: string | null;
  margin: number | null;
  status: RiverDisplayStatus;
};

const parseReadingTime = (raw: string | null | undefined): number | null => {
  if (!raw) return null;
  const ms = Date.parse(raw);
  return Number.isNaN(ms) ? null : ms;
};

const isWithinWindow = (readingAt: string | null | undefined, hours: number): boolean => {
  const ts = parseReadingTime(readingAt);
  if (ts === null) return false;
  return (Date.now() - ts) <= hours * 60 * 60 * 1000;
};

const isSensorError = (
  level: number | null,
  warningLevel: number | null,
  dangerLevel: number | null,
): boolean => {
  if (level === null) return false;
  if (!Number.isFinite(level)) return true;
  if (level < MIN_REASONABLE_WATER_LEVEL) return true;

  let dynamicCeiling = MAX_REASONABLE_WATER_LEVEL;
  const thresholds = [warningLevel, dangerLevel].filter((v): v is number => v !== null && v > 0);
  if (thresholds.length > 0) {
    dynamicCeiling = Math.max(dynamicCeiling, Math.max(...thresholds) * 8);
  }

  return level > dynamicCeiling;
};

const calculateMargin = (level: number | null, warningLevel: number | null): number | null => {
  if (level === null || warningLevel === null) return null;
  return warningLevel - level;
};

const getDisplayStatus = (margin: number | null, status: string | null): RiverDisplayStatus => {
  if (status) {
    const normalized = status.toUpperCase();
    if (normalized === 'DANGER') return 'danger';
    if (normalized === 'WARNING') return 'warning';
    if (normalized.includes('BELOW')) return 'safe';
  }

  if (margin !== null && margin < 0) return 'danger';
  return 'safe';
};

const getTrendIcon = (trend: string | null) => {
  if (trend?.toUpperCase() === 'RISING') {
    return <TrendingUp size={12} strokeWidth={1.7} />;
  }
  return <TrendingDown size={12} strokeWidth={1.7} />;
};

const getTrendLabel = (trend: string | null) => {
  const normalized = trend?.toUpperCase();
  if (normalized === 'RISING') return 'RISING';
  if (normalized === 'FALLING') return 'FALLING';
  return 'STEADY';
};

const getStatusAccent = (status: RiverDisplayStatus) => {
  switch (status) {
    case 'danger':
      return { color: 'var(--status-critical)', bg: 'rgba(196,80,80,0.12)', border: 'rgba(196,80,80,0.3)' };
    case 'warning':
      return { color: 'var(--status-high)', bg: 'rgba(200,112,64,0.12)', border: 'rgba(200,112,64,0.3)' };
    default:
      return { color: '#4da3ff', bg: 'rgba(77,163,255,0.10)', border: 'rgba(77,163,255,0.28)' };
  }
};

const getSeverityChipStyle = (status: RiverDisplayStatus) => {
  const accent = getStatusAccent(status);
  return {
    fontSize: '9px',
    fontWeight: 600,
    padding: '2px 6px',
    textTransform: 'uppercase' as const,
    background: accent.bg,
    color: accent.color,
    border: `1px solid ${accent.border}`,
    fontFamily: 'var(--font-mono)',
  };
};

export const RiverMonitoringWidget = memo(function RiverMonitoringWidget() {
  const [selectedHours, setSelectedHours] = useState(72);
  const [selectedStatus, setSelectedStatus] = useState<RiverStatusFilter>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const { data: stations, isLoading, error, refetch } = useRiverStations();

  const processed = useMemo(() => {
    const rows: RiverViewItem[] = [];
    const query = searchQuery.trim().toLowerCase();

    for (const station of stations ?? []) {
      const readingAt = station.latest_reading?.reading_at ?? station.latest_observed_at ?? null;
      if (!isWithinWindow(readingAt, selectedHours)) continue;
      if (isSensorError(station.current_level, station.warning_level, station.danger_level)) continue;
      if (station.current_level === null) continue;

      const margin = calculateMargin(station.current_level, station.warning_level);
      const status = getDisplayStatus(margin, station.current_status);

      if (selectedStatus !== 'all' && status !== selectedStatus) continue;
      if (query) {
        const haystack = `${station.title} ${station.basin ?? ''}`.toLowerCase();
        if (!haystack.includes(query)) continue;
      }

      rows.push({
        id: station.id,
        title: station.title,
        basin: station.basin,
        current_level: station.current_level,
        warning_level: station.warning_level,
        danger_level: station.danger_level,
        current_status: station.current_status,
        current_trend: station.current_trend,
        reading_at: readingAt,
        margin,
        status,
      });
    }

    rows.sort((a, b) => {
      const weight = { danger: 0, warning: 1, safe: 2 };
      if (weight[a.status] !== weight[b.status]) {
        return weight[a.status] - weight[b.status];
      }
      const aMargin = a.margin ?? Number.POSITIVE_INFINITY;
      const bMargin = b.margin ?? Number.POSITIVE_INFINITY;
      return aMargin - bMargin;
    });

    const stats = rows.reduce(
      (acc, row) => {
        acc.total += 1;
        if (row.status === 'danger') acc.danger += 1;
        else if (row.status === 'warning') acc.warning += 1;
        else acc.safe += 1;
        return acc;
      },
      { total: 0, danger: 0, warning: 0, safe: 0 },
    );

    return { rows, stats };
  }, [searchQuery, selectedHours, selectedStatus, stations]);

  if (isLoading) {
    return (
      <Widget id="rivers" icon={<Waves size={14} />}>
        <WidgetSkeleton />
      </Widget>
    );
  }

  if (error) {
    return (
      <Widget id="rivers" icon={<Waves size={14} />}>
        <WidgetError message="Failed to load river data" onRetry={() => refetch()} />
      </Widget>
    );
  }

  const quickStats = [
    { value: processed.stats.danger, label: 'DANGER STATIONS', className: 'critical' },
    { value: processed.stats.warning, label: 'WARNING STATIONS', className: 'high' },
    { value: processed.stats.total, label: `${selectedHours}H ACTIVE STATIONS`, className: 'medium' },
  ];

  const filterCounts: Record<RiverStatusFilter, number> = {
    all: processed.stats.total,
    danger: processed.stats.danger,
    warning: processed.stats.warning,
    safe: processed.stats.safe,
  };

  return (
    <Widget
      id="rivers"
      icon={<Waves size={14} />}
      badge={processed.stats.total ? `${processed.stats.total} ACTIVE STATIONS` : undefined}
      badgeVariant={processed.stats.danger ? 'critical' : 'default'}
    >
      <div style={{
        display: 'flex',
        gap: '3px',
        padding: '6px 10px',
        borderBottom: '1px solid var(--border-subtle)',
        background: 'var(--bg-elevated)'
      }}>
        {TIME_OPTIONS.map((opt) => (
          <button
            key={opt.hours}
            onClick={() => setSelectedHours(opt.hours)}
            style={{
              flex: 1,
              padding: '3px 6px',
              fontSize: '9px',
              fontWeight: 600,
              fontFamily: 'var(--font-mono)',
              border: 'none',
              cursor: 'pointer',
              background: selectedHours === opt.hours ? 'var(--accent-primary)' : 'var(--bg-active)',
              color: selectedHours === opt.hours ? 'white' : 'var(--text-secondary)',
              transition: 'all 0.15s ease'
            }}
          >
            {opt.label}
          </button>
        ))}
      </div>

      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        padding: '6px 10px',
        borderBottom: '1px solid var(--border-subtle)',
        background: 'rgba(255,255,255,0.01)',
        overflowX: 'auto',
        overflowY: 'hidden',
        scrollbarWidth: 'thin',
      }}>
        <div style={{ display: 'flex', gap: '4px', flexShrink: 0 }}>
          {STATUS_FILTERS.map((opt) => (
            <button
              key={opt.key}
              onClick={() => setSelectedStatus(opt.key)}
              style={{
                ...COMPACT_SEGMENT_STYLE,
                background: selectedStatus === opt.key ? 'var(--bg-secondary)' : 'var(--bg-active)',
                color: selectedStatus === opt.key ? 'var(--text-primary)' : 'var(--text-secondary)',
              }}
            >
              {opt.label} {filterCounts[opt.key]}
            </button>
          ))}
        </div>

        <div style={{
          width: '1px',
          height: '16px',
          background: 'var(--border-subtle)',
          flexShrink: 0,
        }} />

        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '6px 10px',
          background: 'var(--bg-surface)',
          border: '1px solid var(--border-subtle)',
          minWidth: '260px',
          flex: 1,
        }}>
          <Search size={14} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
          <input
            type="text"
            placeholder="Search river or basin..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              flex: 1,
              background: 'transparent',
              border: 'none',
              outline: 'none',
              fontSize: '12px',
              color: 'var(--text-primary)',
              fontFamily: 'inherit'
            }}
          />
        </div>
      </div>

      <div style={{ display: 'flex', borderBottom: '1px solid var(--border-subtle)' }}>
        {quickStats.map((stat, i) => (
          <div key={stat.label} style={{
            flex: 1,
            padding: '10px 12px',
            textAlign: 'center',
            borderRight: i < quickStats.length - 1 ? '1px solid var(--border-subtle)' : 'none'
          }}>
            <div style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '18px',
              fontWeight: 600,
              color: `var(--status-${stat.className})`
            }}>{stat.value}</div>
            <div style={{
              fontSize: '9px',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              color: 'var(--text-muted)'
            }}>{stat.label}</div>
          </div>
        ))}
      </div>

      <div style={{
        display: 'flex',
        flexDirection: 'column',
        flex: '1 1 0',
        minHeight: 0,
        overflowY: 'auto',
        overflowX: 'hidden',
        WebkitOverflowScrolling: 'touch',
      }}>
        {processed.rows.length === 0 ? (
          <WidgetEmpty message="No active river stations in the selected window" />
        ) : (
          processed.rows.map((station) => {
            const accent = getStatusAccent(station.status);
            const trendLabel = getTrendLabel(station.current_trend);
            const trendColor = trendLabel === 'RISING'
              ? 'var(--status-high)'
              : trendLabel === 'FALLING'
                ? 'var(--status-low)'
                : 'var(--text-muted)';
            const levelLabel = station.current_level !== null ? `${station.current_level.toFixed(1)}m` : 'No level';
            const bufferLabel = station.margin !== null
              ? station.margin < 0
                ? `+${Math.abs(station.margin).toFixed(1)}m above warning`
                : `${station.margin.toFixed(1)}m buffer`
              : 'No warning threshold';

            return (
              <div key={station.id} style={{
                display: 'flex',
                gap: '12px',
                padding: '10px 12px',
                borderBottom: '1px solid var(--border-subtle)',
                cursor: 'default',
              }}>
                <div style={{
                  width: '36px',
                  height: '36px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  background: accent.bg,
                  border: `1px solid ${accent.border}`,
                  color: accent.color,
                  flexShrink: 0,
                }}>
                  <Droplets size={16} strokeWidth={1.6} />
                </div>

                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                    <span style={getSeverityChipStyle(station.status)}>
                      {station.status.toUpperCase()}
                    </span>
                    <span style={{
                      fontSize: '12px',
                      fontWeight: 500,
                      color: 'var(--text-primary)',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}>
                      {station.basin || 'River Basin'}
                    </span>
                  </div>

                  <div style={{
                    fontSize: '11px',
                    color: 'var(--text-primary)',
                    marginBottom: '4px',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap'
                  }}>
                    {station.title}
                  </div>

                  <div style={{
                    display: 'flex',
                    gap: '12px',
                    fontSize: '10px',
                    color: 'var(--text-disabled)',
                    flexWrap: 'wrap',
                  }}>
                    <span>{formatTimeAgo(station.reading_at)}</span>
                    <span>{levelLabel}</span>
                    <span>{bufferLabel}</span>
                  </div>
                </div>

                <div style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'flex-end',
                  justifyContent: 'center',
                  gap: '4px',
                  flexShrink: 0,
                  minWidth: '72px',
                }}>
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                    color: trendColor,
                    fontFamily: 'var(--font-mono)',
                    fontSize: '11px',
                    fontWeight: 600,
                  }}>
                    {getTrendIcon(station.current_trend)}
                    {trendLabel}
                  </div>
                  <div style={{
                    fontSize: '9px',
                    color: 'var(--text-muted)',
                    textTransform: 'uppercase',
                  }}>
                    {station.current_status?.replace(/_/g, ' ') || 'Below warning'}
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </Widget>
  );
});
