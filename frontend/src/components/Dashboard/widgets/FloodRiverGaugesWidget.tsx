import { memo, useMemo } from 'react';
import { Radio, RefreshCw } from 'lucide-react';
import { Widget } from '../Widget';
import { useFloodRivers } from '../../../api/hooks/useFlood';
import type { RiverStation } from '../../../api/flood';
import { WidgetSkeleton, WidgetError, WidgetEmpty } from './shared';
import {
  Body,
  MS,
  Note,
  Scroll,
  Section,
  SourceLine,
  Stat,
  StatRow,
  Status,
  TableHead,
  TableRow,
  PROSE,
  dtgZ,
  fmt,
  type Tone,
} from '../../flood/milspec';

const WIDGET_ID = 'flood-river-gauges';
const TITLE = 'HYDROLOGY · GAUGE NET';

// One column template for the head and every row, so the figures line up.
const W = {
  station: '26%',
  basin: '12%',
  status: '10%',
  level: '9%',
  headroom: '14%',
  trend: '10%',
  read: '10%',
} as const;

const HEAD = [
  { label: 'STATION', width: W.station },
  { label: 'BASIN', width: W.basin },
  { label: 'STATUS', width: W.status },
  { label: 'LEVEL', width: W.level, align: 'right' as const },
  { label: 'HEADROOM', width: W.headroom, align: 'right' as const },
  { label: 'TREND', width: W.trend },
  { label: 'LAST READ', width: W.read, align: 'right' as const },
];

/** Colour law: danger critical, warning medium, normal low, offline muted, fault high. */
const ALERT_TONE: Record<string, Tone> = {
  danger: 'critical',
  warning: 'medium',
  normal: 'low',
  offline: 'muted',
  sensor_fault: 'high',
};

/** Rising water is the bad direction here, so it borrows the sensor-fault tone. */
const TREND_TONE: Record<RiverStation['trend'], Tone> = {
  RISING: 'high',
  FALLING: 'low',
  STEADY: 'muted',
  UNKNOWN: 'muted',
};

function GaugeRow({ station }: { station: RiverStation }) {
  const alertTone = ALERT_TONE[station.alert] ?? 'sub';
  const alerting = station.alert === 'danger' || station.alert === 'warning';
  const head = station.headroom_m;

  return (
    <TableRow
      // A reading past the 6h freshness line still describes the past, not now.
      dim={station.stale}
      cells={[
        { node: station.name, width: W.station },
        { node: station.basin ?? 'basin unrecorded', width: W.basin },
        {
          node: <Status tone={alertTone}>{station.alert.replace('_', ' ').toUpperCase()}</Status>,
          width: W.status,
        },
        {
          node: `${station.water_level.toFixed(2)} m`,
          width: W.level,
          align: 'right',
          tone: alerting ? alertTone : 'text',
        },
        {
          node:
            head === null
              ? 'NO DANGER LINE'
              : head < 0
                ? `${Math.abs(head).toFixed(2)} m OVER`
                : `${head.toFixed(2)} m TO DANGER`,
          width: W.headroom,
          align: 'right',
          tone: head === null ? 'muted' : head < 0 ? 'critical' : 'sub',
        },
        {
          node: station.trend === 'UNKNOWN' ? '—' : station.trend,
          width: W.trend,
          tone: TREND_TONE[station.trend] ?? 'muted',
        },
        { node: dtgZ(station.reading_at), width: W.read, align: 'right', tone: 'muted' },
      ]}
    />
  );
}

