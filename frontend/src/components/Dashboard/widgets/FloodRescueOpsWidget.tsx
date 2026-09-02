/**
 * FORCE POSTURE · RESCUE OPERATIONS — who is in the field, in what strength,
 * what they have pulled out, and what the force itself has lost.
 *
 * Three bands under a four-cell stat head, all read from the backend situation
 * panels (NDRRMA rescue register and situation board) plus the assistance
 * board for foreign personnel:
 *   1. FORCE BY AGENCY — Army / Police / APF as proportional bars, then foreign
 *      teams with a stated size.
 *   2. RESCUED — the register split (named, Nepali, foreign, airlifted).
 *   3. FORCE LOSSES · MEDICAL — security personnel the bulletin lists as
 *      missing, and the hospital figures.
 *
 * Every figure is read from a payload. A literal number here would be a bug.
 * Milspec: fitted to the widget's height, no inner scroll, one SourceLine.
 */
import { memo, useMemo } from 'react';
import { Shield } from 'lucide-react';

import { Widget } from '../Widget';
import { useOfficialSituation } from '../../../api/hooks/useFlood';
import type { SituationPanel } from '../../../api/flood';
import { WidgetSkeleton, WidgetError, WidgetEmpty } from './shared';
import { Body, CELL, HAIRLINE, LABEL_XS, MS, Note, Row, Section, SourceLine, Stat, StatRow, dtgDay, fmt } from '../../flood/milspec';
import { useAssistance } from './FloodAssistanceWidget';

const FLIGHTS_ROW = /flights flown/i;
const ACCESS_ROW = /out of reach|unreachable|cut off/i;
const AGENCY_ROWS: { re: RegExp; short: string }[] = [
  { re: /nepali? army/i, short: 'NEPALI ARMY' },
  { re: /nepal police/i, short: 'NEPAL POLICE' },
  { re: /armed police/i, short: 'ARMED POLICE FORCE' },
];
const FORCE_MISSING = /army personnel|police personnel|armed police force personnel/i;

const toNum = (v: string | null | undefined): number | null => {
  if (!v) return null;
  const m = v.replace(/,/g, '').match(/-?\d+(\.\d+)?/);
  return m ? Number(m[0]) : null;
};
const rowsOf = (p: SituationPanel | undefined) => p?.rows ?? [];
const isSubRow = (label: string) => label.trimStart().startsWith('—');

