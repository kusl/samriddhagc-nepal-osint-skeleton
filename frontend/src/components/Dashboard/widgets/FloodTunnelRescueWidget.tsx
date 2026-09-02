/**
 * TUNNEL RESCUE · HYDROPOWER — the per-project ledger of the corridor's
 * flooded tunnels: who is digging where, with whom, how far they got, and
 * what each source has published about the people inside.
 *
 * Reads GET /flood/hydropower: a truth file of projects (every figure with the
 * document it was read from), the tunnel section of the Ministry of Foreign
 * Affairs' daily briefing parsed automatically, and press mentions scanned
 * from the desk's own story store. Nothing is typed here; a figure the desk
 * has not read from a document is shown as "not published", not as zero.
 *
 * Milspec: stat strip, corridor strip (plants at their km on the channel),
 * fitted ledger rows, one SourceLine. No rails, no scroll.
 */
import { memo, useMemo, useState, type CSSProperties } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Zap } from 'lucide-react';

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
  Status,
  Tag,
  dtgDay,
  dtgNpt,
  fmt,
  gradeFor,
  type Tone,
} from '../../flood/milspec';

// ------------------------------------------------------------------ types

interface Sourced {
  source: string;
  url?: string | null;
}
interface Figure extends Sourced {
  kind: string;
  value: number;
  as_of: string;
  note?: string | null;
  unit?: string | null;
}
interface Team extends Sourced {
  country: string;
  unit: string;
  role?: string | null;
}
interface ProjectNote extends Sourced {
  t_npt: string;
  text: string;
  auto?: boolean;
}
interface Evidence {
  title: string;
  outlet: string | null;
  url: string | null;
  published_at: string | null;
  snippet: string | null;
  numbers: number[];
}
interface Project {
  key: string;
  name: string;
  short: string;
  capacity_mw: number | null;
  river: string | null;
  district: string | null;
  place: string | null;
  promoter: string | null;
  lat: number | null;
  lng: number | null;
  km: number | null;
  coord_confidence: string;
  coord_note?: string | null;
  status: 'active' | 'suspended' | 'unreported' | string;
  status_line: string;
  teams: Team[];
  figures: Figure[];
  notes: ProjectNote[];
  evidence?: Evidence[];
}
interface Briefing {
  title: string;
  date: string | null;
  tunnel_section: string | null;
  forensic_section: string | null;
  foreign_nationals_line: string | null;
  url: string | null;
  source: string;
}
interface HydropowerPayload {
  event_key: string;
  as_of: string;
  projects: Project[];
  corridor_figures: Figure[];
  briefing: Briefing | null;
  counts: { projects: number; active: number; suspended: number; evidence: number };
}

// ------------------------------------------------------------------ helpers

const FLAG: Record<string, string> = { NP: 'NPL', IN: 'IND', CN: 'CHN', KR: 'KOR', SG: 'SGP' };
const STATUS_TONE: Record<string, Tone> = { active: 'low', suspended: 'critical', unreported: 'muted' };
const STATUS_WORD: Record<string, string> = { active: 'DIGGING', suspended: 'SUSPENDED', unreported: 'NO FIGURES' };

const figureOf = (p: Project, kind: string): Figure | null => p.figures.find((f) => f.kind === kind) ?? null;

