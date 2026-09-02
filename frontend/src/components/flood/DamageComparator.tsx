/**
 * The same-frame before/after comparator, and the panels that speak for it when
 * there are no pixels to show.
 *
 * PRE and POST are two renders of one bbox from the Esri Disaster Response
 * Program service over the Vantor collection, so the two images register to each
 * other exactly and a divider dragged across them is a true comparison of the
 * same ground. That is the whole mechanism: no reprojection here, no fitting by
 * eye, nothing this module computes about where anything is.
 *
 * It lives beside the map rather than inside a widget because the comparator is
 * now opened from two places — the tactical map's damage chips, where the pair
 * hangs off the point it depicts, and the archived explorer widget, which still
 * walks the corridor as a list. One copy, so a caption fixed in one surface
 * cannot go stale in the other.
 *
 * Three captions here are load-bearing and must survive any edit. The pre frames
 * are 2021–2026 archive baselines, so their age gap is always spelled out — a
 * reader shown PRE beside POST assumes days. The cloud figure is a whole-scene
 * number and is labelled as one, because the 79% pass is cloud-free over
 * Rasuwagadhi and a blanket "79% cloud" over that frame would mislead in the
 * opposite direction. And where the backend reports no footprint in view it
 * sends no URL at all: the service answers uncovered ground with a transparent
 * PNG and HTTP 200, so onError never fires and absence must be stated, never
 * detected.
 */
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { ExternalLink } from 'lucide-react';

import { formatSceneDay, baselineGap, HEAVY_CLOUD_PCT } from './vantorScenes';
import {
  formatGroundWidth,
  formatDateSpan,
  type DamageSitesResponse,
  type DamageSite,
  type DamageLevel,
  type DamagePhase,
  type DamageLevelKey,
} from './damageSites';

export const C = {
  info: 'var(--status-info)',
  warn: 'var(--status-medium)',
  muted: 'var(--text-muted)',
  text: 'var(--text-primary)',
  sub: 'var(--text-secondary)',
  base: 'var(--bg-base)',
  surface: 'var(--bg-surface)',
  elevated: 'var(--bg-elevated)',
  border: 'var(--border-subtle)',
  strong: 'var(--border-default)',
  mono: 'var(--font-mono)',
};

export const label: React.CSSProperties = {
  fontFamily: C.mono,
  fontSize: 10,
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  color: C.muted,
};

export const figure: React.CSSProperties = {
  fontFamily: C.mono,
  fontVariantNumeric: 'tabular-nums',
};

export const chipStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 4,
  padding: '2px 6px',
  border: `1px solid ${C.border}`,
  background: C.elevated,
  color: C.info,
  fontFamily: C.mono,
  fontSize: 9,
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
  textDecoration: 'none',
  whiteSpace: 'nowrap',
};

/** The frame is a 5:3 export; the comparator box matches it so the divider
 *  percentage maps to the imagery and not to letterboxing beside it. */
const FRAME_ASPECT = 5 / 3;

/** Below this the rail and the dossier stop fitting beside a legible frame. */
export const NARROW_PX = 820;

/** The EMS activation that graded Syabrubesi. Cited against licensed pixels of
 *  the same ground: the pair shows, the citation counts. */
export const EMSR927_URL = 'https://mapping.emergency.copernicus.eu/activations/EMSR927/';

export const LEVEL_NAME: Record<DamageLevelKey, string> = {
  context: 'Context',
  site: 'Site',
  detail: 'Detail',
};

type LoadState = 'pending' | 'ok' | 'failed';

/** Whether each half of the record answered just now is part of the record. */
export function provenanceLine(data: DamageSitesResponse): string {
  const word = (s: string) => (s === 'fallback' ? 'vendored record' : s);
  return `IMAGE CATALOG ${word(data.source.drp_catalog)} · STAC ${word(data.source.stac)}`;
}

/**
 * Container size drives the frame box and the layout; the divider is a
 * percentage of it. A callback ref rather than a plain one, because the measured
 * node only mounts once the query resolves — a ref object never changes
 * identity, so the effect would run once against nothing and never re-attach.
 */
export function useBoxSize<T extends HTMLElement>(): [(node: T | null) => void, { w: number; h: number }] {
  const [node, setNode] = useState<T | null>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  useLayoutEffect(() => {
    if (!node) return;
    const ro = new ResizeObserver(([entry]) => {
      const r = entry.contentRect;
      setSize({ w: r.width, h: r.height });
    });
    ro.observe(node);
    return () => ro.disconnect();
  }, [node]);
  return [setNode, size];
}

