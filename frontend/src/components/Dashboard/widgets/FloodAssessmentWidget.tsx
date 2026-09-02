/**
 * The written assessment: what is established, what cannot be seen, what is coming.
 *
 * The rest of the desk is instruments. This is the analytic product that reads
 * them — a numbered SITREP: bottom line, situation, assessment, collection gaps,
 * outlook. It is the only widget on the page that argues.
 *
 * Every figure is READ, never typed. Each sentence is a function over the same
 * API responses the widgets below consume, and returns null when a figure it
 * needs has not been published — so the product loses a line rather than
 * carrying a stale number, and can never disagree with the hero above it. If a
 * number appears in this file as a literal, that is a bug.
 *
 * Text the authorities wrote (the event cause, NDRRMA's recovery-pattern note,
 * a chronology headline, a panel row, the rebuild projection) is quoted through
 * verbatim rather than paraphrased: paraphrase is an unsourced claim.
 *
 * Every line carries its own Admiralty grade where the code actually knows the
 * sentence's authority, and its own confidence. Where no source is known the
 * grade is omitted rather than guessed.
 */
import { Fragment, memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { FileText, X } from 'lucide-react';

import { Widget } from '../Widget';
import apiClient from '../../../api/client';
import { useFloodRivers, useOfficialSituation } from '../../../api/hooks/useFlood';
import type { OfficialSituation, RiverStation, SituationPanel } from '../../../api/flood';
import { useDamageSites, type DamageSite } from '../../flood/damageSites';
import {
  useFloodDistrictGeo,
  type CorridorWaypoint,
  type DistrictProperties,
} from '../../flood/districtGeo';
import { useVantorScenes, type VantorResponse } from '../../flood/vantorScenes';
import {
  Body,
  F,
  Line,
  MS,
  PROSE,
  Section,
  SourceLine,
  dtgDay,
  dtgNpt,
  fmt,
  fmtMoney,
  gradeFor,
  isNum,
  type Confidence,
  HAIRLINE,
  LABEL,
  LABEL_XS,
  Note,
} from '../../flood/milspec';
import { WidgetEmpty, WidgetError, WidgetSkeleton } from './shared';

/** Chronology stamps are fixed +05:45 strings — read, never re-zoned. See FloodChronologyWidget. */
const nptDay = (raw: string): string => raw.slice(0, 10);

/**
 * "<n> dead, <n> missing and <n> rescued" from however many clauses
 * actually have figures behind them. A bulletin that stops publishing one
 * column shortens the sentence instead of blanking it.
 */
const joinClauses = (parts: ReactNode[]): ReactNode => (
  <>
    {parts.map((p, i) => (
      <Fragment key={i}>
        {i > 0 ? (i === parts.length - 1 ? ' and ' : ', ') : null}
        {p}
      </Fragment>
    ))}
  </>
);

/** One rendered assessment line: one sentence, one grade, one confidence. */
interface Assertion {
  node: ReactNode;
  /** The authority for THIS sentence, where the code knows it. Graded, never guessed. */
  source?: string | null;
  /** Overrides the block's default confidence. */
  conf?: Confidence;
}

interface Block {
  key: string;
  n: number;
  title: string;
  meta?: string;
  /** Default analytic confidence for every line in the block. */
  conf: Confidence;
  lines: Assertion[];
  /** Attribution strings for the footer, deduped across blocks. */
  sources: string[];
}

interface AssessmentInputs {
  situation: OfficialSituation;
  chronology: ChronologyEntry[];
  districts: DistrictProperties[];
  corridor: CorridorWaypoint[];
  snapshotCount: number | null;
  vantor: VantorResponse | undefined;
  sites: DamageSite[];
  stations: RiverStation[];
  stationCount: number | null;
}

// ------------------------------------------------------------------ sources

interface ChronologyEntry {
  occurred_at_npt: string;
  time_published: boolean;
  kind: string;
  headline: string;
  detail: string | null;
  source: string | null;
}

/**
 * Declared inline rather than in the shared flood client: the queryKey is the one
 * the chronology widget already uses, so React Query serves both readers from one
 * response and this widget adds no requests to the page.
 */
function useFloodChronology() {
  return useQuery<{ count: number; events: ChronologyEntry[] }>({
    queryKey: ['flood', 'chronology'] as const,
    queryFn: async () => (await apiClient.get('/flood/chronology')).data,
    staleTime: 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  });
}

// ------------------------------------------------------------------ builder

const panelOf = (panels: SituationPanel[], key: string) => panels.find((p) => p.key === key);

/** A panel row located by what its label says, so a reordered bulletin still finds it. */
const rowMatching = (panel: SituationPanel | undefined, test: RegExp) =>
  panel?.rows.find((r) => test.test(r.label));

/** Post-event cloud, read off the acquisitions rather than off any summary field. */
const postCloudRange = (vantor: VantorResponse | undefined): [number, number] | null => {
  const clouds = (vantor?.items ?? [])
    .filter((i) => i.phase === 'post' && isNum(i.cloud))
    .map((i) => i.cloud);
  if (clouds.length === 0) return null;
  return [Math.min(...clouds), Math.max(...clouds)];
};

function buildAssessment(input: AssessmentInputs): Block[] {
  const { situation, chronology, districts, corridor, vantor, sites, stations } = input;
  const { event, official, bipad_cross_check: bipad } = situation;
  const toll = official.latest;
  if (!toll) return [];

  const panels = official.panels ?? [];
  const blocks: Block[] = [];

  // ---- 1. BOTTOM LINE ------------------------------------------------
  {
    const lines: Assertion[] = [];
    const sources: string[] = [];

    const counts: ReactNode[] = [];
    if (isNum(toll.deaths)) counts.push(<><F tone="critical">{fmt(toll.deaths)}</F> dead</>);
    if (isNum(toll.missing)) counts.push(<><F tone="high">{fmt(toll.missing)}</F> missing</>);
    if (isNum(toll.rescued)) counts.push(<><F tone="low">{fmt(toll.rescued)}</F> rescued</>);

    if (counts.length > 0) {
      lines.push({
        node: (
          <>
            As of {dtgDay(toll.as_of)}, {toll.authority} counts {joinClauses(counts)} from the{' '}
            {event.name}.
          </>
        ),
        source: toll.authority,
      });
      sources.push(`${toll.authority} · ${toll.as_of}`);
    }

    const medical = panelOf(panels, 'medical');
    const intensive = rowMatching(medical, /intensive/i);
    if (isNum(toll.injured)) {
      lines.push({
        node: (
          <>
            <F tone="medium">{fmt(toll.injured)}</F> hospitalised
            {intensive ? <>, <F tone="medium">{intensive.value}</F> of them {intensive.label.toLowerCase()}</> : null}.
          </>
        ),
        source: medical?.source ?? toll.authority,
      });
      if (medical?.source) sources.push(medical.source);
    }

    // Authorities disagreeing is information. The desk shows both figures and
    // resolves neither, exactly as the hero above does.
    official.conflicting_reports.forEach((r) => {
      if (!isNum(r.deaths) || !isNum(toll.deaths)) return;
      lines.push({
        node: (
          <>
            {r.authority} report <F tone="critical">{fmt(r.deaths)}</F> dead for the same date,
            against {toll.authority}&rsquo;s <F tone="critical">{fmt(toll.deaths)}</F>.
          </>
        ),
        source: r.authority,
      });
      lines.push({ node: <>Both figures stand on this desk; the desk reconciles neither.</> });
      sources.push(r.authority);
    });

    if (isNum(toll.damage_npr)) {
      lines.push({
        node: (
          <>
            Preliminary damage is put at <F>{fmtMoney(toll.damage_npr, 'NPR')}</F>
            {isNum(toll.damage_usd) ? <> (≈ {fmtMoney(toll.damage_usd, 'USD')})</> : null}.
          </>
        ),
        source: toll.authority,
      });
    }

    blocks.push({ key: 'bluf', n: 1, title: 'BOTTOM LINE', meta: 'BLUF', conf: 'HIGH', lines, sources });
  }

  // ---- 2. SITUATION --------------------------------------------------
  {
    const lines: Assertion[] = [];
    const sources: string[] = [];

    if (event.cause) {
      lines.push({ node: <><F>{dtgDay(event.started_on)}</F>: {event.cause}</> });
    }

    // Only the beat that opens the event may speak for it. A chronology whose
    // first entry post-dates the event start is a later record, not the trigger.
    const first = chronology[0];
    if (first && nptDay(first.occurred_at_npt) === event.started_on) {
      lines.push({
        node: (
          <>
            Record opens <F>{dtgNpt(first.occurred_at_npt, first.time_published)}</F>: {first.headline}
          </>
        ),
        source: first.source,
      });
      if (first.detail) lines.push({ node: <>{first.detail}</>, source: first.source });
      if (first.source) sources.push(first.source);

      // The standing caveat, and only where it is warranted: if the opening beat
      // carries no published clock, the seismic instant and the ground reports
      // are two separate claims and the desk must not appear to have merged them.
      if (!first.time_published) {
        lines.push({ node: <>No clock was published for that beat.</> });
        lines.push({ node: <>Ground reports and the seismic record time this event differently.</> });
        lines.push({ node: <>The desk publishes both and reconciles neither.</> });
      }
    }

    blocks.push({ key: 'what', n: 2, title: 'SITUATION', conf: 'HIGH', lines, sources });
  }

  // ---- 3. ASSESSMENT -------------------------------------------------
  {
    const lines: Assertion[] = [];
    const sources: string[] = [];

    const source = districts.find((d) => d.position === 'source');
    // The deepest downstream recovery count, whichever district holds it — the
    // finding is about geography, not about one district's name.
    const downstream = districts
      .filter((d) => d.position === 'downstream' && isNum(d.bodies_recovered))
      .sort((a, b) => (b.bodies_recovered as number) - (a.bodies_recovered as number))[0];

    if (
      source &&
      downstream &&
      isNum(source.bodies_recovered) &&
      isNum(source.missing) &&
      isNum(downstream.bodies_recovered)
    ) {
      // The kilometre figure is the corridor's own waypoint mark. No distance is
      // published per district, so if the corridor does not name this place the
      // clause is dropped rather than estimated.
      const mark = corridor.find(
        (w) => isNum(w.km) && w.name.toLowerCase().includes(downstream.name.toLowerCase()),
      );
      lines.push({ node: <>Recoveries cluster downstream, not at the source.</> });
      lines.push({
        node: (
          <>
            {downstream.name}
            {mark ? <>, <F>{mark.km} km</F> down the corridor,</> : ''} has recovered{' '}
            <F tone="critical">{fmt(downstream.bodies_recovered)}</F> bodies.
          </>
        ),
      });
      lines.push({
        node: (
          <>
            {source.name} at the source has recovered{' '}
            <F tone="critical">{fmt(source.bodies_recovered)}</F> and holds{' '}
            <F tone="high">{fmt(source.missing)}</F> missing.
          </>
        ),
      });
    }

    // NDRRMA's own explanation of the pattern, quoted rather than restated.
    const deathsPanel = panelOf(panels, 'deaths');
    if (deathsPanel?.note) {
      lines.push({ node: <>{deathsPanel.note}</>, source: deathsPanel.source });
      if (deathsPanel.source) sources.push(deathsPanel.source);
    }

    blocks.push({ key: 'inversion', n: 3, title: 'ASSESSMENT', conf: 'MOD', lines, sources });
  }

  // ---- 4. COLLECTION GAPS --------------------------------------------
  {
    const lines: Assertion[] = [];
    const sources: string[] = [];

    const cloud = postCloudRange(vantor);
    if (cloud) {
      const [lo, hi] = cloud;
      lines.push({
        node: (
          <>
            Post-event passes over the corridor carry{' '}
            <F tone="medium">{lo === hi ? `${lo}%` : `${lo}–${hi}%`}</F> monsoon cloud.
          </>
        ),
        source: vantor?.attribution,
      });
      lines.push({ node: <>Obscured ground is unassessed, not undamaged.</> });
      if (vantor?.attribution) sources.push(vantor.attribution);
    }

    // A site with no frames at all states its own absence better than we can.
    sites
      .filter((s) => s.levels.length === 0 && s.finding)
      .forEach((s) => {
        lines.push({ node: <>{s.name}: {s.finding}.</>, source: s.finding_source });
        if (s.finding_source) sources.push(s.finding_source);
      });

    // Where a frame exists but its ground is only partly covered, the reader is
    // told which places the imagery cannot settle.
    const partial = sites.filter((s) => {
      const site = s.levels.find((l) => l.level === 'site');
      return site ? site.post.edge || !site.post.top : false;
    });
    if (partial.length > 0) {
      lines.push({
        node: (
          <>
            No post-event frame fully covers {partial.map((s) => s.name).join(', ')}; blank pixels
            there are no-data, not ground.
          </>
        ),
      });
    }

    // The deepest zoom is the one that resolves individual buildings. Where the
    // catalogue never rendered it, the corridor below that point is assessed at
    // a coarser scale, and that is a collection limit worth stating.
    const noDetail = sites.filter(
      (s) => s.levels.length > 0 && !s.levels.some((l) => l.level === 'detail'),
    );
    if (noDetail.length > 0) {
      const marks = noDetail.map((s) => s.km_mark).filter(isNum);
      lines.push({
        node: (
          <>
            {noDetail.map((s) => s.name).join(' and ')} carry no detail-level frame
            {marks.length === noDetail.length ? (
              <>
                ; below <F>km {Math.min(...marks)}</F> the corridor is assessed at site scale only
              </>
            ) : null}
            .
          </>
        ),
      });
    }

    if (isNum(input.snapshotCount) && input.snapshotCount > 0) {
      lines.push({
        node: (
          <>
            Per-district tolls exist for <F>{fmt(input.snapshotCount)}</F> date
            {input.snapshotCount === 1 ? '' : 's'} only.
          </>
        ),
      });
      lines.push({ node: <>The map replay steps between published snapshots and interpolates nothing.</> });
    }

    const silent = stations.filter((s) => s.alert === 'offline' || s.alert === 'sensor_fault').length;
    if (stations.length > 0) {
      lines.push({
        node: (
          <>
            <F tone="medium">{fmt(silent)}</F> of <F>{fmt(input.stationCount ?? stations.length)}</F>{' '}
            river gauges are offline or faulted.
          </>
        ),
      });
      lines.push({ node: <>A silent gauge is an instrument state, never presented as danger.</> });
    }

    if (isNum(toll.deaths) && isNum(bipad?.deaths)) {
      lines.push({
        node: (
          <>
            {toll.authority} reports <F tone="critical">{fmt(toll.deaths)}</F> dead; BIPAD&rsquo;s
            feed carries <F tone="critical">{fmt(bipad.deaths)}</F> across{' '}
            <F>{fmt(bipad.incidents)}</F> incidents for the same {bipad.window_days}-day window.
          </>
        ),
        source: 'BIPAD',
      });
      lines.push({
        node: <>The feed does not hold this event; its counts are routine-incident coverage, not a rival toll.</>,
      });
    }

    blocks.push({
      key: 'gaps',
      n: 4,
      title: 'COLLECTION GAPS',
      meta: 'WHAT WE CANNOT SEE',
      conf: 'HIGH',
      lines,
      sources,
    });
  }

  // ---- 5. OUTLOOK ----------------------------------------------------
  {
    const lines: Assertion[] = [];
    const sources: string[] = [];

    // The standing threat is whatever the chronology's latest warning beat says.
    // Reading the kind rather than the wording keeps a future warning in scope.
    const warning = [...chronology].reverse().find((e) => e.kind === 'warning');
    if (warning) {
      lines.push({
        node: (
          <>
            <F tone="medium">{dtgDay(nptDay(warning.occurred_at_npt))}</F>: {warning.headline}
          </>
        ),
        source: warning.source,
        conf: 'MOD',
      });
      if (warning.detail) lines.push({ node: <>{warning.detail}</>, source: warning.source, conf: 'MOD' });
      if (warning.source) sources.push(warning.source);
    }

    const hydro = panelOf(panels, 'hydropower');
    if (hydro?.headline_value) {
      const inside = rowMatching(hydro, /inside/i);
      lines.push({
        node: (
          <>
            <F tone="high">{hydro.headline_value}</F>
            {hydro.headline_label ? <> {hydro.headline_label}</> : null}
            {inside ? <>, of whom <F tone="high">{inside.value}</F> are {inside.label.toLowerCase()}</> : null}
            .
          </>
        ),
        source: hydro.source,
        conf: 'MOD',
      });
      if (hydro.source) sources.push(hydro.source);
    }

    // Access is the binding constraint on the response. The line is whichever
    // panel names it — a row where one exists, and the panel's own note where it
    // spells out the cut — quoted, never summarised, and attributed to the panel
    // it actually came from rather than to whichever panel was looked at first.
    const access = ['operations', 'damage']
      .map((key) => panelOf(panels, key))
      .filter((panel): panel is SituationPanel => !!panel)
      .map((panel) => ({
        panel,
        row: panel.rows.find((r) => /krishnabhir|prithvi|highway|out of reach/i.test(r.label)),
        note: panel.note && /krishnabhir|prithvi|highway/i.test(panel.note) ? panel.note : null,
      }))
      .find((c) => c.row || c.note);
    if (access) {
      if (access.row) {
        lines.push({
          node: <>{access.row.label}: <F>{access.row.value}</F>.</>,
          source: access.panel.source,
          conf: 'MOD',
        });
      }
      if (access.note) {
        lines.push({ node: <>{access.note}</>, source: access.panel.source, conf: 'MOD' });
      }
      if (access.panel.source) sources.push(access.panel.source);
    }

    // The rebuild figure is a projection, not a count: it carries LOW confidence.
    if (toll.damage_note) {
      lines.push({ node: <>{toll.damage_note}</>, source: toll.authority, conf: 'LOW' });
    }

    blocks.push({
      key: 'coming',
      n: 5,
      title: 'OUTLOOK',
      meta: 'INDICATORS TO WATCH',
      conf: 'LOW',
      lines,
      sources,
    });
  }

  return blocks;
}

// ------------------------------------------------------------------ render

/**
 * The lines of one numbered block. A block with nothing behind it says so, so a
 * reader never mistakes silence for an all-clear.
 */
function Lines({ block }: { block: Block | undefined }) {
  if (!block || block.lines.length === 0) {
    return <div style={{ ...PROSE, color: MS.muted, padding: '2px 0' }}>Source unavailable just now.</div>;
  }
  return (
    <>
      {block.lines.map((line, i) => (
        <Line
          key={i}
          conf={line.conf ?? block.conf}
          grade={line.source ? gradeFor(line.source).code : undefined}
        >
          {line.node}
        </Line>
      ))}
    </>
  );
}

/** Height reserved at the foot of a clipped column for the "+N MORE" opener. */
const MORE_H = 18;

/**
 * A section that fits its column instead of scrolling it. Every line is in the
 * DOM, so nothing is re-flowed; lines whose bottom falls past the column's
 * height are made invisible and a "+N MORE" opener at the foot hands the whole
 * section to the inset reader. The measurement re-runs on resize, so a wider
 * or taller widget simply shows more.
 */
function FitColumn({
  n,
  title,
  meta,
  block,
  onMore,
}: {
  n: number;
  title: string;
  meta?: string;
  block: Block | undefined;
  onMore: () => void;
}) {
  const boxRef = useRef<HTMLDivElement | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);
  const [visible, setVisible] = useState<number>(Number.POSITIVE_INFINITY);
  const total = block?.lines.length ?? 0;

  const measure = useCallback(() => {
    const box = boxRef.current;
    const list = listRef.current;
    if (!box || !list) return;
    const limit = box.clientHeight;
    const top = list.offsetTop;
    const kids = Array.from(list.children) as HTMLElement[];
    // First pass: how many fit with nothing reserved; if not all, reserve the opener.
    const fits = (reserve: number) => {
      let count = 0;
      for (const k of kids) {
        if (top + k.offsetTop + k.offsetHeight <= limit - reserve) count += 1;
        else break;
      }
      return count;
    };
    const all = fits(0);
    const next = all >= kids.length ? kids.length : fits(MORE_H);
    setVisible((v) => (v === next ? v : next));
  }, []);

  useLayoutEffect(() => {
    measure();
    const box = boxRef.current;
    if (!box) return;
    const ro = new ResizeObserver(() => measure());
    ro.observe(box);
    return () => ro.disconnect();
  }, [measure, total]);

  const hidden = Number.isFinite(visible) ? Math.max(0, total - visible) : 0;

  return (
    <div ref={boxRef} style={{ minWidth: 0, minHeight: 0, position: 'relative', overflow: 'hidden' }}>
      <Section n={n} title={title} meta={meta} style={{ marginTop: 0 }} />
      <div ref={listRef}>
        {!block || total === 0 ? (
          <div style={{ ...PROSE, color: MS.muted, padding: '2px 0' }}>Source unavailable just now.</div>
        ) : (
          block.lines.map((line, i) => (
            <div key={i} style={{ visibility: i < visible ? 'visible' : 'hidden' }}>
              <Line conf={line.conf ?? block.conf} grade={line.source ? gradeFor(line.source).code : undefined}>
                {line.node}
              </Line>
            </div>
          ))
        )}
      </div>
      {hidden > 0 && (
        <button
          type="button"
          onClick={onMore}
          title={`${hidden} more lines — open the full section`}
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            bottom: 0,
            height: MORE_H,
            background: MS.surface,
            border: 'none',
            borderTop: HAIRLINE,
            padding: 0,
            textAlign: 'left',
            cursor: 'pointer',
            ...LABEL_XS,
            color: MS.info,
          }}
        >
          +{hidden} MORE · OPEN SECTION
        </button>
      )}
    </div>
  );
}