function Bar({ label, value, max, tone }: { label: string; value: number; max: number; tone: string }) {
  const pct = max > 0 ? Math.max(2, Math.round((value / max) * 100)) : 0;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '3px 0', borderBottom: HAIRLINE }}>
      <span style={{ ...LABEL_XS, flex: '0 0 34%', color: MS.text, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{label}</span>
      <span style={{ flex: 1, height: 7, background: MS.hairline, position: 'relative' }}>
        <span style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${pct}%`, background: tone }} />
      </span>
      <span style={{ ...CELL, flex: '0 0 16%', textAlign: 'right', color: MS.text, fontWeight: 600 }}>{fmt(value)}</span>
    </div>
  );
}

export const FloodRescueOpsWidget = memo(function FloodRescueOpsWidget() {
  const { data, isLoading, error, refetch } = useOfficialSituation();
  const assist = useAssistance();

  const foreign = useMemo(() => {
    const cs = assist.data?.countries ?? [];
    return cs
      .filter((c) => c.teams.length)
      .map((c) => ({ code: c.code, name: c.name, personnel: c.personnel_total, unstated: c.personnel_unstated, kinds: c.kinds }))
      .sort((a, b) => b.personnel - a.personnel);
  }, [assist.data]);

  if (isLoading) {
    return (
      <Widget id="flood-rescue-ops" title="FORCE POSTURE · RESCUE OPERATIONS" icon={<Shield size={14} />}>
        <WidgetSkeleton />
      </Widget>
    );
  }
  if (error || !data) {
    return (
      <Widget id="flood-rescue-ops" title="FORCE POSTURE · RESCUE OPERATIONS" icon={<Shield size={14} />}>
        <WidgetError message="Failed to load official situation" onRetry={() => refetch()} />
      </Widget>
    );
  }

  const panels = data.official.panels ?? [];
  const rescued = panels.find((p) => p.key === 'rescued');
  const operations = panels.find((p) => p.key === 'operations');
  const medical = panels.find((p) => p.key === 'medical');
  const missing = panels.find((p) => p.key === 'missing');

  if (!rescued && !operations) {
    return (
      <Widget id="flood-rescue-ops" title="FORCE POSTURE · RESCUE OPERATIONS" icon={<Shield size={14} />}>
        <WidgetEmpty message="No official rescue figures published for this event" />
      </Widget>
    );
  }

  const opsRows = rowsOf(operations);
  const agencies = AGENCY_ROWS.map((a) => {
    const r = opsRows.find((x) => a.re.test(x.label));
    return r ? { label: a.short, value: toNum(r.value) ?? 0 } : null;
  }).filter((x): x is { label: string; value: number } => Boolean(x));
  const agencyMax = Math.max(1, ...agencies.map((a) => a.value));
  const flights = opsRows.find((r) => FLIGHTS_ROW.test(r.label)) ?? rowsOf(rescued).find((r) => FLIGHTS_ROW.test(r.label));
  const access = opsRows.find((r) => ACCESS_ROW.test(r.label));
  const otherOps = opsRows.filter((r) => !AGENCY_ROWS.some((a) => a.re.test(r.label)) && !FLIGHTS_ROW.test(r.label) && !ACCESS_ROW.test(r.label));

  const rescuedRows = rowsOf(rescued).filter((r) => !FLIGHTS_ROW.test(r.label)).slice(0, 6);
  const forceMissing = rowsOf(missing).filter((r) => FORCE_MISSING.test(r.label));
  const foreignStated = foreign.reduce((a, f) => a + f.personnel, 0);
  const asOf = operations?.as_of ?? rescued?.as_of ?? null;

  return (
    <Widget
      id="flood-rescue-ops"
      title="FORCE POSTURE · RESCUE OPERATIONS"
      icon={<Shield size={14} />}
      badge={asOf ? `NDRRMA ${dtgDay(asOf)}` : undefined}
    >
      <Body style={{ overflow: 'hidden' }}>
        <StatRow columns={4}>
          <Stat label={operations?.headline_label?.toUpperCase() ?? 'PERSONNEL MOBILISED'} value={operations?.headline_value ?? '—'} tone="info" size={22} sub={operations?.subtitle ?? 'Army, Police and APF, live register'} />
          <Stat label={rescued?.headline_label?.toUpperCase() ?? 'RESCUED'} value={rescued?.headline_value ?? '—'} tone="low" size={22} sub={rescued?.subtitle ?? null} />
          <Stat label="RESCUE AND RELIEF FLIGHTS" value={flights?.value ?? '—'} size={22} sub="sorties logged by the register" />
          <Stat label="FOREIGN PERSONNEL · STATED" value={foreignStated ? fmt(foreignStated) : foreign.length ? 'n/p' : '—'} tone="high" size={22} sub={foreign.length ? `${foreign.length} countries with teams in Nepal` : 'no foreign team published'} />
        </StatRow>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 22, flex: 1, minHeight: 0, overflow: 'hidden' }}>
          <div style={{ minWidth: 0 }}>
            <Section title="FORCE BY AGENCY" meta="SHARE OF DOMESTIC FORCE" style={{ marginTop: 0 }} />
            {agencies.map((a) => (
              <Bar key={a.label} label={a.label} value={a.value} max={agencyMax} tone={MS.info} />
            ))}
            {foreign.slice(0, 3).map((f) => (
              <Bar key={f.code} label={`${f.name.toUpperCase()} · ${f.kinds.filter((k) => k !== 'ifrc_rr' && k !== 'consular').map((k) => k.toUpperCase()).join('/') || 'TEAM'}`} value={f.personnel} max={agencyMax} tone={MS.high} />
            ))}
          </div>
          <div style={{ minWidth: 0 }}>
            <Section title={rescued?.title.toUpperCase() ?? 'RESCUED'} meta={rescued?.source ?? undefined} style={{ marginTop: 0 }} />
            {rescuedRows.map((r) => (
              <Row key={r.label} label={r.label} value={r.value} dim={isSubRow(r.label)} />
            ))}
          </div>
          <div style={{ minWidth: 0 }}>
            <Section title="FORCE LOSSES · MEDICAL" meta="MISSING FROM THE SECURITY FORCES" style={{ marginTop: 0 }} />
            {forceMissing.map((r) => (
              <Row key={r.label} label={r.label} value={r.value} tone="critical" />
            ))}
            {medical?.headline_value && <Row label={medical.headline_label ?? medical.title} value={medical.headline_value} tone="medium" />}
            {rowsOf(medical).slice(0, 2).map((r) => (
              <Row key={r.label} label={r.label} value={r.value} dim />
            ))}
            {access && <Row label={access.label} value={access.value} tone="high" />}
            {otherOps.slice(0, 1).map((r) => (
              <Row key={r.label} label={r.label} value={r.value} dim />
            ))}
          </div>
        </div>

        {operations?.note && <Note>{operations.note}</Note>}
        <SourceLine source={operations?.source ?? rescued?.source ?? null} asOf={asOf ? dtgDay(asOf) : null} right={<span style={{ whiteSpace: 'nowrap' }}>FOREIGN TEAMS · MOFA BRIEFING + IFRC GO</span>} />
      </Body>
    </Widget>
  );
});