function PhaseCaption({
  phase,
  frame,
  align,
  dimmed,
  terse,
  onSnap,
}: {
  phase: 'PRE' | 'POST';
  frame: DamagePhase;
  align: 'left' | 'right';
  dimmed: boolean;
  /** On a short frame the caption would cover the ground it describes; the
   *  facts it drops are all repeated in the dossier below. */
  terse: boolean;
  onSnap: () => void;
}) {
  const top = frame.top;
  const day = top ? formatSceneDay(top.datetime) : null;
  const gap = phase === 'PRE' && top ? baselineGap(top.datetime) : null;

  return (
    <button
      type="button"
      onClick={onSnap}
      title={`Show ${phase} full frame`}
      style={{
        position: 'absolute',
        top: 0,
        left: align === 'left' ? 0 : undefined,
        right: align === 'right' ? 0 : undefined,
        maxWidth: '48%',
        display: 'flex',
        flexDirection: 'column',
        alignItems: align === 'left' ? 'flex-start' : 'flex-end',
        gap: 1,
        padding: '4px 7px',
        border: 'none',
        background: 'rgba(10,10,11,0.78)',
        cursor: 'pointer',
        textAlign: align,
        opacity: dimmed ? 0.35 : 1,
        transition: 'opacity .15s ease-out',
      }}
    >
      <span style={{ ...figure, fontSize: 10, letterSpacing: '0.1em', color: phase === 'POST' ? C.info : C.sub }}>
        {phase}
      </span>
      <span style={{ ...figure, fontSize: 11, color: C.text, whiteSpace: 'nowrap' }}>
        {day ?? '—'}
        {top && <span style={{ color: C.muted }}>{`  ${top.gsd_m.toFixed(2)} M`}</span>}
      </span>
      {gap && !terse && (
        <span style={{ ...label, fontSize: 9, letterSpacing: '0.06em', lineHeight: 1.3 }}>
          Archive baseline · {gap} before
        </span>
      )}
    </button>
  );
}

/**
 * The comparator. One bbox, two renders, a divider between them; PRE is clipped
 * to the left of the divider so the reader sweeps the same ground rather than
 * glancing between two panes and losing the register.
 */