const clip: CSSProperties = { minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' };

/** Plants on the channel as ticks on a km strip; off-channel plants sit in a side bay.
 *  Plants that share a km (two projects snapped to the same named place) become
 *  ONE tick with a joint label, and ticks closer than ~4% of the strip stagger. */
function CorridorStrip({ projects, maxKm }: { projects: Project[]; maxKm: number }) {
  const onLine = [...projects.filter((p) => typeof p.km === 'number')].sort((a, b) => (a.km as number) - (b.km as number));
  const offLine = projects.filter((p) => typeof p.km !== 'number');
  const groups: { key: string; km: number; members: Project[] }[] = [];
  for (const p of onLine) {
    const last = groups[groups.length - 1];
    if (last && Math.abs((p.km as number) - last.km) / maxKm < 0.012) last.members.push(p);
    else groups.push({ key: p.key, km: p.km as number, members: [p] });
  }
  const rowOf: Record<string, 0 | 1> = {};
  let lastX = -100;
  let lastRow: 0 | 1 = 1;
  for (const g of groups) {
    const x = (g.km / maxKm) * 100;
    const row: 0 | 1 = x - lastX < 4 ? (lastRow === 0 ? 1 : 0) : 0;
    rowOf[g.key] = row;
    lastX = x;
    lastRow = row;
  }
  const rank: Record<string, number> = { suspended: 0, active: 1, unreported: 2 };
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 14, margin: '6px 0 2px' }}>
      <span style={{ ...LABEL_XS, whiteSpace: 'nowrap' }}>RASUWAGADHI · KM 0</span>
      <div style={{ position: 'relative', flex: 1, height: 27 }}>
        <div style={{ position: 'absolute', left: 0, right: 0, top: 13, height: 1, background: MS.rule }} />
        {groups.map((g) => {
          const x = Math.max(0, Math.min(100, (g.km / maxKm) * 100));
          const lead = [...g.members].sort((a, b) => (rank[a.status] ?? 9) - (rank[b.status] ?? 9))[0];
          const t = STATUS_TONE[lead.status] ?? 'muted';
          const label = g.members.map((m) => m.short).join(' · ');
          const title = g.members.map((m) => `${m.name} · km ${m.km} · ${m.coord_confidence}`).join('\n');
          const approx = g.members.some((m) => m.coord_confidence !== 'published');
          const labelStyle = { ...LABEL_XS, color: MS[t], whiteSpace: 'nowrap' as const, height: 10, lineHeight: '10px' };
          return (
            <div key={g.key} title={title} style={{ position: 'absolute', left: `${x}%`, top: 0, transform: 'translateX(-50%)', textAlign: 'center' }}>
              <div style={{ ...labelStyle, visibility: rowOf[g.key] === 1 ? 'visible' : 'hidden' }}>{label}</div>
              <div style={{ width: g.members.length > 1 ? 9 : 7, height: 7, margin: '0 auto', background: lead.status === 'suspended' ? 'transparent' : MS[t], border: `1.5px solid ${MS[t]}`, borderRadius: approx ? '50%' : 0 }} />
              <div style={{ ...labelStyle, visibility: rowOf[g.key] === 0 ? 'visible' : 'hidden' }}>{label}</div>
            </div>
          );
        })}
      </div>
      <span style={{ ...LABEL_XS, whiteSpace: 'nowrap' }}>KM {Math.round(maxKm)}</span>
      {offLine.length > 0 && (
        <span style={{ ...LABEL_XS, whiteSpace: 'nowrap', color: MS.muted }}>
          OFF-CHANNEL: {offLine.map((p) => p.short).join(' · ')}
        </span>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ widget

export const FloodTunnelRescueWidget = memo(function FloodTunnelRescueWidget() {
  const q = useQuery<HydropowerPayload | null>({
    queryKey: [...floodKeys.all, 'hydropower'] as const,
    queryFn: async () => {
      try {
        return (await apiClient.get('/flood/hydropower')).data as HydropowerPayload;
      } catch (err) {
        const status = (err as { response?: { status?: number } }).response?.status;
        if (status === 404) return null;
        throw err;
      }
    },
    staleTime: 5 * 60 * 1000,
    refetchInterval: 10 * 60 * 1000,
  });
  const [openKey, setOpenKey] = useState<string | null>(null);

  const data = q.data ?? null;
  const projects = useMemo(() => data?.projects ?? [], [data]);
  const maxKm = useMemo(() => Math.max(60, ...projects.map((p) => (typeof p.km === 'number' ? p.km : 0))), [projects]);

  const totals = useMemo(() => {
    const missing = projects.reduce((a, p) => a + (figureOf(p, 'missing')?.value ?? 0), 0);
    const rescued = projects.reduce((a, p) => a + (figureOf(p, 'rescued')?.value ?? 0), 0);
    const withMissing = projects.filter((p) => figureOf(p, 'missing')).length;
    const withRescued = projects.filter((p) => figureOf(p, 'rescued')).length;
    const countries = new Set(projects.flatMap((p) => p.teams.map((t) => t.country)).filter((c) => c !== 'NP'));
    return { missing, rescued, withMissing, withRescued, countries: [...countries] };
  }, [projects]);

  const ippan = data?.corridor_figures.find((f) => f.kind === 'unaccounted_all_projects') ?? null;
  const inside = data?.corridor_figures.find((f) => f.kind === 'believed_inside_all') ?? null;

  if (q.isLoading) {
    return (
      <Widget id="flood-tunnel-rescue" title="TUNNEL RESCUE · HYDROPOWER" icon={<Zap size={14} />}>
        <WidgetSkeleton />
      </Widget>
    );
  }
  if (q.error) {
    return (
      <Widget id="flood-tunnel-rescue" title="TUNNEL RESCUE · HYDROPOWER" icon={<Zap size={14} />}>
        <WidgetError message="Failed to load the tunnel ledger" onRetry={() => q.refetch()} />
      </Widget>
    );
  }
  if (!data || !projects.length) {
    return (
      <Widget id="flood-tunnel-rescue" title="TUNNEL RESCUE · HYDROPOWER" icon={<Zap size={14} />}>
        <WidgetEmpty message="No tunnel ledger published for this event" />
      </Widget>
    );
  }

  const open = openKey ? projects.find((p) => p.key === openKey) ?? null : null;

  return (
    <Widget
      id="flood-tunnel-rescue"
      title="TUNNEL RESCUE · HYDROPOWER"
      icon={<Zap size={14} />}
      badge={`${data.counts.active} DIGGING · ${data.counts.suspended} SUSPENDED`}
      badgeVariant="high"
    >
      <Body style={{ position: 'relative', overflow: 'hidden' }}>
        <StatRow columns={5}>
          <Stat label="PROJECTS ON THE CORRIDOR" value={fmt(projects.length)} size={20} sub={`${data.counts.active} with teams digging`} />
          <Stat label="UNACCOUNTED · ALL PROJECTS" value={ippan ? fmt(ippan.value) : '—'} tone="high" size={20} sub={ippan ? `${ippan.source.split(',')[0]} · ${dtgDay(ippan.as_of)}` : 'not published'} />
          <Stat label="BELIEVED STILL INSIDE" value={inside ? `~${fmt(inside.value)}` : '—'} tone="critical" size={20} sub={inside ? `${inside.source.split(',')[0]} · ${dtgDay(inside.as_of)}` : 'not published'} />
          <Stat label="MISSING · PER-PROJECT PUBLISHED" value={totals.withMissing ? fmt(totals.missing) : '—'} tone="high" size={20} sub={`${totals.withMissing} of ${projects.length} projects publish a figure`} />
          <Stat label="FOREIGN TUNNEL TEAMS" value={totals.countries.length ? totals.countries.map((c) => FLAG[c] ?? c).join(' · ') : '—'} tone="info" size={16} sub="with the Nepali Army, per MoFA briefing" />
        </StatRow>

        <CorridorStrip projects={projects} maxKm={maxKm} />

        <div style={{ display: 'flex', gap: 10, padding: '2px 0 4px', borderBottom: `1px solid ${MS.rule}` }}>
          {[
            ['PROJECT', '17%'], ['MW', '5%'], ['STATUS', '9%'], ['TEAMS', '14%'], ['MISSING', '8%', 'right'], ['RESCUED', '8%', 'right'], ['LATEST', '', 'left'], ['AS OF', '8%', 'right'],
          ].map(([l, w, a]) => (
            <span key={l} style={{ ...LABEL_XS, flex: w ? `0 0 ${w}` : 1, minWidth: 0, textAlign: (a as 'left' | 'right') ?? 'left' }}>{l}</span>
          ))}
        </div>

        <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
          {projects.map((p) => {
            const missing = figureOf(p, 'missing');
            const rescued = figureOf(p, 'rescued');
            const latest = p.notes.length ? [...p.notes].sort((a, b) => (a.t_npt < b.t_npt ? 1 : -1))[0] : null;
            const t = STATUS_TONE[p.status] ?? 'muted';
            return (
              <div
                key={p.key}
                onClick={() => setOpenKey(p.key)}
                title="Open the project's sources"
                style={{ display: 'flex', gap: 10, alignItems: 'baseline', padding: '3px 0', borderBottom: HAIRLINE, cursor: 'pointer' }}
              >
                <span style={{ flex: '0 0 17%', minWidth: 0, display: 'flex', gap: 6, alignItems: 'baseline' }}>
                  <span style={{ ...CELL, color: MS.text, fontWeight: 600, whiteSpace: 'nowrap' }}>{p.name}</span>
                  <span style={{ ...LABEL_XS, ...clip, flex: 1 }} title={`${p.place ?? p.district ?? ''}${typeof p.km === 'number' ? ` · km ${p.km}` : ''}${p.coord_confidence !== 'published' ? ' · position approximate' : ''}`}>
                    {typeof p.km === 'number' ? `KM ${p.km}` : (p.place ?? p.district ?? '')}{p.coord_confidence !== 'published' ? ' ~' : ''}
                  </span>
                </span>
                <span style={{ ...CELL, flex: '0 0 5%', color: MS.sub }}>{p.capacity_mw ?? '—'}</span>
                <span style={{ flex: '0 0 9%' }}><Status tone={t}>{STATUS_WORD[p.status] ?? p.status.toUpperCase()}</Status></span>
                <span style={{ flex: '0 0 14%', display: 'flex', gap: 4, flexWrap: 'wrap', minWidth: 0 }}>
                  {p.teams.length ? p.teams.map((tm, i) => (
                    <Tag key={i} tone={tm.country === 'NP' ? 'sub' : 'info'}>{FLAG[tm.country] ?? tm.country}</Tag>
                  )) : <span style={LABEL_XS}>—</span>}
                </span>
                <span style={{ ...CELL, flex: '0 0 8%', textAlign: 'right', color: missing ? MS.high : MS.muted, fontWeight: 600 }}>{missing ? fmt(missing.value) : 'n/p'}</span>
                <span style={{ ...CELL, flex: '0 0 8%', textAlign: 'right', color: rescued ? MS.low : MS.muted, fontWeight: 600 }}>{rescued ? fmt(rescued.value) : 'n/p'}</span>
                <span style={{ ...CELL, flex: 1, minWidth: 0, color: MS.sub, ...clip }} title={p.status_line}>{p.status_line}</span>
                <span style={{ ...LABEL_XS, flex: '0 0 8%', textAlign: 'right', whiteSpace: 'nowrap' }}>{latest ? dtgDay(latest.t_npt) : '—'}</span>
              </div>
            );
          })}
        </div>

        <Note>
          n/p = not published by any source the desk has read. Missing figures are the operators' own counts of staff unaccounted for; they are not added across projects that report differently. A ~ after the km means the plant's position is snapped to the nearest named place on the channel, not surveyed.
        </Note>
        <SourceLine
          source={data.briefing ? `${data.briefing.source}` : 'MoFA daily briefing not yet parsed'}
          asOf={dtgDay(data.as_of)}
          url={data.briefing?.url ?? null}
          right={<span style={{ whiteSpace: 'nowrap' }}>{fmt(data.counts.evidence)} PRESS MENTIONS SCANNED</span>}
        />

        {open && (
          <div
            onClick={() => setOpenKey(null)}
            style={{ position: 'absolute', inset: 0, zIndex: 20, background: MS.surface, display: 'flex', flexDirection: 'column', padding: '8px 12px 7px' }}
          >
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flex: '0 0 auto' }}>
              <span style={{ ...LABEL, color: MS.text, fontWeight: 600 }}>{open.name.toUpperCase()}</span>
              <span style={LABEL_XS}>{open.capacity_mw ? `${open.capacity_mw} MW` : ''} · {open.river ?? ''} · {open.district ?? ''}</span>
              <Status tone={STATUS_TONE[open.status] ?? 'muted'}>{STATUS_WORD[open.status] ?? open.status}</Status>
              <span style={{ flex: 1, borderBottom: HAIRLINE, transform: 'translateY(-3px)' }} />
              <span style={LABEL_XS}>ESC · CLICK TO CLOSE</span>
            </div>
            <div onClick={(e) => e.stopPropagation()} style={{ flex: 1, minHeight: 0, overflowY: 'auto', marginTop: 6, columnCount: 2, columnGap: 28 }}>
              <div style={{ breakInside: 'avoid' }}>
                <Section n={1} title="FIGURES" meta="AS PUBLISHED" style={{ marginTop: 0 }} />
                {open.figures.length ? open.figures.map((f, i) => (
                  <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'baseline', padding: '3px 0', borderBottom: HAIRLINE }}>
                    <span style={{ ...LABEL_XS, flex: '0 0 34%' }}>{f.kind.replace(/_/g, ' ').toUpperCase()}</span>
                    <F tone={f.kind === 'missing' ? 'high' : f.kind === 'rescued' ? 'low' : 'text'}>{fmt(f.value)}</F>
                    <span style={{ ...LABEL_XS, ...clip, flex: 1 }} title={f.note ?? ''}>{f.note ?? ''}</span>
                    <span style={{ ...LABEL_XS, whiteSpace: 'nowrap' }}>{dtgDay(f.as_of)}</span>
                    <Grade code={gradeFor(f.source).code} />
                  </div>
                )) : <div style={{ ...PROSE, color: MS.muted }}>No per-project figure has been published by any source the desk has read.</div>}
                <Section n={2} title="TEAMS" meta="WHO IS DIGGING" />
                {open.teams.length ? open.teams.map((tm, i) => (
                  <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'baseline', padding: '3px 0', borderBottom: HAIRLINE }}>
                    <Tag tone={tm.country === 'NP' ? 'sub' : 'info'}>{FLAG[tm.country] ?? tm.country}</Tag>
                    <span style={{ ...CELL, color: MS.text, ...clip, flex: 1 }}>{tm.unit}</span>
                    <span style={{ ...LABEL_XS, ...clip, maxWidth: '40%' }}>{tm.source}</span>
                    <Grade code={gradeFor(tm.source).code} />
                  </div>
                )) : <div style={{ ...PROSE, color: MS.muted }}>No team assignment published.</div>}
                {open.promoter && <Note>Promoter / contractors: {open.promoter}. {open.coord_note ? `Position: ${open.coord_note}.` : ''}</Note>}
              </div>
              <div style={{ breakInside: 'avoid' }}>
                <Section n={3} title="RECORD" meta="LATEST FIRST" style={{ marginTop: 0 }} />
                {[...open.notes].sort((a, b) => (a.t_npt < b.t_npt ? 1 : -1)).map((n, i) => (
                  <div key={i} style={{ padding: '3px 0', borderBottom: HAIRLINE }}>
                    <div style={{ ...LABEL_XS, display: 'flex', gap: 8 }}>
                      <span>{dtgNpt(n.t_npt)}</span>
                      {n.auto && <span style={{ color: MS.high }}>AUTO · UNREVIEWED</span>}
                      <span style={{ ...clip, flex: 1 }}>{n.source}</span>
                      <Grade code={gradeFor(n.source).code} />
                      {n.url && <a href={n.url} target="_blank" rel="noreferrer noopener" style={{ color: MS.info, textDecoration: 'none' }}>SOURCE</a>}
                    </div>
                    <div style={{ ...PROSE, marginTop: 2 }}>{n.text}</div>
                  </div>
                ))}
                {(open.evidence ?? []).length > 0 && (
                  <>
                    <Section n={4} title="PRESS MENTIONS" meta="SCANNED FROM THE DESK'S STORY STORE · UNVERIFIED" />
                    {(open.evidence ?? []).slice(0, 8).map((e, i) => (
                      <a key={i} href={e.url ?? undefined} target="_blank" rel="noreferrer noopener" style={{ display: 'block', padding: '3px 0', borderBottom: HAIRLINE, textDecoration: 'none', color: 'inherit' }}>
                        <div style={{ ...LABEL_XS, display: 'flex', gap: 8 }}>
                          <span>{dtgDay(e.published_at)}</span>
                          <span style={{ ...clip, flex: 1 }}>{e.outlet ?? 'OUTLET NOT STATED'}</span>
                          <Grade code={gradeFor(e.outlet).code} />
                          {e.numbers.length > 0 && <span style={{ color: MS.sub }}>{e.numbers.slice(0, 3).map((v) => fmt(v)).join(' · ')}</span>}
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
