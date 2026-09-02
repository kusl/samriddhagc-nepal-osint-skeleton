/**
 * INTERNATIONAL ASSISTANCE — who sent what. Left: an arc board on a lat/long
 * graticule, every sending capital tied to Kathmandu, stroke by stated
 * personnel. Right: the country ledger — teams by kind and size, materials,
 * money, flights, latest date, grade of the best source.
 *
 * Reads GET /flood/assistance. Team rows come from named documents (truth
 * file), from the newest MoFA briefing (automatic, marked), and from IFRC GO's
 * personnel register (automatic). Money is shown in the donor's currency and
 * never summed. A country with no published figure shows none.
 *
 * Milspec: stat strip, two-pane body, fitted rows, one SourceLine, inset
 * overlay for a country's documents. No rails, no scroll.
 */
import { memo, useMemo, useState, type CSSProperties } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Globe2 } from 'lucide-react';

import { Widget } from '../Widget';
import apiClient from '../../../api/client';
import { floodKeys } from '../../../api/hooks/useFlood';
import { WidgetEmpty, WidgetError, WidgetSkeleton } from './shared';
import {
  Body,
  CELL,
  F,
  Grade,
  HAIRLINE,
  LABEL,
  LABEL_XS,
  MS,
  Note,
  PROSE,
  Section,
  SourceLine,
  Stat,
  StatRow,
  Tag,
  dtgDay,
  fmt,
  gradeFor,
} from '../../flood/milspec';

// ------------------------------------------------------------------ types

interface Sourced {
  source: string;
  url?: string | null;
  note?: string | null;
}
export interface AssistTeam extends Sourced {
  kind: string;
  personnel: number | null;
  sites: string[];
  since: string | null;
  auto?: boolean;
  confirmed_by_briefing?: string | null;
}
interface Material extends Sourced {
  item: string;
  qty: number | null;
  unit: string | null;
  date: string | null;
  /** A reported running total; shown as a floor instead of being added to per-flight rows. */
  cumulative?: boolean;
}
interface Money extends Sourced {
  amount: number;
  currency: string;
  channel: string | null;
  date: string | null;
}
interface Flight extends Sourced {
  n: number;
  aircraft: string | null;
  date: string | null;
}
interface Evidence {
  title: string;
  outlet: string | null;
  url: string | null;
  published_at: string | null;
  numbers: number[];
}
export interface AssistCountry {
  code: string;
  name: string;
  lat: number | null;
  lng: number | null;
  teams: AssistTeam[];
  materials: Material[];
  money: Money[];
  flights: Flight[];
  evidence: Evidence[];
  evidence_count: number;
  personnel_total: number;
  personnel_unstated: number;
  kinds: string[];
  in_briefing: boolean;
  in_truth_file: boolean;
  latest: string | null;
}
export interface AssistancePayload {
  as_of: string;
  kathmandu: { lat: number; lng: number };
  countries: AssistCountry[];
  announced_only: string[];
  announced_only_source: { source: string; url: string | null } | null;
  briefing: { title: string; date: string | null; url: string | null; source: string } | null;
  requested_by_nepal: string | null;
  ifrc: {
    event_url: string;
    appeal: { amount_requested_chf: number | null; amount_funded_chf: number | null; beneficiaries: number | null; url: string } | null;
    personnel: { code: string; name: string; personnel: number }[];
    surge_alerts: { message: string; opens: string; status: number | null }[];
    num_affected: number | null;
  };
  counts: {
    countries: number;
    with_teams: number;
    tunnel_countries: string[];
    forensic_countries: string[];
    personnel_stated: number;
    evidence: number;
  };
}

export function useAssistance() {
  return useQuery<AssistancePayload | null>({
    queryKey: [...floodKeys.all, 'assistance'] as const,
    queryFn: async () => {
      try {
        return (await apiClient.get('/flood/assistance')).data as AssistancePayload;
      } catch (err) {
        const status = (err as { response?: { status?: number } }).response?.status;
        if (status === 404) return null;
        throw err;
      }
    },
    staleTime: 5 * 60 * 1000,
    refetchInterval: 10 * 60 * 1000,
  });
}

// ------------------------------------------------------------------ helpers