export function Comparator({ level, siteName }: { level: DamageLevel; siteName: string }) {
  const [outerRef, { w, h }] = useBoxSize<HTMLDivElement>();
  const boxRef = useRef<HTMLDivElement>(null);
  const [x, setX] = useState(50);
  const [preState, setPreState] = useState<LoadState>('pending');
  const [postState, setPostState] = useState<LoadState>('pending');

  const key = `${siteName}|${level.level}`;
  useEffect(() => {
    setPreState('pending');
    setPostState('pending');
    setX(50);
  }, [key]);

  // The pane is far wider than the 5:3 export, so fitting the whole frame inside
  // it would shrink the 0.30 m pixels into a third of the canvas and leave the
  // rest black. Where the pane is the wider shape the frame is scaled to the
  // full width and cropped top and bottom instead: the ground width the caption
  // states stays exactly true, the site stays centred where the bbox put it, and
  // twice as many pixels reach the reader. Where the pane is the taller shape
  // the whole frame is shown and the box takes the frame's own aspect — either
  // way the image spans the box horizontally, so the divider percentage maps to
  // imagery and never to letterboxing beside it.
  const cropped = w > 0 && h > 0 && w / h > FRAME_ASPECT;
  const boxW = w > 0 && h > 0 ? (cropped ? w : Math.min(w, h * FRAME_ASPECT)) : 0;
  const boxH = cropped ? h : boxW / FRAME_ASPECT;
  const fit: React.CSSProperties['objectFit'] = cropped ? 'cover' : 'contain';
  const terse = (boxH > 0 && boxH < 150) || (boxW > 0 && boxW < 480);
  // Stacked layouts scroll, so the frame may claim a readable slice of its own
  // width there; in the side-by-side layout the pane's height is the budget and
  // the floor only stops the facts crowding the picture out altogether.
  const floor = w > 0 && w < NARROW_PX ? Math.min(Math.round(w / FRAME_ASPECT), 240) : 96;

  const setFromClientX = useCallback((clientX: number) => {
    const rect = boxRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0) return;
    const pct = ((clientX - rect.left) / rect.width) * 100;
    setX(Math.max(0, Math.min(100, pct)));
  }, []);

  const dragging = useRef(false);
  const onGripDown = (e: React.PointerEvent) => {
    dragging.current = true;
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    setFromClientX(e.clientX);
    e.preventDefault();
  };
  const onGripMove = (e: React.PointerEvent) => {
    if (dragging.current) setFromClientX(e.clientX);
  };
  const onGripUp = (e: React.PointerEvent) => {
    dragging.current = false;
    (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
  };

  // Mouse users may sweep anywhere on the frame; touch is grip-only, since a
  // full-frame touch drag would fight the dashboard's own scrolling.
  const onFrameMove = (e: React.PointerEvent) => {
    if (e.pointerType === 'mouse' && e.buttons === 1) setFromClientX(e.clientX);
  };

  const onKey = (e: React.KeyboardEvent) => {
    const step = e.shiftKey ? 1 : 5;
    if (e.key === 'ArrowLeft') setX((v) => Math.max(0, v - step));
    else if (e.key === 'ArrowRight') setX((v) => Math.min(100, v + step));
    else if (e.key === 'Home') setX(100);
    else if (e.key === 'End') setX(0);
    else return;
    e.preventDefault();
  };

  const preUrl = level.pre.export_url;
  const postUrl = level.post.export_url;
  const preShown = Boolean(preUrl) && preState !== 'failed';
  const postShown = Boolean(postUrl) && postState !== 'failed';
  const bothShown = preShown && postShown;
  const settled =
    (!preUrl || preState !== 'pending') && (!postUrl || postState !== 'pending');

  const anyShown = preShown || postShown;

  if (!preUrl && !postUrl) {
    return (
      <div ref={outerRef} style={frameOuter}>
        <AbsencePanel level={level} />
      </div>
    );
  }

  if (settled && !anyShown) {
    // Both hotlinks died. The record of what was flown over this ground is
    // still true and still linkable, so it degrades to the record rather than
    // to two broken-image icons.
    return (
      <div ref={outerRef} style={frameOuter}>
        <ServiceDownPanel level={level} />
      </div>
    );
  }

  const postTop = level.post.top;
  const heavyCloud = postTop ? postTop.cloud >= HEAVY_CLOUD_PCT : false;

  return (
    <>
    <div ref={outerRef} style={{ ...frameOuter, minHeight: floor }}>
      <div
        ref={boxRef}
        onPointerMove={bothShown ? onFrameMove : undefined}
        onPointerDown={bothShown ? (e) => e.pointerType === 'mouse' && setFromClientX(e.clientX) : undefined}
        style={{
          position: 'relative',
          width: boxW || '100%',
          height: boxH || '100%',
          background: C.base,
          border: `1px solid ${C.border}`,
          overflow: 'hidden',
          cursor: bothShown ? 'ew-resize' : 'default',
          touchAction: 'pan-y',
        }}
      >
        {postShown && postUrl && (
          <img
            src={postUrl}
            alt={`${siteName}, after the flood`}
            decoding="async"
            draggable={false}
            onLoad={() => setPostState('ok')}
            onError={() => setPostState('failed')}
            style={{ ...imgStyle, objectFit: fit }}
          />
        )}
        {preShown && preUrl && (
          <img
            src={preUrl}
            alt={`${siteName}, before the flood`}
            decoding="async"
            draggable={false}
            onLoad={() => setPreState('ok')}
            onError={() => setPreState('failed')}
            style={{
              ...imgStyle,
              objectFit: fit,
              // Only where both frames exist does the divider mean anything; a
              // lone survivor is shown whole rather than half-clipped.
              clipPath: bothShown ? `inset(0 ${100 - x}% 0 0)` : undefined,
            }}
          />
        )}

        {!settled && (
          <div
            className="animate-pulse"
            style={{ position: 'absolute', inset: 0, background: C.elevated }}
          />
        )}

        {settled && bothShown && (
          <>
            <PhaseCaption
              phase="PRE"
              frame={level.pre}
              align="left"
              dimmed={x < 14}
              terse={terse}
              onSnap={() => setX(100)}
            />
            <PhaseCaption
              phase="POST"
              frame={level.post}
              align="right"
              dimmed={x > 86}
              terse={terse}
              onSnap={() => setX(0)}
            />
            <div
              role="slider"
              tabIndex={0}
              aria-label={`Before and after divider, ${siteName}`}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(x)}
              aria-valuetext={`${Math.round(x)}% before-image`}
              onPointerDown={onGripDown}
              onPointerMove={onGripMove}
              onPointerUp={onGripUp}
              onPointerCancel={onGripUp}
              onKeyDown={onKey}
              style={{
                position: 'absolute',
                top: 0,
                bottom: 0,
                left: `${x}%`,
                width: 22,
                marginLeft: -11,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'ew-resize',
                touchAction: 'none',
                background: 'transparent',
              }}
            >
              <div style={{ position: 'absolute', top: 0, bottom: 0, width: 2, background: C.text }} />
              <div style={{
                position: 'relative',
                width: 16,
                height: 16,
                background: C.elevated,
                border: `1px solid ${C.strong}`,
              }} />
            </div>
          </>
        )}

        {settled && cropped && anyShown && (
          <span style={{
            position: 'absolute',
            right: 0,
            bottom: 0,
            padding: '2px 6px',
            background: 'rgba(10,10,11,0.78)',
            ...label,
            fontSize: 9,
            letterSpacing: '0.06em',
          }}>
            Full width shown · cropped to pane height
          </span>
        )}

        {settled && !bothShown && (
          <SoloOverlay
            level={level}
            shownPhase={postShown ? 'post' : 'pre'}
            failed={postShown ? preState === 'failed' : postState === 'failed'}
          />
        )}
      </div>
    </div>

    <div style={readingLine}>
      {heavyCloud && postTop ? (
        // The figure is per scene, not per frame — the 79% pass is cloud-free
        // over Rasuwagadhi. Saying only "79% cloud" over this frame would
        // mislead as badly as omitting it.
        <span style={{ ...label, fontSize: 9, letterSpacing: '0.06em', lineHeight: 1.45, color: C.warn, flex: '1 1 260px' }}>
          Post scene {postTop.cloud}% cloud (whole-scene figure, not this frame) — white in frame
          may be cloud; obscured ground is unassessed, not undamaged
        </span>
      ) : (
        <span style={{ ...label, fontSize: 9, letterSpacing: '0.06em', lineHeight: 1.45, flex: '1 1 260px' }}>
          Identical bbox, both phases — the frames register to each other exactly
        </span>
      )}
      {bothShown && (
        <span style={{ ...figure, fontSize: 9, letterSpacing: '0.06em', textTransform: 'uppercase', color: C.muted, flexShrink: 0 }}>
          Drag · ← → keys · click a label
        </span>
      )}
    </div>
    </>
  );
}

