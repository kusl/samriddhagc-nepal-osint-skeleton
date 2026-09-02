/**
 * Hydropower tunnel rescue for the active flood event.
 *
 * Every figure here is authored by the backend `hydropower` situation panel, so
 * an NDRRMA/IPPAN revision reaches the desk without a frontend change. Nothing
 * is hardcoded and nothing is derived — the panel's own rows, note and source
 * line are rendered as published, through the MILSPEC grammar
 * (components/flood/milspec) that every flood-desk widget shares.
 */
import { memo } from 'react';
import { Zap } from 'lucide-react';

import { Widget } from '../Widget';
import { useOfficialSituation } from '../../../api/hooks/useFlood';
import { WidgetSkeleton, WidgetError, WidgetEmpty } from './shared';
import { Body, HAIRLINE, Note, Row, Scroll, SourceLine, Stat, dtgDay } from '../../flood/milspec';

/** Matches the tone the retired OfficialSituation panel grid gave this key:
 *  the headline counts people not yet accounted for. */
const TONE = 'high' as const;

export const FloodTunnelRescueWidget = memo(function FloodTunnelRescueWidget() {
  const { data, isLoading, error, refetch } = useOfficialSituation();

  if (isLoading) {
    return (
      <Widget id="flood-tunnel-rescue" icon={<Zap size={14} />}>
        <WidgetSkeleton />
      </Widget>
    );
  }

  if (error || !data) {
    return (
      <Widget id="flood-tunnel-rescue" icon={<Zap size={14} />}>
        <WidgetError message="Failed to load rescue figures" onRetry={() => refetch()} />
      </Widget>
    );
  }

  const panel = data.official.panels.find((p) => p.key === 'hydropower');

  if (!panel) {
    return (
      <Widget id="flood-tunnel-rescue" icon={<Zap size={14} />}>
        <WidgetEmpty message="No hydropower rescue figures published" />
      </Widget>
    );
  }

  return (
    <Widget
      id="flood-tunnel-rescue"
      icon={<Zap size={14} />}
      // The headline is the whole point of the panel; in the header it survives
      // a scrolled row list and a collapsed widget.
      badge={panel.headline_value ? `${panel.headline_value} MISSING` : undefined}
      badgeVariant="high"
    >
      <Body>
        <Stat
          label={panel.headline_label ?? panel.title}
          value={panel.headline_value ?? '—'}
          tone={TONE}
          sub={panel.subtitle}
          size={24}
        />

        <Scroll style={{ borderTop: HAIRLINE, paddingTop: 4 }}>
          {panel.rows.map((row) => (
            <Row key={row.label} label={row.label} value={row.value} />
          ))}
          {panel.note && <Note>{panel.note}</Note>}
        </Scroll>

        <SourceLine source={panel.source} asOf={panel.as_of ? dtgDay(panel.as_of) : null} />
      </Body>
    </Widget>
  );
});
