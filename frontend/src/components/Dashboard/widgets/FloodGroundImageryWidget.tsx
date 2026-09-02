/**
 * Ground imagery for the active flood event — what the corridor actually looks
 * like, under the licence each frame was published with.
 *
 * Two tiers, and the split is legal rather than cosmetic. Government agencies
 * (OPMCM rescue portal, NDRRMA press notes) publish their photographs for
 * republication, so those render as pictures with the crediting line the licence
 * asks for. Press pictures are the outlet's own link preview: they stay small,
 * always carry the outlet name, and every one of them is a link back to the
 * article. Nothing is rehosted — `image_url` is the desk's own proxy for the
 * upstream file, and the press column exists to send the reader to the outlet.
 *
 * Every string and every frame comes from the API. Rendered through the MILSPEC
 * grammar (components/flood/milspec) like the rest of the flood desk: no rails,
 * no cards, one scroll region, one source line last.
 */
import { memo, useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Camera, ExternalLink, X, ChevronLeft, ChevronRight } from 'lucide-react';

import { Widget } from '../Widget';
import apiClient from '../../../api/client';
import { floodKeys } from '../../../api/hooks/useFlood';
import { WidgetEmpty, WidgetError, WidgetSkeleton } from './shared';
import {
  Body,
  CELL,
  Grade,
  HAIRLINE,
  LABEL,
  LABEL_XS,
  MS,
  Note,
  PROSE,
  Section,
  SourceLine,
  dtgDay,
  gradeFor,
  FIGURE,
} from '../../flood/milspec';

// ------------------------------------------------------------------ payloads

/** `GET /flood/photos` — govt frames first by display order, then press leads. */
interface FloodPhoto {
  id: string;
  source: string;
  kind: string;
  title: string;
  title_ne: string | null;
  caption: string | null;
  credit: string | null;
  outlet: string | null;
  page_url: string | null;
  image_url: string;
  licence_tier: string;
  published_at: string | null;
}

interface FloodPhotosResponse {
  event_key: string;
  count: number;
  items: FloodPhoto[];
}

/** `GET /flood/press` — matched stories, with a link-preview image where one exists. */
interface FloodPressItem {
  id: string;
  title: string;
  outlet: string | null;
  url: string | null;
  published_at: string | null;
  image_url: string | null;
  districts: string[] | null;
}

interface FloodPressResponse {
  event_key: string;
  count: number;
  items: FloodPressItem[];
}

const EMPTY_PHOTOS: FloodPhotosResponse = { event_key: '', count: 0, items: [] };
const EMPTY_PRESS: FloodPressResponse = { event_key: '', count: 0, items: [] };

/**
 * The live-sync endpoints land after this widget does, so a 404 is a normal
 * state of the world here, not a failure: it renders as "nothing published yet".
 * Anything else still surfaces as an error, because a 500 is worth telling
 * someone about.
 */
const isNotFound = (err: unknown): boolean =>
  typeof err === 'object' && err !== null &&
  (err as { response?: { status?: number } }).response?.status === 404;

async function getOrEmpty<T>(path: string, empty: T): Promise<T> {
  try {
    return (await apiClient.get(path)).data as T;
  } catch (err) {
    if (isNotFound(err)) return empty;
    throw err;
  }
}

/**
 * The API hands back a server-absolute path ("/api/v1/flood/photos/<id>/image").
 * That is correct when the client talks to a relative base, but wrong when
 * VITE_API_URL points the desk at another host — the browser would ask the Vite
 * dev server for a picture only the API can stream. So the path is re-anchored
 * on the client's own base instead of being trusted as written.
 */
function imageSrc(url: string | null | undefined): string | null {
  if (!url) return null;
  if (/^(https?:|data:|blob:)/i.test(url)) return url;
  const base = (apiClient.defaults.baseURL ?? '').replace(/\/+$/, '');
  if (!base || base.startsWith('/')) return url;
  return `${base.replace(/\/api\/v1$/, '')}${url}`;
}

// ------------------------------------------------------------------ layout

const CLAMP2: CSSProperties = {
  display: '-webkit-box',
  WebkitLineClamp: 2,
  WebkitBoxOrient: 'vertical',
  overflow: 'hidden',
};

const ONE_LINE: CSSProperties = {
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
};

const newest = (values: Array<string | null | undefined>): string | null =>
  values.reduce<string | null>((best, v) => (v && (!best || v > best) ? v : best), null);

// ------------------------------------------------------------------ sizing

