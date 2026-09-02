/**
 * NDRRMA SITREP LOG — the authority's own numbered situation reports, listed
 * exactly as they were published.
 *
 * This is a publication record, not an analysis. Every row is one PDF NDRRMA put
 * out: its date, its number as printed, the language it was written in, and the
 * link back to the file. The order is the API's order — newest first, ties left
 * alone. Sitrep numbering and sitrep dates disagree in this event (a report can
 * be published late, or two can share a day), so re-sorting by number here would
 * silently reshuffle the authority's own sequence.
 *
 * KEY FIGURES is read from the backend's `extracted` object, which exists only
 * where the English PDF parsed. Where it is null the cell says NOT PARSED rather
 * than borrowing a neighbouring report's numbers: the Nepali reports extract with
 * doubled vowel signs and are not parsed at all, and a blank would read as zero.
 */
import { memo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ExternalLink, FileText } from 'lucide-react';

import { Widget } from '../Widget';
import apiClient from '../../../api/client';
import { floodKeys } from '../../../api/hooks/useFlood';
import { WidgetEmpty, WidgetError, WidgetSkeleton } from './shared';
import {
  Body,
  CELL,
  F,
  HAIRLINE,
  LABEL_XS,
  MS,
  Note,
  Scroll,
  SourceLine,
  Stat,
  StatRow,
  TableHead,
  Tag,
  dtgDay,
  fmt,
  isNum,
  type Tone,
} from '../../flood/milspec';

// ------------------------------------------------------------------ payload

/** Figures parsed out of an English sitrep PDF; every key is optional. */
interface SitrepExtracted {
  deaths?: number | null;
  missing?: number | null;
  injured?: number | null;
  rescued?: number | null;
  personnel?: number | null;
  foreign_rescued?: number | null;
  bridges_washed?: number | null;
  bridges_damaged?: number | null;
  households_isolated?: number | null;
  population_isolated?: number | null;
  districts_affected?: number | null;
  highlights?: string[] | null;
}

interface Sitrep {
  id: string;
  source_id: number;
  /** As printed on the report ("# ११", "#8"); null where the title carried none. */
  number: number | null;
  lang: string;
  title: string | null;
  title_ne: string | null;
  report_date: string | null;
  /** As printed, e.g. "18:00 NPT" — never re-zoned, never inferred. */
  report_time: string | null;
  pdf_url: string | null;
  page_url: string | null;
  extracted: SitrepExtracted | null;
  fetched_at: string | null;
}

interface SitrepResponse {
  event_key: string;
  count: number;
  items: Sitrep[];
}

const EMPTY: SitrepResponse = { event_key: '', count: 0, items: [] };

const SITREP_STALE = 5 * 60 * 1000;
const SITREP_REFRESH = 10 * 60 * 1000;

const SITUATION_PAGE = 'https://ndrrma.gov.np/np/rasuwa/situation';

/**
 * The feed is built alongside this widget, so a missing router is the expected
 * state on a cold backend, not a fault worth showing a red retry for. Anything
 * else still throws and reaches <WidgetError>.
 */
function useFloodSitreps() {
  return useQuery<SitrepResponse>({
    queryKey: [...floodKeys.all, 'sitreps'] as const,
    queryFn: async () => {
      try {
        const res = await apiClient.get<SitrepResponse>('/flood/sitreps');
        return res.data ?? EMPTY;
      } catch (err) {
        const status = (err as { response?: { status?: number } })?.response?.status;
        if (status === 404) return EMPTY;
        throw err;
      }
    },
    staleTime: SITREP_STALE,
    refetchInterval: SITREP_REFRESH,
  });
}

// ------------------------------------------------------------------ figures

/**
 * Which parsed keys reach the KEY FIGURES cell, in reading order, and the tone
 * each carries. Deaths and missing are the toll; rescued and deployed are the
 * response. Only keys actually present in a report are rendered.
 */
const FIGURE_SPEC: Array<{ key: keyof SitrepExtracted; label: string; tone: Tone }> = [
  { key: 'deaths', label: 'DEAD', tone: 'critical' },
  { key: 'missing', label: 'MISSING', tone: 'high' },
  { key: 'injured', label: 'INJURED', tone: 'high' },
  { key: 'rescued', label: 'RESCUED', tone: 'low' },
  { key: 'personnel', label: 'DEPLOYED', tone: 'info' },
  { key: 'foreign_rescued', label: 'FOREIGN RESCUED', tone: 'low' },
  { key: 'households_isolated', label: 'HH ISOLATED', tone: 'high' },
  { key: 'bridges_washed', label: 'BRIDGES LOST', tone: 'high' },
  { key: 'districts_affected', label: 'DISTRICTS', tone: 'info' },
];

function KeyFigures({ extracted }: { extracted: SitrepExtracted | null }) {
  const parts = extracted
    ? FIGURE_SPEC.filter((s) => isNum(extracted[s.key] as number | null | undefined))
    : [];

  if (parts.length === 0) {
    return <span style={{ ...LABEL_XS, color: MS.muted }}>NOT PARSED</span>;
  }

  const plain = parts
    .map((s) => `${fmt(extracted?.[s.key] as number)} ${s.label}`)
    .join(' · ');

  return (
    <span title={plain}>
      {parts.map((s, i) => (
        <span key={s.key}>
          {i > 0 && <span style={{ color: MS.disabled }}> {'·'} </span>}
          <F tone={s.tone}>{fmt(extracted?.[s.key] as number)}</F>
          <span style={{ color: MS.muted }}> {s.label}</span>
        </span>
      ))}
    </span>
  );
}

