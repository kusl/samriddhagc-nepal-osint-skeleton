/**
 * Cost of the Trishuli flood and the money moving against it, in one ledger.
 *
 * Damage and relief are two sides of the same account — the loss estimate
 * against what has actually been pledged — so they sit side by side rather than
 * in separate widgets where a reader would have to hold one number in their head
 * to read the other. Loss is toned high, funds received low; nothing else on the
 * widget carries colour.
 *
 * Every figure is rendered as the authority published it. The NPR→USD
 * conversion comes from the API and is never recomputed here.
 *
 * Scrolling is owned by the single <Scroll> that wraps both columns. When the
 * rows also scrolled, the two containers competed: the grid clipped the damage
 * column at the fold while the row list still believed it had room, so
 * "Under-construction capacity damaged" was sliced in half with no way to reach
 * it. One scroll container means every row arrives whole, and the source line
 * sits outside it so the footer never scrolls away.
 */
import { memo } from 'react';
import { Banknote } from 'lucide-react';

import { Widget } from '../Widget';
import { useOfficialSituation } from '../../../api/hooks/useFlood';
import { WidgetSkeleton, WidgetError, WidgetEmpty } from './shared';
import {
  Body,
  Grade,
  MS,
  Note,
  Row,
  Scroll,
  SourceLine,
  Stat,
  dtgDay,
  fmtMoney,
  gradeFor,
} from '../../flood/milspec';

const TITLE = 'Damage & Relief';

export const FloodDamageAidWidget = memo(function FloodDamageAidWidget() {
  const { data, isLoading, error, refetch } = useOfficialSituation();

  if (isLoading) {
    return (
      <Widget id="flood-damage-aid" title={TITLE} icon={<Banknote size={14} />}>
        <WidgetSkeleton />
      </Widget>
    );
  }

  if (error || !data) {
    return (
      <Widget id="flood-damage-aid" title={TITLE} icon={<Banknote size={14} />}>
        <WidgetError message="Failed to load official damage figures" onRetry={() => refetch()} />
      </Widget>
    );
  }

  const { official } = data;
  const damage = official.panels.find((p) => p.key === 'damage');
  const aid = official.panels.find((p) => p.key === 'aid');
  const latest = official.latest;

  if (!damage && !aid && !latest?.damage_npr) {
    return (
      <Widget id="flood-damage-aid" title={TITLE} icon={<Banknote size={14} />}>
        <WidgetEmpty message="No official damage assessment published yet" />
      </Widget>
    );
  }

  // The panel headline is the authority's own wording; the raw damage_npr is
  // only a fallback, and then formatted, never typed.
  const damageHeadline =
    damage?.headline_value ?? (latest?.damage_npr != null ? fmtMoney(latest.damage_npr, 'NPR') : '—');
  const damageUsd = latest?.damage_usd != null ? `≈ ${fmtMoney(latest.damage_usd, 'USD')}` : null;
  const damageSub = [damage?.headline_label, damageUsd].filter(Boolean).join(' · ') || undefined;

  // One note, not two: the panel note and the toll record's damage_note both
  // carry the finance ministry's rebuild projection in different words, and
  // printing both read as a stutter. The panel note is the authored one; the
  // toll caveat only stands in when no panel note was published.
  const damageNotes = [damage?.note ?? latest?.damage_note].filter((n): n is string => Boolean(n));

  const primarySource = damage?.source ?? aid?.source ?? null;
  const secondarySource = damage?.source && aid?.source && aid.source !== damage.source ? aid.source : null;
  const asOf = damage?.as_of ?? aid?.as_of ?? null;

  return (
    <Widget
      id="flood-damage-aid"
      title={TITLE}
      icon={<Banknote size={14} />}
      badge={asOf ? dtgDay(asOf) : undefined}
    >
      <Body>
        <Scroll>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
              alignItems: 'start',
              gap: 32,
            }}
          >
            {damage && (
              <div style={{ minWidth: 0 }}>
                <Stat
                  label={damage.title}
                  value={damageHeadline}
                  sub={damageSub}
                  tone="high"
                  size={24}
                />
                {damageNotes.map((n) => (
                  <Note key={n}>{n}</Note>
                ))}
                <div style={{ marginTop: 6 }}>
                  {damage.rows.map((r) => (
                    <Row key={r.label} label={r.label} value={r.value} />
                  ))}
                </div>
              </div>
            )}

            {aid && (
              <div style={{ minWidth: 0 }}>
                <Stat
                  label={aid.title}
                  value={aid.headline_value ?? '—'}
                  sub={aid.headline_label ?? undefined}
                  tone="low"
                  size={24}
                />
                <div style={{ marginTop: 6 }}>
                  {aid.rows.map((r) => (
                    <Row key={r.label} label={r.label} value={r.value} />
                  ))}
                </div>
                {aid.note && <Note>{aid.note}</Note>}
              </div>
            )}
          </div>
        </Scroll>

        <SourceLine
          source={primarySource}
          asOf={asOf ? dtgDay(asOf) : null}
          url={latest?.source_url ?? null}
          right={
            secondarySource ? (
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  color: MS.muted,
                  minWidth: 0,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {secondarySource}
                <Grade code={gradeFor(secondarySource).code} />
              </span>
            ) : undefined
          }
        />
      </Body>
    </Widget>
  );
});