/** Tile geometry. Frames are 4:3; the caption band under each is fixed. */
const TILE_MIN_W = 190;
const TILE_GAP = 8;
const CAPTION_H = 30;
const SECTION_H = 24;
/** A press row is a fixed height so the column can be counted, not scrolled. */
const PRESS_ROW_H = 56;

interface Box { w: number; h: number }

/**
 * Live size of an element, so the layout can count what fits instead of
 * scrolling. A callback ref rather than a ref object: the measured element
 * mounts only after the loading state, so an effect that ran once on first
 * render would observe nothing and the grid would never learn its size.
 */
function useBox<T extends HTMLElement>(): [(node: T | null) => void, Box] {
  const [box, setBox] = useState<Box>({ w: 0, h: 0 });
  const obs = useRef<ResizeObserver | null>(null);
  const attach = useCallback((node: T | null) => {
    obs.current?.disconnect();
    obs.current = null;
    if (!node) return;
    const read = () => {
      const r = node.getBoundingClientRect();
      setBox((b) => (Math.abs(b.w - r.width) < 1 && Math.abs(b.h - r.height) < 1 ? b : { w: r.width, h: r.height }));
    };
    read();
    const ro = new ResizeObserver(read);
    ro.observe(node);
    obs.current = ro;
  }, []);
  return [attach, box];
}

/**
 * How many 4:3 tiles fit a box, and at what size. The rule is FILL, not "as
 * many as possible": among the column counts that give at least one row, the
 * one whose rows use the most of the box's height wins, so a short widget
 * shows a few large frames rather than a strip of small ones, and a taller
 * widget gains rows before it gains columns. Below four frames of capacity
 * the next column count is tried, so a gallery never collapses to two tiles.
 */
function tileCapacity(box: Box, frames: number): { cols: number; rows: number; tileW: number } {
  if (box.w <= 0 || box.h <= 0) return { cols: 0, rows: 0, tileW: 0 };
  const avail = box.h - SECTION_H;
  let best: { cols: number; rows: number; tileW: number; used: number } | null = null;
  for (let cols = 2; cols <= 6; cols += 1) {
    const tileW = (box.w - TILE_GAP * (cols - 1)) / cols;
    if (tileW < TILE_MIN_W * 0.8) break;
    const tileH = tileW * 0.75 + CAPTION_H;
    const rows = Math.floor((avail + TILE_GAP) / (tileH + TILE_GAP));
    if (rows < 1) continue;
    if (cols * rows < Math.min(4, frames) && cols < 6) continue;
    const used = rows * tileH + (rows - 1) * TILE_GAP;
    if (!best || used > best.used + 1) best = { cols, rows, tileW, used };
  }
  if (!best) {
    // Nothing fits cleanly: fall back to the narrowest tiles in one row.
    const cols = 6;
    return { cols, rows: 1, tileW: (box.w - TILE_GAP * (cols - 1)) / cols };
  }
  return { cols: best.cols, rows: best.rows, tileW: best.tileW };
}

// ------------------------------------------------------------------ lightbox

/**
 * Inset gallery viewer. It covers the widget rather than the page because a
 * photograph of the border post is evidence for the desk it opened from, not a
 * separate exhibit — and an overlay that escapes its widget breaks the wall.
 * It browses the WHOLE gallery, including frames the grid had no room for,
 * which is how the widget stays fitted without hiding anything.
 */
