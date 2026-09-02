/**
 * Source Reliability Matrix — every source the flood desk actually draws on,
 * each carrying the desk's own NATO Admiralty grade.
 *
 * The row set is DERIVED, never authored here. It is assembled by scanning the
 * same four API responses the rest of the desk renders: the official situation
 * (toll authority, conflicting authorities, situation panels), the cited
 * reporting record, the chronology, and the river gauge net. If a source stops
 * appearing in those payloads it leaves this matrix on its own; if a new outlet
 * is cited tomorrow it arrives graded without a frontend change. A hand-typed
 * roster would drift the moment the backend moved, and a matrix that disagrees
 * with the widgets beside it is worse than no matrix.
 *
 * The grade is the desk's assessment of the SOURCE, not a verdict on any one
 * figure it published — the note under the table says so, and the footer line
 * is stamped DESK ASSESSMENT rather than borrowing an authority's name.
 */
import { memo, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ExternalLink, ShieldCheck } from 'lucide-react';

import { Widget } from '../Widget';
import apiClient from '../../../api/client';
import { floodKeys, useFloodRivers, useOfficialSituation } from '../../../api/hooks/useFlood';
import { WidgetEmpty, WidgetError, WidgetSkeleton } from './shared';
import {
  Body,
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
  Tag,
  dtgDay,
  fmt,
  gradeFor,
  type SourceGrade,
} from '../../flood/milspec';

// ------------------------------------------------------------------ payloads

/** Mirrors FloodCitedReportingWidget's contract; only the fields scanned here. */
interface Citation {
  outlet: string;
  date: string | null;
  url: string | null;
  theme: string;
}

interface FloodCitations {
  count: number;
  items: Citation[];
}

/** Mirrors FloodChronologyWidget's contract; only the fields scanned here. */
interface ChronologyEntry {
  occurred_at_npt: string;
  source: string | null;
  source_url: string | null;
}

interface ChronologyResponse {
  count: number;
  events: ChronologyEntry[];
}

// ------------------------------------------------------------------ dedupe

/**
 * Sources arrive spelled however their publisher wrote them: "NDRRMA",
 * "NDRRMA bulletin, 1 Sept 2026 09:00 NPT", "Nepal Police (Kathmandu)". The
 * matrix must show one row per source, so names are normalised to lowercase
 * alphanumeric words before comparison.
 */
const norm = (s: string): string =>
  s.toLowerCase().replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' ').trim();

/**
 * Whole-word containment: a dated bulletin string folds into the bare authority
 * it names. Word-boundary padded rather than a raw substring test, so a short
 * key like "ap" cannot swallow an unrelated name that merely spells it inside a
 * longer word.
 */
const contains = (haystack: string, needle: string): boolean =>
  ` ${haystack} `.includes(` ${needle} `);

/** Day precision only: bulletin dates and citation dates are plain ISO days. */
const day = (iso: string | null | undefined): string | null => (iso ? iso.slice(0, 10) : null);

const MONTH_WORDS: Record<string, string> = {
  jan: '01', january: '01', feb: '02', february: '02', mar: '03', march: '03',
  apr: '04', april: '04', may: '05', jun: '06', june: '06', jul: '07', july: '07',
  aug: '08', august: '08', sep: '09', sept: '09', september: '09',
  oct: '10', october: '10', nov: '11', november: '11', dec: '12', december: '12',
};

const pad2 = (v: string): string => v.padStart(2, '0');

/**
 * Is this trailing fragment a date stamp rather than part of the source's name?
 * Returns the ISO day where the fragment carries one, the empty string where it
 * is a date but names no year, and null where it is not a date at all.
 */
