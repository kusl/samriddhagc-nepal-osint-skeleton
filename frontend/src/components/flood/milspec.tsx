/**
 * MILSPEC — the one visual grammar every flood-desk widget renders through.
 *
 * The desk is an intelligence product, not a dashboard of cards. Every widget on
 * the flood preset composes these primitives and nothing else, so the tab reads
 * as a single document: one label style, one figure style, one row, one section
 * head, one way to stamp a time, one way to grade a source.
 *
 * Rules the primitives enforce (do not work around them in a widget):
 *   - No side rails. No `borderLeft` accents, no coloured bars, no nested boxes.
 *     Structure is horizontal hairlines and whitespace only.
 *   - No rounded corners beyond 2px. No shadows. No gradients.
 *   - Tone (red/orange/yellow/green/blue) is carried by TEXT colour only, and
 *     only on figures, grades, confidence tags and status words. Never on
 *     backgrounds, except the hairline-grid divider trick in <StatRow>.
 *   - Times are DTGs. Sources are graded. Assessments carry confidence.
 *   - Figures are READ from the API, never typed. A literal number in a widget
 *     file is a bug.
 */
import type { CSSProperties, ReactNode } from 'react';
import { ExternalLink } from 'lucide-react';

// ------------------------------------------------------------------ tokens

export const MS = {
  critical: 'var(--status-critical)',
  high: 'var(--status-high)',
  medium: 'var(--status-medium)',
  low: 'var(--status-low)',
  info: 'var(--status-info)',
  text: 'var(--text-primary)',
  sub: 'var(--text-secondary)',
  muted: 'var(--text-muted)',
  disabled: 'var(--text-disabled)',
  surface: 'var(--bg-surface)',
  elevated: 'var(--bg-elevated)',
  hairline: 'var(--border-subtle)',
  rule: 'var(--border-default)',
  mono: 'var(--font-mono)',
} as const;

export type Tone = 'critical' | 'high' | 'medium' | 'low' | 'info' | 'text' | 'sub' | 'muted';

export const tone = (t: Tone | undefined): string => (t ? MS[t] : MS.text);

/** 10px uppercase mono label — the only label style on the desk. */
export const LABEL: CSSProperties = {
  fontFamily: MS.mono,
  fontSize: 10,
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  color: MS.muted,
  lineHeight: 1.3,
};

/** 9px variant for footers and metadata. */
export const LABEL_XS: CSSProperties = { ...LABEL, fontSize: 9 };

/** Tabular mono figure — headline size varies, nothing else does. */
export const FIGURE: CSSProperties = {
  fontFamily: MS.mono,
  fontVariantNumeric: 'tabular-nums',
  fontWeight: 600,
  lineHeight: 1.05,
  letterSpacing: '-0.01em',
};

/** Body prose: 11px, 1.5 leading, secondary colour. Sentences, not paragraphs. */
export const PROSE: CSSProperties = {
  fontFamily: MS.mono,
  fontSize: 11,
  lineHeight: 1.5,
  color: MS.sub,
};

/** Fixed-column table text. */
export const CELL: CSSProperties = {
  fontFamily: MS.mono,
  fontSize: 11,
  lineHeight: 1.35,
  fontVariantNumeric: 'tabular-nums',
};

export const HAIRLINE = `1px solid ${MS.hairline}`;

// ------------------------------------------------------------------ time

const MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];
const pad = (v: number) => String(v).padStart(2, '0');

/**
 * Day-precision DTG for bulletin dates, which are plain ISO days with no clock.
 * "2026-09-01" → "01 SEP 26". String-sliced, never Date-parsed: parsing a bare
 * day as UTC and printing it in NPT would shift it across midnight.
 */
export function dtgDay(isoDay: string | null | undefined): string {
  if (!isoDay) return '—';
  const [y, m, d] = isoDay.slice(0, 10).split('-');
  const month = MONTHS[Number(m) - 1];
  if (!month || !d || !y) return isoDay;
  return `${d} ${month} ${y.slice(2)}`;
}

/**
 * Full Zulu DTG from any ISO datetime that carries an offset:
 * "2026-08-26T08:37:00+05:45" → "260252Z AUG 26".
 * An offset-less string is treated as already-UTC. A bare day falls back to dtgDay.
 */