/** Inset reader for one section at full widget height. Never leaves the widget. */
function SectionReader({ block, n, title, meta, onClose }: { block: Block | undefined; n: number; title: string; meta?: string; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  return (
    <div
      onClick={onClose}
      style={{ position: 'absolute', inset: 0, zIndex: 20, background: MS.surface, display: 'flex', flexDirection: 'column', padding: '8px 12px 7px' }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flex: '0 0 auto' }}>
        <span style={{ ...LABEL, color: MS.sub, fontWeight: 600 }}>{String(n).padStart(2, '0')}</span>
        <span style={{ ...LABEL, color: MS.text, fontWeight: 600 }}>{title}</span>
        {meta && <span style={LABEL_XS}>{meta}</span>}
        <span style={{ flex: 1, borderBottom: HAIRLINE, transform: 'translateY(-3px)' }} />
        <span style={{ ...LABEL_XS, display: 'inline-flex', alignItems: 'center', gap: 3 }}>ESC <X size={10} /></span>
      </div>
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ flex: 1, minHeight: 0, overflowY: 'auto', marginTop: 6, columnCount: 2, columnGap: 32 }}
      >
        <Lines block={block} />
      </div>
    </div>
  );
}

const COLUMNS: Array<{ key: string; n: number; title: string; meta?: string }> = [
  { key: 'what', n: 2, title: 'SITUATION' },
  { key: 'inversion', n: 3, title: 'ASSESSMENT' },
  { key: 'gaps', n: 4, title: 'COLLECTION GAPS', meta: 'WHAT WE CANNOT SEE' },
  { key: 'coming', n: 5, title: 'OUTLOOK', meta: 'INDICATORS TO WATCH' },
];