function readDateTail(tail: string): string | null {
  const core = tail
    .trim()
    .replace(/\s+/g, ' ')
    // "09:00 NPT" — a punctuated clock, with or without its zone.
    .replace(/\s+\d{1,2}[:.]\d{2}(\s*[A-Za-z]{2,4})?$/, '')
    // "0900 NPT" — an unpunctuated clock, only ever when a zone follows it, so
    // that a bare four-digit year is never mistaken for a time and eaten.
    .replace(/\s+\d{4}\s+[A-Za-z]{2,4}$/, '')
    .trim();

  const iso = /^(\d{4})-(\d{2})-(\d{2})$/.exec(core);
  if (iso) return core;

  const dmy = /^(\d{1,2})\s+([A-Za-z]{3,9})\.?(?:,?\s+(\d{4}))?$/.exec(core);
  if (dmy) {
    const m = MONTH_WORDS[dmy[2].toLowerCase()];
    if (m) return dmy[3] ? `${dmy[3]}-${m}-${pad2(dmy[1])}` : '';
  }

  const mdy = /^([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:,?\s+(\d{4}))?$/.exec(core);
  if (mdy) {
    const m = MONTH_WORDS[mdy[1].toLowerCase()];
    if (m) return mdy[3] ? `${mdy[3]}-${m}-${pad2(mdy[2])}` : '';
  }

  return null;
}

/**
 * Several backend sources carry their own timestamp inside the name string:
 * "NDRRMA bulletin, 1 Sept 2026 09:00 NPT", "Nepal Police / diplomatic missions
 * · 1 Sept", "ICIMOD · Sept 1, 2026". Left alone, the same authority splits into
 * a new row every time it publishes, so the stamp is peeled off the display name
 * and the dedupe key before folding.
 *
 * Separators are tried from the last backwards, because a stamp can contain one
 * of its own: splitting "ICIMOD · Sept 1, 2026" at the comma leaves a bare year
 * that reads as nothing, while splitting at the middot recovers the whole date.
 * A year-less stamp is dropped rather than given a guessed year — the payload's
 * own as_of/date field is what reaches the LATEST column in that case.
 */
function stripDateSuffix(raw: string): { name: string; date: string | null } {
  let name = raw.trim();
  let date: string | null = null;

  for (let pass = 0; pass < 3; pass += 1) {
    const seps: number[] = [];
    for (let i = 0; i < name.length; i += 1) {
      if (name[i] === ',' || name[i] === '\u00b7') seps.push(i);
    }

    let cut = -1;
    let found: string | null = null;
    for (let s = seps.length - 1; s >= 0; s -= 1) {
      const read = readDateTail(name.slice(seps[s] + 1));
      if (read !== null) {
        cut = seps[s];
        found = read;
        break;
      }
    }

    if (cut < 0) break;
    const remainder = name.slice(0, cut).trim();
    // A name that is nothing but a date is left exactly as published.
    if (!remainder) break;
    if (found && !date) date = found;
    name = remainder;
  }

  return { name, date };
}

interface MatrixRow {
  key: string;
  name: string;
  usedFor: string[];
  date: string | null;
  url: string | null;
  sub: string | null;
}

interface GradedRow extends MatrixRow {
  grade: SourceGrade;
}

/**
 * Fold one observed source into the row set. Merges used-for labels, keeps the
 * newest date and the first URL, and lets the shorter name win so the matrix
 * reads "NDRRMA" rather than a timestamped bulletin title.
 */
function absorb(
  rows: MatrixRow[],
  name: string | null | undefined,
  usedFor: string,
  date?: string | null,
  url?: string | null,
  sub?: string | null,
): void {
  if (!name) return;
  // The stamp comes off before anything else: it is not part of the name, and
  // leaving it on would key a fresh row per bulletin.
  const { name: clean, date: stamped } = stripDateSuffix(name);
  const key = norm(clean);
  if (!key) return;

  const hit = rows.find((r) => r.key === key || contains(r.key, key) || contains(key, r.key));
  // The payload's own date field wins; the stamp read off the name is a fallback.
  const when = day(date) ?? (stamped || null);

  if (!hit) {
    rows.push({ key, name: clean, usedFor: [usedFor], date: when, url: url ?? null, sub: sub ?? null });
    return;
  }

  if (!hit.usedFor.includes(usedFor)) hit.usedFor.push(usedFor);
  if (when && (!hit.date || when > hit.date)) hit.date = when;
  if (!hit.url && url) hit.url = url;
  if (!hit.sub && sub) hit.sub = sub;
  // The shorter spelling is the source's name; the longer one was a bulletin title.
  if (key.length < hit.key.length) {
    hit.key = key;
    hit.name = clean;
  }
}

/** Reading order of the matrix: what the desk counts on, before what it merely reads. */
const KIND_ORDER: SourceGrade['kind'][] = [
  'OFFICIAL',
  'INSTRUMENT',
  'IMAGERY',
  'WIRE',
  'NGO',
  'INDUSTRY',
  'OPEN',
];

const COLS = [
  { label: 'SOURCE', width: '22%' },
  { label: 'KIND', width: '9%' },
  { label: 'GRADE', width: '6%' },
  { label: 'BASIS', width: '30%' },
  { label: 'ON THIS DESK', width: '21%' },
  { label: 'LATEST', width: '8%', align: 'right' as const },
  { label: '↗', width: '4%' },
];

function SourceRef({ url }: { url: string | null }) {
  if (!url) return <span style={{ color: MS.disabled }}>—</span>;
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer noopener"
      style={{ ...LABEL_XS, color: MS.info, textDecoration: 'none', display: 'inline-flex', alignItems: 'center' }}
    >
      <ExternalLink size={9} />
    </a>
  );
}

