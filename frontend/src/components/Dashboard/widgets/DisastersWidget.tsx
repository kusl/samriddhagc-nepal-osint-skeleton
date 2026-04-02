import { memo, useMemo, useState } from 'react';
import { AlertTriangle, Flame, Droplets, Mountain, Zap, Activity, Wind, Snowflake, Bug, AlertCircle } from 'lucide-react';
import { Widget } from '../Widget';
import { useDisasterStats, useDisasterAlerts } from '../../../api/hooks';
import { WidgetSkeleton, WidgetError, WidgetEmpty, formatTimeAgo } from './shared';
import { formatHazardType } from '../../../api/disasterAlerts';

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

// Professional hazard icons using Lucide
const getHazardLucideIcon = (hazardType: string | null) => {
  const iconProps = { size: 16, strokeWidth: 1.5 };
  switch (hazardType) {
    case 'fire': return <Flame {...iconProps} />;
    case 'forest_fire': return <Flame {...iconProps} />;
    case 'flood': return <Droplets {...iconProps} />;
    case 'heavy_rainfall': return <Droplets {...iconProps} />;
    case 'landslide': return <Mountain {...iconProps} />;
    case 'earthquake': return <Activity {...iconProps} />;
    case 'lightning': return <Zap {...iconProps} />;
    case 'windstorm': return <Wind {...iconProps} />;
    case 'wind_storm': return <Wind {...iconProps} />;
    case 'cold_wave': return <Snowflake {...iconProps} />;
    case 'avalanche': return <Mountain {...iconProps} />;
    case 'epidemic': return <Bug {...iconProps} />;
    case 'pollution': return <Wind {...iconProps} />;
    default: return <AlertCircle {...iconProps} />;
  }
};

const TIME_OPTIONS = [
  { label: '1H', hours: 1 },
  { label: '24H', hours: 24 },
  { label: '48H', hours: 48 },
  { label: '72H', hours: 72 },
];

const HAZARD_FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'forest_fire', label: 'Fire' },
  { key: 'flood', label: 'Flood' },
  { key: 'heavy_rainfall', label: 'Rain' },
  { key: 'pollution', label: 'Air' },
];

const ENTRY_FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'alert', label: 'Alerts' },
  { key: 'incident', label: 'Incidents' },
];

const getHazardAccent = (hazardType: string | null) => {
  switch (hazardType) {
    case 'fire':
    case 'forest_fire':
      return { color: '#ff5a36', bg: 'rgba(255,90,54,0.12)', border: 'rgba(255,90,54,0.35)' };
    case 'flood':
      return { color: '#2f8fff', bg: 'rgba(47,143,255,0.12)', border: 'rgba(47,143,255,0.35)' };
    case 'heavy_rainfall':
      return { color: '#48b4ff', bg: 'rgba(72,180,255,0.12)', border: 'rgba(72,180,255,0.35)' };
    case 'pollution':
      return { color: '#b7c0cc', bg: 'rgba(183,192,204,0.12)', border: 'rgba(183,192,204,0.35)' };
    case 'landslide':
    case 'avalanche':
      return { color: '#c49a6c', bg: 'rgba(196,154,108,0.12)', border: 'rgba(196,154,108,0.35)' };
    case 'earthquake':
      return { color: '#f6c343', bg: 'rgba(246,195,67,0.12)', border: 'rgba(246,195,67,0.35)' };
    case 'lightning':
      return { color: '#ffe066', bg: 'rgba(255,224,102,0.12)', border: 'rgba(255,224,102,0.35)' };
    case 'windstorm':
    case 'wind_storm':
      return { color: '#78dce8', bg: 'rgba(120,220,232,0.12)', border: 'rgba(120,220,232,0.35)' };
    default:
      return { color: 'var(--text-secondary)', bg: 'var(--bg-elevated)', border: 'var(--border-subtle)' };
  }
};