function Lightbox({
  frames,
  index,
  onIndex,
  onClose,
}: {
  frames: FloodPhoto[];
  index: number;
  onIndex: (i: number) => void;
  onClose: () => void;
}) {
  const photo = frames[index];
  const prev = useCallback(() => onIndex((index - 1 + frames.length) % frames.length), [index, frames.length, onIndex]);
  const next = useCallback(() => onIndex((index + 1) % frames.length), [index, frames.length, onIndex]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      else if (e.key === 'ArrowLeft') prev();
      else if (e.key === 'ArrowRight') next();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, prev, next]);

  if (!photo) return null;
  const src = imageSrc(photo.image_url);
  const kind = photo.source === 'ndrrma_press' ? 'OFFICIAL NOTICE' : 'OFFICIAL PHOTOGRAPH';

  const navBtn: CSSProperties = {
    ...LABEL_XS,
    color: MS.text,
    background: 'transparent',
    border: `1px solid ${MS.rule}`,
    borderRadius: 2,
    padding: '2px 6px',
    cursor: 'pointer',
    display: 'inline-flex',
    alignItems: 'center',
    gap: 2,
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: 'absolute',
        inset: 0,
        zIndex: 20,
        background: MS.surface,
        display: 'flex',
        flexDirection: 'column',
        padding: '10px 12px 8px',
        gap: 8,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: '0 0 auto' }}>
        <span style={{ ...LABEL, color: MS.text, fontWeight: 600 }}>{kind}</span>
        <span style={{ ...LABEL_XS }}>{dtgDay(photo.published_at)}</span>
        <span style={{ ...LABEL_XS, fontVariantNumeric: 'tabular-nums' }}>
          {index + 1} / {frames.length}
        </span>
        <span style={{ flex: 1, borderBottom: HAIRLINE }} />
        <button type="button" onClick={(e) => { e.stopPropagation(); prev(); }} style={navBtn} title="Previous (←)">
          <ChevronLeft size={10} /> PREV
        </button>
        <button type="button" onClick={(e) => { e.stopPropagation(); next(); }} style={navBtn} title="Next (→)">
          NEXT <ChevronRight size={10} />
        </button>
        <span style={{ ...LABEL_XS, display: 'inline-flex', alignItems: 'center', gap: 3 }}>
          ESC <X size={10} />
        </span>
      </div>

      {src && (
        <img
          src={src}
          alt={photo.title}
          onClick={(e) => { e.stopPropagation(); next(); }}
          style={{ flex: 1, minHeight: 0, width: '100%', objectFit: 'contain', background: MS.elevated, cursor: 'e-resize' }}
        />
      )}

      <div style={{ flex: '0 0 auto' }}>
        <div style={{ ...CELL, color: MS.text }}>{photo.title}</div>
        {photo.title_ne && (
          <div style={{ ...CELL, color: MS.sub, marginTop: 2 }}>{photo.title_ne}</div>
        )}
        {photo.caption && <div style={{ ...PROSE, marginTop: 3 }}>{photo.caption}</div>}
        <div style={{ ...LABEL_XS, marginTop: 4, display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ minWidth: 0, ...ONE_LINE }}>{photo.credit ?? 'CREDIT NOT STATED'}</span>
          {photo.page_url && (
            <a
              href={photo.page_url}
              target="_blank"
              rel="noreferrer noopener"
              onClick={(e) => e.stopPropagation()}
              style={{ color: MS.info, textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 3, whiteSpace: 'nowrap' }}
            >
              PUBLISHER <ExternalLink size={9} />
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ widget

export const FloodGroundImageryWidget = memo(function FloodGroundImageryWidget() {
  const photos = useQuery<FloodPhotosResponse>({
    queryKey: [...floodKeys.all, 'photos'] as const,
    queryFn: () => getOrEmpty('/flood/photos', EMPTY_PHOTOS),
    staleTime: 5 * 60 * 1000,
    refetchInterval: 10 * 60 * 1000,
  });

  const press = useQuery<FloodPressResponse>({
    queryKey: [...floodKeys.all, 'press'] as const,
    queryFn: () => getOrEmpty('/flood/press?hours=72&limit=24', EMPTY_PRESS),
    staleTime: 60 * 1000,
  });

  // A frame whose bytes never arrive is removed rather than left as a broken
  // icon: a hole in the grid says "nothing published", which would be a lie.
  const [broken, setBroken] = useState<ReadonlySet<string>>(() => new Set<string>());
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  const markBroken = useCallback((id: string) => {
    setBroken((prev) => {
      if (prev.has(id)) return prev;
      const next = new Set(prev);
      next.add(id);
      return next;
    });
  }, []);

  // Photographs lead the gallery; NDRRMA press-note graphics (a QR code, a
  // funds table) follow them — government-published, but not photographs, so
  // they never sit in the frame grid beside a rescue.
  const photoFrames = useMemo(
    () =>
      (photos.data?.items ?? []).filter(
        (p) => p.licence_tier !== 'link_preview' && p.source !== 'ndrrma_press' && p.image_url && !broken.has(p.id),
      ),
    [photos.data, broken],
  );
  const noticeFrames = useMemo(
    () =>
      (photos.data?.items ?? []).filter(
        (p) => p.source === 'ndrrma_press' && p.image_url && !broken.has(p.id),
      ),
    [photos.data, broken],
  );
  const gallery = useMemo(() => [...photoFrames, ...noticeFrames], [photoFrames, noticeFrames]);

  const pressItems = useMemo(() => (press.data?.items ?? []).slice(0, 24), [press.data]);

  const asOf = useMemo(
    () => newest([...gallery.map((p) => p.published_at), ...pressItems.map((p) => p.published_at)]),
    [gallery, pressItems],
  );

  // The layout counts what fits. Nothing in this widget scrolls: the grid shows
  // as many frames as its box holds, the last tile carries the remainder into
  // the gallery, and the press column shows as many rows as its height allows.
  const [gridRef, gridBox] = useBox<HTMLDivElement>();
  const [pressRef, pressBox] = useBox<HTMLDivElement>();
  const cap = tileCapacity(gridBox, photoFrames.length);
  const capacity = cap.cols * cap.rows;
  const overflow = Math.max(0, photoFrames.length - capacity);
  const visibleFrames = overflow > 0 ? photoFrames.slice(0, Math.max(0, capacity - 1)) : photoFrames;
  const moreTile = overflow > 0 ? photoFrames[Math.max(0, capacity - 1)] : null;
  const hiddenCount = overflow > 0 ? overflow + 1 : 0;
  const pressRows = Math.max(1, Math.floor((pressBox.h - SECTION_H) / PRESS_ROW_H));
  const visiblePress = pressItems.slice(0, pressRows);
  const pressHidden = Math.max(0, pressItems.length - visiblePress.length);

  const total = gallery.length + pressItems.length;

  const close = useCallback(() => setOpenIndex(null), []);

  if (photos.isLoading || press.isLoading) {
    return (
      <Widget id="flood-ground-imagery" title="GROUND IMAGERY" icon={<Camera size={14} />}>
        <WidgetSkeleton />
      </Widget>
    );
  }

  // One feed failing is survivable — the other column still carries the picture.
  if (photos.error && press.error) {
    return (
      <Widget id="flood-ground-imagery" title="GROUND IMAGERY" icon={<Camera size={14} />}>
        <WidgetError
          message="Failed to load ground imagery"
          onRetry={() => {
            photos.refetch();
            press.refetch();
          }}
        />
      </Widget>
    );
  }

  if (total === 0) {
    return (
      <Widget id="flood-ground-imagery" title="GROUND IMAGERY" icon={<Camera size={14} />}>
        <WidgetEmpty message="No imagery published yet" />
      </Widget>
    );
  }

  const tileStyle = (): CSSProperties => ({ minWidth: 0, cursor: 'pointer' });

  return (
    <Widget
      id="flood-ground-imagery"
      title="GROUND IMAGERY"
      icon={<Camera size={14} />}
      badge={`${total} FRAMES`}
    >
      <Body style={{ position: 'relative', overflow: 'hidden' }}>
        <div style={{ display: 'flex', alignItems: 'stretch', gap: 20, flex: 1, minHeight: 0, overflow: 'hidden' }}>
          {/* -------------------------------------------- official photographs */}
          <div ref={gridRef} style={{ flex: '1 1 64%', minWidth: 0, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <Section
              n={1}
              title="OFFICIAL PHOTOGRAPHS"
              meta={`DISPLAY TIER · GOVERNMENT-PUBLISHED${noticeFrames.length ? ` · ${noticeFrames.length} NOTICES IN GALLERY` : ''}`}
              style={{ marginTop: 0 }}
            />

            {photoFrames.length === 0 ? (
              <div style={{ ...LABEL_XS, padding: '6px 0' }}>NO OFFICIAL FRAMES PUBLISHED</div>
            ) : cap.cols === 0 ? null : (
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: `repeat(${cap.cols}, minmax(0, 1fr))`,
                  gridAutoRows: 'max-content',
                  gap: TILE_GAP,
                  paddingTop: 2,
                  overflow: 'hidden',
                }}
              >
                {visibleFrames.map((p, i) => {
                  const src = imageSrc(p.image_url);
                  if (!src) return null;
                  return (
                    <div key={p.id} onClick={() => setOpenIndex(i)} title={p.caption ?? p.title} style={tileStyle()}>
                      <img
                        src={src}
                        alt={p.title}
                        loading="lazy"
                        decoding="async"
                        onError={() => markBroken(p.id)}
                        style={{ display: 'block', width: '100%', aspectRatio: '4 / 3', objectFit: 'cover', background: MS.elevated }}
                      />
                      <div style={{ ...LABEL_XS, marginTop: 3, ...ONE_LINE }}>
                        {p.credit ?? 'CREDIT NOT STATED'} · {dtgDay(p.published_at)}
                      </div>
                      <div style={{ ...CELL, color: MS.text, ...ONE_LINE }}>{p.title}</div>
                    </div>
                  );
                })}

                {moreTile && (() => {
                  const src = imageSrc(moreTile.image_url);
                  return (
                    <div
                      key="more"
                      onClick={() => setOpenIndex(visibleFrames.length)}
                      title={`${hiddenCount} more frames — open the gallery`}
                      style={{ ...tileStyle(), position: 'relative' }}
                    >
                      {src && (
                        <img
                          src={src}
                          alt=""
                          loading="lazy"
                          decoding="async"
                          onError={() => markBroken(moreTile.id)}
                          style={{ display: 'block', width: '100%', aspectRatio: '4 / 3', objectFit: 'cover', background: MS.elevated, opacity: 0.28 }}
                        />
                      )}
                      <div
                        style={{
                          position: 'absolute',
                          left: 0,
                          right: 0,
                          top: 0,
                          aspectRatio: '4 / 3',
                          display: 'flex',
                          flexDirection: 'column',
                          alignItems: 'center',
                          justifyContent: 'center',
                          gap: 4,
                        }}
                      >
                        <span style={{ ...FIGURE, fontSize: 26, color: MS.text }}>+{hiddenCount}</span>
                        <span style={{ ...LABEL_XS, color: MS.sub }}>MORE · OPEN GALLERY</span>
                      </div>
                      <div style={{ ...LABEL_XS, marginTop: 3, ...ONE_LINE }}>{gallery.length} FRAMES · ← → TO BROWSE</div>
                      <div style={{ ...CELL, color: MS.text, ...ONE_LINE }}>Gallery</div>
                    </div>
                  );
                })()}
              </div>
            )}
          </div>

          {/* ------------------------------------------------- press link previews */}
          <div ref={pressRef} style={{ flex: '1 1 36%', minWidth: 0, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <Section
              n={2}
              title="PRESS · LINK PREVIEWS"
              meta={`© EACH OUTLET · LINKED, NOT REHOSTED${pressHidden ? ` · +${pressHidden} MORE IN LOG` : ''}`}
              style={{ marginTop: 0 }}
            />

            {pressItems.length === 0 ? (
              <div style={{ ...LABEL_XS, padding: '6px 0' }}>NO MATCHED PRESS IN THE WINDOW</div>
            ) : (
              visiblePress.map((item) => {
                const thumb = broken.has(item.id) ? null : imageSrc(item.image_url);
                const grade = gradeFor(item.outlet);
                return (
                  <a
                    key={item.id}
                    href={item.url ?? undefined}
                    target="_blank"
                    rel="noreferrer noopener"
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      height: PRESS_ROW_H,
                      boxSizing: 'border-box',
                      padding: '4px 0',
                      borderBottom: HAIRLINE,
                      textDecoration: 'none',
                      color: 'inherit',
                      overflow: 'hidden',
                    }}
                  >
                    <span style={{ flex: '0 0 auto', width: 64, height: 44, background: MS.elevated, overflow: 'hidden' }}>
                      {thumb && (
                        <img
                          src={thumb}
                          alt=""
                          loading="lazy"
                          decoding="async"
                          onError={() => markBroken(item.id)}
                          style={{ display: 'block', width: 64, height: 44, objectFit: 'cover' }}
                        />
                      )}
                    </span>
                    <span style={{ minWidth: 0, flex: 1 }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span style={{ ...LABEL_XS, minWidth: 0, ...ONE_LINE }}>{item.outlet ?? 'OUTLET NOT STATED'}</span>
                        <Grade code={grade.code} />
                        <span style={{ ...LABEL_XS, whiteSpace: 'nowrap' }}>{dtgDay(item.published_at)}</span>
                      </span>
                      <span style={{ ...CELL, color: MS.sub, marginTop: 2, ...CLAMP2, WebkitLineClamp: 2, lineHeight: 1.3 }} title={item.title}>
                        {item.title}
                      </span>
                    </span>
                    <ExternalLink size={10} color={MS.info} style={{ flex: '0 0 auto' }} />
                  </a>
                );
              })
            )}
          </div>
        </div>

        <Note>
          Official photographs are published by government agencies and shown with credit. Press images are the
          outlet’s own link preview, shown small and linked; nothing is rehosted.
        </Note>
        <SourceLine
          source={`${photoFrames.length} OFFICIAL FRAMES · ${noticeFrames.length} NOTICES · ${pressItems.length} PRESS ITEMS`}
          grade={false}
          asOf={dtgDay(asOf)}
        />

        {openIndex !== null && gallery.length > 0 && (
          <Lightbox frames={gallery} index={Math.min(openIndex, gallery.length - 1)} onIndex={setOpenIndex} onClose={close} />
        )}
      </Body>
    </Widget>
  );
});