export function dtgZ(iso: string | null | undefined): string {
  if (!iso) return '—';
  if (iso.length <= 10) return dtgDay(iso);
  const t = new Date(iso);
  if (Number.isNaN(t.getTime())) return iso;
  return `${pad(t.getUTCDate())}${pad(t.getUTCHours())}${pad(t.getUTCMinutes())}Z ${MONTHS[t.getUTCMonth()]} ${String(t.getUTCFullYear()).slice(2)}`;
}

/**
 * Local (Nepal, +05:45) clock read straight off a fixed-offset string:
 * "2026-08-26T08:37:00+05:45" → "0837 NPT". No re-zoning, ever.
 */
export function clockNpt(iso: string | null | undefined): string {
  if (!iso || iso.length < 16) return '—';
  return `${iso.slice(11, 13)}${iso.slice(14, 16)} NPT`;
}

/** "26 AUG · 0837 NPT" for chronology rows; day only if the time is unpublished. */
export function dtgNpt(iso: string | null | undefined, timePublished = true): string {
  if (!iso) return '—';
  const day = dtgDay(iso);
  return timePublished && iso.length >= 16 ? `${day} · ${clockNpt(iso)}` : day;
}

/** Now, as a Zulu DTG — for "PICTURE AS OF" stamps. */
export function dtgNow(): string {
  return dtgZ(new Date().toISOString());
}

// ------------------------------------------------------------------ figures

export const isNum = (v: number | null | undefined): v is number =>
  typeof v === 'number' && Number.isFinite(v);

export const fmt = (v: number | null | undefined): string =>
  isNum(v) ? v.toLocaleString('en-IN') : '—';

export const fmtDelta = (v: number | null | undefined): string =>
  isNum(v) ? (v > 0 ? `+${v.toLocaleString('en-IN')}` : v.toLocaleString('en-IN')) : '—';

/** "Rs 200bn" / "USD 4.5bn" from raw units. */
export function fmtMoney(v: number | null | undefined, unit: 'NPR' | 'USD'): string {
  if (!isNum(v)) return '—';
  const prefix = unit === 'NPR' ? 'Rs ' : 'USD ';
  if (v >= 1e9) return `${prefix}${(v / 1e9).toFixed(v >= 1e10 ? 0 : 1).replace(/\.0$/, '')}bn`;
  if (v >= 1e6) return `${prefix}${(v / 1e6).toFixed(v >= 1e7 ? 0 : 1).replace(/\.0$/, '')}m`;
  return `${prefix}${v.toLocaleString('en-IN')}`;
}

// ------------------------------------------------------------------ grading

/**
 * NATO Admiralty (STANAG 2511) source grading. Letter = reliability of the
 * SOURCE, digit = credibility of the INFORMATION. These are DESK-ASSIGNED
 * assessments and are labelled as such wherever shown.
 */
export const RELIABILITY: Record<string, string> = {
  A: 'Completely reliable',
  B: 'Usually reliable',
  C: 'Fairly reliable',
  D: 'Not usually reliable',
  E: 'Unreliable',
  F: 'Reliability cannot be judged',
};

export const CREDIBILITY: Record<string, string> = {
  '1': 'Confirmed by other sources',
  '2': 'Probably true',
  '3': 'Possibly true',
  '4': 'Doubtful',
  '5': 'Improbable',
  '6': 'Truth cannot be judged',
};

export interface SourceGrade {
  code: string;
  /** Short category used in the matrix: OFFICIAL / WIRE / IMAGERY / INSTRUMENT / OPEN. */
  kind: 'OFFICIAL' | 'WIRE' | 'IMAGERY' | 'INSTRUMENT' | 'OPEN' | 'NGO' | 'INDUSTRY';
  /** One line on WHY the desk grades it so — shown in the matrix. */
  basis: string;
}

/**
 * Pattern → grade. First match wins; order matters (specific before generic).
 * Unknown sources fall to F6, which is the honest default: the desk has not
 * assessed them, and says so.
 */