export const DisastersWidget = memo(function DisastersWidget() {
  const [selectedHours, setSelectedHours] = useState(72);
  const [selectedHazard, setSelectedHazard] = useState('all');
  const [selectedEntryType, setSelectedEntryType] = useState<'all' | 'alert' | 'incident'>('all');
  const { data: stats, isLoading: statsLoading, error: statsError, refetch } = useDisasterStats(selectedHours);
  const { data: alerts, isLoading: alertsLoading, error: alertsError } = useDisasterAlerts(200, selectedHours);
  const filteredAlerts = useMemo(() => {
    return (alerts ?? []).filter((alert) => {
      if (selectedHazard !== 'all' && alert.hazard_type !== selectedHazard) {
        return false;
      }
      if (selectedEntryType !== 'all' && alert.entry_type !== selectedEntryType) {
        return false;
      }
      return true;
    });
  }, [alerts, selectedEntryType, selectedHazard]);

  const isLoading = statsLoading || alertsLoading;
  const error = statsError || alertsError;

  if (isLoading) {
    return (
      <Widget id="disasters" icon={<AlertTriangle size={14} />}>
        <WidgetSkeleton />
      </Widget>
    );
  }

  if (error) {
    return (
      <Widget id="disasters" icon={<AlertTriangle size={14} />}>
        <WidgetError message="Failed to load disaster data" onRetry={() => refetch()} />
      </Widget>
    );
  }

  const quickStats = [
    { value: stats?.danger_alerts ?? 0, label: 'CRITICAL', className: 'critical' },
    { value: stats?.active_alerts ?? 0, label: 'ACTIVE ALERTS', className: 'high' },
    { value: stats?.incidents_in_window ?? 0, label: `${selectedHours}H INCIDENTS`, className: 'medium' },
  ];

  const getSeverityStyle = (severity: string) => {
    const styles: Record<string, { bg: string; color: string }> = {
      danger: { bg: 'var(--status-critical)', color: 'white' },
      warning: { bg: 'var(--status-high)', color: 'black' },
      watch: { bg: 'var(--status-medium)', color: 'black' },
      normal: { bg: 'var(--bg-active)', color: 'var(--text-secondary)' },
    };
    return styles[severity] || styles.normal;
  };

  return (
    <Widget
      id="disasters"
      icon={<AlertTriangle size={14} />}
      badge={stats?.active_alerts ? `${stats.active_alerts} ACTIVE ALERTS` : undefined}
      badgeVariant={stats?.danger_alerts ? 'critical' : 'default'}
    >
      {/* Time Filter */}
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
          {ENTRY_FILTERS.map((opt) => (
            <button
              key={opt.key}
              onClick={() => setSelectedEntryType(opt.key as 'all' | 'alert' | 'incident')}
              style={{
                ...COMPACT_SEGMENT_STYLE,
                background: selectedEntryType === opt.key ? 'var(--bg-secondary)' : 'var(--bg-active)',
                color: selectedEntryType === opt.key ? 'var(--text-primary)' : 'var(--text-secondary)',
              }}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <div style={{
          width: '1px',
          height: '16px',
          background: 'var(--border-subtle)',
          flexShrink: 0,
        }} />
        <div style={{ display: 'flex', gap: '4px', flexShrink: 0 }}>
          {HAZARD_FILTERS.map((opt) => (
            <button
              key={opt.key}
              onClick={() => setSelectedHazard(opt.key)}
              style={{
                ...COMPACT_SEGMENT_STYLE,
                background: selectedHazard === opt.key ? 'var(--bg-secondary)' : 'var(--bg-active)',
                color: selectedHazard === opt.key ? 'var(--text-primary)' : 'var(--text-secondary)',
              }}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Stats Row */}
      <div style={{ display: 'flex', borderBottom: '1px solid var(--border-subtle)' }}>
        {quickStats.map((stat, i) => (
          <div key={i} style={{
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

      {/* Alerts List */}
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        flex: '1 1 0',
        minHeight: 0,
        overflowY: 'auto',
        overflowX: 'hidden',
        WebkitOverflowScrolling: 'touch',
      }}>
        {filteredAlerts.length === 0 ? (
          <WidgetEmpty message="No matching disaster alerts or incidents" />
        ) : (
          filteredAlerts.map((alert) => {
            const severityStyle = getSeverityStyle(alert.severity);
            const hazardAccent = getHazardAccent(alert.hazard_type);
            return (
              <div key={alert.id} style={{
                display: 'flex',
                gap: '12px',
                padding: '10px 12px',
                borderBottom: '1px solid var(--border-subtle)',
                cursor: 'pointer'
              }}>
                <div style={{
                  width: '36px',
                  height: '36px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  background: hazardAccent.bg,
                  border: `1px solid ${hazardAccent.border}`,
                  color: hazardAccent.color,
                  flexShrink: 0
                }}>
                  {getHazardLucideIcon(alert.hazard_type)}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                    <span style={{
                      fontSize: '9px',
                      fontWeight: 600,
                      padding: '2px 6px',
                      textTransform: 'uppercase',
                      background: severityStyle.bg,
                      color: severityStyle.color
                    }}>
                      {alert.severity.toUpperCase()}
                    </span>
                    <span style={{
                      fontSize: '9px',
                      fontWeight: 600,
                      padding: '2px 6px',
                      textTransform: 'uppercase',
                      background: alert.entry_type === 'alert' ? 'rgba(47,143,255,0.12)' : 'var(--bg-active)',
                      color: alert.entry_type === 'alert' ? '#78b8ff' : 'var(--text-secondary)',
                      border: alert.entry_type === 'alert'
                        ? '1px solid rgba(47,143,255,0.35)'
                        : '1px solid var(--border-subtle)'
                    }}>
                      {alert.entry_type === 'alert' ? 'ALERT' : 'INCIDENT'}
                    </span>
                    <span style={{ fontSize: '12px', fontWeight: 500, color: 'var(--text-primary)' }}>
                      {alert.district || formatHazardType(alert.hazard_type)}
                    </span>
                  </div>
                  <div style={{
                    fontSize: '11px',
                    color: 'var(--text-muted)',
                    marginBottom: '4px',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap'
                  }}>
                    {alert.title}
                  </div>
                  <div style={{ display: 'flex', gap: '12px', fontSize: '10px', color: 'var(--text-disabled)' }}>
                    <span>{formatTimeAgo(alert.started_at || alert.created_at)}</span>
                    {alert.entry_type === 'alert' && alert.is_active ? <span>Active</span> : null}
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
