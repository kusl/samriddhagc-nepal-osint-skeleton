import { memo, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, ExternalLink, RefreshCw } from 'lucide-react';

import { Widget } from '../Widget';
import apiClient from '../../../api/client';
import { floodKeys, useOfficialSituation } from '../../../api/hooks/useFlood';
import { WidgetSkeleton, WidgetError, WidgetEmpty } from './shared';
import {
  Body,
  ControlStrip,
  FIGURE,
  Grade,
  LABEL_XS,
  MS,
  Note,
  Scroll,
  Section,
  SourceLine,
  Stat,
  StatRow,
  TableHead,
  TableRow,
  dtgDay,
  dtgNow,
  dtgZ,
  fmt,
  fmtDelta,
  fmtMoney,
  gradeFor,
  isNum,
  type Tone,
} from '../../flood/milspec';

type BulletinPoint = { as_of: string; deaths: number | null; missing: number | null };

/**
 * Live upstream feeds, polled by the backend sync and served as the last good
 * payload per feed. Every payload is upstream JSON the desk does not own, so it
 * is typed `unknown` and read defensively: a feed that changes shape, fails, or
 * has not run yet must leave the widget exactly as it renders without it.
 */
interface FloodLiveFeed {
  ok: boolean;
  fetched_at: string | null;
  payload: unknown;
}

interface FloodLive {
  event_key: string;
  synced_at: string | null;
  feeds: Partial<Record<string, FloodLiveFeed | null>>;
}

/**
 * Title of the standing NDRRMA advisory, if one is published. The upstream feed
 * returns `{results: [...]}`; a bare array is accepted too, because the desk does
 * not control that shape.
 */
function advisoryTitleOf(live: FloodLive | undefined): string | null {
  const payload = live?.feeds?.ndrrma_advisory?.payload;
  if (!payload || typeof payload !== 'object') return null;
  const list = Array.isArray(payload) ? payload : (payload as { results?: unknown }).results;
  if (!Array.isArray(list) || list.length === 0) return null;
  const title = (list[0] as { title?: unknown } | null)?.title;
  return typeof title === 'string' && title.trim() ? title.trim() : null;
}

/** Settlements still unreached, from the NDRRMA rescue register. */
function outOfReachOf(live: FloodLive | undefined): number | null {
  const payload = live?.feeds?.ndrrma_rescue?.payload;
  if (!payload || typeof payload !== 'object') return null;
  const value = (payload as { out_of_reach?: unknown }).out_of_reach;
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/**
 * Change in one field between the last two bulletins that published it.
 * Pure subtraction of adjacent published figures — never an interpolation.
 */
function bulletinDelta(points: BulletinPoint[], field: 'deaths' | 'missing') {
  const usable = points.filter((p) => isNum(p[field]));
  if (usable.length < 2) return null;
  const last = usable[usable.length - 1][field] as number;
  const prev = usable[usable.length - 2];
  return { change: last - (prev[field] as number), since: prev.as_of };
}

/** Delta chip text for a <Stat>: "+84 SINCE 31 AUG 26". */
const deltaChip = (d: { change: number; since: string } | null): string | undefined =>
  d ? `${fmtDelta(d.change)} SINCE ${dtgDay(d.since)}` : undefined;

/** A rising toll is severity; a falling one is a revision, not relief. */
const deltaTone = (d: { change: number } | null): Tone => (d && d.change > 0 ? 'high' : 'muted');

/**
 * Local primitive: an inline source link inside a table row. Milspec covers the
 * footer link (<SourceLine>) but has no in-row variant; this reuses its exact
 * grammar — LABEL_XS, info colour, 9px external-link glyph.
 */
function SourceRef({ url }: { url: string | null }) {
  if (!url) return <span style={{ color: MS.disabled }}>—</span>;
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer noopener"
      style={{ ...LABEL_XS, color: MS.info, textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 3 }}
    >
      SOURCE <ExternalLink size={9} />
    </a>
  );
}

const CHART_H = 40;
/** Headroom inside the plot for the delta chips, which hang above their step. */
const CHART_TOP = 15;
const CHART_BOT = 3;