export const FloodRiverGaugesWidget = memo(function FloodRiverGaugesWidget() {
  const { data, isLoading, error, refetch } = useFloodRivers(false);

  const view = useMemo(() => {
    const stations = data?.stations ?? [];

    // Freshness is decided upstream and decided first: a gauge that has gone
    // silent or is returning impossible values is an instrument state, never a
    // flood alarm, so it can never reach the danger/warning counts below.
    const alerting: RiverStation[] = [];
    const reporting: RiverStation[] = [];
    let offline = 0;
    let sensorFault = 0;
    let stale = 0;
    let newest: string | null = null;

    for (const s of stations) {
      if (s.reading_at && (newest === null || s.reading_at > newest)) newest = s.reading_at;
      if (s.alert === 'offline') { offline += 1; continue; }
      if (s.alert === 'sensor_fault') { sensorFault += 1; continue; }
      if (s.stale) stale += 1;
      if (s.alert === 'danger' || s.alert === 'warning') alerting.push(s);
      else reporting.push(s);
    }

    const byHeadroom = (a: RiverStation, b: RiverStation) =>
      (a.headroom_m ?? Number.POSITIVE_INFINITY) - (b.headroom_m ?? Number.POSITIVE_INFINITY);

    const severity = { danger: 0, warning: 1 } as Record<string, number>;
    alerting.sort((a, b) => (severity[a.alert] - severity[b.alert]) || byHeadroom(a, b));

    // Gauges with no published danger line cannot be ranked against one, so
    // they sit below the ranked list rather than being given an implied zero.
    const ranked = reporting.filter((s) => s.headroom_m !== null).sort(byHeadroom);
    const unranked = reporting.filter((s) => s.headroom_m === null);

    return {
      alerting,
      ranked,
      unranked,
      newest,
      total: stations.length,
      reporting: alerting.length + reporting.length,
      danger: alerting.filter((s) => s.alert === 'danger').length,
      warning: alerting.filter((s) => s.alert === 'warning').length,
      offline,
      sensorFault,
      stale,
    };
  }, [data]);

  if (isLoading) {
    return (
      <Widget id={WIDGET_ID} title={TITLE} icon={<Radio size={14} />}>
        <WidgetSkeleton />
      </Widget>
    );
  }

  if (error || !data) {
    return (
      <Widget id={WIDGET_ID} title={TITLE} icon={<Radio size={14} />}>
        <WidgetError message="Failed to load river gauges" onRetry={() => refetch()} />
      </Widget>
    );
  }

  if (view.total === 0) {
    return (
      <Widget id={WIDGET_ID} title={TITLE} icon={<Radio size={14} />}>
        <WidgetEmpty message="No gauges returned by the hydrology feed" />
      </Widget>
    );
  }

  const badge = view.danger > 0
    ? `${view.danger} DANGER`
    : view.warning > 0
      ? `${view.warning} WARNING`
      : `${view.reporting} REPORTING`;

  return (
    <Widget
      id={WIDGET_ID}
      title={TITLE}
      icon={<Radio size={14} />}
      badge={badge}
      badgeVariant={view.danger > 0 ? 'critical' : view.warning > 0 ? 'high' : 'default'}
      actions={
        <button onClick={() => refetch()} className="widget-action" title="Refresh gauges">
          <RefreshCw size={12} />
        </button>
      }
    >
      <Body>
        {/* A zero never glows: an empty danger column is good news, not an alarm. */}
        <StatRow columns={5}>
          <Stat
            label="REPORTING"
            value={fmt(view.reporting)}
            sub={`of ${fmt(view.total)} stations`}
            size={20}
          />
          <Stat label="WARNING" value={fmt(view.warning)} tone={view.warning > 0 ? 'medium' : 'muted'} size={20} />
          <Stat label="DANGER" value={fmt(view.danger)} tone={view.danger > 0 ? 'critical' : 'muted'} size={20} />
          <Stat label="OFFLINE" value={fmt(view.offline)} tone="muted" size={20} />
          <Stat
            label="SENSOR FAULT"
            value={fmt(view.sensorFault)}
            tone={view.sensorFault > 0 ? 'high' : 'muted'}
            size={20}
          />
        </StatRow>

        <TableHead cols={HEAD} />

        <Scroll>
          {view.alerting.length === 0 ? (
            <div style={{ ...PROSE, color: MS.low, padding: '4px 0' }}>
              No reporting gauge is above its warning line.
            </div>
          ) : (
            view.alerting.map((s) => <GaugeRow key={s.station_id} station={s} />)
          )}

          {view.ranked.length > 0 && (
            <>
              <Section title="NEAREST TO DANGER" meta={`${view.ranked.length} GAUGES`} />
              {view.ranked.map((s) => <GaugeRow key={s.station_id} station={s} />)}
            </>
          )}

          {view.unranked.length > 0 && (
            <>
              <Section title="NO DANGER LINE PUBLISHED" meta={`${view.unranked.length} GAUGES`} />
              {view.unranked.map((s) => <GaugeRow key={s.station_id} station={s} />)}
            </>
          )}
        </Scroll>

        {(view.offline > 0 || view.sensorFault > 0 || view.stale > 0) && (
          <Note>
            {view.offline} silent and {view.sensorFault} faulty gauges are excluded from
            the counts above: the feed serves a dead gauge's last reading indefinitely,
            so a station silent for years would otherwise still read as flooding.
            {view.stale > 0 && ` ${view.stale} reporting gauges last read over 6 hours ago and are dimmed.`}
          </Note>
        )}

        <SourceLine
          source="DHM / BIPAD river telemetry"
          asOf={view.newest ? dtgZ(view.newest) : null}
        />
      </Body>
    </Widget>
  );
});
