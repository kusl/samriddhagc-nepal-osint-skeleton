import { memo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ExternalLink, History } from 'lucide-react';

import { Widget } from '../Widget';
import apiClient from '../../../api/client';
import { WidgetEmpty, WidgetError, WidgetSkeleton } from './shared';
import {
  Body,
  CELL,
  Grade,
  HAIRLINE,
  LABEL_XS,
  MS,
  PROSE,
  Scroll,
  SourceLine,
  Status,
  TableHead,
  Tag,
  dtgDay,
  dtgNpt,
  dtgZ,
  gradeFor,
  type Tone,
} from '../../flood/milspec';

interface ChronologyEntry {
  occurred_at: string;
  /** Same instant at +05:45 — the only one a Kathmandu desk should read. */
  occurred_at_npt: string;
  /** False when only the date was published; render no clock in that case. */
  time_published: boolean;
  kind: string;
  headline: string;
  detail: string | null;
  source: string | null;
  source_url: string | null;
}

interface ChronologyResponse {
  event_key: string;
  count: number;
  events: ChronologyEntry[];
}

const CHRONOLOGY_REFRESH = 5 * 60 * 1000;

/** Tone per beat, so a renewed-collapse warning never reads like a toll update. */
const KIND_TONE: Record<string, Tone> = {
  trigger: 'critical',
  impact: 'high',
  warning: 'high',
  assessment: 'medium',
  response: 'info',
};

const KIND_LABEL: Record<string, string> = {
  trigger: 'TRIGGER',
  impact: 'IMPACT',
  warning: 'ONGOING THREAT',
  assessment: 'ASSESSMENT',
  response: 'RESPONSE',
};

// Column template shared by the head and every beat.
const W = { dtg: '11%', kind: '8%', source: '16%' } as const;

const HEAD = [
  { label: 'DTG', width: W.dtg },
  { label: 'KIND', width: W.kind },
  { label: 'EVENT' },
  { label: 'SOURCE', width: W.source, align: 'right' as const },
];

function useFloodChronology() {
  return useQuery<ChronologyResponse>({
    queryKey: ['flood', 'chronology'] as const,
    queryFn: async () => (await apiClient.get('/flood/chronology')).data,
    refetchInterval: CHRONOLOGY_REFRESH,
    staleTime: 60 * 1000,
  });
}

/**
 * A beat row. <TableRow> is one nowrap line per cell, which would clip the
 * detail sentence, so the row is composed locally from MS tokens and keeps the
 * same hairline-and-columns grammar.
 */
function Beat({ entry }: { entry: ChronologyEntry }) {
  const grade = entry.source ? gradeFor(entry.source) : null;

  return (
    <div
      style={{
        display: 'flex',
        gap: 10,
        padding: '5px 0',
        borderBottom: HAIRLINE,
        alignItems: 'baseline',
      }}
    >
      {/* Timestamps arrive as fixed +05:45 strings and are READ, never re-zoned. */}
      <div style={{ flex: `0 0 ${W.dtg}`, minWidth: 0 }}>
        <div style={{ ...CELL, color: MS.text, whiteSpace: 'nowrap' }}>
          {dtgNpt(entry.occurred_at_npt, entry.time_published)}
        </div>
        <div style={{ ...LABEL_XS, whiteSpace: 'nowrap' }}>
          {entry.time_published ? dtgZ(entry.occurred_at_npt) : 'TIME NOT PUBLISHED'}
        </div>
      </div>

      <div style={{ flex: `0 0 ${W.kind}`, minWidth: 0 }}>
        <Tag tone={KIND_TONE[entry.kind] ?? 'muted'}>
          {KIND_LABEL[entry.kind] ?? entry.kind.toUpperCase()}
        </Tag>
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ ...CELL, color: MS.text, fontWeight: 600 }}>{entry.headline}</div>
        {entry.detail && <div style={{ ...PROSE, marginTop: 2 }}>{entry.detail}</div>}
      </div>

      <div style={{ flex: `0 0 ${W.source}`, minWidth: 0, textAlign: 'right' }}>
        {entry.source && (
          <div style={{ ...LABEL_XS, textTransform: 'none', letterSpacing: 0, lineHeight: 1.4 }}>
            {entry.source}
          </div>
        )}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'flex-end',
            gap: 6,
            marginTop: 3,
          }}
        >
          {grade && <Grade code={grade.code} />}
          {entry.source_url && (
            <a
              href={entry.source_url}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                ...LABEL_XS,
                color: MS.info,
                display: 'inline-flex',
                alignItems: 'center',
                gap: 3,
                textDecoration: 'none',
                whiteSpace: 'nowrap',
              }}
            >
              SOURCE
              <ExternalLink size={9} />
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

export const FloodChronologyWidget = memo(function FloodChronologyWidget() {
  const { data, isLoading, error, refetch } = useFloodChronology();

  if (isLoading) {
    return (
      <Widget id="flood-chronology" icon={<History size={14} />}>
        <WidgetSkeleton />
      </Widget>
    );
  }

  if (error || !data) {
    return (
      <Widget id="flood-chronology" icon={<History size={14} />}>
        <WidgetError message="Failed to load event chronology" onRetry={() => refetch()} />
      </Widget>
    );
  }

  // Ordering is authored server-side (occurred_at, then display_order); several
  // 26 Aug beats share a timestamp, so re-sorting here would put the surge
  // before the collapse that caused it.
  const events = data.events ?? [];

  if (events.length === 0) {
    return (
      <Widget id="flood-chronology" icon={<History size={14} />}>
        <WidgetEmpty message="No chronology recorded for the active event" />
      </Widget>
    );
  }

  const first = events[0];
  const last = events[events.length - 1];
  const threat = [...events].reverse().find((e) => e.kind === 'warning');
  const sources = new Set(events.map((e) => e.source).filter(Boolean)).size;

  return (
    <Widget
      id="flood-chronology"
      icon={<History size={14} />}
      badge={`${events.length} BEATS`}
      badgeVariant={threat ? 'high' : 'default'}
    >
      <Body>
        <div
          style={{
            display: 'flex',
            alignItems: 'baseline',
            gap: 12,
            paddingBottom: 4,
            flexShrink: 0,
          }}
        >
          <span style={{ ...LABEL_XS, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>
            {dtgNpt(first.occurred_at_npt, first.time_published)} →{' '}
            {dtgNpt(last.occurred_at_npt, last.time_published)}
          </span>
          <span style={{ flex: 1 }} />
          {threat && (
            <Status tone="high">ONGOING THREAT · {dtgDay(threat.occurred_at_npt)}</Status>
          )}
        </div>

        <TableHead cols={HEAD} />

        <Scroll>
          {events.map((entry) => (
            <Beat key={`${entry.occurred_at}-${entry.headline}`} entry={entry} />
          ))}
        </Scroll>

        <SourceLine source={`${events.length} ENTRIES · ${sources} SOURCES`} grade={false} />
      </Body>
    </Widget>
  );
});
