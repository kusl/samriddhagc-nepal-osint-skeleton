/**
 * OPERATIONAL PICTURE · 3D — the replay of what happened, when and where.
 *
 * This widget is a frame, not an author. It owns three things and nothing else:
 * the fetch of `/flood/replay` (the script the backend serves), the layer
 * switches the reader may throw, and the box that the map, the HUD and the
 * source line sit in. The animation itself belongs to `replay3d/`: the map to
 * `OperationalPicture3D`, the arithmetic of time to `replayEngine`, the
 * transport and the readout to `ReplayHud`.
 *
 * Two rules from the desk are load-bearing here and are enforced by the layout
 * rather than by comment:
 *
 *   - NOTHING SCROLLS. The Body has no padding of its own, the map area takes
 *     every pixel the HUD and the source line do not, and the HUD is a fixed
 *     band. Anything that would overflow is drawn as an inset overlay on the
 *     map (the legend, the stamp), never as a scroll region.
 *   - NOTHING IS TYPED. No date, figure or coordinate appears in this file.
 *     The counts in the source line are the lengths of what the API served;
 *     the beats, the fixes, the toll and the front all reach the screen
 *     through the engine, carrying their own source and confidence.
 *
 * The 3D picture needs a GPU context. Where the browser cannot give one the
 * widget says so plainly instead of mounting a map that would paint nothing:
 * a blank black rectangle is a worse lie than an honest error.
 */
import { memo, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Orbit } from 'lucide-react';

import { Widget } from '../Widget';
import apiClient from '../../../api/client';
import { floodKeys } from '../../../api/hooks/useFlood';
import { WidgetEmpty, WidgetError, WidgetSkeleton } from './shared';
import { Body, FIGURE, LABEL_XS, MS, SourceLine, Tag, dtgNow } from '../../flood/milspec';
import {
  OperationalPicture3D,
  type LayerToggles,
  type ReplayPayload,
} from '../../flood/replay3d/OperationalPicture3D';
import { buildFilm, buildTimeline, useReplayClock } from '../../flood/replay3d/replayEngine';
import { ReplayCards, type CommonsItem, type PhotoItem } from '../../flood/replay3d/ReplayCards';
import { HUD_HEIGHT, ReplayHud } from '../../flood/replay3d/ReplayHud';

// ------------------------------------------------------------------ fetch

/**
 * The replay endpoint is served alongside the rest of the flood router, but it
 * is the newest thing on it: a desk pointed at an API that has not shipped it
 * yet should read "no replay published", not "the widget is broken". Any other
 * status is a real failure and still surfaces as one.
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

// ------------------------------------------------------------------ webgl

/**
 * Probed once per module load, not per render: the answer cannot change while
 * the tab is open, and creating a throwaway GPU context on every re-render of
 * an animating widget would be its own bug. The canvas is never attached to the
 * document, so it costs nothing after this call.
 */
const WEBGL_OK: boolean = (() => {
  try {
    const probe = document.createElement('canvas');
    return probe.getContext('webgl') !== null;
  } catch {
    return false;
  }
})();

// ------------------------------------------------------------------ layout

/** Overlays float over the map canvas; MapLibre's own controls sit under this. */
const OVERLAY_Z = 5;

/** Layers the reader may throw. GIBS water is off until asked for: it is 250 m
 *  regional product and would otherwise read as the flood's own extent. */
const DEFAULT_LAYERS: LayerToggles = {
  gibs: false,
  gauges: true,
  districts: true,
  damage: true,
  vantor: true,
};

const LAYER_LABELS: Array<{ key: keyof LayerToggles; label: string }> = [
  { key: 'gibs', label: 'GIBS WATER' },
  { key: 'gauges', label: 'GAUGES' },
  { key: 'districts', label: 'DISTRICTS' },
  { key: 'damage', label: 'DAMAGE' },
  { key: 'vantor', label: 'VANTOR SCENES' },
];

// ------------------------------------------------------------------ widget

const TITLE = 'OPERATIONAL PICTURE · 3D';