const GRADE_RULES: Array<[RegExp, SourceGrade]> = [
  [/ndrrma|nepal disaster|home ministry|ministry of home/i, { code: 'B2', kind: 'OFFICIAL', basis: 'National authority; figures revised daily and not independently confirmed' }],
  [/nepal police|nepali army|armed police|joint (command|rescue)/i, { code: 'B2', kind: 'OFFICIAL', basis: 'Operational reporting from responding forces; self-reported' }],
  [/ministry of health|mohp/i, { code: 'B2', kind: 'OFFICIAL', basis: 'Hospital admissions are counted, not estimated' }],
  [/finance ministry|ministry of finance|nrb/i, { code: 'B3', kind: 'OFFICIAL', basis: 'Preliminary estimate; the ministry’s own rebuild figure differs by 3.8×' }],
  [/nepal\.gov\.np|government of nepal|pmo|prime minister/i, { code: 'A2', kind: 'OFFICIAL', basis: 'Primary portal; content is the government’s own statement' }],
  [/copernicus|emsr/i, { code: 'A1', kind: 'IMAGERY', basis: 'Damage graded from 0.3 m WorldView-3; product peer-reviewed within EMS' }],
  [/unosat|unitar/i, { code: 'A2', kind: 'IMAGERY', basis: 'UN mapping from Sentinel/commercial passes; extent, not building-level' }],
  [/vantor|maxar/i, { code: 'A1', kind: 'IMAGERY', basis: '0.3 m native scenes with published footprints and acquisition times' }],
  [/nasa|gibs|viirs|modis/i, { code: 'B3', kind: 'IMAGERY', basis: '250 m regional flood water; cloud-limited during monsoon' }],
  [/sentinel|esa/i, { code: 'A2', kind: 'IMAGERY', basis: '10 m optical; cloud-limited' }],
  [/international charter|charter/i, { code: 'A2', kind: 'IMAGERY', basis: 'Coordinated multi-agency tasking; product log, not raw imagery' }],
  [/dhm|hydrology|gauge/i, { code: 'B2', kind: 'INSTRUMENT', basis: 'Telemetered; a third of stations silent, stale readings served as live' }],
  [/bipad/i, { code: 'C4', kind: 'OFFICIAL', basis: 'Routine incident feed; carried none of this event during the emergency' }],
  [/ippan|hydropower/i, { code: 'B3', kind: 'INDUSTRY', basis: 'Operator association; tunnel counts are operator self-reports' }],
  [/ocha|un ocha|reliefweb|ifrc|red cross/i, { code: 'B2', kind: 'NGO', basis: 'Compiled from government and cluster partners; lagged' }],
  [/\bap\b|associated press|reuters|afp|nyt|new york times|bloomberg|bbc|al jazeera|abc/i, { code: 'B2', kind: 'WIRE', basis: 'Wire and broadcast; toll figures sourced back to officials' }],
  [/kathmandu post|republica|himalayan|onlinekhabar|setopati|kantipur|ekantipur|nagarik|gorkhapatra|rising nepal|risingnepal|nepalnews|nepal news|himal ?press|himal ?khabar|image channel|khabarhub|thaha ?khabar|ratopati|annapurna|ujyaalo|news24|avenues|nepal live|deshsanchar|kantipur tv|nepali times|rajdhani|naya patrika|karobar|arthasarokar|bizmandu|barakhari|hamrakura|swasthya/i, { code: 'B3', kind: 'WIRE', basis: 'Domestic press; fastest local detail, variable sourcing' }],
  [/wikimedia|commons/i, { code: 'C3', kind: 'OPEN', basis: 'Licensed user uploads; provenance per file' }],
  [/wikipedia/i, { code: 'C3', kind: 'OPEN', basis: 'Tertiary compilation; used only for its citations' }],
  [/phys\.org|planet labs|seismic|usgs|gfz/i, { code: 'B2', kind: 'INSTRUMENT', basis: 'Seismic detection is instrumental; timing interpretation is secondary' }],
  [/icimod|nrsc|isro|british geological|sertit/i, { code: 'A2', kind: 'IMAGERY', basis: 'Charter-tasked mapping agency' }],
  [/social|facebook|twitter|x\.com|tiktok|telegram/i, { code: 'F6', kind: 'OPEN', basis: 'Unverified social; not used for figures' }],
];

export function gradeFor(source: string | null | undefined): SourceGrade {
  if (!source) return { code: 'F6', kind: 'OPEN', basis: 'Source not stated' };
  for (const [re, g] of GRADE_RULES) if (re.test(source)) return g;
  return { code: 'F6', kind: 'OPEN', basis: 'Not yet assessed by the desk' };
}

export function gradeTone(code: string): Tone {
  const letter = code[0];
  const digit = code[1];
  if (letter === 'A' && (digit === '1' || digit === '2')) return 'low';
  if ((letter === 'A' || letter === 'B') && Number(digit) <= 3) return 'info';
  if (letter === 'C' || digit === '4') return 'medium';
  if (letter === 'F' || digit === '6') return 'muted';
  return 'high';
}

