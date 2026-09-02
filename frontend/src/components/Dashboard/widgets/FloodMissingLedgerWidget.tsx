/**
 * Missing persons ledger for the active flood event.
 *
 * The missing total and the foreign-national breakdown sit in one widget
 * because the foreign nationals are a row *inside* the authority's missing
 * total — split across two widgets the reader would be left reconciling two
 * totals that were never meant to be added. Side by side, in two columns of one
 * grid with nothing but whitespace between them, the subset relationship reads
 * itself.
 *
 * Every figure is rendered verbatim from the panel payload. Nothing is summed,
 * converted or reconciled here — including Tibet's separately counted missing,
 * whose exclusion the panel note states and this widget keeps as a note under
 * the column it qualifies.
 */
import { memo } from 'react';
import { UserSearch } from 'lucide-react';

import { Widget } from '../Widget';
import { useOfficialSituation } from '../../../api/hooks/useFlood';
import type { SituationPanel } from '../../../api/flood';
import { WidgetSkeleton, WidgetError, WidgetEmpty } from './shared';
import { Body, Scroll, Section, Stat, Row, Note, SourceLine, dtgDay, type Tone } from '../../flood/milspec';

/**
 * Exact label of the missing row the foreign column expands in full. Matched
 * verbatim — never by substring — so a category row can never be mistaken for
 * another and dropped.
 */
const FOREIGN_ROW_LABEL = 'Foreign nationals';

function LedgerColumn({
  panel,
  meta,
  rows,
  caption,
  tone,
}: {
  panel: SituationPanel;
  /** Section meta: who publishes it, or how the column is cut. */
  meta?: string;
  /** Row list to render; defaults to the panel's own, overridden to deduplicate. */
  rows?: SituationPanel['rows'];
  /** Editorial line naming the column's relation to the other; never a figure. */
  caption?: string;
  tone?: Tone;
}) {
  const visibleRows = rows ?? panel.rows;

  return (
    <div style={{ minWidth: 0 }}>
      <Section title={panel.title} meta={meta ?? undefined} style={{ marginTop: 0 }} />
      <Stat
        label={panel.headline_label ?? panel.title}
        value={panel.headline_value ?? '—'}
        tone={tone}
        size={24}
        sub={caption ?? panel.subtitle ?? undefined}
      />
      {visibleRows.length === 0 ? (
        <Note>No breakdown published</Note>
      ) : (
        visibleRows.map((r) => <Row key={r.label} label={r.label} value={r.value} />)
      )}
      {panel.note && <Note>{panel.note}</Note>}
    </div>
  );
}

export const FloodMissingLedgerWidget = memo(function FloodMissingLedgerWidget() {
  const { data, isLoading, error, refetch } = useOfficialSituation();

  if (isLoading) {
    return (
      <Widget id="flood-missing-ledger" icon={<UserSearch size={14} />}>
        <WidgetSkeleton />
      </Widget>
    );
  }

  if (error || !data) {
    return (
      <Widget id="flood-missing-ledger" icon={<UserSearch size={14} />}>
        <WidgetError message="Failed to load official missing figures" onRetry={() => refetch()} />
      </Widget>
    );
  }

  const missing = data.official.panels.find((p) => p.key === 'missing');
  const foreign = data.official.panels.find((p) => p.key === 'foreign');
  // The public rescue portal counts FILINGS, not people, so it can never share a
  // column with the authority's registry above. It gets its own band, beneath the
  // rule, with its own note saying what the figures are not.
  const portal = data.official.panels.find((p) => p.key === 'portal');

  if (!data.official.available || !missing) {
    return (
      <Widget id="flood-missing-ledger" icon={<UserSearch size={14} />}>
        <WidgetEmpty message="No official missing-persons registry published for this event" />
      </Widget>
    );
  }

  // With the foreign column present, its headline *is* the "Foreign nationals"
  // row of the missing panel — printing both puts the same figure on screen
  // twice. The row is dropped only while the column that replaces it is
  // rendered; without the panel the row stays, so nothing is ever lost.
  const missingRows = foreign
    ? missing.rows.filter((r) => r.label !== FOREIGN_ROW_LABEL)
    : missing.rows;

  // The portal headline leads its own band as an ordinary ledger row, so the band
  // reads as one list and no figure is promoted to hero size beside the registry.
  const portalRows: Array<{ label: string; value: string; tone?: Tone }> = portal
    ? [
        {
          label: portal.headline_label ?? portal.title,
          value: portal.headline_value ?? '—',
          tone: 'high' as Tone,
        },
        ...portal.rows,
      ]
    : [];
  const portalSplit = Math.ceil(portalRows.length / 2);

  const authority = data.official.latest?.authority ?? missing.source ?? undefined;
  const sources = Array.from(
    new Set([missing.source, foreign?.source, portal?.source].filter((s): s is string => Boolean(s))),
  ).join(' · ');
  const asOf = missing.as_of ?? foreign?.as_of ?? data.official.latest?.as_of ?? null;

  return (
    <Widget
      id="flood-missing-ledger"
      icon={<UserSearch size={14} />}
      badge={missing.headline_value ? `${missing.headline_value} MISSING` : undefined}
      badgeVariant="high"
    >
      <Body>
        <Scroll>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: foreign ? 'repeat(2, minmax(0, 1fr))' : 'minmax(0, 1fr)',
              gap: 24,
              alignItems: 'start',
            }}
          >
            <LedgerColumn panel={missing} meta={authority} rows={missingRows} tone="high" />
            {foreign && (
              <LedgerColumn
                panel={foreign}
                meta={foreign.subtitle ?? 'BY NATIONALITY'}
                caption={`counted within the ${missing.headline_value ?? 'total'} at left`}
              />
            )}
          </div>

          {portal && (
            <>
              <Section n={3} title={portal.title.toUpperCase()} meta={portal.subtitle ?? undefined} />
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
                  gap: 24,
                  alignItems: 'start',
                }}
              >
                <div style={{ minWidth: 0 }}>
                  {portalRows.slice(0, portalSplit).map((r) => (
                    <Row key={r.label} label={r.label} value={r.value} tone={r.tone} />
                  ))}
                </div>
                <div style={{ minWidth: 0 }}>
                  {portalRows.slice(portalSplit).map((r) => (
                    <Row key={r.label} label={r.label} value={r.value} tone={r.tone} />
                  ))}
                </div>
              </div>
              {portal.note && <Note>{portal.note}</Note>}
            </>
          )}
        </Scroll>

        <SourceLine source={sources || authority || null} asOf={asOf ? dtgDay(asOf) : undefined} />
      </Body>
    </Widget>
  );
});