/** API-relative image paths re-anchored on the client's base (see GroundImagery). */
function imageSrc(url: string | null | undefined): string | null {
  if (!url) return null;
  if (/^(https?:|data:|blob:)/i.test(url)) return url;
  const base = (apiClient.defaults.baseURL ?? '').replace(/\/+$/, '');
  if (!base || base.startsWith('/')) return url;
  return `${base.replace(/\/api\/v1$/, '')}${url}`;
}

export const FloodOperationalPictureWidget = memo(function FloodOperationalPictureWidget() {
  const replay = useQuery<ReplayPayload | null>({
    queryKey: [...floodKeys.all, 'replay'] as const,
    queryFn: () => getOrEmpty<ReplayPayload | null>('/flood/replay', null),
    staleTime: 5 * 60 * 1000,
  });

  const [layers, setLayers] = useState<LayerToggles>(DEFAULT_LAYERS);

  const payload = replay.data ?? null;

  // The timeline is derived, so it is memoised on the payload identity rather
  // than rebuilt every frame the clock ticks — the clock re-renders this
  // component many times a second while playing. `buildTimeline` takes a null
  // payload and hands back the empty timeline, so the hooks below run
  // unconditionally and the engine simply holds at rest until data lands.
  const timeline = useMemo(() => buildTimeline(payload), [payload]);
  const film = useMemo(() => buildFilm(payload, timeline), [payload, timeline]);
  const clock = useReplayClock({ timeline, film, mode: film ? 'film' : 'manual' });

  // Evidence for the cards: the desk's licensed Commons files and the official
  // photographs. Both endpoints already exist; a 404 is an empty deck, not an error.
  const media = useQuery<{ items: CommonsItem[] } | null>({
    queryKey: [...floodKeys.all, 'media'] as const,
    queryFn: () => getOrEmpty<{ items: CommonsItem[] } | null>('/flood/media', null),
    staleTime: 10 * 60 * 1000,
  });
  const photos = useQuery<{ items: PhotoItem[] } | null>({
    queryKey: [...floodKeys.all, 'photos'] as const,
    queryFn: () => getOrEmpty<{ items: PhotoItem[] } | null>('/flood/photos', null),
    staleTime: 5 * 60 * 1000,
  });
  const commonsItems = media.data?.items ?? [];
  const photoItems = photos.data?.items ?? [];
  const filmIdle = !!film && clock.mode === 'film' && !clock.playing && clock.filmR <= 0;

  if (!WEBGL_OK) {
    return (
      <Widget id="flood-operational-picture" title={TITLE} icon={<Orbit size={14} />} badge="REPLAY">
        <WidgetError message="WebGL required for the 3D picture" />
      </Widget>
    );
  }

  if (replay.isLoading) {
    return (
      <Widget id="flood-operational-picture" title={TITLE} icon={<Orbit size={14} />} badge="REPLAY">
        <WidgetSkeleton />
      </Widget>
    );
  }

  if (replay.error) {
    return (
      <Widget id="flood-operational-picture" title={TITLE} icon={<Orbit size={14} />} badge="REPLAY">
        <WidgetError message="Failed to load the replay" onRetry={() => replay.refetch()} />
      </Widget>
    );
  }

  // A script with no front fixes and no beats has nothing to animate; that is
  // an empty state, not an error — the event may simply not be scripted yet.
  const fixes = timeline.keyframes.length;
  const beats = timeline.beats.length;

  if (!payload || (fixes === 0 && beats === 0)) {
    return (
      <Widget id="flood-operational-picture" title={TITLE} icon={<Orbit size={14} />} badge="REPLAY">
        <WidgetEmpty message="No replay published for this event" />
      </Widget>
    );
  }

  return (
    <Widget id="flood-operational-picture" title={TITLE} icon={<Orbit size={14} />} badge="REPLAY">
      <Body style={{ position: 'relative', overflow: 'hidden', padding: 0 }}>
        {/* ------------------------------------------------------------ map */}
        <div style={{ flex: 1, minHeight: 0, position: 'relative', overflow: 'hidden' }}>
          <OperationalPicture3D data={payload} clock={clock} layers={layers} playing={clock.playing} />

          {/* Layer switches. Top-left, over the terrain, with only enough of
              the surface behind them to stay legible — not a card on the map. */}
          <div
            style={{
              position: 'absolute',
              top: 8,
              left: 8,
              zIndex: OVERLAY_Z,
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              padding: '4px 6px',
              borderRadius: 2,
              background: 'rgba(17, 17, 19, 0.85)',
            }}
          >
            <span style={{ ...LABEL_XS, marginRight: 2, color: MS.muted }}>LAYERS</span>
            {LAYER_LABELS.map(({ key, label }) => (
              <Tag
                key={key}
                active={layers[key]}
                tone={layers[key] ? 'text' : 'muted'}
                onClick={() => setLayers((prev) => ({ ...prev, [key]: !prev[key] }))}
              >
                {label}
              </Tag>
            ))}
          </div>

          {/* When the picture was assembled — the same stamp the rest of the
              desk carries. Never intercepts the pointer: the corner it covers
              still pans the map. */}
          <div
            style={{
              position: 'absolute',
              top: 8,
              right: 8,
              zIndex: OVERLAY_Z,
              pointerEvents: 'none',
              padding: '4px 6px',
              borderRadius: 2,
              background: 'rgba(17, 17, 19, 0.85)',
              ...LABEL_XS,
              letterSpacing: '0.14em',
              color: MS.sub,
              whiteSpace: 'nowrap',
            }}
          >
            PICTURE {dtgNow()}
          </div>
        </div>

        {/* ---------------------------------------------------- evidence */}
        {/* The director's cards ride the right third of the picture. Hidden in
            manual mode: a reader scrubbing freely is reading the map. */}
        {clock.mode === 'film' && clock.film && (
          <ReplayCards
            scene={clock.film.scene}
            t={clock.t}
            filmR={clock.filmR}
            commons={commonsItems}
            photos={photoItems}
            damageSites={payload.damage_sites ?? []}
            beats={timeline.beats}
            imageSrc={imageSrc}
            sources={payload.sources ?? []}
            style={{ zIndex: OVERLAY_Z, top: 40, bottom: HUD_HEIGHT + 34 }}
          />
        )}

        {/* Opening prompt: the film waits to be asked for. */}
        {filmIdle && film && (
          <button
            type="button"
            onClick={() => clock.setPlaying(true)}
            aria-label="Play the film"
            style={{
              position: 'absolute',
              left: '50%',
              top: `calc((100% - ${HUD_HEIGHT + 30}px) * 0.45)`,
              transform: 'translate(-50%, -50%)',
              zIndex: OVERLAY_Z + 1,
              background: 'rgba(17, 17, 19, 0.88)',
              border: `1px solid ${MS.rule}`,
              borderRadius: 2,
              padding: '14px 22px',
              cursor: 'pointer',
              textAlign: 'center',
              color: MS.text,
            }}
          >
            <div style={{ ...FIGURE, fontSize: 22, color: MS.text }}>▶ PLAY THE PICTURE</div>
            <div style={{ ...LABEL_XS, marginTop: 6, color: MS.sub }}>
              {film.scenes.length} CHAPTERS · {Math.round(film.totalS / 60)} MIN · EVERY FRAME AND FIGURE SOURCED
            </div>
            <div style={{ ...LABEL_XS, marginTop: 3, color: MS.muted }}>{film.title}</div>
          </button>
        )}

        {/* ---------------------------------------------------- transport */}
        {/* The band's own height, published by the HUD, so the map is told
            exactly what is left rather than guessing at a number twice. */}
        <div
          style={{
            flex: `0 0 ${HUD_HEIGHT}px`,
            height: HUD_HEIGHT,
            minHeight: HUD_HEIGHT,
            overflow: 'hidden',
          }}
        >
          <ReplayHud clock={clock} />
        </div>

        {/* The Body has no padding, so the source line carries its own gutter
            rather than running to the widget's edge. */}
        <div style={{ flex: '0 0 auto', padding: '0 12px 7px' }}>
          <SourceLine
            source={`${beats} BEATS · ${fixes} FRONT FIXES · TERRAIN AWS/MAPZEN · IMAGERY ESRI · VANTOR SCENES CC BY-NC VIA ESRI DRP`}
            grade={false}
          />
        </div>
      </Body>
    </Widget>
  );
});