const ISO3: Record<string, string> = {
  IN: 'IND', CN: 'CHN', KR: 'KOR', SG: 'SGP', US: 'USA', AU: 'AUS', AE: 'UAE', JP: 'JPN', GB: 'GBR', DK: 'DNK',
  NL: 'NLD', ID: 'IDN', QA: 'QAT', NZ: 'NZL', MY: 'MYS', BD: 'BGD', PK: 'PAK', MM: 'MMR', DE: 'DEU', CH: 'CHE',
  FR: 'FRA', TR: 'TUR', IL: 'ISR', CA: 'CAN', NP: 'NPL',
};
const iso3 = (c: string) => ISO3[c] ?? c;

const KIND_LABEL: Record<string, string> = {
  tunnel: 'TUNNEL', forensic: 'FORENSIC', dvi: 'DVI', sar: 'SAR', consular: 'CONSULAR', ifrc_rr: 'IFRC RR', medical: 'MEDICAL', relief: 'RELIEF',
};
const KIND_TONE: Record<string, 'critical' | 'high' | 'info' | 'sub' | 'low'> = {
  tunnel: 'critical', forensic: 'high', dvi: 'high', sar: 'info', consular: 'sub', ifrc_rr: 'low',
};

const clip: CSSProperties = { minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' };

/** "NPR 336m", "USD 500k", "AUD 2m" — the donor's currency, never converted. */
function money(m: Money): string {
  const a = m.amount;
  const s = a >= 1e9 ? `${(a / 1e9).toFixed(a % 1e9 ? 1 : 0)}bn` : a >= 1e6 ? `${(a / 1e6).toFixed(a % 1e6 ? 1 : 0)}m` : a >= 1e3 ? `${Math.round(a / 1e3)}k` : String(a);
  return `${m.currency} ${s}`;
}
function materialsLine(c: AssistCountry): string {
  const cum = c.materials.find((m) => m.cumulative && m.unit === 't' && typeof m.qty === 'number');
  const t = cum
    ? (cum.qty as number)
    : c.materials.filter((m) => m.unit === 't' && typeof m.qty === 'number').reduce((a, m) => a + (m.qty as number), 0);
  const parts: string[] = [];
  if (t > 0) parts.push(`${cum ? '≥' : ''}${t % 1 ? t.toFixed(1) : t} t`);
  const flights = c.flights.length ? Math.max(...c.flights.map((f) => f.n)) : 0;
  if (flights) parts.push(`${flights} flt`);
  const items = c.materials.length - (t > 0 ? c.materials.filter((m) => m.unit === 't').length : 0);
  if (!parts.length && items > 0) parts.push(`${items} ${items === 1 ? 'consignment' : 'consignments'}`);
  return parts.join(' · ') || '—';
}
function bestGrade(c: AssistCountry) {
  const sources = [...c.teams, ...c.materials, ...c.money].map((x) => x.source);
  const graded = sources.map((s) => gradeFor(s));
  graded.sort((a, b) => a.code.localeCompare(b.code));
  return graded[0]?.code ?? 'F6';
}

// ------------------------------------------------------------------ arc board

const LON0 = -110;
const LON1 = 165;
const LAT0 = -48;
const LAT1 = 72;

interface WorldLite {
  source: string;
  countries: { iso: string; name: string; rings: number[][][] }[];
}

/** Natural Earth 1:110m outlines, simplified and vendored under /data — no tiles,
 *  no keys, drawn in the desk's own palette. */
function useWorld() {
  return useQuery<WorldLite | null>({
    queryKey: ['world-lite'],
    queryFn: async () => {
      const r = await fetch('/data/world_lite.json');
      return r.ok ? ((await r.json()) as WorldLite) : null;
    },
    staleTime: Infinity,
  });
}

function ArcBoard({ data, active, onPick }: { data: AssistancePayload; active: string | null; onPick: (c: string) => void }) {
  const world = useWorld().data ?? null;
  const W = 660;
  const H = 300;
  const px = (lng: number) => ((lng - LON0) / (LON1 - LON0)) * W;
  const py = (lat: number) => ((LAT1 - lat) / (LAT1 - LAT0)) * H;
  const ktm = data.kathmandu;
  const kx = px(ktm.lng);
  const ky = py(ktm.lat);
  const nodes = data.countries.filter((c) => typeof c.lat === 'number' && typeof c.lng === 'number');
  const maxP = Math.max(1, ...nodes.map((c) => c.personnel_total));
  const onBoard: Record<string, string> = {};
  for (const c of nodes) onBoard[c.code] = c.kinds.includes('tunnel') ? MS.critical : c.teams.length ? MS.info : MS.sub;
  const grat: number[] = [];
  for (let lon = -90; lon <= 150; lon += 30) grat.push(lon);
  const lats = [-30, 0, 30, 60];

  // Labels go on the side away from Kathmandu so no arc runs through its own
  // caption; where two would still overlap, the later one (by latitude) drops a line.
  const placed: { x0: number; x1: number; y: number }[] = [{ x0: kx + 9, x1: kx + 70, y: ky - 5 }];
  const labelPos: Record<string, { x: number; y: number; anchor: 'start' | 'end' }> = {};
  for (const c of [...nodes].sort((a, b) => (b.lat as number) - (a.lat as number))) {
    const nx = px(c.lng as number);
    const west = nx < kx;
    const text = `${iso3(c.code)}${c.personnel_total ? ` ${c.personnel_total}` : ''}`;
    const wpx = text.length * 5.2;
    const x = west ? nx - 6 : nx + 6;
    const x0 = west ? x - wpx : x;
    const x1 = west ? x : x + wpx;
    let y = py(c.lat as number) + 3;
    for (let guard = 0; guard < 6; guard++) {
      const hit = placed.some((p) => x0 < p.x1 + 4 && x1 > p.x0 - 4 && Math.abs(p.y - y) < 9);
      if (!hit) break;
      y += 9;
    }
    placed.push({ x0, x1, y });
    labelPos[c.code] = { x, y, anchor: west ? 'end' : 'start' };
  }

  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet" style={{ width: '100%', height: '100%', display: 'block' }}>
      <defs>
        <clipPath id="arc-clip"><rect x={0} y={0} width={W} height={H} /></clipPath>
      </defs>
      <g clipPath="url(#arc-clip)">
        {world?.countries.map((c) => {
          const hl = onBoard[c.iso];
          const d = c.rings.map((r) => r.map(([lng, lat], i) => `${i ? 'L' : 'M'}${px(lng).toFixed(1)},${py(lat).toFixed(1)}`).join('') + 'Z').join('');
          return (
            <path
              key={c.iso + c.name}
              d={d}
              fill={hl ?? MS.rule}
              fillOpacity={hl ? (hl === MS.sub ? 0.16 : 0.22) : 0.28}
              stroke={hl ?? MS.rule}
              strokeOpacity={hl ? 0.8 : 0.55}
              strokeWidth={hl ? 0.7 : 0.45}
              style={{ cursor: hl ? 'pointer' : 'default' }}
              onClick={hl ? () => onPick(c.iso) : undefined}
            />
          );
        })}
        {grat.map((lon) => (
          <line key={`g${lon}`} x1={px(lon)} x2={px(lon)} y1={0} y2={H} stroke={MS.rule} strokeOpacity={0.35} strokeWidth={0.5} />
        ))}
        {lats.map((lat) => (
          <line key={`l${lat}`} x1={0} x2={W} y1={py(lat)} y2={py(lat)} stroke={MS.rule} strokeOpacity={lat === 0 ? 0.6 : 0.35} strokeWidth={0.5} />
        ))}
        {nodes.map((c) => {
          const x = px(c.lng as number);
          const y = py(c.lat as number);
          const mx = (x + kx) / 2;
          const my = Math.min(y, ky) - Math.abs(x - kx) * 0.22 - 8;
          const w = 0.6 + 2.2 * Math.sqrt(c.personnel_total / maxP);
          const teams = c.teams.length > 0;
          const tone = onBoard[c.code];
          const dim = active && active !== c.code;
          const lp = labelPos[c.code];
          return (
            <g key={c.code} opacity={dim ? 0.25 : 1} style={{ cursor: 'pointer' }} onClick={() => onPick(c.code)}>
              <path d={`M${x},${y} Q${mx},${my} ${kx},${ky}`} fill="none" stroke={tone} strokeWidth={w} strokeOpacity={teams ? 0.85 : 0.5} strokeDasharray={teams ? undefined : '3 3'} />
              <circle cx={x} cy={y} r={teams ? 3 : 2.2} fill={teams ? tone : MS.surface} stroke={tone} strokeWidth={1} />
              <text x={lp.x} y={lp.y} textAnchor={lp.anchor} fill={tone} fontSize={8} fontFamily={MS.mono} letterSpacing={0.5} style={{ paintOrder: 'stroke', stroke: MS.surface, strokeWidth: 2.5 }}>
                {iso3(c.code)}{c.personnel_total ? ` ${c.personnel_total}` : ''}
              </text>
            </g>
          );
        })}
        <circle cx={kx} cy={ky} r={6} fill="none" stroke={MS.text} strokeWidth={1} />
        <circle cx={kx} cy={ky} r={2} fill={MS.text} />
        <text x={kx + 9} y={ky - 5} fill={MS.text} fontSize={8} fontFamily={MS.mono} fontWeight={700} letterSpacing={0.5} style={{ paintOrder: 'stroke', stroke: MS.surface, strokeWidth: 2.5 }}>KATHMANDU</text>
        {grat.filter((_, i) => i % 2 === 0).map((lon) => (
          <text key={`t${lon}`} x={px(lon) + 2} y={H - 3} fill={MS.muted} fontSize={7} fontFamily={MS.mono}>{lon < 0 ? `${-lon}W` : `${lon}E`}</text>
        ))}
      </g>
    </svg>
  );
}