export const FloodAssessmentWidget = memo(function FloodAssessmentWidget() {
  const situation = useOfficialSituation();
  const chronology = useFloodChronology();
  const geo = useFloodDistrictGeo();
  const vantor = useVantorScenes();
  const damage = useDamageSites();
  const rivers = useFloodRivers(false);

  const [reader, setReader] = useState<string | null>(null);
  const closeReader = useCallback(() => setReader(null), []);
  const blocks = useMemo<Block[]>(() => {
    if (!situation.data) return [];
    return buildAssessment({
      situation: situation.data,
      chronology: chronology.data?.events ?? [],
      districts: (geo.data?.districts.features ?? []).map((f) => f.properties),
      corridor: geo.data?.corridor ?? [],
      snapshotCount: geo.data?.toll_snapshots?.length ?? null,
      vantor: vantor.data,
      sites: damage.data?.sites ?? [],
      stations: rivers.data?.stations ?? [],
      stationCount: rivers.data?.count ?? null,
    });
  }, [situation.data, chronology.data, geo.data, vantor.data, damage.data, rivers.data]);

  // Only the official record can empty this widget. The other four queries
  // degrade sentence by sentence — a satellite outage must not take down the
  // bottom line.
  if (situation.isLoading) {
    return (
      <Widget id="flood-assessment" icon={<FileText size={14} />}>
        <WidgetSkeleton />
      </Widget>
    );
  }

  if (situation.error || !situation.data) {
    return (
      <Widget id="flood-assessment" icon={<FileText size={14} />}>
        <WidgetError message="Failed to load the official record" onRetry={() => situation.refetch()} />
      </Widget>
    );
  }

  const { official } = situation.data;
  if (!official.available || !official.latest) {
    return (
      <Widget id="flood-assessment" icon={<FileText size={14} />}>
        <WidgetEmpty message="No official record to assess yet" />
      </Widget>
    );
  }

  const toll = official.latest;
  const sources = Array.from(new Set(blocks.flatMap((b) => b.sources)));
  const blockOf = (key: string) => blocks.find((b) => b.key === key);

  return (
    <Widget
      id="flood-assessment"
      icon={<FileText size={14} />}
      badge={`${toll.authority} ${dtgDay(toll.as_of)}`}
      badgeVariant="high"
    >
      <Body style={{ position: 'relative', overflow: 'hidden' }}>
        {/* The bottom line is the one block a reader must not scroll past, so it
            runs the full width above the rest and is never clipped. */}
        <div style={{ flex: '0 0 auto' }}>
          <Section n={1} title="BOTTOM LINE" meta="BLUF" style={{ marginTop: 0 }} />
          <Lines block={blockOf('bluf')} />
        </div>

        {/* Four fitted columns. Nothing here scrolls: each column shows the
            lines its height holds and hands the rest to the inset reader. */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(4, minmax(0, 1fr))',
            alignItems: 'stretch',
            gap: 24,
            flex: 1,
            minHeight: 0,
            marginTop: 8,
            overflow: 'hidden',
          }}
        >
          {COLUMNS.map((c) => (
            <FitColumn key={c.key} n={c.n} title={c.title} meta={c.meta} block={blockOf(c.key)} onMore={() => setReader(c.key)} />
          ))}
        </div>

        {/* Grades ride on the individual lines, so the footer carries none. */}
        <SourceLine
          source={sources.length > 0 ? sources.join(' · ') : null}
          grade={false}
          asOf={dtgDay(toll.as_of)}
          url={toll.source_url}
          right={<span style={{ whiteSpace: 'nowrap' }}>FIGURES READ, NEVER TYPED</span>}
        />

        {reader && (() => {
          const c = COLUMNS.find((x) => x.key === reader);
          return c ? <SectionReader block={blockOf(c.key)} n={c.n} title={c.title} meta={c.meta} onClose={closeReader} /> : null;
        })()}
      </Body>
    </Widget>
  );
});

