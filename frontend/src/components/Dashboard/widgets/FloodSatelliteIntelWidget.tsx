/**
 * The published-product record for the active flood event: the International
 * Charter activation plus every satellite product any body has released, each
 * one linking back to the publisher that hosts it.
 *
 * This widget is the catalogue, not the picture. The pixels this desk is
 * licensed to show live elsewhere — CC0 Gyirong Port ground imagery inside the
 * District Impact Map, the CC BY-NC 4.0 Vantor open-data scenes in Damage
 * Pairs. Everything else listed here is an acquisition this desk may not
 * redistribute, so it stays a sourced row that opens at its publisher.
 *
 * Claims taken from coverage we cannot reproduce at all — tolls, bridge counts,
 * damage figures — are not products and are not here; they are in Cited
 * Reporting, which carries no imagery by construction.
 *
 * Nothing here is derived or interpolated. Where an acquisition date was never
 * published — the April 2024 Rasuwagadhi baseline, Planet's next clear pass —
 * the card prints no date at all rather than inventing one or printing an empty
 * field as though the absence were itself a figure.
 */
import { memo, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ExternalLink, Satellite } from 'lucide-react';

import { Widget } from '../Widget';
import apiClient from '../../../api/client';
import { floodKeys } from '../../../api/hooks/useFlood';
import { WidgetSkeleton, WidgetError, WidgetEmpty } from './shared';

interface ImageryActivation {
  activation_id: string;
  name: string;
  activated_at: string;
  requested_by: string;
  on_behalf_of: string;
  project_manager: string;
  products_published: number;
  contributing_bodies: string[];
  url: string;
}

interface ImageryProduct {
  provider: string;
  title: string;
  product_type: string;
  sensor: string | null;
  area: string | null;
  /** null where the acquisition date was never published — never guessed. */
  acquired_before: string | null;
  acquired_after: string | null;
  published_on: string | null;
  description: string | null;
  url: string;
  credit: string | null;
}

interface FloodImagery {
  event_key: string;
  activation: ImageryActivation | null;
  count: number;
  products: ImageryProduct[];
}

const C = {
  critical: 'var(--status-critical)',
  high: 'var(--status-high)',
  info: 'var(--status-info)',
  muted: 'var(--text-muted)',
  text: 'var(--text-primary)',
  sub: 'var(--text-secondary)',
  surface: 'var(--bg-surface)',
  elevated: 'var(--bg-elevated)',
  border: 'var(--border-subtle)',
  mono: 'var(--font-mono)',
};

const label: React.CSSProperties = {
  fontSize: 10,
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  color: C.muted,
  fontFamily: C.mono,
};

const figure: React.CSSProperties = {
  fontFamily: C.mono,
  fontVariantNumeric: 'tabular-nums',
  color: C.text,
};

/** A before/after pair is evidence; an analysis is an argument. Read differently. */
const TYPE_TONE: Record<string, string> = {
  pre_post: C.info,
  impact_map: C.high,
  analysis: C.sub,
};

const TYPE_FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'pre_post', label: 'Pre/Post' },
  { key: 'impact_map', label: 'Impact Map' },
  { key: 'analysis', label: 'Analysis' },
] as const;

type TypeFilter = (typeof TYPE_FILTERS)[number]['key'];

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** Date-only strings are formatted by hand: Date parsing would shift them a day west. */
const formatDay = (iso: string | null): string | null => {
  if (!iso) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  return `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]}`;
};

/**
 * The activation timestamp is rendered in the offset the Charter published it
 * in (UTC+02:00), not converted — the record is what the Charter stated.
 */
const formatActivatedAt = (iso: string): string => {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::\d{2})?(Z|[+-]\d{2}:\d{2})?/.exec(iso);
  if (!m) return iso;
  const zone = !m[6] || m[6] === 'Z' ? 'UTC' : `UTC${m[6]}`;
  return `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]} · ${m[4]}:${m[5]} ${zone}`;
};

const fetchImagery = async (): Promise<FloodImagery> =>
  (await apiClient.get('/flood/imagery')).data;