/**
 * Death-toll trajectory as a stepped line: each point is a bulletin, and the toll
 * holds at the published figure until the next one, so interpolating between
 * revisions would draw deaths on days nobody counted them.
 *
 * Fixed height rather than flex-grow: five bulletins carry no more information at
 * 200px than at 40px, and the hero's vertical budget belongs to the figures.
 * The dots and delta chips are HTML rather than SVG because the plot is stretched
 * non-uniformly (preserveAspectRatio="none"), which would turn circles into
 * ellipses and text into slabs.
 */
function TollTrajectory({ points }: { points: BulletinPoint[] }) {
  const geometry = useMemo(() => {
    const usable = points.filter((p) => p.deaths !== null);
    if (usable.length < 2) return null;

    const W = 1000;
    const values = usable.map((p) => p.deaths as number);
    const max = Math.max(...values);
    const min = Math.min(...values);
    // Domain floors at the first published toll, not zero: a zero baseline spends
    // a fifth of the plot on a range no bulletin ever reported. Every figure is
    // still printed beneath the axis, so nothing is hidden by it.
    const span = max - min || 1;
    const lo = min - span * 0.1;
    const plot = CHART_H - CHART_TOP - CHART_BOT;

    const x = (i: number) => (i / (usable.length - 1)) * W;
    const y = (v: number) => CHART_TOP + (1 - (v - lo) / (max - lo)) * plot;

    let line = `M ${x(0).toFixed(1)} ${y(values[0]).toFixed(1)}`;
    for (let i = 1; i < usable.length; i += 1) {
      line += ` L ${x(i).toFixed(1)} ${y(values[i - 1]).toFixed(1)} L ${x(i).toFixed(1)} ${y(values[i]).toFixed(1)}`;
    }

    const dots = usable.map((p, i) => ({ left: (i / (usable.length - 1)) * 100, top: y(p.deaths as number) }));

    // The climb is the story — each step is a day downstream districts were reached —
    // so the deltas are annotated.
    const deltas = usable.slice(1).map((p, i) => {
      const change = (p.deaths as number) - (usable[i].deaths as number);
      return {
        key: p.as_of,
        change,
        left: ((i + 0.5) / (usable.length - 1)) * 100,
        top: Math.max(0, y(p.deaths as number) - 4),
      };
    });

    return { W, line, dots, deltas, points: usable };
  }, [points]);

  if (!geometry) return null;

  const last = geometry.points.length - 1;

  return (
    <div style={{ flex: '0 0 auto' }}>
      <div style={{ position: 'relative', height: CHART_H }}>
        <svg
          viewBox={`0 0 ${geometry.W} ${CHART_H}`}
          preserveAspectRatio="none"
          width="100%"
          height={CHART_H}
          style={{ display: 'block' }}
          aria-hidden
        >
          <path d={geometry.line} fill="none" stroke={MS.critical} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
        </svg>

        {geometry.dots.map((d, i) => (
          <span
            key={i}
            style={{
              position: 'absolute',
              left: `${d.left}%`,
              top: d.top,
              width: 4,
              height: 4,
              background: MS.critical,
              transform: 'translate(-50%, -50%)',
            }}
          />
        ))}

        {geometry.deltas
          .filter((d) => d.change !== 0)
          .map((d) => (
            <span
              key={d.key}
              style={{
                ...FIGURE,
                position: 'absolute',
                left: `${d.left}%`,
                top: d.top,
                transform: 'translate(-50%, -100%)',
                fontSize: 10,
                color: d.change > 0 ? MS.high : MS.muted,
                whiteSpace: 'nowrap',
              }}
            >
              {fmtDelta(d.change)}
            </span>
          ))}
      </div>

      <div style={{ position: 'relative', height: 28, marginTop: 3 }}>
        {geometry.points.map((p, i) => (
          <div
            key={p.as_of}
            style={{
              position: 'absolute',
              left: `${(i / last) * 100}%`,
              transform: i === 0 ? 'none' : i === last ? 'translateX(-100%)' : 'translateX(-50%)',
              textAlign: i === 0 ? 'left' : i === last ? 'right' : 'center',
              whiteSpace: 'nowrap',
            }}
          >
            <div style={{ ...FIGURE, fontSize: 12, color: MS.critical }}>{fmt(p.deaths)}</div>
            <div style={{ ...LABEL_XS, marginTop: 2 }}>
              {dtgDay(p.as_of)} · {fmt(p.missing)} MISSING
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export const FloodSituationCommandWidget = memo(function FloodSituationCommandWidget() {
  const { data, isLoading, error, refetch } = useOfficialSituation();
  // Live feeds are an enrichment, never a dependency: this query's error and
  // loading states are deliberately unread, so the widget renders its published
  // figures whether or not the sync has run.
  const { data: live } = useQuery<FloodLive>({
    queryKey: [...floodKeys.all, 'live'] as const,
    queryFn: async () => (await apiClient.get('/flood/live')).data,
    staleTime: 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
    retry: 1,
  });

  if (isLoading) {
    return (
      <Widget id="flood-situation-command" icon={<AlertTriangle size={14} />}>
        <WidgetSkeleton />
      </Widget>
    );
  }

  if (error || !data) {
    return (
      <Widget id="flood-situation-command" icon={<AlertTriangle size={14} />}>
        <WidgetError message="Failed to load the official situation" onRetry={() => refetch()} />
      </Widget>
    );
  }

  const { event, official, bipad_cross_check: bipad } = data;
  const toll = official.latest;

  if (!official.available || !toll) {
    return (
      <Widget id="flood-situation-command" icon={<AlertTriangle size={14} />}>
        <WidgetEmpty message="No official toll published for this event yet" />
      </Widget>
    );
  }

  const authority = toll.authority.toUpperCase();
  const deadDelta = bulletinDelta(official.trajectory, 'deaths');
  const missingDelta = bulletinDelta(official.trajectory, 'missing');
  const conflictNote = official.conflicting_reports.find((r) => r.note)?.note ?? null;
  const advisory = advisoryTitleOf(live);
  const outOfReach = outOfReachOf(live);
  const syncStamp = live ? ` · FEEDS SYNCED ${live.synced_at ? dtgZ(live.synced_at) : '—'}` : '';

  return (
    <Widget
      id="flood-situation-command"
      icon={<AlertTriangle size={14} />}
      badge={event.status.toUpperCase()}
      badgeVariant="critical"
      actions={
        <button onClick={() => refetch()} className="widget-action" title="Refresh official figures">
          <RefreshCw size={12} />
        </button>
      }
    >
      <Body>
        <ControlStrip
          left={`OPEN SOURCE INTELLIGENCE // ${event.name.toUpperCase()} // PUBLISHED SOURCES ONLY // DESK ASSESSMENT — NOT AN OFFICIAL PRODUCT`}
          right={`PICTURE AS OF ${dtgNow()} · LATEST BULLETIN ${dtgDay(toll.as_of)}${syncStamp}`}
        />

        <Scroll>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap', marginBottom: 7 }}>
            <span style={{ fontFamily: MS.mono, fontSize: 13, fontWeight: 700, color: MS.text, letterSpacing: '-0.01em' }}>
              {event.name}
            </span>
            <span style={LABEL_XS}>
              SINCE {dtgDay(event.started_on)} · {event.rivers.join(' / ')} · {event.districts.length} DISTRICTS · STATUS{' '}
              {event.status.toUpperCase()}
              {outOfReach !== null && <> · {fmt(outOfReach)} STILL OUT OF REACH</>}
            </span>
          </div>

          {/* The advisory is carried verbatim in the authority's own Nepali — translating
              an instruction to the public would make the desk its author. */}
          {advisory && (
            <Note>
              <span
                title={`NDRRMA ADVISORY · ${advisory}`}
                style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
              >
                NDRRMA ADVISORY · {advisory}
              </span>
            </Note>
          )}

          {/* One attribution for the whole band, in the source footer: the authority and
              as-of date are identical across every cell. */}
          <StatRow columns={6}>
            <Stat
              label="Confirmed dead"
              value={fmt(toll.deaths)}
              tone="critical"
              delta={deltaChip(deadDelta)}
              deltaTone={deltaTone(deadDelta)}
            />
            <Stat
              label="Missing"
              value={fmt(toll.missing)}
              tone="high"
              delta={deltaChip(missingDelta)}
              deltaTone={deltaTone(missingDelta)}
            />
            <Stat label="Rescued" value={fmt(toll.rescued)} tone="low" />
            <Stat label="Hospitalised" value={fmt(toll.injured)} tone="medium" />
            <Stat label="Foreign nationals missing" value={fmt(toll.foreign_nationals_missing)} tone="text" />
            <Stat
              label="Preliminary damage"
              value={fmtMoney(toll.damage_npr, 'NPR')}
              tone="high"
              sub={isNum(toll.damage_usd) ? fmtMoney(toll.damage_usd, 'USD') : undefined}
            />
          </StatRow>

          <Section n={1} title="TOLL TRAJECTORY" meta={`${authority} BULLETINS`} />
          <TollTrajectory points={official.trajectory} />

          {/* Authorities disagreeing is information; the desk shows both and reconciles neither. */}
          <Section n={2} title="SOURCE DISAGREEMENT" />
          <TableHead
            cols={[
              { label: 'AUTHORITY' },
              { label: 'DEAD', width: '72px', align: 'right' },
              { label: 'MISSING', width: '78px', align: 'right' },
              { label: `Δ VS ${authority}`, width: '104px', align: 'right' },
              { label: 'GRADE', width: '46px' },
              { label: 'SOURCE', width: '70px' },
            ]}
          />
          <TableRow
            cells={[
              {
                node: (
                  <>
                    {toll.authority}
                    <span style={{ ...LABEL_XS, marginLeft: 8 }}>{dtgDay(toll.as_of)}</span>
                  </>
                ),
              },
              { node: fmt(toll.deaths), width: '72px', align: 'right', tone: 'critical' },
              { node: fmt(toll.missing), width: '78px', align: 'right', tone: 'high' },
              { node: 'BASELINE', width: '104px', align: 'right', tone: 'muted' },
              { node: <Grade code={gradeFor(toll.authority).code} />, width: '46px' },
              { node: <SourceRef url={toll.source_url} />, width: '70px' },
            ]}
          />
          {official.conflicting_reports.map((report) => {
            const gap = isNum(report.deaths) && isNum(toll.deaths) ? report.deaths - toll.deaths : null;
            return (
              <TableRow
                key={`${report.authority}-${report.as_of}`}
                cells={[
                  {
                    node: (
                      <>
                        {report.authority}
                        <span style={{ ...LABEL_XS, marginLeft: 8 }}>{dtgDay(report.as_of)}</span>
                      </>
                    ),
                  },
                  { node: fmt(report.deaths), width: '72px', align: 'right', tone: 'critical' },
                  { node: fmt(report.missing), width: '78px', align: 'right', tone: 'high' },
                  {
                    node: gap === null ? '—' : fmtDelta(gap),
                    width: '104px',
                    align: 'right',
                    tone: gap === null || gap === 0 ? 'muted' : 'medium',
                  },
                  { node: <Grade code={gradeFor(report.authority).code} />, width: '46px' },
                  { node: <SourceRef url={report.source_url} />, width: '70px' },
                ]}
              />
            );
          })}
          {conflictNote && <Note>{conflictNote}</Note>}

          {toll.note && <Note>{toll.note}</Note>}

          {/* Counts read from the cross-check object, never typed: the incident feed
              carried none of this event, and that absence is the finding. */}
          {bipad && (
            <Note>
              BIPAD routine feed: {fmt(bipad.deaths)} deaths, {fmt(bipad.incidents)} incidents in {fmt(bipad.window_days)} days
              — this event absent.
            </Note>
          )}
        </Scroll>

        <SourceLine
          source={toll.source_title ?? toll.authority}
          asOf={dtgDay(toll.as_of)}
          url={toll.source_url}
          grade={gradeFor(toll.authority).code}
        />
      </Body>
    </Widget>
  );
});
