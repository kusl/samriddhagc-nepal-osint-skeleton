/**
 * Response-capacity view for the active flood event: who is in the field and
 * what they have pulled out. It is the counterweight to the toll widgets — the
 * same NDRRMA bulletin that carries the dead also carries the rescued, and
 * showing one without the other misreads the operation.
 *
 * Rendered through the MILSPEC grammar (components/flood/milspec): the widget is
 * one document — a two-cell stat head, one scrolling region carrying the two
 * ledgers side by side and the access and medical bands beneath them, and a
 * single source line outside the scroll. The old layout gave each ledger column
 * its own scroll inside a fixed-height band, which parked the taller column's
 * last row on the clip line and read as a truncated figure. One scroll over the
 * whole body removes the clip line entirely.
 *
 * Every figure is read from the backend situation panels. A literal number here
 * would be a bug.
 */
import { memo } from 'react';
import { LifeBuoy } from 'lucide-react';

import { Widget } from '../Widget';
import { useOfficialSituation } from '../../../api/hooks/useFlood';
import type { SituationPanel } from '../../../api/flood';
import { WidgetSkeleton, WidgetError, WidgetEmpty } from './shared';
import { Body, LABEL_XS, Note, Row, Scroll, Section, SourceLine, Stat, StatRow, dtgDay } from '../../flood/milspec';

/** Access is the binding constraint on this response, so it is lifted out of the
 *  operations ledger and stated once, beside the highway note that explains it. */
const ACCESS_ROW = /out of reach|unreachable|cut off/i;

/** NDRRMA publishes the flight count in both the rescued and the operations
 *  panel. It is an operations figure, so it is kept there and dropped from the
 *  rescued column — printing the same sortie count twice in one widget reads as
 *  two separate air efforts. */
const FLIGHTS_ROW = 'Rescue and relief flights flown';

/** The seed indents sub-totals with an em dash ("— of these, foreign"); the dash
 *  and the dimmed row carry that hierarchy, so no indent is applied — an
 *  indented content column inside a widget reads as a side rail. */
const isSubRow = (rowLabel: string) => rowLabel.trimStart().startsWith('—');

/**
 * The panel's own source, stamped on its <Section> head in the grammar's own
 * LABEL_XS. It goes in the head's `right` slot rather than its `meta` slot for
 * one reason: measured in JetBrains Mono at the widget's 6-column width, the
 * operations head ("SEARCH OPERATION AND SECURITY FORCES" + its source) needs
 * 450px in a 448px column, and a narrower widget makes that worse. `meta` is a
 * bare nowrap span, so the overflow spills across the column gutter. This span
 * carries the shrink itself (flexShrink far above the title's default 1) and
 * ellipsizes, with the full text verbatim in the tooltip. Same type, same rule,
 * nothing lost and nothing clipped.
 */
function HeadSource({ source }: { source: string | null }) {
  if (!source) return null;
  return (
    <span
      title={source}
      style={{
        ...LABEL_XS,
        flexShrink: 100,
        minWidth: 0,
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
      }}
    >
      {source}
    </span>
  );
}

export const FloodRescueOpsWidget = memo(function FloodRescueOpsWidget() {
  const { data, isLoading, error, refetch } = useOfficialSituation();

  if (isLoading) {
    return (
      <Widget id="flood-rescue-ops" title="Rescue Operations" icon={<LifeBuoy size={14} />}>
        <WidgetSkeleton />
      </Widget>
    );
  }

  if (error || !data) {
    return (
      <Widget id="flood-rescue-ops" title="Rescue Operations" icon={<LifeBuoy size={14} />}>
        <WidgetError message="Failed to load official situation" onRetry={() => refetch()} />
      </Widget>
    );
  }

  const panels = data.official.panels ?? [];
  const rescued = panels.find((p) => p.key === 'rescued');
  const operations = panels.find((p) => p.key === 'operations');
  const medical = panels.find((p) => p.key === 'medical');

  if (!rescued && !operations) {
    return (
      <Widget id="flood-rescue-ops" title="Rescue Operations" icon={<LifeBuoy size={14} />}>
        <WidgetEmpty message="No official rescue figures published for this event" />
      </Widget>
    );
  }

  const opsRows = operations?.rows ?? [];
  const accessRow = opsRows.find((r) => ACCESS_ROW.test(r.label));
  const opsLedgerRows = opsRows.filter((r) => r !== accessRow);
  const accessNote = operations?.note ?? null;

  // Exact-label match only: a substring test would also swallow a future
  // "Rescue and relief flights flown (Army)" that carries a different figure.
  const rescuedLedgerRows = (rescued?.rows ?? []).filter(
    (r) => !(r.label.trim() === FLIGHTS_ROW && opsLedgerRows.some((o) => o.label.trim() === FLIGHTS_ROW)),
  );

  const asOf = operations?.as_of ?? rescued?.as_of ?? null;

  // Built from the panels that actually came back, so <StatRow> is never asked
  // to draw a column it has no figure for — an empty cell in a hairline grid
  // paints as a bar, which the grammar does not allow.
  const heads = [
    { panel: rescued, tone: 'low' as const },
    { panel: operations, tone: 'info' as const },
  ].filter((h): h is { panel: SituationPanel; tone: 'low' | 'info' } => Boolean(h.panel));

  return (
    <Widget
      id="flood-rescue-ops"
      title="Rescue Operations"
      icon={<LifeBuoy size={14} />}
      badge={asOf ? `NDRRMA ${dtgDay(asOf)}` : undefined}
    >
      <Body>
        <StatRow columns={heads.length}>
          {heads.map((head) => (
            <Stat
              key={head.panel.key}
              label={head.panel.headline_label ?? head.panel.title}
              value={head.panel.headline_value ?? '—'}
              tone={head.tone}
              sub={head.panel.subtitle}
              size={24}
            />
          ))}
        </StatRow>

        <Scroll>
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: 24, alignItems: 'start' }}>
            <div style={{ minWidth: 0 }}>
              {rescued && (
                <>
                  <Section title={rescued.title} right={<HeadSource source={rescued.source} />} />
                  {rescuedLedgerRows.map((row) => (
                    <Row key={row.label} label={row.label} value={row.value} dim={isSubRow(row.label)} />
                  ))}
                  {rescued.note && <Note>{rescued.note}</Note>}
                </>
              )}
            </div>

            <div style={{ minWidth: 0 }}>
              {operations && (
                <>
                  <Section title={operations.title} right={<HeadSource source={operations.source} />} />
                  {opsLedgerRows.map((row) => (
                    <Row key={row.label} label={row.label} value={row.value} dim={isSubRow(row.label)} />
                  ))}
                </>
              )}
            </div>
          </div>

          {(accessRow || accessNote) && (
            <>
              <Section title="ACCESS" />
              {accessRow && <Row label={accessRow.label} value={accessRow.value} tone="high" />}
              {accessNote && <Note>{accessNote}</Note>}
            </>
          )}

          {medical && (
            <>
              <Section title="MEDICAL" right={<HeadSource source={medical.source} />} />
              {medical.headline_value && (
                <Row
                  label={medical.headline_label ?? medical.title}
                  value={medical.headline_value}
                  tone="medium"
                />
              )}
              {medical.rows.map((row) => (
                <Row key={row.label} label={row.label} value={row.value} dim={isSubRow(row.label)} />
              ))}
              {medical.note && <Note>{medical.note}</Note>}
            </>
          )}
        </Scroll>

        <SourceLine
          source={operations?.source ?? rescued?.source ?? null}
          asOf={asOf ? dtgDay(asOf) : null}
        />
      </Body>
    </Widget>
  );
});