// ------------------------------------------------------------------ columns

const W = { dtg: '16%', num: '6%', lang: '7%', figures: '30%', pdf: '6%' } as const;

const HEAD = [
  { label: 'DTG', width: W.dtg },
  { label: '#', width: W.num },
  { label: 'LANG', width: W.lang },
  { label: 'TITLE' },
  { label: 'KEY FIGURES', width: W.figures },
  { label: 'PDF', width: W.pdf },
];

/** The title the report was actually written under, in its own language. */
function titleOf(s: Sitrep): string {
  const preferred = s.lang === 'ne' ? s.title_ne : s.title;
  return (preferred || s.title || s.title_ne || '—').trim();
}

/**
 * One published report. <TableRow> is a single nowrap line per cell and the DTG
 * cell is two (day, then the clock as printed), so the row is composed here from
 * the same CELL/HAIRLINE tokens the chronology beat uses.
 */
function SitrepRow({ item }: { item: Sitrep }) {
  const title = titleOf(item);

  return (
    <div
      style={{
        display: 'flex',
        gap: 10,
        padding: '4px 0',
        borderBottom: HAIRLINE,
        alignItems: 'baseline',
      }}
    >
      <div style={{ flex: `0 0 ${W.dtg}`, minWidth: 0 }}>
        <div style={{ ...CELL, color: MS.text, whiteSpace: 'nowrap' }}>{dtgDay(item.report_date)}</div>
        {item.report_time && (
          <div style={{ ...LABEL_XS, whiteSpace: 'nowrap' }}>{item.report_time}</div>
        )}
      </div>

      <div
        style={{
          ...CELL,
          flex: `0 0 ${W.num}`,
          minWidth: 0,
          color: isNum(item.number) ? MS.text : MS.disabled,
          whiteSpace: 'nowrap',
        }}
      >
        {isNum(item.number) ? item.number : '—'}
      </div>

      <div style={{ flex: `0 0 ${W.lang}`, minWidth: 0 }}>
        {item.lang === 'en' ? <Tag tone="info">EN</Tag> : <Tag>NE</Tag>}
      </div>

      <div
        style={{
          ...CELL,
          flex: 1,
          minWidth: 0,
          color: MS.text,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
        title={title}
      >
        {title}
      </div>

      <div
        style={{
          ...CELL,
          flex: `0 0 ${W.figures}`,
          minWidth: 0,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        <KeyFigures extracted={item.extracted} />
      </div>

      <div style={{ flex: `0 0 ${W.pdf}`, minWidth: 0 }}>
        {item.pdf_url ? (
          <a
            href={item.pdf_url}
            target="_blank"
            rel="noreferrer noopener"
            title="Open the published PDF"
            style={{
              ...LABEL_XS,
              color: MS.info,
              textDecoration: 'none',
              display: 'inline-flex',
              alignItems: 'center',
            }}
          >
            <ExternalLink size={10} />
          </a>
        ) : (
          <span style={{ color: MS.disabled, ...CELL }}>{'—'}</span>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ widget

export const FloodSitrepLogWidget = memo(function FloodSitrepLogWidget() {
  const { data, isLoading, error, refetch } = useFloodSitreps();

  if (isLoading) {
    return (
      <Widget id="flood-sitrep-log" title="NDRRMA SITREP LOG" icon={<FileText size={14} />}>
        <WidgetSkeleton />
      </Widget>
    );
  }

  if (error || !data) {
    return (
      <Widget id="flood-sitrep-log" title="NDRRMA SITREP LOG" icon={<FileText size={14} />}>
        <WidgetError message="Failed to load the NDRRMA sitrep log" onRetry={() => refetch()} />
      </Widget>
    );
  }

  // Server order is the publication order and is kept: numbers and dates
  // disagree in this event, so any local sort would rewrite NDRRMA's sequence.
  const items = data.items ?? [];

  if (items.length === 0) {
    return (
      <Widget id="flood-sitrep-log" title="NDRRMA SITREP LOG" icon={<FileText size={14} />}>
        <WidgetEmpty message="No situation reports fetched yet" />
      </Widget>
    );
  }

  const newest = items[0];
  const english = items.filter((s) => s.lang === 'en').length;

  return (
    <Widget
      id="flood-sitrep-log"
      title="NDRRMA SITREP LOG"
      icon={<FileText size={14} />}
      badge={`${fmt(items.length)} REPORTS`}
    >
      <Body>
        <StatRow columns={3}>
          <Stat label="Reports" value={fmt(items.length)} tone="text" size={18} />
          <Stat
            label="Latest"
            value={dtgDay(newest.report_date)}
            tone="text"
            size={18}
            sub={newest.report_time ?? undefined}
          />
          <Stat
            label="English"
            value={fmt(english)}
            tone="info"
            size={18}
            sub={`of ${fmt(items.length)}`}
          />
        </StatRow>

        <TableHead cols={HEAD} />

        <Scroll>
          {items.map((item) => (
            <SitrepRow key={item.id} item={item} />
          ))}
        </Scroll>

        <Note>
          Official NDRRMA situation reports, listed as published. Figures shown are parsed from the
          English reports only; Nepali reports link to the PDF.
        </Note>

        <SourceLine
          source="NDRRMA · publication/rasuwa-sitrep"
          asOf={dtgDay(newest.report_date)}
          url={newest.page_url ?? SITUATION_PAGE}
        />
      </Body>
    </Widget>
  );
});
