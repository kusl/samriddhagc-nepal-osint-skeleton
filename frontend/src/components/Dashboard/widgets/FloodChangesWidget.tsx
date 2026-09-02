/**
 * CHANGE LOG · 24H — what moved since yesterday, as the detector saw it.
 *
 * Reads GET /flood/changes. Each row is a difference between two published
 * states the desk holds (toll, a tunnel, a country, a site, the review queue),
 * with the before/after in the summary, the source, and whether the owner was
 * told. Empty means nothing moved, and says so.
 *
 * Milspec: fitted rows, one SourceLine, no rails, no scroll.
 */
import { memo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Activity } from 'lucide-react';

import { Widget } from '../Widget';
import apiClient from '../../../api/client';
import { floodKeys } from '../../../api/hooks/useFlood';
import { WidgetError, WidgetSkeleton } from './shared';
import { Body, CELL, HAIRLINE, LABEL_XS, MS, SourceLine, Stat, StatRow, Tag, clockNpt, fmt, type Tone } from '../../flood/milspec';

interface Change {
  id: string;
  kind: string;
  key: string;
  severity: 'critical' | 'high' | 'info' | string;
  summary: string;
  source: string | null;
  url: string | null;
  detected_at: string;
  notified_at: string | null;
  channels: string | null;
}
interface ChangesPayload {
  hours: number;
  count: number;
  channels: { telegram: boolean; email: boolean };
  changes: Change[];
}

const KIND_LABEL: Record<string, string> = { toll: 'TOLL', tunnel: 'TUNNEL', assistance: 'ASSISTANCE', site: 'SITE', facts: 'EXTRACTOR' };
const SEV_TONE: Record<string, Tone> = { critical: 'critical', high: 'high', info: 'info' };

export const FloodChangesWidget = memo(function FloodChangesWidget() {
  const q = useQuery<ChangesPayload>({
    queryKey: [...floodKeys.all, 'changes'] as const,
    queryFn: async () => (await apiClient.get('/flood/changes?hours=24')).data as ChangesPayload,
    staleTime: 2 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  });

  if (q.isLoading) {
    return (
      <Widget id="flood-changes" title="CHANGE LOG · 24H" icon={<Activity size={14} />}>
        <WidgetSkeleton />
      </Widget>
    );
  }
  if (q.error || !q.data) {
    return (
      <Widget id="flood-changes" title="CHANGE LOG · 24H" icon={<Activity size={14} />}>
        <WidgetError message="Failed to load the change log" onRetry={() => q.refetch()} />
      </Widget>
    );
  }

  const d = q.data;
  const critical = d.changes.filter((c) => c.severity === 'critical').length;
  const high = d.changes.filter((c) => c.severity === 'high').length;
  const alerted = d.changes.filter((c) => c.notified_at).length;
  const channelText = [d.channels.telegram ? 'TELEGRAM' : null, d.channels.email ? 'EMAIL' : null].filter(Boolean).join(' + ') || 'NO CHANNEL CONFIGURED';
  const rows = d.changes.slice(0, 7);

  return (
    <Widget
      id="flood-changes"
      title="CHANGE LOG · 24H"
      icon={<Activity size={14} />}
      badge={d.count ? `${d.count} MOVED` : 'NO MOVEMENT'}
      badgeVariant={critical ? 'critical' : high ? 'high' : 'default'}
    >
      <Body style={{ overflow: 'hidden' }}>
        <StatRow columns={4}>
          <Stat label="CHANGES DETECTED" value={fmt(d.count)} size={20} sub="differences between two published states" />
          <Stat label="CRITICAL · HIGH" value={`${critical} · ${high}`} tone={critical ? 'critical' : 'high'} size={20} sub="toll, tunnels, burial grounds" />
          <Stat label="OWNER ALERTED" value={fmt(alerted)} tone="info" size={20} sub={channelText} />
          <Stat label="DETECTOR" value="10 MIN" size={20} sub="runs after every feed sync" />
        </StatRow>
        <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
          {rows.length === 0 ? (
            <div style={{ ...LABEL_XS, padding: '8px 0' }}>NOTHING THE DESK WATCHES HAS MOVED IN THE LAST 24 HOURS</div>
          ) : rows.map((c) => (
            <div key={c.id} style={{ display: 'flex', gap: 10, alignItems: 'baseline', padding: '3px 0', borderBottom: HAIRLINE }}>
              <span style={{ ...LABEL_XS, flex: '0 0 52px', whiteSpace: 'nowrap' }}>{clockNpt(c.detected_at)}</span>
              <span style={{ flex: '0 0 84px' }}><Tag tone={SEV_TONE[c.severity] ?? 'muted'}>{KIND_LABEL[c.kind] ?? c.kind.toUpperCase()}</Tag></span>
              <span style={{ ...CELL, flex: 1, minWidth: 0, color: MS.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={c.summary}>{c.summary}</span>
              <span style={{ ...LABEL_XS, flex: '0 0 auto', whiteSpace: 'nowrap', color: c.notified_at ? MS.low : MS.muted }}>{c.notified_at ? `SENT · ${(c.channels ?? '').toUpperCase()}` : 'DESK ONLY'}</span>
            </div>
          ))}
        </div>
        <SourceLine source="DESK CHANGE DETECTOR · DIFFERENCES BETWEEN PUBLISHED STATES, NEVER INFERRED" grade={false} right={<span style={{ whiteSpace: 'nowrap' }}>{d.count > rows.length ? `${d.count - rows.length} MORE IN THE LOG` : ''}</span>} />
      </Body>
    </Widget>
  );
});