export function gradeTitle(code: string): string {
  return `${code} · ${RELIABILITY[code[0]] ?? '?'} / ${CREDIBILITY[code[1]] ?? '?'} (desk-assigned)`;
}

// ------------------------------------------------------------------ primitives

/** Widget body: fills the widget, pads uniformly, never scrolls itself. */
export function Body({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        minHeight: 0,
        padding: '8px 12px 7px',
        ...style,
      }}
    >
      {children}
    </div>
  );
}

/** The one region inside a widget that may scroll. */
export function Scroll({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return (
    <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', overflowX: 'hidden', ...style }}>{children}</div>
  );
}

/**
 * Classification-style control strip. Sits at the very top of the hero and
 * nowhere else. Says what this product is (open-source, desk-assessed) and
 * when the picture was assembled.
 */
export function ControlStrip({ left, right }: { left: string; right?: string }) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        gap: 12,
        padding: '3px 0 5px',
        borderBottom: HAIRLINE,
        marginBottom: 8,
        ...LABEL_XS,
        letterSpacing: '0.14em',
        color: MS.sub,
      }}
    >
      <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{left}</span>
      {right && <span style={{ whiteSpace: 'nowrap', color: MS.muted }}>{right}</span>}
    </div>
  );
}

/**
 * Numbered section head: "01  BOTTOM LINE ————————— meta".
 * Numbering is what turns prose into a product; the rule carries the eye.
 */
export function Section({
  n,
  title,
  meta,
  right,
  style,
}: {
  n?: string | number;
  title: string;
  meta?: string;
  right?: ReactNode;
  style?: CSSProperties;
}) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'baseline',
        gap: 8,
        marginTop: 8,
        marginBottom: 4,
        ...style,
      }}
    >
      {n !== undefined && (
        <span style={{ ...LABEL, color: MS.sub, fontWeight: 600 }}>{typeof n === 'number' ? pad(n) : n}</span>
      )}
      <span style={{ ...LABEL, color: MS.text, fontWeight: 600, whiteSpace: 'nowrap' }}>{title}</span>
      {meta && <span style={{ ...LABEL_XS, whiteSpace: 'nowrap' }}>{meta}</span>}
      <span style={{ flex: 1, borderBottom: HAIRLINE, transform: 'translateY(-3px)' }} />
      {right}
    </div>
  );
}

/** Inner gutter of a <Stat>, and the distance <StatRow> bleeds to line up with <Body>. */
const STAT_GUTTER = 12;
const STAT_SUB_LINES = 2;

/**
 * Stat cell. Label row (label left, change chip right), figure, optional sub-line.
 *
 * Three fixed bands so a row of cells reads as one instrument panel: every label
 * sits on one line, every figure on one baseline, every sub-line in a reserved
 * two-line band. Nothing wraps and nothing is ragged — a figure or label too wide
 * for its column is clipped with an ellipsis and carries the full text as a title.
 * Never has its own border — <StatRow> draws the hairlines between cells.
 */