function ActivationBand({ activation }: { activation: ImageryActivation }) {
  // The four activation facts read as one sentence at 10px instead of a
  // four-cell grid; same published fields, roughly half the band height.
  const provenance = [
    `Activated ${formatActivatedAt(activation.activated_at)}`,
    `requested by ${activation.requested_by}`,
    `on behalf of ${activation.on_behalf_of}`,
    `PM ${activation.project_manager}`,
  ].join(' · ');

  return (
    <div style={{
      padding: '8px 12px',
      background: C.elevated,
      borderBottom: `1px solid ${C.border}`,
      flexShrink: 0,
    }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <span style={{ ...label, fontSize: 9, minWidth: 0 }}>
          International Charter · Activation {activation.activation_id}
        </span>
        <span style={{ ...label, fontSize: 9, marginLeft: 'auto', whiteSpace: 'nowrap' }}>
          <span style={{ ...figure, fontSize: 12, fontWeight: 600 }}>
            {activation.products_published}
          </span>{' '}
          published
        </span>
      </div>

      <a
        href={activation.url}
        target="_blank"
        rel="noreferrer"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 5,
          marginTop: 2,
          fontSize: 12,
          color: C.text,
          textDecoration: 'none',
        }}
      >
        {activation.name}
        <ExternalLink size={11} style={{ color: C.muted, flexShrink: 0 }} />
      </a>

      <div style={{ fontSize: 10, color: C.sub, lineHeight: 1.4, marginTop: 3 }}>
        {provenance}
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 5 }}>
        {activation.contributing_bodies.map((body) => (
          <span
            key={body}
            style={{
              fontFamily: C.mono,
              fontSize: 9,
              padding: '1px 5px',
              color: C.sub,
              background: C.surface,
              border: `1px solid ${C.border}`,
            }}
          >
            {body}
          </span>
        ))}
      </div>
    </div>
  );
}

function ProductCard({ product }: { product: ImageryProduct }) {
  const tone = TYPE_TONE[product.product_type] ?? C.sub;
  const before = formatDay(product.acquired_before);
  const after = formatDay(product.acquired_after);
  const published = formatDay(product.published_on);
  const meta = [product.sensor, product.area].filter(Boolean).join(' · ');

  // One date line carrying only what the publisher gave. Half these products
  // have no acquisition date at all, and a "not published" row printed at full
  // weight read as a figure when it was the absence of one — the card's own
  // description is where a withheld date is explained.
  const acquired = before && after
    ? `PRE ${before} → POST ${after}`
    : after
      ? `POST ${after}`
      : before
        ? `PRE ${before}`
        : null;

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      gap: 5,
      padding: '8px 9px',
      background: C.surface,
      // Plain border on all four sides: a toned left edge repeated down a
      // single-column grid drew a rail through the widget.
      border: `1px solid ${C.border}`,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ ...label, fontSize: 9, color: tone, whiteSpace: 'nowrap' }}>
          {product.provider}
        </span>
        <span style={{ ...label, fontSize: 9, marginLeft: 'auto', whiteSpace: 'nowrap' }}>
          {product.product_type.replace('_', '/')}
        </span>
      </div>

      <a
        href={product.url}
        target="_blank"
        rel="noreferrer"
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: 5,
          fontSize: 12,
          lineHeight: 1.3,
          color: C.text,
          textDecoration: 'none',
        }}
      >
        <span>{product.title}</span>
        <ExternalLink size={11} style={{ color: C.muted, flexShrink: 0, marginTop: 2 }} />
      </a>

      {(meta || acquired || published) && (
        <div style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '2px 10px',
          ...figure,
          fontSize: 10,
          lineHeight: 1.35,
        }}>
          {acquired && <span>{acquired}</span>}
          {published && <span style={{ color: C.muted }}>PUBLISHED {published}</span>}
          {meta && <span style={{ color: C.sub }}>{meta}</span>}
        </div>
      )}

      {product.description && (
        <div style={{ fontSize: 11, color: C.sub, lineHeight: 1.4 }}>{product.description}</div>
      )}

      {product.credit && (
        <div style={{
          fontSize: 9,
          color: C.muted,
          fontFamily: C.mono,
          lineHeight: 1.35,
          marginTop: 'auto',
          paddingTop: 4,
          borderTop: `1px solid ${C.border}`,
        }}>
          {product.credit}
        </div>
      )}
    </div>
  );
}

