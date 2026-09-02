import { memo, useEffect, useMemo } from 'react';
import { Activity, RefreshCw } from 'lucide-react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';
import { dtgDay } from '../../flood/milspec';
import { Widget } from '../Widget';
import { Sparkline } from '../Sparkline';
import { useKPISnapshot, useHourlyTrends, useLatestBrief, kpiKeys } from '../../../api/hooks';
import { useSettingsStore } from '../../../store/slices/settingsSlice';
import { useAuthStore } from '../../../store/slices/authSlice';
import { WidgetSkeleton, WidgetError } from './shared';

// Threat level styling
const THREAT_LEVELS: Record<string, { border: string; indicator: string }> = {
  CRITICAL: { border: 'var(--status-critical)', indicator: 'var(--status-critical)' },
  ELEVATED: { border: 'var(--status-high)', indicator: 'var(--status-high)' },
  GUARDED: { border: 'var(--status-medium)', indicator: 'var(--status-medium)' },
  LOW: { border: 'var(--status-low)', indicator: 'var(--status-low)' },
};

export const KPIWidget = memo(function KPIWidget() {
  const queryClient = useQueryClient();

  // Get selected districts from settings store
  const { getSelectedDistricts } = useSettingsStore();
  const selectedDistricts = useMemo(() => getSelectedDistricts(), [getSelectedDistricts]);

  // Pass districts to the hooks - empty array means no filter (show all)
  const districts = selectedDistricts.length > 0 ? selectedDistricts : undefined;
  const { data: kpi, isLoading, error, refetch } = useKPISnapshot(24, districts);
  const { data: hourlyTrends } = useHourlyTrends(24, districts);
  const { data: latestBrief } = useLatestBrief();
  // The flood toll the desk publishes — same official series the Flood tab
  // runs on, read here so the News page carries the headline figures too.
  // /flood/official needs a bearer token, and the anonymous bootstrap is
  // deliberately deferred so it does not block first paint. Firing before it
  // lands 401s, and with a 10-minute refetch the toll cell would sit empty
  // until the next tick — so wait for the token.
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const { data: floodToll } = useQuery<{ latest: { as_of: string; authority: string; deaths: number | null; missing: number | null; rescued: number | null; source_url?: string | null } | null } | null>({
    queryKey: ['flood', 'official', 'kpi'],
    enabled: isAuthenticated,
    queryFn: async () => {
      try {
        const r = await apiClient.get('/flood/official');
        const latest = r.data?.official?.latest ?? null;
        return { latest };
      } catch {
        return null;
      }
    },
    staleTime: 5 * 60 * 1000,
    refetchInterval: 10 * 60 * 1000,
  });
  const toll = floodToll?.latest ?? null;

  const sparklineData = useMemo(() => {
    if (!hourlyTrends?.length) return [];
    return hourlyTrends.map((t) => t.count);
  }, [hourlyTrends]);

  // Extract top categories from hourly trends
  const topCategories = useMemo(() => {
    if (!hourlyTrends?.length) return [];
    const catCounts: Record<string, number> = {};
    hourlyTrends.forEach((h) => {
      Object.entries(h.category_breakdown || {}).forEach(([cat, count]) => {
        catCounts[cat] = (catCounts[cat] || 0) + count;
      });
    });
    return Object.entries(catCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([cat]) => cat);
  }, [hourlyTrends]);

  // WebSocket KPI updates
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      try {
        const message = JSON.parse(event.data);
        if (message.type === 'kpi_update' && message.data) {
          // Only update cache if we're viewing all districts (no filter)
          // Filtered views should refetch to get accurate data
          if (!districts) {
            queryClient.setQueryData(kpiKeys.snapshot(24, districts), message.data);
          }
        }
      } catch {
        // Ignore
      }
    };
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [queryClient, districts]);

  if (isLoading) {
    return (
      <Widget id="kpi" icon={<Activity size={14} />}>
        <WidgetSkeleton />
      </Widget>
    );
  }

  if (error || !kpi) {
    return (
      <Widget id="kpi" icon={<Activity size={14} />}>
        <WidgetError message="Failed to load KPIs" onRetry={() => refetch()} />
      </Widget>
    );
  }

  const threatStyle = THREAT_LEVELS[kpi.threat_level.level] || THREAT_LEVELS.LOW;
  const trendSymbol = kpi.events_today.trend === 'INCREASING' ? '▲' : kpi.events_today.trend === 'DECREASING' ? '▼' : '―';
  const velocitySymbol = kpi.trend_velocity.direction === 'UP' ? '▲' : kpi.trend_velocity.direction === 'DOWN' ? '▼' : '―';

  // Get alert categories for display
  const alertCategories = Object.entries(kpi.active_alerts.by_category || {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3);

  // Build key areas list — prefer analyst brief hotspots, fall back to KPI hotspots, then categories
  const briefHotspots = latestBrief?.hotspots?.map(
    (h: { district?: string; province?: string; description?: string }) => h.district || h.province || h.description || '',
  ).filter(Boolean).slice(0, 3);

  const keyAreas = briefHotspots && briefHotspots.length > 0
    ? briefHotspots
    : kpi.districts_affected.hotspots.length > 0
      ? kpi.districts_affected.hotspots.slice(0, 3)
      : topCategories.length > 0
        ? topCategories
        : ['Monitoring...'];

  // Casualties display
  const hasCasualties = kpi.casualties_24h.deaths > 0 || kpi.casualties_24h.injured > 0;

  // Determine if ingestion is healthy (last fetch within 60 minutes — scheduler polls every 10-30 min)
  const isIngestionHealthy = kpi.source_coverage.last_fetch_seconds_ago < 3600;

  return (
    <Widget
      id="kpi"
      icon={<Activity size={14} />}
      actions={
        <button
          onClick={() => refetch()}
          className="widget-action"
          title="Refresh KPIs"
          style={{ display: 'flex', alignItems: 'center', gap: 4 }}
        >
          <RefreshCw size={12} />
        </button>
      }
    >
      <div className="kpi-container">
        {/* Row 1: Primary Metrics */}
        <div className="kpi-row kpi-primary">
          {/* Threat Level */}
          <div className="kpi-cell kpi-threat" title="Overall security assessment based on active alerts, severity, and trends">
            <div className="kpi-label">THREAT LEVEL</div>
            <div className="kpi-value-lg" style={{ color: threatStyle.indicator }}>
              {kpi.threat_level.level}
            </div>
            <div className="kpi-sub">
              {kpi.threat_level.score.toFixed(0)}/100 · {latestBrief?.trend_vs_previous
                ? latestBrief.trend_vs_previous.replace('_', '-')
                : kpi.threat_level.trajectory.replace('_', '-')}
            </div>
          </div>

          {/* Active Alerts */}
          <div className="kpi-cell" title="Number of unresolved high-severity news events in the last 24 hours">
            <div className="kpi-label">ACTIVE ALERTS</div>
            <div className="kpi-value-lg">
              {kpi.active_alerts.count}
              {kpi.active_alerts.by_severity.critical > 0 && (
                <span className="kpi-crit">{kpi.active_alerts.by_severity.critical} CRIT</span>
              )}
            </div>
            <div className="kpi-sub">
              {alertCategories.length > 0
                ? alertCategories.map(([cat, count]) => `${cat}: ${count}`).join(' · ')
                : 'No active alerts'}
            </div>
          </div>

          {/* Events Volume */}
          <div className="kpi-cell" title="Total news stories and incidents tracked in the last 24 hours">
            <div className="kpi-label">EVENTS 24H</div>
            <div className="kpi-value-lg">
              {kpi.events_today.total}
              <span className={`kpi-trend-icon ${kpi.events_today.trend.toLowerCase()}`}>{trendSymbol}</span>
            </div>
            <div className="kpi-sub">
              {kpi.events_today.change_vs_yesterday > 0 ? '+' : ''}{kpi.events_today.change_vs_yesterday.toFixed(0)}% vs prev · {kpi.events_today.clustered} clustered
            </div>
          </div>

          {/* Sparkline */}
          <div className="kpi-cell kpi-sparkline-cell">
            <div className="kpi-label">24H ACTIVITY</div>
            <div className="kpi-sparkline-wrap">
              {sparklineData.length > 0 ? (
                <Sparkline
                  data={sparklineData}
                  trend={kpi.events_today.trend === 'INCREASING' ? 'up' : kpi.events_today.trend === 'DECREASING' ? 'down' : 'stable'}
                  height={32}
                  width={100}
                  strokeWidth={1.5}
                  showArea={true}
                />
              ) : (
                <span className="kpi-no-data">Collecting...</span>
              )}
            </div>
            <div className="kpi-sub">
              {kpi.trend_velocity.events_this_hour}/hr now
              <span className={`kpi-trend-icon ${kpi.trend_velocity.direction.toLowerCase()}`}>{velocitySymbol}</span>
              {kpi.trend_velocity.anomaly_detected && <span className="kpi-anomaly-tag">SPIKE</span>}
            </div>
          </div>
        </div>

        {/* Row 2: Intelligence Focus */}
        <div className="kpi-row kpi-secondary">
          {/* Key Areas to Watch, with the primary driver on the same cell so
              the second row keeps the first row's four columns. */}
          <div className="kpi-cell kpi-watchlist">
            <div className="kpi-label">KEY AREAS · PRIMARY DRIVER</div>
            <div className="kpi-areas" style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
              {keyAreas.map((area, i) => (
                <span key={i} className="kpi-area-tag">{area}</span>
              ))}
              <span className="kpi-value-md" style={{ marginLeft: 4 }}>{kpi.threat_level.primary_driver || '―'}</span>
            </div>
          </div>

          {/* Trishuli flood toll — the desk's official series, not a 24 h count */}
          {toll && (
            <div className="kpi-cell" title={`${toll.authority} · as of ${toll.as_of}`}>
              <div className="kpi-label">TRISHULI FLOOD · {toll.authority}</div>
              <div className="kpi-value-md kpi-casualties" style={{ display: 'flex', gap: 10, alignItems: 'baseline', flexWrap: 'wrap' }}>
                <span style={{ color: 'var(--status-critical)' }}>{(toll.deaths ?? 0).toLocaleString('en-IN')} dead</span>
                <span style={{ color: 'var(--status-high)' }}>{(toll.missing ?? 0).toLocaleString('en-IN')} missing</span>
                <span style={{ color: 'var(--status-low)' }}>{(toll.rescued ?? 0).toLocaleString('en-IN')} rescued</span>
              </div>
              <div className="kpi-sub">AS OF {dtgDay(toll.as_of)} · SEE FLOOD TAB</div>
            </div>
          )}

          {/* Casualties (if any) or Sources */}
          {hasCasualties ? (
            <div className="kpi-cell">
              <div className="kpi-label">CASUALTIES 24H</div>
              <div className="kpi-value-md kpi-casualties">
                {kpi.casualties_24h.deaths > 0 && <span>{kpi.casualties_24h.deaths} dead</span>}
                {kpi.casualties_24h.deaths > 0 && kpi.casualties_24h.injured > 0 && <span> · </span>}
                {kpi.casualties_24h.injured > 0 && <span>{kpi.casualties_24h.injured} injured</span>}
              </div>
            </div>
          ) : (
            <div className="kpi-cell">
              <div className="kpi-label">INGESTION</div>
              <div className="kpi-value-md" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span
                  className={`kpi-health-dot ${isIngestionHealthy ? 'healthy' : 'unhealthy'}`}
                  title={isIngestionHealthy ? 'Ingestion running normally' : 'Ingestion may be stalled'}
                />
                {kpi.source_coverage.active_sources}/{kpi.source_coverage.total_sources}
              </div>
              <div className="kpi-sub">
                {isIngestionHealthy ? 'ONLINE' : 'STALE'} · {Math.floor(kpi.source_coverage.last_fetch_seconds_ago / 60)}m ago
              </div>
            </div>
          )}

          {/* Confidence */}
          <div className="kpi-cell kpi-confidence" title="How confident the system is in its assessment — based on source coverage and data freshness">
            <div className="kpi-label">CONFIDENCE</div>
            <div className="kpi-confidence-bar">
              <div
                className="kpi-confidence-fill"
                style={{ width: `${kpi.threat_level.confidence * 100}%` }}
              />
            </div>
            <div className="kpi-sub">{(kpi.threat_level.confidence * 100).toFixed(0)}% · {kpi.data_freshness_seconds}s ago</div>
          </div>
        </div>
      </div>

      <style>{`
        .kpi-container {
          width: 100%;
          height: 100%;
          padding: 8px 10px;
          font-family: var(--font-mono, 'SF Mono', 'Monaco', 'Consolas', monospace);
          display: flex;
          flex-direction: column;
          gap: 6px;
        }

        .kpi-row {
          /* Both rows share one four-column grid so the hairlines between
             cells fall on the same x in each row. */
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          align-items: stretch;
          gap: 1px;
          background: var(--border-color);
        }

        .kpi-primary {
          flex: 1;
          min-height: 0;
        }

        .kpi-cell {
          flex: 1;
          background: var(--bg-primary);
          padding: 8px 10px;
          display: flex;
          flex-direction: column;
          min-width: 0;
        }

        .kpi-threat {
          flex: 0.9;
        }

        .kpi-label {
          font-size: 8px;
          color: var(--text-muted);
          letter-spacing: 0.5px;
          margin-bottom: 4px;
          white-space: nowrap;
        }

        .kpi-value-lg {
          font-size: 20px;
          font-weight: 600;
          color: var(--text-primary);
          line-height: 1.1;
          display: flex;
          align-items: baseline;
          gap: 6px;
          flex-wrap: wrap;
        }

        .kpi-value-md {
          font-size: 13px;
          font-weight: 500;
          color: var(--text-primary);
          line-height: 1.2;
        }

        .kpi-sub {
          font-size: 9px;
          color: var(--text-muted);
          margin-top: auto;
          padding-top: 4px;
          display: flex;
          align-items: center;
          gap: 4px;
          flex-wrap: wrap;
        }

        .kpi-crit {
          font-size: 9px;
          color: var(--status-critical);
          font-weight: 600;
          padding: 1px 4px;
          background: rgba(220, 38, 38, 0.15);
        }

        .kpi-trend-icon {
          font-size: 11px;
        }
        .kpi-trend-icon.increasing, .kpi-trend-icon.up { color: var(--status-critical); }
        .kpi-trend-icon.decreasing, .kpi-trend-icon.down { color: var(--status-low); }
        .kpi-trend-icon.stable { color: var(--text-muted); }

        .kpi-anomaly-tag {
          font-size: 8px;
          color: var(--status-high);
          font-weight: 600;
          padding: 0 3px;
          border: 1px solid var(--status-high);
          margin-left: 2px;
        }

        .kpi-sparkline-cell {
          flex: 1.2;
        }

        .kpi-sparkline-wrap {
          flex: 1;
          display: flex;
          align-items: center;
          justify-content: center;
          min-height: 32px;
        }

        .kpi-no-data {
          font-size: 10px;
          color: var(--text-muted);
          font-style: italic;
        }

        .kpi-secondary {
          flex: 0 0 auto;
        }

        .kpi-watchlist {
          flex: 1.5;
        }

        .kpi-areas {
          display: flex;
          flex-wrap: wrap;
          gap: 4px;
          flex: 1;
          align-items: flex-start;
        }

        .kpi-area-tag {
          font-size: 10px;
          font-weight: 500;
          color: var(--text-primary);
          background: var(--bg-secondary);
          padding: 2px 6px;
          border: 1px solid var(--border-color);
        }

        .kpi-casualties {
          color: var(--status-critical);
        }

        .kpi-health-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          flex-shrink: 0;
        }

        .kpi-health-dot.healthy {
          background: var(--status-low);
          box-shadow: 0 0 6px var(--status-low);
        }

        .kpi-health-dot.unhealthy {
          background: var(--status-critical);
          box-shadow: 0 0 6px var(--status-critical);
          animation: pulse 1.5s infinite;
        }

        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }

        .kpi-confidence {
          flex: 0.8;
        }

        .kpi-confidence-bar {
          height: 4px;
          background: var(--bg-active);
          margin: 6px 0;
          overflow: hidden;
        }

        .kpi-confidence-fill {
          height: 100%;
          background: var(--accent-primary);
          transition: width 0.3s ease;
        }
      `}</style>
    </Widget>
  );
});
