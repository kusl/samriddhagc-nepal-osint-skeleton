/**
 * The film's evidence cards — what the director puts beside the map while a
 * chapter holds: a public-domain CCTV clip of the port going under, the CC0
 * satellite pair of the same site, a Vantor same-frame before/after, an
 * official Army photograph, or a text citation for a finding nobody has
 * released an image of.
 *
 * Every visual card is a DISPLAY-tier file the desk already serves with its
 * author and licence; the card prints both. A cite card is text only. Nothing
 * here is typed in: the scene names a file, a photo title, a site, or a beat,
 * and the card resolves it against live data or renders nothing.
 *
 * Milspec: no rails, no rounded cards, one hairline between header and media,
 * uppercase mono labels. Fits its column; never scrolls.
 */
import { memo, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { ExternalLink } from 'lucide-react';

import { CELL, Grade, HAIRLINE, LABEL_XS, MS, PROSE, Status, Tag, dtgDay, dtgNpt, gradeFor } from '../milspec';
import type { FilmCard, FilmScene, TimelineBeat } from './replayEngine';

// ------------------------------------------------------------------ inputs

/** One file from GET /flood/media (Wikimedia Commons, curated + discovered). */
export interface CommonsItem {
  id: string;
  file: string;
  title: string;
  caption?: string | null;
  provider?: string | null;
  author?: string | null;
  license?: string | null;
  license_url?: string | null;
  kind: 'image' | 'video' | 'pdf' | string;
  mime?: string | null;
  thumb_url?: string | null;
  file_url?: string | null;
  page_url?: string | null;
  capture_date?: string | null;
  width?: number | null;
  height?: number | null;
}

/** One frame from GET /flood/photos (official, display tier). */
export interface PhotoItem {
  id: string;
  source: string;
  kind: string;
  title: string;
  title_ne?: string | null;
  caption?: string | null;
  credit?: string | null;
  page_url?: string | null;
  image_url: string;
  licence_tier: string;
  published_at?: string | null;
}

export interface VantorLevelLike {
  level: string;
  width_m?: number;
  bbox?: number[];
  pre: { export_url: string; top?: { platform?: string | null; datetime?: string; gsd_m?: number | null; cloud?: number | null } | null };
  post: { export_url: string; top?: { platform?: string | null; datetime?: string; gsd_m?: number | null; cloud?: number | null } | null };
}

export interface DamageSiteLike {
  key: string;
  name: string;
  levels?: VantorLevelLike[];
}

export interface ReplayCardsProps {
  scene: FilmScene | null;
  /** Event time now — cards with a start time appear only once it has passed. */
  t: number;
  /** Real seconds into the film: drives the card cycle. */
  filmR: number;
  commons: CommonsItem[];
  photos: PhotoItem[];
  damageSites: DamageSiteLike[];
  beats: TimelineBeat[];
  /** Resolves an API-relative image path to something an <img> can load. */
  imageSrc: (url: string | null | undefined) => string | null;
  sources?: Array<{ label: string; url: string }>;
  style?: CSSProperties;
}

// ------------------------------------------------------------------ licence

/** Files the desk may put on screen. Anything else is a link, never a picture. */
const DISPLAY_LICENCES = /cc0|public domain|cc by|cc-by|attribution/i;
const NON_DISPLAY = /all rights reserved|©|copyright|nd\b/i;

const displayable = (licence: string | null | undefined): boolean =>
  !!licence && DISPLAY_LICENCES.test(licence) && !NON_DISPLAY.test(licence.replace(/cc[- ]by[- ]nc/i, ''));

const norm = (v: string) => v.toLowerCase().replace(/[_\s]+/g, ' ').trim();

// ------------------------------------------------------------------ pieces

const head: CSSProperties = {
  display: 'flex',
  alignItems: 'baseline',
  gap: 6,
  padding: '0 0 3px',
  borderBottom: HAIRLINE,
  minWidth: 0,
};

const clip: CSSProperties = { minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' };

function Footer({ author, licence, licenceUrl, pageUrl, extra }: { author?: string | null; licence?: string | null; licenceUrl?: string | null; pageUrl?: string | null; extra?: string | null }) {
  return (
    <div style={{ ...LABEL_XS, display: 'flex', alignItems: 'center', gap: 6, marginTop: 4, minWidth: 0 }}>
      <span style={clip}>{author ?? 'AUTHOR NOT STATED'}</span>
      {licence && (
        <a
          href={licenceUrl ?? undefined}
          target="_blank"
          rel="noreferrer noopener"
          style={{ color: MS.low, textDecoration: 'none', whiteSpace: 'nowrap', border: `1px solid ${MS.low}`, borderRadius: 2, padding: '0 4px', lineHeight: '14px', opacity: 0.9 }}
        >
          {licence.toUpperCase()}
        </a>
      )}
      {extra && <span style={{ ...clip, color: MS.muted }}>{extra}</span>}
      <span style={{ flex: 1 }} />
      {pageUrl && (
        <a href={pageUrl} target="_blank" rel="noreferrer noopener" style={{ color: MS.info, textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 3, whiteSpace: 'nowrap' }}>
          SOURCE <ExternalLink size={9} />
        </a>
      )}
    </div>
  );
}

function MediaBox({ children, aspect = 16 / 10 }: { children: React.ReactNode; aspect?: number }) {
  return (
    <div style={{ position: 'relative', width: '100%', aspectRatio: String(aspect), background: MS.elevated, overflow: 'hidden' }}>{children}</div>
  );
}

/** Same-frame before/after: a wipe that sweeps left→right over eight seconds
 *  and back, so the eye is led across the change rather than shown two stills. */
function Wipe({ pre, post, preLabel, postLabel }: { pre: string; post: string; preLabel: string; postLabel: string }) {
  const [x, setX] = useState(0);
  useEffect(() => {
    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const p = ((now - start) / 8000) % 2; // 0..2
      const v = p < 1 ? p : 2 - p; // triangle 0→1→0
      setX(Math.round(v * 1000) / 10);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);
  return (
    <MediaBox aspect={1600 / 960}>
      <img src={pre} alt={preLabel} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }} />
      <img src={post} alt={postLabel} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', clipPath: `inset(0 0 0 ${x}%)` }} />
      <div style={{ position: 'absolute', top: 0, bottom: 0, left: `${x}%`, width: 1, background: MS.text, opacity: 0.9 }} />
      <span style={{ ...LABEL_XS, position: 'absolute', left: 6, bottom: 4, color: MS.text, textShadow: `0 0 3px ${MS.surface}` }}>{preLabel}</span>
      <span style={{ ...LABEL_XS, position: 'absolute', right: 6, bottom: 4, color: MS.critical, textShadow: `0 0 3px ${MS.surface}` }}>{postLabel}</span>
    </MediaBox>
  );
}

const sceneStamp = (top: VantorLevelLike['pre']['top']): string =>
  top ? `${(top.platform ?? 'VANTOR').toUpperCase()} ${dtgDay(top.datetime)}${typeof top.gsd_m === 'number' ? ` · ${top.gsd_m.toFixed(2)} M` : ''}${typeof top.cloud === 'number' ? ` · ${Math.round(top.cloud)}% CLOUD` : ''}` : 'DATE NOT STATED';

// ------------------------------------------------------------------ cards

function CommonsCard({ item, caption, video }: { item: CommonsItem; caption?: string; video: boolean }) {
  const src = video ? item.file_url : item.thumb_url ?? item.file_url;
  if (!src || !displayable(item.license)) return null;
  return (
    <div style={{ minWidth: 0 }}>
      <div style={head}>
        <Tag tone={video ? 'critical' : 'info'}>{video ? 'FOOTAGE' : 'IMAGE'}</Tag>
        <span style={{ ...CELL, color: MS.text, ...clip }} title={item.title}>{item.title}</span>
        {item.capture_date && <span style={{ ...LABEL_XS, whiteSpace: 'nowrap' }}>{dtgDay(item.capture_date)}</span>}
      </div>
      <div style={{ marginTop: 6 }}>
        <MediaBox aspect={item.width && item.height ? item.width / item.height : 16 / 10}>
          {video ? (
            <video src={src} autoPlay muted loop playsInline preload="auto" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }} />
          ) : (
            <img src={src} alt={item.title} loading="eager" decoding="async" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }} />
          )}
        </MediaBox>
      </div>
      {(caption ?? item.caption) && <div style={{ ...PROSE, marginTop: 4, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{caption ?? item.caption}</div>}
      <Footer author={item.author} licence={item.license} licenceUrl={item.license_url} pageUrl={item.page_url} extra={item.provider} />
    </div>
  );
}