export function Stat({
  label,
  value,
  tone: t,
  sub,
  delta,
  deltaTone,
  deltaTitle,
  size = 26,
  align = 'left',
}: {
  label: string;
  value: ReactNode;
  tone?: Tone;
  sub?: ReactNode;
  delta?: string;
  deltaTone?: Tone;
  deltaTitle?: string;
  size?: number;
  align?: 'left' | 'right';
}) {
  return (
    <div
      style={{
        background: MS.surface,
        // Symmetric gutters: content never touches the hairline either side of it.
        padding: `8px ${STAT_GUTTER}px 9px`,
        minWidth: 0,
        textAlign: align,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: 8,
          flexDirection: align === 'right' ? 'row-reverse' : 'row',
        }}
      >
        <span
          style={{ ...LABEL, flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
          title={label}
        >
          {label}
        </span>
        {delta && (
          <span
            title={deltaTitle}
            style={{ ...FIGURE, fontSize: 10, letterSpacing: '0.02em', color: tone(deltaTone ?? 'muted'), whiteSpace: 'nowrap' }}
          >
            {delta}
          </span>
        )}
      </div>

      <div
        style={{ ...FIGURE, fontSize: size, color: tone(t), marginTop: 5, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}
        title={typeof value === 'string' ? value : undefined}
      >
        {value}
      </div>

      {sub && (
        <div
          style={{
            ...LABEL_XS,
            textTransform: 'none',
            letterSpacing: '0.02em',
            lineHeight: 1.4,
            marginTop: 6,
            // Reserved two-line band: a one-line sub and a two-line sub leave the
            // row the same height, so the hairlines stay square.
            minHeight: STAT_SUB_LINES * 9 * 1.4,
            display: '-webkit-box',
            WebkitLineClamp: STAT_SUB_LINES,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
          title={typeof sub === 'string' ? sub : undefined}
        >
          {sub}
        </div>
      )}
    </div>
  );
}

/**
 * Hairline grid for <Stat> cells: the container paints the hairline colour and
 * the 1px gap between cells reveals it. No borders on cells, so nothing doubles.
 *
 * The row bleeds `bleed` px past <Body>'s padding on both sides so its rules run
 * the full width of the widget, while each cell's own gutter puts the first
 * label back exactly on the document's left margin. Pass `bleed={0}` where the
 * row is not a direct child of <Body>.
 */
export function StatRow({
  children,
  columns,
  bleed = STAT_GUTTER,
  style,
}: {
  children: ReactNode;
  columns?: number;
  bleed?: number;
  style?: CSSProperties;
}) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: columns ? `repeat(${columns}, minmax(0, 1fr))` : 'repeat(auto-fit, minmax(140px, 1fr))',
        gap: 1,
        background: MS.hairline,
        borderTop: HAIRLINE,
        borderBottom: HAIRLINE,
        marginLeft: -bleed,
        marginRight: -bleed,
        ...style,
      }}
    >
      {children}
    </div>
  );
}

/** Ledger row: label left, figure right, hairline under. */
export function Row({
  label,
  value,
  tone: t,
  sub,
  dim,
  indent,
  right,
}: {
  label: ReactNode;
  value?: ReactNode;
  tone?: Tone;
  sub?: ReactNode;
  dim?: boolean;
  indent?: boolean;
  right?: ReactNode;
}) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'baseline',
        gap: 12,
        padding: '3px 0',
        borderBottom: HAIRLINE,
        paddingLeft: indent ? 12 : 0,
      }}
    >
      <span style={{ ...CELL, color: dim ? MS.muted : MS.sub, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {label}
        {sub && <span style={{ ...LABEL_XS, marginLeft: 8, textTransform: 'none', letterSpacing: 0 }}>{sub}</span>}
      </span>
      {right}
      {value !== undefined && (
        <span style={{ ...CELL, fontWeight: 600, color: tone(t ?? (dim ? 'muted' : 'text')), whiteSpace: 'nowrap' }}>{value}</span>
      )}
    </div>
  );
}

/** Admiralty grade chip. Tone from the code; tooltip explains it. */
export function Grade({ code, title }: { code: string; title?: string }) {
  return (
    <span
      title={title ?? gradeTitle(code)}
      style={{
        ...LABEL_XS,
        fontWeight: 700,
        letterSpacing: '0.06em',
        color: tone(gradeTone(code)),
        border: `1px solid ${tone(gradeTone(code))}`,
        borderRadius: 2,
        padding: '0 4px',
        lineHeight: '14px',
        display: 'inline-block',
        opacity: 0.9,
      }}
    >
      {code}
    </span>
  );
}

export type Confidence = 'HIGH' | 'MOD' | 'LOW';

const CONF_TONE: Record<Confidence, Tone> = { HIGH: 'low', MOD: 'medium', LOW: 'high' };

/** Analytic confidence tag. Appears at the end of every assessment line. */
export function Conf({ level }: { level: Confidence }) {
  return (
    <span
      title={`Desk confidence: ${level}`}
      style={{ ...LABEL_XS, fontWeight: 700, color: tone(CONF_TONE[level]), marginLeft: 8, whiteSpace: 'nowrap' }}
    >
      [{level}]
    </span>
  );
}

/** Neutral chip for themes, kinds, status words. Text-only tone. */
export function Tag({ children, tone: t, active, onClick }: { children: ReactNode; tone?: Tone; active?: boolean; onClick?: () => void }) {
  const c = tone(t ?? 'muted');
  return (
    <span
      onClick={onClick}
      style={{
        ...LABEL_XS,
        color: active ? MS.text : c,
        border: `1px solid ${active ? MS.rule : MS.hairline}`,
        borderRadius: 2,
        padding: '1px 5px',
        lineHeight: '13px',
        display: 'inline-block',
        cursor: onClick ? 'pointer' : 'default',
        userSelect: 'none',
        whiteSpace: 'nowrap',
      }}
    >
      {children}
    </span>
  );
}