const readingLine: React.CSSProperties = {
  flexShrink: 0,
  display: 'flex',
  alignItems: 'baseline',
  gap: 8,
  flexWrap: 'wrap',
  padding: '4px 10px',
  borderTop: `1px solid ${C.border}`,
  background: C.base,
};

export const frameOuter: React.CSSProperties = {
  // Basis auto, not 0: the mobile shell gives the widget body an automatic
  // height, and a zero-basis chain resolves to a zero-height widget there.
  flex: '1 1 auto',
  // The imagery is the widget; the facts around it may not squeeze it out of
  // existence when the pane is short.
  minHeight: 96,
  minWidth: 0,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: 6,
  background: C.surface,
};

const imgStyle: React.CSSProperties = {
  position: 'absolute',
  inset: 0,
  width: '100%',
  height: '100%',
  objectFit: 'contain',
  display: 'block',
  userSelect: 'none',
};

/** One phase is missing: say which, and whether it is missing because nothing
 *  was ever flown or because the service would not answer just now. */
function SoloOverlay({
  level,
  shownPhase,
  failed,
}: {
  level: DamageLevel;
  shownPhase: 'pre' | 'post';
  failed: boolean;
}) {
  const missing = shownPhase === 'post' ? 'PRE' : 'POST';
  const shown = shownPhase === 'post' ? level.post : level.pre;
  const day = shown.top ? formatSceneDay(shown.top.datetime) : null;
  return (
    <div style={{
      position: 'absolute',
      top: 0,
      left: 0,
      right: 0,
      display: 'flex',
      alignItems: 'baseline',
      gap: 8,
      flexWrap: 'wrap',
      padding: '4px 7px',
      background: 'rgba(10,10,11,0.78)',
    }}>
      <span style={{ ...figure, fontSize: 10, letterSpacing: '0.1em', color: C.sub }}>
        {shownPhase.toUpperCase()} ONLY
      </span>
      <span style={{ ...figure, fontSize: 11, color: C.text }}>{day ?? '—'}</span>
      <span style={{ ...label, fontSize: 9, letterSpacing: '0.06em' }}>
        {failed
          ? `${missing} frame unavailable — image service unreachable`
          : `No ${missing.toLowerCase()}-event coverage of this frame`}
      </span>
    </div>
  );
}