function PhotoCard({ item, src, caption }: { item: PhotoItem; src: string; caption?: string }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div style={head}>
        <Tag tone="info">OFFICIAL PHOTOGRAPH</Tag>
        <span style={{ ...CELL, color: MS.text, ...clip }} title={item.title}>{item.title}</span>
        {item.published_at && <span style={{ ...LABEL_XS, whiteSpace: 'nowrap' }}>{dtgDay(item.published_at)}</span>}
      </div>
      <div style={{ marginTop: 6 }}>
        <MediaBox aspect={16 / 10}>
          <img src={src} alt={item.title} loading="eager" decoding="async" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }} />
        </MediaBox>
      </div>
      {(caption ?? item.title_ne) && <div style={{ ...PROSE, marginTop: 4, ...clip }}>{caption ?? item.title_ne}</div>}
      <Footer author={item.credit} licence="GOVERNMENT-PUBLISHED" pageUrl={item.page_url} />
    </div>
  );
}

function VantorCard({ site, level, caption }: { site: DamageSiteLike; level: VantorLevelLike; caption?: string }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div style={head}>
        <Tag tone="high">SAME-FRAME BEFORE / AFTER</Tag>
        <span style={{ ...CELL, color: MS.text, ...clip }}>{site.name}</span>
        {level.width_m && <span style={{ ...LABEL_XS, whiteSpace: 'nowrap' }}>{level.width_m} M FRAME</span>}
      </div>
      <div style={{ marginTop: 6 }}>
        <Wipe pre={level.pre.export_url} post={level.post.export_url} preLabel={`PRE · ${sceneStamp(level.pre.top)}`} postLabel={`POST · ${sceneStamp(level.post.top)}`} />
      </div>
      {caption && <div style={{ ...PROSE, marginTop: 4, ...clip }}>{caption}</div>}
      <Footer author="Vantor (formerly Maxar) Open Data, via Esri Disaster Response Program" licence="CC BY-NC 4.0" licenceUrl="https://creativecommons.org/licenses/by-nc/4.0/" pageUrl="https://vantor-opendata.s3.amazonaws.com/events/Nepal-Flooding-Aug-2026/collection.json" />
    </div>
  );
}

