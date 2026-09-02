/**
 * The cite tier: findings this desk repeats from coverage it is not licensed to
 * reproduce.
 *
 * Separate from the Published Imagery Record next door because that widget
 * catalogues acquisitions and map products — sensor, area, acquisition dates —
 * while these rows are claims: a toll, a bridge count, a WASH damage figure.
 * Forcing "17,000 children psychologically impacted" into a product card would
 * have meant inventing a sensor for it.
 *
 * LICENSING IS LOAD-BEARING. Everything here is a citation and nothing more:
 * headline, outlet, date, finding, link out. No <img> tag appears in this file,
 * no OpenGraph scrape, no favicon fetch, no thumbnail of any kind — a reader
 * must never be able to mistake a line we cite for a picture we host.
 *
 * Where the briefing carried no date and no verified URL — AP, the NYT, UN News,
 * the three Ratopati items — the row prints neither. A guessed date and a
 * guessed link are the same failure.
 *
 * Rendered as a MILSPEC ledger: the row is drawn locally rather than with
 * <TableRow> because <TableRow> single-lines every cell, and a finding needs two
 * lines with its citation set under it. Same column widths, same CELL/HAIRLINE
 * grammar, no borders but the horizontal hairline.
 */
import { memo, useMemo, useState } from 'react';
import type { CSSProperties } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ExternalLink, Newspaper } from 'lucide-react';

import { Widget } from '../Widget';
import apiClient from '../../../api/client';
import { floodKeys } from '../../../api/hooks/useFlood';
import { WidgetSkeleton, WidgetError } from './shared';
import {
  MS,
  LABEL_XS,
  CELL,
  HAIRLINE,
  dtgDay,
  gradeFor,
  gradeTitle,
  Grade,
  Tag,
  TableHead,
  Note,
  Body,
  Scroll,
  SourceLine,
} from '../../flood/milspec';
import type { Tone } from '../../flood/milspec';

interface Citation {
  outlet: string;
  headline: string;
  /** null where the briefing stated no publication date — never guessed. */
  date: string | null;
  finding: string;
  /** null where no URL was verified. A row without one is plain text. */
  url: string | null;
  theme: string;
  /** Present only where the publisher's terms need restating, e.g. EMS maps. */
  rights?: string | null;
  tier: string;
  display_order: number;
}

interface FloodCitations {
  event_key: string;
  tier: string;
  count: number;
  items: Citation[];
  note: string | null;
}

/** Same reading as the imagery catalogue's type tones: what kind of claim this is. */
const THEME_TONE: Record<string, Tone> = {
  imagery: 'info',
  toll: 'critical',
  infrastructure: 'high',
  humanitarian: 'medium',
};

const THEME_FILTERS = [
  { key: 'all', label: 'ALL' },
  { key: 'imagery', label: 'IMAGERY' },
  { key: 'toll', label: 'TOLL' },
  { key: 'infrastructure', label: 'INFRA' },
  { key: 'humanitarian', label: 'HUMAN' },
] as const;

type ThemeFilter = (typeof THEME_FILTERS)[number]['key'];

/** Column geometry, shared by the head and every row. */
const COLS = {
  dtg: '9%',
  outlet: '20%',
  grade: '6%',
  theme: '9%',
  link: '4%',
} as const;

const HEAD = [
  { label: 'DTG', width: COLS.dtg },
  { label: 'OUTLET', width: COLS.outlet },
  { label: 'GRADE', width: COLS.grade },
  { label: 'THEME', width: COLS.theme },
  { label: 'FINDING' },
  { label: '↗', width: COLS.link },
];

const fixedCell = (width: string): CSSProperties => ({
  ...CELL,
  flex: `0 0 ${width}`,
  minWidth: 0,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  color: MS.sub,
});

/**
 * Two-line clamp. <TableRow> cannot do this — it pins every cell to one line —
 * so the clamp is implemented here on MS tokens only.
 */
const CLAMP2: CSSProperties = {
  ...CELL,
  color: MS.sub,
  whiteSpace: 'normal',
  display: '-webkit-box',
  WebkitLineClamp: 2,
  WebkitBoxOrient: 'vertical',
  overflow: 'hidden',
};

const CLAMP1: CSSProperties = {
  ...LABEL_XS,
  textTransform: 'none',
  letterSpacing: '0.02em',
  marginTop: 2,
  whiteSpace: 'nowrap',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
};

const fetchCitations = async (): Promise<FloodCitations> =>
  (await apiClient.get('/flood/citations')).data;