// ------------------------------------------------------------------ widget

export const FloodAssistanceWidget = memo(function FloodAssistanceWidget() {
  const q = useAssistance();
  const [openCode, setOpenCode] = useState<string | null>(null);
  const [hover, setHover] = useState<string | null>(null);
  const data = q.data ?? null;
  const countries = useMemo(() => data?.countries ?? [], [data]);

  if (q.isLoading) {
    return (
      <Widget id="flood-assistance" title="INTERNATIONAL ASSISTANCE" icon={<Globe2 size={14} />}>
        <WidgetSkeleton />
      </Widget>
    );
  }
  if (q.error) {
    return (
      <Widget id="flood-assistance" title="INTERNATIONAL ASSISTANCE" icon={<Globe2 size={14} />}>
        <WidgetError message="Failed to load the assistance board" onRetry={() => q.refetch()} />
      </Widget>
    );
  }
  if (!data || !countries.length) {
    return (
      <Widget id="flood-assistance" title="INTERNATIONAL ASSISTANCE" icon={<Globe2 size={14} />}>
        <WidgetEmpty message="No international assistance published for this event" />
      </Widget>
    );
  }

  const appeal = data.ifrc?.appeal ?? null;
  const open = openCode ? countries.find((c) => c.code === openCode) ?? null : null;
  const unstated = countries.reduce((a, c) => a + c.personnel_unstated, 0);

  return (
    <Widget
      id="flood-assistance"
      title="INTERNATIONAL ASSISTANCE"
      icon={<Globe2 size={14} />}
      badge={`${data.counts.with_teams} COUNTRIES WITH TEAMS IN`}
      badgeVariant="high"
    >
      <Body style={{ position: 'relative', overflow: 'hidden' }}>
        <StatRow columns={5}>
          <Stat label="COUNTRIES ON THE BOARD" value={fmt(data.counts.countries)} size={20} sub={`${data.counts.with_teams} with personnel in Nepal`} />
          <Stat label="TUNNEL RESCUE TEAMS" value={data.counts.tunnel_countries.map(iso3).join(' · ') || '—'} tone="critical" size={16} sub="per MoFA briefing, with the Nepali Army" />
          <Stat label="FORENSIC · DVI TEAMS" value={data.counts.forensic_countries.map(iso3).join(' · ') || '—'} tone="high" size={16} sub="DNA and victim identification, with Nepal Police" />
          <Stat label="PERSONNEL · STATED" value={fmt(data.counts.personnel_stated)} tone="info" size={20} sub={unstated ? `${unstated} ${unstated === 1 ? 'team' : 'teams'} without a published size` : 'every team has a published size'} />
          <Stat
            label="IFRC EMERGENCY APPEAL"
            value={appeal?.amount_requested_chf ? `CHF ${(appeal.amount_requested_chf / 1e6).toFixed(0)}m` : '—'}
            tone="low"
            size={20}
            sub={appeal ? `${appeal.amount_funded_chf ? `CHF ${(appeal.amount_funded_chf / 1e6).toFixed(1)}m` : 'nil'} recorded funded · ${fmt(appeal.beneficiaries ?? 0)} to reach` : 'IFRC GO unreachable'}
          />
        </StatRow>

        <div style={{ display: 'grid', gridTemplateColumns: '46% minmax(0, 1fr)', gap: 22, flex: 1, minHeight: 0, marginTop: 4 }}>
          <div style={{ minWidth: 0, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'flex', gap: 10, alignItems: 'baseline', ...LABEL_XS, paddingBottom: 3, borderBottom: `1px solid ${MS.rule}` }}>
              <span style={{ color: MS.text }}>ARC BOARD</span>
              <span style={{ color: MS.critical }}>■ TUNNEL</span>
              <span style={{ color: MS.info }}>■ TEAMS</span>
              <span style={{ color: MS.sub }}>┄ MATERIEL / MONEY</span>
              <span style={{ marginLeft: 'auto' }}>STROKE = STATED PERSONNEL</span>
            </div>
            <div style={{ flex: 1, minHeight: 0 }}>
              <ArcBoard data={data} active={hover ?? openCode} onPick={(c) => setOpenCode(c)} />
            </div>
          </div>

          <div style={{ minWidth: 0, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'flex', gap: 10, padding: '0 0 3px', borderBottom: `1px solid ${MS.rule}` }}>
              {[
                ['COUNTRY', '17%'], ['TEAMS IN NEPAL', ''], ['MATERIEL', '15%'], ['MONEY', '14%'], ['LATEST', '9%', 'right'], ['SRC', '4%', 'right'],
              ].map(([l, w, a]) => (
                <span key={l} style={{ ...LABEL_XS, flex: w ? `0 0 ${w}` : 1, minWidth: 0, textAlign: (a as 'left' | 'right') ?? 'left' }}>{l}</span>
              ))}
            </div>
            <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
              {countries.map((c) => (
                <div
                  key={c.code}
                  onClick={() => setOpenCode(c.code)}
                  onMouseEnter={() => setHover(c.code)}
                  onMouseLeave={() => setHover(null)}
                  title="Open the country's documents"
                  style={{ display: 'flex', gap: 10, alignItems: 'baseline', padding: '1px 0', lineHeight: 1.25, borderBottom: HAIRLINE, cursor: 'pointer', background: hover === c.code ? MS.hairline : 'transparent' }}
                >
                  <span style={{ flex: '0 0 17%', minWidth: 0, display: 'flex', gap: 6, alignItems: 'baseline' }}>
                    <span style={{ ...CELL, color: MS.text, fontWeight: 600, whiteSpace: 'nowrap' }}>{iso3(c.code)}</span>
                    <span style={{ ...LABEL_XS, ...clip, flex: 1 }}>{c.name}</span>
                  </span>
                  <span style={{ flex: 1, minWidth: 0, display: 'flex', gap: 4, overflow: 'hidden', whiteSpace: 'nowrap' }}>
                    {c.teams.length ? c.teams.map((t, i) => (
                      <Tag key={i} tone={KIND_TONE[t.kind] ?? 'sub'}>
                        {KIND_LABEL[t.kind] ?? t.kind.toUpperCase()}{t.personnel ? ` ${t.personnel}` : ''}{t.auto ? ' ·A' : ''}
                      </Tag>
                    )) : <span style={LABEL_XS}>—</span>}
                  </span>
                  <span style={{ ...CELL, flex: '0 0 15%', color: MS.sub, ...clip }} title={c.materials.map((m) => m.item).join(' · ')}>{materialsLine(c)}</span>
                  <span style={{ ...CELL, flex: '0 0 14%', color: c.money.length ? MS.low : MS.muted, ...clip }} title={c.money.map((m) => `${money(m)} · ${m.channel ?? ''}`).join(' · ')}>
                    {c.money.length ? c.money.map(money).join(' · ') : '—'}
                  </span>
                  <span style={{ ...LABEL_XS, flex: '0 0 9%', textAlign: 'right', whiteSpace: 'nowrap' }}>{c.latest ? dtgDay(c.latest) : '—'}</span>
                  <span style={{ flex: '0 0 4%', textAlign: 'right' }}><Grade code={bestGrade(c)} /></span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <Note>
          {data.requested_by_nepal ? `NEPAL HAS ASKED FOR ${data.requested_by_nepal.replace(/^We have also requested the supply of\s*/i, '').replace(/\s*and other items\.?$/i, '.')} ` : ''}
          {data.announced_only.length ? `Announced, not yet arrived: ${data.announced_only.join(', ')}. ` : ''}
          ·A = matched automatically. Money in the donor's currency, never summed.
        </Note>
        <SourceLine
          source={data.briefing ? `${data.briefing.source} · IFRC GO` : 'IFRC GO · press'}
          asOf={dtgDay(data.as_of)}
          url={data.briefing?.url ?? data.ifrc?.event_url ?? null}
          right={<span style={{ whiteSpace: 'nowrap' }}>{fmt(data.counts.evidence)} PRESS MENTIONS SCANNED</span>}
        />

        {open && (
          <div
            onClick={() => setOpenCode(null)}
            style={{ position: 'absolute', inset: 0, zIndex: 20, background: MS.surface, display: 'flex', flexDirection: 'column', padding: '8px 12px 7px' }}
          >
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flex: '0 0 auto' }}>
              <span style={{ ...LABEL, color: MS.text, fontWeight: 600 }}>{open.name.toUpperCase()}</span>
              <span style={LABEL_XS}>{iso3(open.code)} · {open.teams.length} TEAM {open.teams.length === 1 ? 'ROW' : 'ROWS'} · {open.materials.length} MATERIEL · {open.money.length} MONEY</span>
              {open.in_briefing && <Tag tone="info">IN TODAY'S MOFA BRIEFING</Tag>}
              <span style={{ flex: 1, borderBottom: HAIRLINE, transform: 'translateY(-3px)' }} />
              <span style={LABEL_XS}>CLICK TO CLOSE</span>
            </div>
            <div onClick={(e) => e.stopPropagation()} style={{ flex: 1, minHeight: 0, overflowY: 'auto', marginTop: 6, columnCount: 2, columnGap: 28 }}>
              <div style={{ breakInside: 'avoid' }}>
                <Section n={1} title="TEAMS" meta="KIND · SIZE · SITE · SINCE" style={{ marginTop: 0 }} />
                {open.teams.length ? open.teams.map((t, i) => (
                  <div key={i} style={{ padding: '3px 0', borderBottom: HAIRLINE }}>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
                      <Tag tone={KIND_TONE[t.kind] ?? 'sub'}>{KIND_LABEL[t.kind] ?? t.kind.toUpperCase()}</Tag>
                      <F tone={t.personnel ? 'text' : 'muted'}>{t.personnel ? fmt(t.personnel) : 'size n/p'}</F>
                      <span style={{ ...LABEL_XS, ...clip, flex: 1 }}>{t.sites.length ? t.sites.join(', ').replace(/_/g, ' ').toUpperCase() : ''}</span>
                      <span style={{ ...LABEL_XS, whiteSpace: 'nowrap' }}>{t.since ? `SINCE ${dtgDay(t.since)}` : ''}</span>
                      <Grade code={gradeFor(t.source).code} />
                      {t.url && <a href={t.url} target="_blank" rel="noreferrer noopener" style={{ ...LABEL_XS, color: MS.info, textDecoration: 'none' }}>SOURCE</a>}
                    </div>
                    {t.note && <div style={{ ...PROSE, marginTop: 2, color: MS.sub }}>{t.note}{t.confirmed_by_briefing ? ` — confirmed by MoFA briefing of ${dtgDay(t.confirmed_by_briefing)}.` : ''}</div>}
                  </div>
                )) : <div style={{ ...PROSE, color: MS.muted }}>No personnel reported in Nepal by any source the desk has read.</div>}
                <Section n={2} title="MONEY" meta="DONOR'S CURRENCY" />
                {open.money.length ? open.money.map((m, i) => (
                  <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'baseline', padding: '3px 0', borderBottom: HAIRLINE }}>
                    <F tone="low">{money(m)}</F>
                    <span style={{ ...LABEL_XS, ...clip, flex: 1 }}>{m.channel ?? ''}</span>
                    <span style={{ ...LABEL_XS, whiteSpace: 'nowrap' }}>{m.date ? dtgDay(m.date) : ''}</span>
                    <Grade code={gradeFor(m.source).code} />
                    {m.url && <a href={m.url} target="_blank" rel="noreferrer noopener" style={{ ...LABEL_XS, color: MS.info, textDecoration: 'none' }}>SOURCE</a>}
                  </div>
                )) : <div style={{ ...PROSE, color: MS.muted }}>No cash pledge published.</div>}
              </div>
              <div style={{ breakInside: 'avoid' }}>
                <Section n={3} title="MATERIEL · FLIGHTS" meta="AS REPORTED" style={{ marginTop: 0 }} />
                {open.materials.map((m, i) => (
                  <div key={i} style={{ padding: '3px 0', borderBottom: HAIRLINE }}>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
                      <span style={{ ...CELL, color: MS.text, ...clip, flex: 1 }}>{m.item}</span>
                      <F tone={typeof m.qty === 'number' ? 'text' : 'muted'}>{typeof m.qty === 'number' ? `${m.qty} ${m.unit ?? ''}` : 'qty n/p'}</F>
                      <span style={{ ...LABEL_XS, whiteSpace: 'nowrap' }}>{m.date ? dtgDay(m.date) : ''}</span>
                      <Grade code={gradeFor(m.source).code} />
                      {m.url && <a href={m.url} target="_blank" rel="noreferrer noopener" style={{ ...LABEL_XS, color: MS.info, textDecoration: 'none' }}>SOURCE</a>}
                    </div>
                    {m.note && <div style={{ ...LABEL_XS, marginTop: 1 }}>{m.note}</div>}
                  </div>
                ))}
                {open.flights.map((f, i) => (
                  <div key={`f${i}`} style={{ display: 'flex', gap: 8, alignItems: 'baseline', padding: '3px 0', borderBottom: HAIRLINE }}>
                    <F>{fmt(f.n)}</F>
                    <span style={{ ...CELL, color: MS.sub, ...clip, flex: 1 }}>{f.n === 1 ? 'flight' : 'flights'} · {f.aircraft ?? 'aircraft not stated'}</span>
                    <span style={{ ...LABEL_XS, whiteSpace: 'nowrap' }}>{f.date ? dtgDay(f.date) : ''}</span>
                    <Grade code={gradeFor(f.source).code} />
                  </div>
                ))}
                {!open.materials.length && !open.flights.length && <div style={{ ...PROSE, color: MS.muted }}>No consignment reported.</div>}
                {open.evidence.length > 0 && (
                  <>
                    <Section n={4} title="PRESS MENTIONS" meta="FROM THE DESK'S STORY STORE · UNVERIFIED" />
                    {open.evidence.slice(0, 6).map((e, i) => (
                      <a key={i} href={e.url ?? undefined} target="_blank" rel="noreferrer noopener" style={{ display: 'block', padding: '3px 0', borderBottom: HAIRLINE, textDecoration: 'none', color: 'inherit' }}>
                        <div style={{ ...LABEL_XS, display: 'flex', gap: 8 }}>
                          <span>{dtgDay(e.published_at)}</span>
                          <span style={{ ...clip, flex: 1 }}>{e.outlet ?? 'OUTLET NOT STATED'}</span>
                          <Grade code={gradeFor(e.outlet).code} />
                        </div>
                        <div style={{ ...CELL, color: MS.text, ...clip }}>{e.title}</div>
                      </a>
                    ))}
                  </>
                )}
              </div>
            </div>
          </div>
        )}
      </Body>
    </Widget>
  );
});