/** Neither phase has pixels here. The record says so rather than rendering the
 *  service's transparent answer, which arrives as a perfectly successful load. */
function AbsencePanel({ level }: { level: DamageLevel }) {
  return (
    <div style={{
      maxWidth: 460,
      padding: '10px 12px',
      border: `1px solid ${C.border}`,
      background: C.base,
      textAlign: 'center',
    }}>
      <div style={{ ...label, fontSize: 10, color: C.sub }}>No coverage of this frame</div>
      <div style={{ marginTop: 4, fontSize: 11, lineHeight: 1.5, color: C.muted }}>
        No published footprint intersects this {formatGroundWidth(level.width_m).toLowerCase()} frame.
      </div>
    </div>
  );
}

/** The service would not answer. Every fact the caption carried is still true
 *  and still linkable — the pixels are the only thing missing. */
function ServiceDownPanel({ level }: { level: DamageLevel }) {
  const links: Array<{ phase: string; top: NonNullable<DamagePhase['top']> }> = [];
  if (level.pre.top) links.push({ phase: 'PRE', top: level.pre.top });
  if (level.post.top) links.push({ phase: 'POST', top: level.post.top });

  return (
    <div style={{
      maxWidth: 520,
      padding: '12px 14px',
      border: `1px solid ${C.border}`,
      background: C.base,
      textAlign: 'center',
    }}>
      <div style={{ ...label, fontSize: 10, color: C.sub }}>Image service unreachable</div>
      <div style={{ marginTop: 5, fontSize: 11, lineHeight: 1.55, color: C.muted }}>
        Neither frame could be fetched. What was flown over this ground, and when, is unchanged —
        the scenes themselves are linked below.
      </div>
      <div style={{ display: 'flex', gap: 6, justifyContent: 'center', flexWrap: 'wrap', marginTop: 8 }}>
        {links.map((l) => (
          <a
            key={l.phase}
            href={l.top.item_url}
            target="_blank"
            rel="noopener noreferrer"
            style={chipStyle}
          >
            {l.phase} STAC item <ExternalLink size={9} />
          </a>
        ))}
      </div>
    </div>
  );
}