function CitationRow({ item }: { item: Citation }) {
  const grade = gradeFor(item.outlet);

  return (
    <div
      style={{
        display: 'flex',
        gap: 10,
        padding: '4px 0',
        borderBottom: HAIRLINE,
        alignItems: 'flex-start',
      }}
    >
      <span style={{ ...fixedCell(COLS.dtg), color: MS.text }}>{dtgDay(item.date)}</span>
      <span style={fixedCell(COLS.outlet)} title={item.outlet}>
        {item.outlet}
      </span>
      <span style={{ ...fixedCell(COLS.grade), overflow: 'visible' }}>
        <Grade code={grade.code} title={gradeTitle(grade.code)} />
      </span>
      <span style={{ ...fixedCell(COLS.theme), overflow: 'visible' }}>
        <Tag tone={THEME_TONE[item.theme]}>{item.theme}</Tag>
      </span>

      {/* The claim carries the weight; the headline sits under it in citation
          register — the inverse of a news card, on purpose. */}
      <span style={{ flex: 1, minWidth: 0 }}>
        <span style={CLAMP2} title={item.headline}>
          {item.finding}
        </span>
        <span style={{ ...CLAMP1, display: 'block' }} title={item.headline}>
          {item.headline}
        </span>
        {item.rights && (
          <span style={{ ...CLAMP1, display: 'block', color: MS.disabled }} title={item.rights}>
            {item.rights}
          </span>
        )}
      </span>

      {/* Link out only. No verified URL means no anchor: a dead link and an
          invented one are the same lie to a reader who clicks. */}
      <span style={{ ...fixedCell(COLS.link), textAlign: 'right', color: MS.disabled }}>
        {item.url ? (
          <a
            href={item.url}
            target="_blank"
            rel="noreferrer noopener"
            title={item.headline}
            style={{ color: MS.info, display: 'inline-flex', alignItems: 'center', textDecoration: 'none' }}
          >
            <ExternalLink size={10} />
          </a>
        ) : (
          '—'
        )}
      </span>
    </div>
  );
}

export const FloodCitedReportingWidget = memo(function FloodCitedReportingWidget() {
  const [themeFilter, setThemeFilter] = useState<ThemeFilter>('all');

  // Declared inline rather than in api/hooks/useFlood.ts because the shared
  // flood client is owned by another agent this run; the key is namespaced under
  // the same 'flood' root so it invalidates with the rest of the desk.
  const { data, isLoading, error, refetch } = useQuery<FloodCitations>({
    queryKey: [...floodKeys.all, 'citations'] as const,
    queryFn: fetchCitations,
    // A closed, hand-verified editorial record. It changes when someone edits it.
    staleTime: 60 * 60 * 1000,
  });

  const counts = useMemo(() => {
    const acc: Record<ThemeFilter, number> = {
      all: 0, imagery: 0, toll: 0, infrastructure: 0, humanitarian: 0,
    };
    for (const item of data?.items ?? []) {
      acc.all += 1;
      if (item.theme in acc) acc[item.theme as ThemeFilter] += 1;
    }
    return acc;
  }, [data]);

  const outlets = useMemo(
    () => new Set((data?.items ?? []).map((i) => i.outlet)).size,
    [data],
  );

  const items = useMemo(
    () => (data?.items ?? []).filter((i) => themeFilter === 'all' || i.theme === themeFilter),
    [data, themeFilter],
  );

  if (isLoading) {
    return (
      <Widget id="flood-cited-reporting" title="REPORTING LOG" icon={<Newspaper size={14} />}>
        <WidgetSkeleton />
      </Widget>
    );
  }

  if (error || !data) {
    return (
      <Widget id="flood-cited-reporting" title="REPORTING LOG" icon={<Newspaper size={14} />}>
        <WidgetError message="Failed to load cited reporting" onRetry={() => refetch()} />
      </Widget>
    );
  }

  return (
    <Widget id="flood-cited-reporting" title="REPORTING LOG" icon={<Newspaper size={14} />} badge="CITE ONLY">
      <Body>
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', flex: '0 0 auto', paddingBottom: 6 }}>
          {THEME_FILTERS.map((opt) => (
            <Tag
              key={opt.key}
              active={themeFilter === opt.key}
              onClick={() => setThemeFilter(opt.key)}
            >
              {opt.label} {counts[opt.key]}
            </Tag>
          ))}
        </div>

        <TableHead cols={HEAD} />

        <Scroll>
          {items.length === 0 ? (
            <div style={{ ...LABEL_XS, padding: '6px 0' }}>
              NO CITATIONS IN THIS THEME
            </div>
          ) : (
            items.map((item) => (
              <CitationRow key={`${item.outlet}:${item.headline}`} item={item} />
            ))
          )}
        </Scroll>

        <Note>
          Cited and linked only. No image, rehosting or thumbnail from these sources appears on
          this desk.
        </Note>

        <SourceLine source={`${data.count} CITATIONS · ${outlets} OUTLETS`} grade={false} />
      </Body>
    </Widget>
  );
});