/** Status word in its tone: DANGER, OFFLINE, ACTIVE … */
export function Status({ children, tone: t }: { children: ReactNode; tone: Tone }) {
  return <span style={{ ...LABEL_XS, fontWeight: 700, color: tone(t) }}>{children}</span>;
}

/**
 * Footer source line: "NDRRMA · B2 · AS OF 01 SEP 26 · SOURCE ↗". One per widget,
 * always last, always hairline-topped. Grade is desk-assigned from the source name.
 */
export function SourceLine({
  source,
  asOf,
  url,
  right,
  grade,
}: {
  source: string | null | undefined;
  asOf?: string | null;
  url?: string | null;
  right?: ReactNode;
  grade?: string | false;
}) {
  const g = grade === false ? null : (grade ?? gradeFor(source).code);
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        marginTop: 6,
        paddingTop: 5,
        borderTop: HAIRLINE,
        flex: '0 0 auto',
        ...LABEL_XS,
      }}
    >
      <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{source ?? 'SOURCE NOT STATED'}</span>
      {g && <Grade code={g} />}
      {asOf && <span style={{ whiteSpace: 'nowrap' }}>AS OF {asOf}</span>}
      {url && (
        <a
          href={url}
          target="_blank"
          rel="noreferrer noopener"
          style={{ color: MS.info, display: 'inline-flex', alignItems: 'center', gap: 3, textDecoration: 'none', whiteSpace: 'nowrap' }}
        >
          SOURCE <ExternalLink size={9} />
        </a>
      )}
      <span style={{ flex: 1 }} />
      {right}
    </div>
  );
}

/** One assessment line: sentence + confidence + optional source grade. */
export function Line({
  children,
  conf,
  grade,
  tone: t,
}: {
  children: ReactNode;
  conf?: Confidence;
  grade?: string;
  tone?: Tone;
}) {
  return (
    <div style={{ ...PROSE, color: t ? tone(t) : MS.sub, padding: '2px 0', display: 'flex', alignItems: 'baseline', gap: 6 }}>
      <span style={{ color: MS.disabled, flex: '0 0 auto' }}>▸</span>
      <span style={{ minWidth: 0 }}>
        {children}
        {grade && <span style={{ marginLeft: 8 }}><Grade code={grade} /></span>}
        {conf && <Conf level={conf} />}
      </span>
    </div>
  );
}

/** A figure inside prose: mono, brighter, optionally toned. */
export function F({ children, tone: t }: { children: ReactNode; tone?: Tone }) {
  return <span style={{ ...FIGURE, fontSize: 'inherit', fontWeight: 600, color: tone(t ?? 'text') }}>{children}</span>;
}

/** Fixed-column table header. Columns are fractions of the row. */
export function TableHead({ cols }: { cols: Array<{ label: string; width?: string; align?: 'left' | 'right' }> }) {
  return (
    <div style={{ display: 'flex', gap: 10, padding: '2px 0 4px', borderBottom: `1px solid ${MS.rule}` }}>
      {cols.map((c) => (
        <span key={c.label} style={{ ...LABEL_XS, flex: c.width ? `0 0 ${c.width}` : 1, minWidth: 0, textAlign: c.align ?? 'left' }}>
          {c.label}
        </span>
      ))}
    </div>
  );
}

export function TableRow({ cells, dim }: { cells: Array<{ node: ReactNode; width?: string; align?: 'left' | 'right'; tone?: Tone }>; dim?: boolean }) {
  return (
    <div style={{ display: 'flex', gap: 10, padding: '3px 0', borderBottom: HAIRLINE, alignItems: 'baseline', opacity: dim ? 0.55 : 1 }}>
      {cells.map((c, i) => (
        <span
          key={i}
          style={{
            ...CELL,
            flex: c.width ? `0 0 ${c.width}` : 1,
            minWidth: 0,
            textAlign: c.align ?? 'left',
            color: c.tone ? tone(c.tone) : i === 0 ? MS.text : MS.sub,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {c.node}
        </span>
      ))}
    </div>
  );
}

/** Note text under a table or section: what the figures do NOT say. */
export function Note({ children }: { children: ReactNode }) {
  return <div style={{ ...LABEL_XS, textTransform: 'none', letterSpacing: '0.02em', lineHeight: 1.45, marginTop: 5, color: MS.muted }}>{children}</div>;
}