export const FloodSatelliteIntelWidget = memo(function FloodSatelliteIntelWidget() {
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('all');
  const { data, isLoading, error, refetch } = useQuery<FloodImagery>({
    queryKey: [...floodKeys.all, 'imagery'] as const,
    queryFn: fetchImagery,
    // Published imagery products are appended over days, never minutes.
    staleTime: 30 * 60 * 1000,
  });

  const counts = useMemo(() => {
    const acc: Record<TypeFilter, number> = { all: 0, pre_post: 0, impact_map: 0, analysis: 0 };
    for (const p of data?.products ?? []) {
      acc.all += 1;
      if (p.product_type in acc) acc[p.product_type as TypeFilter] += 1;
    }
    return acc;
  }, [data]);

  const products = useMemo(
    () => (data?.products ?? []).filter((p) => typeFilter === 'all' || p.product_type === typeFilter),
    [data, typeFilter],
  );

  if (isLoading) {
    return (
      <Widget id="flood-satellite-intel" icon={<Satellite size={14} />}>
        <WidgetSkeleton />
      </Widget>
    );
  }

  if (error || !data) {
    return (
      <Widget id="flood-satellite-intel" icon={<Satellite size={14} />}>
        <WidgetError message="Failed to load imagery intelligence" onRetry={() => refetch()} />
      </Widget>
    );
  }

  return (
    <Widget
      id="flood-satellite-intel"
      icon={<Satellite size={14} />}
      badge={data.count ? `${data.count} PUBLISHED` : undefined}
    >
      {data.activation && <ActivationBand activation={data.activation} />}

      <div style={{
        display: 'flex',
        gap: 4,
        padding: '5px 12px',
        borderBottom: `1px solid ${C.border}`,
        flexShrink: 0,
        overflowX: 'auto',
      }}>
        {TYPE_FILTERS.map((opt) => (
          <button
            key={opt.key}
            onClick={() => setTypeFilter(opt.key)}
            style={{
              padding: '3px 7px',
              fontSize: 9,
              fontWeight: 600,
              fontFamily: C.mono,
              letterSpacing: '0.06em',
              textTransform: 'uppercase',
              cursor: 'pointer',
              whiteSpace: 'nowrap',
              border: `1px solid ${C.border}`,
              background: typeFilter === opt.key ? C.elevated : 'transparent',
              color: typeFilter === opt.key ? C.text : C.muted,
            }}
          >
            {opt.label} {counts[opt.key]}
          </button>
        ))}
      </div>

      <div style={{
        flex: '1 1 0',
        minHeight: 0,
        overflowY: 'auto',
        overflowX: 'hidden',
        padding: 10,
      }}>
        {products.length === 0 ? (
          <WidgetEmpty message="No imagery products recorded for this event" />
        ) : (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
            gap: 8,
            alignItems: 'stretch',
          }}>
            {products.map((p) => (
              <ProductCard key={`${p.provider}:${p.title}`} product={p} />
            ))}
          </div>
        )}
      </div>

      {/* Stays out of the scroll region: a reader who never reaches the bottom
          of the catalogue still has to be told what this desk can and cannot
          show them at full resolution. */}
      <div style={{
        flexShrink: 0,
        padding: '6px 12px',
        borderTop: `1px solid ${C.border}`,
        background: C.surface,
        fontSize: 9,
        lineHeight: 1.5,
        color: C.muted,
      }}>
        Published record, not the imagery itself — each product opens at full resolution
        on the publisher's own site. The two collections this desk is licensed to display are
        shown elsewhere: CC0 Gyirong Port ground imagery in the District Impact Map, and the
        CC BY-NC 4.0 Vantor open-data scenes in Damage Pairs. Every other product here
        remains a link to the publisher's own site.
      </div>
    </Widget>
  );
});