export function PhaseDossier({
  phase,
  frame,
  compact,
}: {
  phase: 'PRE' | 'POST';
  frame: DamagePhase;
  compact: boolean;
}) {
  const top = frame.top;
  const day = top ? formatSceneDay(top.datetime) : null;
  const gap = phase === 'PRE' && top ? baselineGap(top.datetime) : null;
  const span = formatDateSpan(frame.dates);

  if (compact) {
    // Where the pane is small the frame is the scarce thing, so the facts
    // collapse to two lines. The caveats do not collapse with them: an archive
    // baseline and a no-data edge change how the picture reads and travel with
    // it at every size.
    return (
      <div style={{ flex: '1 1 0', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 1 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
          <span style={{ ...figure, fontSize: 10, letterSpacing: '0.1em', color: phase === 'POST' ? C.info : C.sub }}>
            {phase}
          </span>
          <span style={{ ...figure, fontSize: 11, color: C.text, marginLeft: 'auto' }}>
            {day ?? 'NONE'}
          </span>
        </div>
        {top && (
          <span style={{ ...figure, fontSize: 9, letterSpacing: '0.04em', color: C.sub }}>
            {top.gsd_m.toFixed(2)} m · {top.platform} · cloud {top.cloud}% · {frame.in_view} frame
            {frame.in_view === 1 ? '' : 's'}
          </span>
        )}
        {gap && (
          <span style={{ ...label, fontSize: 9, letterSpacing: '0.06em', lineHeight: 1.4, color: C.sub }}>
            Archive baseline — {gap} before
          </span>
        )}
        {frame.edge && (
          <span style={{ ...label, fontSize: 9, letterSpacing: '0.06em', lineHeight: 1.4, color: C.warn }}>
            Partly outside coverage — blank is no-data
          </span>
        )}
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
        <span style={{ ...figure, fontSize: 10, letterSpacing: '0.1em', color: phase === 'POST' ? C.info : C.sub }}>
          {phase}
        </span>
        <span style={{ ...figure, fontSize: 11, color: C.text, marginLeft: 'auto' }}>
          {day ?? 'NONE'}
        </span>
      </div>

      {!top ? (
        <div style={{ fontSize: 10, lineHeight: 1.45, color: C.muted }}>
          No published pass over this frame.
        </div>
      ) : (
        <>
          <Row k="Resolution" v={`${top.gsd_m.toFixed(2)} m`} />
          <Row k="Platform" v={top.platform} />
          {top.off_nadir !== null && <Row k="Off-nadir" v={`${top.off_nadir.toFixed(1)}°`} />}
          <Row k="Scene cloud" v={`${top.cloud}%`} tone={top.cloud >= HEAVY_CLOUD_PCT ? C.warn : undefined} />
          <Row k="In view" v={`${frame.in_view} frame${frame.in_view === 1 ? '' : 's'}`} />
          {frame.in_view > 1 && span && (
            <div style={{ ...label, fontSize: 9, letterSpacing: '0.06em', lineHeight: 1.4 }}>
              Mosaic {span} · top frame labelled
            </div>
          )}
          {!top.full_frame && (
            <div style={{ ...label, fontSize: 9, letterSpacing: '0.06em', lineHeight: 1.4, color: C.sub }}>
              Top frame covers part of the view — label speaks for the centre
            </div>
          )}
          {gap && (
            <div style={{ ...label, fontSize: 9, letterSpacing: '0.06em', lineHeight: 1.4, color: C.sub }}>
              Archive baseline — {gap} before the flood
            </div>
          )}
          {frame.edge && (
            <div style={{ ...label, fontSize: 9, letterSpacing: '0.06em', lineHeight: 1.4, color: C.warn }}>
              Frame partly outside coverage — blank is no-data, not ground
            </div>
          )}
        </>
      )}
    </div>
  );
}

function Row({ k, v, tone }: { k: string; v: string; tone?: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, minWidth: 0 }}>
      <span style={{ ...label, fontSize: 9, letterSpacing: '0.06em', flex: '1 1 auto' }}>{k}</span>
      <span style={{ ...figure, fontSize: 10, color: tone ?? C.sub, flexShrink: 0 }}>{v}</span>
    </div>
  );
}

/** Copernicus graded this ground and its count is the one authoritative damage
 *  figure the desk holds over any of these frames. The map products themselves
 *  are all-rights-reserved and are cited, never rehosted. */
export function Emsr927Note({ divider = true }: { divider?: boolean } = {}) {
  return (
    // The rule separates it from the frame facts it sits under in the explorer
    // column. Opened over the map it is the whole of its cell, and a rule there
    // would double the row's own border.
    <div style={divider ? { paddingTop: 6, borderTop: `1px solid ${C.border}` } : undefined}>
      <div style={{ fontSize: 11, lineHeight: 1.4, color: C.text }}>
        More than 240 buildings destroyed, 32 damaged in the mapped area around Syapru Besi.
      </div>
      <div style={{ ...label, fontSize: 9, letterSpacing: '0.06em', lineHeight: 1.45, marginTop: 2 }}>
        Copernicus EMS Rapid Mapping · EMSR927 · WorldView-3 27 Aug 2026 05:05 UTC · cited — map
        products all rights reserved, not rehosted
      </div>
      <a
        href={EMSR927_URL}
        target="_blank"
        rel="noopener noreferrer"
        style={{ ...chipStyle, marginTop: 4 }}
      >
        EMSR927 <ExternalLink size={9} />
      </a>
    </div>
  );
}

/** No frames at all: Vantor has flown nothing over this ground since the
 *  collapse. The site keeps its place in the corridor so the gap is visible. */
export function SiteStatement({ site }: { site: DamageSite }) {
  return (
    <div style={{ ...frameOuter, padding: 16 }}>
      <div style={{ maxWidth: 520, textAlign: 'center' }}>
        <div style={{ ...label, fontSize: 10, color: C.sub }}>No post-event coverage</div>
        <div style={{ marginTop: 6, fontSize: 12, lineHeight: 1.55, color: C.text }}>
          {site.finding ?? 'No published pass over this site.'}
        </div>
        <div style={{ marginTop: 6, fontSize: 11, lineHeight: 1.55, color: C.muted }}>
          Every published post-event footprint stops west of {site.lng.toFixed(3)}° E. There is no
          frame to render here, and an empty export would look like ground.
        </div>
        <div style={{ ...figure, fontSize: 10, color: C.muted, marginTop: 8 }}>
          {site.lat.toFixed(3)}° N · {site.lng.toFixed(3)}° E
        </div>
      </div>
    </div>
  );
}