function CiteCard({ beat }: { beat: TimelineBeat }) {
  const g = gradeFor(beat.source).code;
  return (
    <div style={{ minWidth: 0 }}>
      <div style={head}>
        <Tag tone="muted">CITED · NO IMAGE RELEASED</Tag>
        <span style={{ ...LABEL_XS, whiteSpace: 'nowrap' }}>{dtgNpt(beat.t_npt, beat.time_published)}</span>
      </div>
      <div style={{ ...CELL, color: MS.text, marginTop: 6, lineHeight: 1.35 }}>{beat.headline}</div>
      {beat.detail && <div style={{ ...PROSE, marginTop: 4, display: '-webkit-box', WebkitLineClamp: 4, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{beat.detail}</div>}
      <div style={{ ...LABEL_XS, display: 'flex', alignItems: 'center', gap: 6, marginTop: 5, minWidth: 0 }}>
        <span style={clip}>{beat.source}</span>
        <Grade code={g} />
        <span style={{ flex: 1 }} />
        {beat.source_url && (
          <a href={beat.source_url} target="_blank" rel="noreferrer noopener" style={{ color: MS.info, textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 3, whiteSpace: 'nowrap' }}>
            SOURCE <ExternalLink size={9} />
          </a>
        )}
      </div>
    </div>
  );
}

function EndCard({ sources }: { sources: Array<{ label: string; url: string }> }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div style={head}>
        <Tag tone="text">SOURCES</Tag>
        <span style={{ ...LABEL_XS }}>EVERY FIGURE AND FRAME IN THIS FILM</span>
      </div>
      <div style={{ marginTop: 6 }}>
        {sources.slice(0, 14).map((s) => (
          <a key={s.url} href={s.url} target="_blank" rel="noreferrer noopener" style={{ ...LABEL_XS, display: 'flex', gap: 6, alignItems: 'center', padding: '2px 0', borderBottom: HAIRLINE, textDecoration: 'none', color: MS.sub, minWidth: 0 }}>
            <Grade code={gradeFor(s.label).code} />
            <span style={clip}>{s.label}</span>
            <ExternalLink size={9} color={MS.info} style={{ flex: '0 0 auto' }} />
          </a>
        ))}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ panel

/** Seconds each card holds the panel before the next one in the scene. */
const CARD_CYCLE_S = 9;

export const ReplayCards = memo(function ReplayCards({ scene, t, filmR, commons, photos, damageSites, beats, imageSrc, sources = [], style }: ReplayCardsProps) {
  const active = useMemo(() => (scene ? scene.cards.filter((c) => t >= c.t) : []), [scene, t]);
  // One card at a time, large enough to read, cycling through the chapter's
  // deck in the director's order — footage first where there is footage.
  const cycleIndex = active.length ? Math.floor(Math.max(0, filmR - (scene?.realStart ?? 0)) / CARD_CYCLE_S) % active.length : 0;
  const shown = useMemo(() => (active.length ? [active[cycleIndex]] : []), [active, cycleIndex]);
  const boxRef = useRef<HTMLDivElement | null>(null);

  if (!scene || !shown.length) return null;

  const resolve = (card: FilmCard, i: number) => {
    switch (card.kind) {
      case 'commons':
      case 'video': {
        const want = norm(card.file ?? '');
        const item = commons.find((c) => norm(c.file) === want || norm(c.title) === want);
        return item ? <CommonsCard key={`${card.kind}-${i}`} item={item} caption={card.caption} video={card.kind === 'video' || item.kind === 'video'} /> : null;
      }
      case 'photo': {
        const want = norm(card.match ?? '');
        const item = photos.find((p) => p.licence_tier === 'display' && norm(p.title).includes(want));
        const src = item ? imageSrc(item.image_url) : null;
        return item && src ? <PhotoCard key={`photo-${i}`} item={item} src={src} caption={card.caption} /> : null;
      }
      case 'vantor': {
        const site = damageSites.find((d) => d.key === card.site);
        const level = site?.levels?.find((l) => l.level === (card.level ?? 'detail')) ?? site?.levels?.[0];
        return site && level?.pre?.export_url && level?.post?.export_url ? <VantorCard key={`vantor-${i}`} site={site} level={level} caption={card.caption} /> : null;
      }
      case 'cite': {
        const beat = typeof card.beat === 'number' ? beats[card.beat] : undefined;
        return beat ? <CiteCard key={`cite-${i}`} beat={beat} /> : null;
      }
      case 'end':
        return <EndCard key="end" sources={sources} />;
      default:
        return null;
    }
  };

  const nodes = shown.map(resolve).filter(Boolean);
  if (!nodes.length) return null;

  return (
    <div
      ref={boxRef}
      style={{
        position: 'absolute',
        top: 40,
        right: 8,
        bottom: 8,
        width: '34%',
        minWidth: 280,
        maxWidth: 560,
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        padding: '8px 10px',
        background: 'rgba(17, 17, 19, 0.9)',
        borderRadius: 2,
        overflow: 'hidden',
        pointerEvents: 'auto',
        ...style,
      }}
    >
      <div style={{ ...LABEL_XS, display: 'flex', alignItems: 'center', gap: 6 }}>
        <Status tone="text">EVIDENCE</Status>
        <span style={{ ...clip, color: MS.muted }}>{scene.title}</span>
        {active.length > 1 && <span style={{ marginLeft: 'auto', whiteSpace: 'nowrap', color: MS.muted }}>CARD {cycleIndex + 1} / {active.length}</span>}
      </div>
      {nodes}
    </div>
  );
});

export default ReplayCards;