// ------------------------------------------------------------------ widget

export const FloodSourceMatrixWidget = memo(function FloodSourceMatrixWidget() {
  const situation = useOfficialSituation();
  const rivers = useFloodRivers();

  // Keys are the ones the citation and chronology widgets already own, so all
  // three surfaces share one cache entry and can never disagree about a source.
  const citations = useQuery<FloodCitations>({
    queryKey: [...floodKeys.all, 'citations'] as const,
    queryFn: async () => (await apiClient.get('/flood/citations')).data,
    staleTime: 60 * 60 * 1000,
  });

  const chronology = useQuery<ChronologyResponse>({
    queryKey: ['flood', 'chronology'] as const,
    queryFn: async () => (await apiClient.get('/flood/chronology')).data,
    staleTime: 60 * 1000,
  });

  const rows = useMemo<GradedRow[]>(() => {
    const acc: MatrixRow[] = [];

    const official = situation.data?.official;
    if (official) {
      absorb(acc, official.latest?.authority, 'Official toll', official.latest?.as_of, official.latest?.source_url);
      for (const c of official.conflicting_reports ?? []) {
        absorb(acc, c.authority, 'Toll cross-check', c.as_of, c.source_url);
      }
      for (const p of official.panels ?? []) {
        absorb(acc, p.source, `Panel: ${p.title}`, p.as_of);
      }
    }

    for (const item of citations.data?.items ?? []) {
      absorb(acc, item.outlet, `Reporting: ${item.theme}`, item.date, item.url);
    }

    for (const e of chronology.data?.events ?? []) {
      absorb(acc, e.source, 'Chronology', e.occurred_at_npt, e.source_url);
    }

    const stations = rivers.data?.stations ?? [];
    if (stations.length > 0) {
      // "Reporting" matches the backend's own definition (flood_service): a gauge
      // is reporting when it carries a flood state, not an instrument state.
      const reporting = stations.filter(
        (s) => s.alert === 'danger' || s.alert === 'warning' || s.alert === 'normal',
      );
      const newest = stations.reduce<string | null>(
        (best, s) => (s.reading_at && (!best || s.reading_at > best) ? s.reading_at : best),
        null,
      );
      absorb(
        acc,
        'DHM river gauge telemetry',
        'Gauge net',
        newest,
        null,
        `${fmt(reporting.length)}/${fmt(stations.length)} stations reporting`,
      );
    }

    const bipad = situation.data?.bipad_cross_check;
    if (bipad) {
      absorb(
        acc,
        'BIPAD incident feed',
        'Cross-check only',
        null,
        null,
        `${fmt(bipad.incidents)} incidents · ${fmt(bipad.deaths)} deaths in ${fmt(bipad.window_days)}d`,
      );
    }

    return acc
      .map((r) => ({ ...r, grade: gradeFor(r.name) }))
      .sort((a, b) => {
        const k = KIND_ORDER.indexOf(a.grade.kind) - KIND_ORDER.indexOf(b.grade.kind);
        return k !== 0 ? k : a.grade.code.localeCompare(b.grade.code);
      });
  }, [situation.data, citations.data, chronology.data, rivers.data]);

  const tally = useMemo(() => {
    let strong = 0;
    let fair = 0;
    let unassessed = 0;
    for (const r of rows) {
      const letter = r.grade.code[0];
      if (letter === 'A' || letter === 'B') strong += 1;
      else if (letter === 'C' || letter === 'D') fair += 1;
      else unassessed += 1;
    }
    return { strong, fair, unassessed };
  }, [rows]);

  const loading =
    situation.isLoading || citations.isLoading || chronology.isLoading || rivers.isLoading;

  if (loading) {
    return (
      <Widget id="flood-source-matrix" icon={<ShieldCheck size={14} />}>
        <WidgetSkeleton />
      </Widget>
    );
  }

  if (situation.error || !situation.data) {
    return (
      <Widget id="flood-source-matrix" icon={<ShieldCheck size={14} />}>
        <WidgetError
          message="Failed to load the source matrix"
          onRetry={() => {
            situation.refetch();
            citations.refetch();
            chronology.refetch();
            rivers.refetch();
          }}
        />
      </Widget>
    );
  }

  if (rows.length === 0) {
    return (
      <Widget id="flood-source-matrix" icon={<ShieldCheck size={14} />}>
        <WidgetEmpty message="No sources published for the active event" />
      </Widget>
    );
  }

  const groups = KIND_ORDER.map((kind) => ({ kind, items: rows.filter((r) => r.grade.kind === kind) }))
    .filter((g) => g.items.length > 0);

  return (
    <Widget id="flood-source-matrix" icon={<ShieldCheck size={14} />} badge={`${fmt(rows.length)} SOURCES`}>
      <Body>
        <StatRow columns={4}>
          <Stat label="Sources" value={fmt(rows.length)} tone="text" size={20} />
          <Stat label="Graded A–B" value={fmt(tally.strong)} tone="low" size={20} />
          <Stat label="Graded C–D" value={fmt(tally.fair)} tone="medium" size={20} />
          <Stat label="Unassessed F" value={fmt(tally.unassessed)} tone="muted" size={20} />
        </StatRow>

        <TableHead cols={COLS} />

        <Scroll>
          {groups.map((group) => (
            <div key={group.kind}>
              <Section title={group.kind} meta={fmt(group.items.length)} />
              {group.items.map((r) => (
                <TableRow
                  key={r.key}
                  cells={[
                    { node: r.name, width: COLS[0].width },
                    { node: <Tag>{r.grade.kind}</Tag>, width: COLS[1].width },
                    { node: <Grade code={r.grade.code} />, width: COLS[2].width },
                    { node: r.grade.basis, width: COLS[3].width, tone: 'muted' },
                    {
                      node: (
                        <>
                          {r.usedFor.join(' · ')}
                          {r.sub && (
                            <span style={{ ...LABEL_XS, textTransform: 'none', letterSpacing: 0, marginLeft: 6 }}>
                              {r.sub}
                            </span>
                          )}
                        </>
                      ),
                      width: COLS[4].width,
                    },
                    { node: dtgDay(r.date), width: COLS[5].width, align: 'right' },
                    { node: <SourceRef url={r.url} />, width: COLS[6].width },
                  ]}
                />
              ))}
            </div>
          ))}
        </Scroll>

        <Note>
          Desk-assigned Admiralty grades. Letter = source reliability A–F. Digit = information
          credibility 1–6. A grade is the desk’s assessment of the source, not of any single figure.
        </Note>

        <SourceLine
          source="DESK ASSESSMENT"
          grade={false}
          asOf={dtgDay(situation.data.official.latest?.as_of)}
        />
      </Body>
    </Widget>
  );
});
