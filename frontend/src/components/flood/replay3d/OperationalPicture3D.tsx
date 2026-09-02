/**
 * OPERATIONAL PICTURE · 3D — the map core.
 *
 * The widget answers one question: WHAT happened, WHEN, and WHERE. This file
 * owns only the WHERE. It holds no clock and no lore: it is handed a payload
 * (the served replay script) and a clock view (the engine's reading of that
 * script at an instant) and paints exactly that. Every fact on the map comes
 * out of `data`; every position on the map comes out of `clock`.
 *
 * Three rules the implementation exists to keep:
 *
 *  1. THE MAP IS BUILT ONCE. A MapLibre map with terrain, three raster sources
 *     and a dozen layers costs a second to construct and re-downloads every
 *     tile. The clock ticks at animation rate, so a rebuild per tick would make
 *     the replay a slideshow. Every frame is therefore a `setData` /
 *     `setFilter` / `setPaintProperty` on sources and layers created at load.
 *
 *  2. NOTHING IS INVENTED. A beat with no place is not placed. A gauge with no
 *     coordinates is not drawn. The stretch of corridor the front has crossed
 *     is drawn SOLID only as far as the last PUBLISHED fix the clock has
 *     reached; from there to the front's current position it is dashed, because
 *     that arrival time is interpolated and the reader must be able to see the
 *     difference without reading the HUD.
 *
 *  3. IT NEVER THROWS. A tile 404, a WebGL context loss or a malformed feature
 *     must degrade the picture, not take the desk down with it: map errors are
 *     logged, and every imperative call into MapLibre goes through `safe`.
 *
 * The type surface below is the contract the engine, the HUD and the widget
 * import. It mirrors the served payload rather than re-deriving it, so a field
 * the backend renames breaks the typecheck instead of the picture.
 */
import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react';
import type { Ref } from 'react';
import type { Feature, FeatureCollection, Geometry, LineString, Point } from 'geojson';
import maplibregl from 'maplibre-gl';
import type { GeoJSONSource, Map as MapLibreMap, Marker as MapLibreMarker } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';

import { NPT_OFFSET_MS, dayCloseMs } from '../floodReplay';
import {
  GIBS_SOURCE,
  LAYER_GIBS,
  TERRAIN_EXAGGERATION,
  TERRAIN_SOURCE,
  buildReplayStyle,
  gibsTiles,
  readMapPalette,
} from './mapStyle';
import type { MapPalette, StyleLayerDef, StyleSourceDef } from './mapStyle';

// ==================================================================== types

/** How a position or a fact got here. `estimated` is the engine's own
 *  interpolation between two published fixes and is always drawn as such. */
export type ReplayConfidence = 'published' | 'derived' | 'estimated';

/** Roles the script gives a place. Open-ended: a new role must not break the map. */
export type ReplayPlaceRole = 'origin' | 'corridor' | 'impact' | 'response' | 'gauge' | 'district' | (string & {});

export interface ReplayPlace {
  key: string;
  name: string;
  name_ne?: string | null;
  lat: number;
  lng: number;
  /** Kilometres downstream of the corridor's zero mark. null where the record
   *  publishes no distance — never 0, which would mean "at the zero mark". */
  km: number | null;
  /** Merged from the DEM where the endpoint could resolve one. */
  elev_m?: number | null;
  role: ReplayPlaceRole;
  source?: string | null;
  source_url?: string | null;
}

/** A time-stamped fix of the flood FRONT along the corridor. */
export interface ReplayKeyframe {
  t_npt: string;
  place_key: string;
  km: number;
  confidence: ReplayConfidence;
  source: string;
  source_url: string | null;
  note?: string | null;
}

/** Something that happened, carrying the place it happened at. */
export interface ReplayBeat {
  t_npt: string;
  /** false = the source gave a date only; the clock in `t_npt` is ordering
   *  convenience and must never be shown. */
  time_published: boolean;
  kind: string;
  headline: string;
  detail: string;
  place_key: string | null;
  source: string;
  source_url: string | null;
  confidence: ReplayConfidence;
}

/** The director's cut: where the camera should be, and when. */
export interface ReplayCameraMark {
  t_npt: string;
  center: [number, number];
  zoom: number;
  pitch: number;
  bearing: number;
  hold_s?: number | null;
  label?: string | null;
}

export interface ReplayTollMark {
  t_npt: string;
  deaths: number | null;
  missing: number | null;
  source: string;
  source_url: string | null;
}

export interface ReplaySourceRef {
  label: string;
  url: string;
  grade_hint?: string | null;
}

/** Corridor waypoint as /flood/districts/geo serves it. A schematic path
 *  between named places — not the river's course. */
export interface ReplayCorridorWaypoint {
  name: string;
  lat: number;
  lng: number;
  kind: string;
  km: number | null;
}

/** One Vantor scene as the DRP image service reports it for a frame. */
export interface ReplayDamageScene {
  id: string;
  datetime: string;
  cloud?: number | null;
  gsd_m?: number | null;
  platform?: string | null;
  item_url?: string | null;
}

/** One phase (pre / post) of a same-frame export: the URL a browser can load,
 *  and which scene sits on top of the mosaic inside that frame. */
export interface ReplayDamagePhase {
  export_url: string;
  top?: ReplayDamageScene | null;
  dates?: string[];
  in_view?: number;
  edge?: boolean;
}

/** A framed export around a damage site at one width (context / site / detail). */
export interface ReplayDamageLevel {
  level: string;
  width_m: number;
  /** [minLng, minLat, maxLng, maxLat] in EPSG:4326 — axis-aligned, so the four
   *  corners map exactly onto a MapLibre image source. */
  bbox: [number, number, number, number];
  pre: ReplayDamagePhase;
  post: ReplayDamagePhase;
}

export interface ReplayDamageSite {
  key: string;
  name: string;
  lat: number;
  lng: number;
  km_mark: number | null;
  finding?: string | null;
  finding_source?: string | null;
  levels?: ReplayDamageLevel[];
}

export type ReplayGaugeAlert = 'danger' | 'warning' | 'normal' | 'sensor_fault' | 'offline' | (string & {});

export interface ReplayGauge {
  station_id: string | number;
  name: string;
  basin?: string | null;
  lat: number | null;
  /** The rivers feed spells it `lon`; kept as served. */
  lon: number | null;
  water_level?: number | null;
  warning_level?: number | null;
  danger_level?: number | null;
  alert: ReplayGaugeAlert;
  trend?: string | null;
  reading_at?: string | null;
  stale?: boolean;
}

export interface ReplayChronologyEvent {
  occurred_at: string;
  occurred_at_npt: string;
  time_published: boolean;
  kind: string;
  headline: string;
  detail: string;
  source: string;
  source_url: string | null;
}

export interface ReplayDistrictProperties {
  name: string;
  geo_name?: string | null;
  province?: string | null;
  code?: string | null;
  centroid?: { lat: number; lng: number } | null;
  /** null means the authority published no figure — never that it is zero. */
  bodies_recovered?: number | null;
  missing?: number | null;
  position?: string | null;
  authority?: string | null;
  as_of?: string | null;
}

export type ReplayDistrictFeature = Feature<Geometry, ReplayDistrictProperties>;
export type ReplayDistrictCollection = FeatureCollection<Geometry, ReplayDistrictProperties>;

/** A dated per-district breakdown. Values are either a bare recovered count or
 *  the split object the bulletin published. */
export interface ReplayTollSnapshot {
  as_of: string;
  authority: string | null;
  district_tolls: Record<string, { bodies_recovered?: number | null; missing?: number | null } | number>;
}

/**
 * The served replay: the lore file exactly as written, plus the live layers the
 * endpoint merges into it. Merged fields are optional because the picture must
 * still draw when one of them is unavailable — a missing gauge feed removes
 * points, it does not blank the map.
 */
export interface ReplayPayload {
  event_key: string;
  title: string;
  t0_npt: string;
  t_end_npt: string;
  notes?: string[];
  places: ReplayPlace[];
  keyframes: ReplayKeyframe[];
  beats: ReplayBeat[];
  camera: ReplayCameraMark[];
  toll_marks: ReplayTollMark[];
  sources: ReplaySourceRef[];
  // ---- merged by GET /flood/replay
  corridor?: ReplayCorridorWaypoint[];
  damage_sites?: ReplayDamageSite[];
  gauges?: ReplayGauge[];
  chronology?: ReplayChronologyEvent[];
  districts?: ReplayDistrictCollection | null;
  toll_snapshots?: ReplayTollSnapshot[];
}

export interface ReplayCameraView {
  center: [number, number];
  zoom: number;
  pitch: number;
  bearing: number;
}

export interface ReplayFrontView {
  lng: number;
  lat: number;
  confidence: ReplayConfidence;
  /** Names of the two published fixes an estimated position sits between;
   *  null when the position is itself a published fix. */
  between: [string, string] | null;
}

export interface ReplayTollView {
  deaths: number | null;
  missing: number | null;
  source: string | null;
}

/** The engine's reading of the script at one instant. The map holds no clock;
 *  this is the only thing that moves it. */
export interface ReplayClockView {
  /** Epoch milliseconds. */
  t: number;
  frontKm: number;
  front: ReplayFrontView;
  camera: ReplayCameraView | null;
  activeBeatIndex: number;
  tollNow: ReplayTollView | null;
  visibleBeatCount: number;
  /** Director state when a film is loaded; the map reads only the effect. */
  film?: { scene: { fx?: 'collapse' | null } } | null;
}

export interface LayerToggles {
  gibs: boolean;
  gauges: boolean;
  districts: boolean;
  damage: boolean;
  /** Vantor 0.3 m scenes draped on the terrain at each damage site. */
  vantor: boolean;
}

export interface OperationalPicture3DProps {
  data: ReplayPayload;
  clock: ReplayClockView;
  layers: LayerToggles;
  /** True while the replay clock runs: render density drops for frame rate. */
  playing?: boolean;
  onReady?: () => void;
}

export interface OperationalPicture3DHandle {
  /** Director's override, used by the engine when the reader jumps the clock. */
  flyTo: (camera: ReplayCameraView, durationMs?: number) => void;
  /** Escape hatch for the widget; null before load and after unmount. */
  getMap: () => MapLibreMap | null;
}

// ================================================================= internals

const SRC = {
  corridor: 'replay-corridor',
  front: 'replay-front',
  beats: 'replay-beats',
  damage: 'replay-damage',
  gauges: 'replay-gauges',
  districts: 'replay-districts',
  origin: 'replay-origin',
  originLink: 'replay-origin-link',
  fx: 'replay-fx',
} as const;

const LYR = {
  districtFill: 'replay-districts-fill',
  districtLine: 'replay-districts-line',
  corridorBase: 'replay-corridor-base',
  corridorEst: 'replay-corridor-estimated',
  corridorPassed: 'replay-corridor-passed',
  damage: 'replay-damage-pin',
  gauges: 'replay-gauges-dot',
  beats: 'replay-beats-dot',
  beatsActive: 'replay-beats-active',
  origin: 'replay-origin-mark',
  originLink: 'replay-origin-link-line',
  corridorRun: 'replay-corridor-run',
  frontHalo: 'replay-front-halo',
  fxRing: 'replay-fx-ring',
  frontCore: 'replay-front-core',
} as const;

// Vantor same-frame exports, draped on the terrain. The DRP service renders a
// bbox from the event mosaic at native resolution; PRE and POST share the bbox,
// so the two rasters register exactly and the crossfade is a true before/after.
/** Render density while the clock runs (frames) and while it is paused (crispness). */
const PLAYING_PIXEL_RATIO = 1.25;
const PAUSED_PIXEL_RATIO = 2;
const VANTOR_LEVEL = 'context';
/** km of front travel past a site over which its POST frame fades in. */
const VANTOR_FADE_KM = 3;
const VANTOR_ATTRIBUTION =
  'Satellite imagery © 2026 Vantor (formerly Maxar), Open Data program, CC BY-NC 4.0 · via Esri Disaster Response Program';
const vantorId = (key: string, phase: 'pre' | 'post') => `replay-vantor-${key}-${phase}`;

const MONTHS_UP = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];
/** "2026-08-27T05:05:11Z" → "27 AUG 26"; string-sliced like milspec.dtgDay. */
function dayStamp(iso: string | null | undefined): string {
  if (!iso || iso.length < 10) return '—';
  const [y, m, d] = iso.slice(0, 10).split('-');
  const mon = MONTHS_UP[Number(m) - 1];
  return mon && d && y ? `${d} ${mon} ${y.slice(2)}` : iso.slice(0, 10);
}

function vantorLabel(site: ReplayDamageSite, level: ReplayDamageLevel, postMix: number): string {
  const phase = postMix >= 0.99 ? level.post : level.pre;
  const top = phase.top;
  const stamp = top ? `${(top.platform ?? 'VANTOR').toUpperCase()} ${dayStamp(top.datetime)}` : 'SCENE DATE NOT STATED';
  const gsd = top && typeof top.gsd_m === 'number' ? ` · ${top.gsd_m.toFixed(2)} M/PX` : '';
  const cloud = top && typeof top.cloud === 'number' ? ` · ${Math.round(top.cloud)}% CLOUD` : '';
  const state = postMix >= 0.99 ? 'POST-EVENT PASS' : postMix > 0.01 ? 'REVEALING POST-EVENT PASS' : 'PRE-EVENT BASELINE';
  return `VANTOR · ${state} · ${stamp}${gsd}${cloud}`;
}


const CAMERA_EASE_MS = 2400;
/** An update arriving sooner than this after the last one is the engine's own
 *  interpolation running, not a cut. See the camera block for why it matters. */
const CAMERA_CUT_GAP_MS = 250;

/** Every call into MapLibre goes through here: a style that has been swapped,
 *  a source removed by a reload or a context loss must not reach the desk. */
function safe<T>(what: string, fn: () => T): T | undefined {
  try {
    return fn();
  } catch (err) {
    console.warn(`[OperationalPicture3D] ${what}:`, err);
    return undefined;
  }
}

const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);

/** ISO strings in the script always carry the +05:45 offset, so Date.parse is
 *  unambiguous. NaN for anything malformed, which callers drop. */
const ms = (iso: string | null | undefined): number => (iso ? Date.parse(iso) : Number.NaN);

/** The NPT calendar day an instant falls on — the day GIBS composites are
 *  addressed by. The browser's own zone is never consulted. */
function nptDay(t: number): string {
  return new Date(t + NPT_OFFSET_MS).toISOString().slice(0, 10);
}

type Props = Record<string, unknown>;

const point = (lng: number, lat: number, properties: Props): Feature<Point, Props> => ({
  type: 'Feature',
  geometry: { type: 'Point', coordinates: [lng, lat] },
  properties,
});

const line = (coords: Array<[number, number]>, properties: Props): Feature<LineString, Props> => ({
  type: 'Feature',
  geometry: { type: 'LineString', coordinates: coords },
  properties,
});

const fc = <G extends Geometry>(features: Array<Feature<G, Props>>): FeatureCollection<G, Props> => ({
  type: 'FeatureCollection',
  features,
});

const EMPTY = fc([]);

// ------------------------------------------------------------- corridor path

interface PathVertex {
  km: number;
  lng: number;
  lat: number;
  name: string;
}

/**
 * The corridor as a km-parameterised polyline, origin first.
 *
 * The served corridor is the authority: it is the same nine waypoints the
 * district map draws. The collapse origin carries no km of its own (it is
 * upstream of the zero mark), so its distance is READ from the keyframes — the
 * script states the origin's km there — and never assumed.
 */
function buildPath(data: ReplayPayload): PathVertex[] {
  const fromCorridor = (data.corridor ?? [])
    .filter((w) => isNum(w.km) && isNum(w.lat) && isNum(w.lng))
    .map((w) => ({ km: w.km as number, lng: w.lng, lat: w.lat, name: w.name }));

  const vertices = fromCorridor.length
    ? fromCorridor
    : data.places
        .filter((p) => isNum(p.km) && p.role !== 'gauge' && p.role !== 'district')
        .map((p) => ({ km: p.km as number, lng: p.lng, lat: p.lat, name: p.name }));

  vertices.sort((a, b) => a.km - b.km);

  const origin = data.places.find((p) => p.role === 'origin');
  if (origin && isNum(origin.lat) && isNum(origin.lng)) {
    const originKm = data.keyframes
      .filter((k) => k.place_key === origin.key && isNum(k.km))
      .reduce<number | null>((acc, k) => (acc === null || k.km < acc ? k.km : acc), null);
    const km = originKm ?? (vertices.length ? vertices[0].km : 0);
    if (!vertices.length || km < vertices[0].km) {
      vertices.unshift({ km, lng: origin.lng, lat: origin.lat, name: origin.name });
    }
  }
  return vertices;
}

/** Position along the polyline at a km mark, linear within each segment. */
function atKm(path: PathVertex[], km: number): [number, number] | null {
  if (!path.length) return null;
  if (km <= path[0].km) return [path[0].lng, path[0].lat];
  const last = path[path.length - 1];
  if (km >= last.km) return [last.lng, last.lat];
  for (let i = 1; i < path.length; i += 1) {
    const a = path[i - 1];
    const b = path[i];
    if (km <= b.km) {
      const span = b.km - a.km;
      const f = span > 0 ? (km - a.km) / span : 0;
      return [a.lng + (b.lng - a.lng) * f, a.lat + (b.lat - a.lat) * f];
    }
  }
  return [last.lng, last.lat];
}

/** The stretch of path between two km marks, with both ends interpolated. */
function slice(path: PathVertex[], fromKm: number, toKm: number): Array<[number, number]> {
  if (!path.length || toKm <= fromKm) return [];
  const start = atKm(path, fromKm);
  const end = atKm(path, toKm);
  if (!start || !end) return [];
  const middle = path.filter((v) => v.km > fromKm && v.km < toKm).map((v) => [v.lng, v.lat] as [number, number]);
  return [start, ...middle, end];
}

// ------------------------------------------------------------------- helpers

function addSource(map: MapLibreMap, id: string, spec: StyleSourceDef) {
  safe(`addSource ${id}`, () => {
    if (!map.getSource(id)) map.addSource(id, spec as never);
  });
}

function addLayer(map: MapLibreMap, spec: StyleLayerDef) {
  const id = String(spec.id);
  safe(`addLayer ${id}`, () => {
    if (!map.getLayer(id)) map.addLayer(spec as never);
  });
}

function setData(map: MapLibreMap, id: string, data: FeatureCollection<Geometry, Props>) {
  safe(`setData ${id}`, () => {
    const src = map.getSource(id) as GeoJSONSource | undefined;
    // The style spec's GeoJSON union is wider than our feature types; the cast
    // is the one place the two meet.
    if (src && typeof src.setData === 'function') src.setData(data as never);
  });
}

function setVisible(map: MapLibreMap, ids: string[], visible: boolean) {
  ids.forEach((id) =>
    safe(`visibility ${id}`, () => {
      if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none');
    }),
  );
}

/** Recovered figure for a district in a snapshot, under the bulletin's own
 *  shape: a bare number, or the split object. Never a zero stand-in for null. */
function recoveredIn(snapshot: ReplayTollSnapshot | null, name: string): number | null {
  if (!snapshot) return null;
  const entry = snapshot.district_tolls?.[name];
  if (typeof entry === 'number') return entry;
  if (entry && typeof entry === 'object' && isNum(entry.bodies_recovered)) return entry.bodies_recovered;
  return null;
}

/**
 * The latest published breakdown whose Nepal-time day has CLOSED at the clock's
 * instant. A bulletin dated the 29th is not true at 00:05 on the 29th — the
 * same rule the district map's replay bar keeps, so the two never disagree.
 */
function snapshotIndexAt(snapshots: ReplayTollSnapshot[], t: number): number {
  let idx = -1;
  for (let i = 0; i < snapshots.length; i += 1) {
    const day = snapshots[i].as_of?.slice(0, 10);
    if (!day) continue;
    const close = dayCloseMs(day);
    if (Number.isFinite(close) && t >= close) idx = i;
  }
  return idx;
}

// ================================================================= component

function OperationalPicture3DInner({ data, clock, layers, onReady, playing = false }: OperationalPicture3DProps,
  ref: Ref<OperationalPicture3DHandle>,
) {
  const holderRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markersRef = useRef<MapLibreMarker[]>([]);
  /** Vantor frames installed for the current payload, by site key. */
  const vantorRef = useRef<Map<string, { site: ReplayDamageSite; level: ReplayDamageLevel; label: HTMLElement; marker: maplibregl.Marker; mix: number }>>(new Map());
  const labelLayoutRef = useRef<(() => void) | null>(null);
  const fxWasOnRef = useRef<boolean>(false);
  const fxRef = useRef<string | null>(null);
  const fxOriginRef = useRef<[number, number] | null>(null);
  const gradientKeyRef = useRef<string>('');
  const paletteRef = useRef<MapPalette | null>(null);
  const draggingRef = useRef(false);
  const cameraKeyRef = useRef<string>('');
  const cameraAtRef = useRef<number>(0);
  const beatCountRef = useRef<number>(-1);
  const snapshotRef = useRef<number>(-2);
  const gibsDayRef = useRef<string>('');
  const rafRef = useRef<number | null>(null);
  const readyRef = useRef(false);
  const onReadyRef = useRef(onReady);
  onReadyRef.current = onReady;

  const [ready, setReady] = useState(false);

  // ---------------------------------------------------------------- derived

  const path = useMemo(() => buildPath(data), [data]);
  const placeByKey = useMemo(() => {
    const m = new Map<string, ReplayPlace>();
    data.places.forEach((p) => m.set(p.key, p));
    return m;
  }, [data.places]);

  /** Beats in the engine's own order — time ascending, ties in script order —
   *  so `activeBeatIndex` and `visibleBeatCount` address the same items here. */
  const beats = useMemo(
    () =>
      data.beats
        .map((b, i) => ({ beat: b, i, t: ms(b.t_npt) }))
        .filter((x) => Number.isFinite(x.t))
        .sort((a, b) => a.t - b.t || a.i - b.i),
    [data.beats],
  );

  const beatFeatures = useMemo(
    () =>
      beats
        .map(({ beat }, idx) => {
          const place = beat.place_key ? placeByKey.get(beat.place_key) : undefined;
          // A beat with no place is a beat the HUD carries and the map does not
          // invent a position for.
          if (!place || !isNum(place.lat) || !isNum(place.lng)) return null;
          return point(place.lng, place.lat, {
            idx,
            kind: beat.kind,
            confidence: beat.confidence,
            headline: beat.headline,
            place: place.name,
          });
        })
        .filter((f): f is Feature<Point, Props> => f !== null),
    [beats, placeByKey],
  );

  const damageFeatures = useMemo(
    () =>
      (data.damage_sites ?? [])
        .filter((s) => isNum(s.lat) && isNum(s.lng))
        .map((s) => point(s.lng, s.lat, { key: s.key, name: s.name, km: s.km_mark ?? null })),
    [data.damage_sites],
  );

  const gaugeFeatures = useMemo(
    () =>
      (data.gauges ?? [])
        .filter((g) => isNum(g.lat) && isNum(g.lon))
        .map((g) =>
          point(g.lon as number, g.lat as number, {
            id: String(g.station_id),
            name: g.name,
            alert: g.alert ?? 'normal',
            stale: Boolean(g.stale),
          }),
        ),
    [data.gauges],
  );

  const originFeatures = useMemo(
    () =>
      data.places
        .filter((p) => p.role === 'origin' && isNum(p.lat) && isNum(p.lng))
        .map((p) => point(p.lng, p.lat, { key: p.key, name: p.name })),
    [data.places],
  );

  const snapshots = useMemo(() => data.toll_snapshots ?? [], [data.toll_snapshots]);

  /** District polygons carrying the figure that was published as of the clock.
   *  Rebuilt only when the active bulletin changes — the fills step between
   *  breakdowns, they never interpolate across days nobody counted. */
  const districtsAt = useCallback(
    (snapIdx: number): FeatureCollection<Geometry, Props> => {
      const source = data.districts;
      if (!source || !Array.isArray(source.features)) return EMPTY as FeatureCollection<Geometry, Props>;
      const snap = snapIdx >= 0 && snapIdx < snapshots.length ? snapshots[snapIdx] : null;
      return {
        type: 'FeatureCollection',
        features: source.features.map((f) => {
          const name = f.properties?.name ?? '';
          const recovered = snap ? recoveredIn(snap, name) : f.properties?.bodies_recovered ?? null;
          return {
            type: 'Feature',
            geometry: f.geometry,
            properties: {
              name,
              // -1 marks "no figure published", which the fill ramp reads as
              // unshaded. It is never rendered as a number.
              recovered: isNum(recovered) ? recovered : -1,
              position: f.properties?.position ?? null,
            } as Props,
          } as Feature<Geometry, Props>;
        }),
      };
    },
    [data.districts, snapshots],
  );

  // ------------------------------------------------------------------- init

  useEffect(() => {
    const holder = holderRef.current;
    if (!holder || mapRef.current) return undefined;

    const palette = readMapPalette(holder);
    paletteRef.current = palette;

    const first = data.camera?.[0];
    const origin = data.places.find((p) => p.role === 'origin') ?? data.places[0];
    const center: [number, number] = first?.center ??
      (origin && isNum(origin.lng) && isNum(origin.lat) ? [origin.lng, origin.lat] : [0, 0]);

    const style = buildReplayStyle({
      gibsDate: nptDay(Number.isFinite(clock.t) ? clock.t : ms(data.t0_npt)),
      palette,
      gibsVisible: false,
    });

    const map = safe('construct', () =>
      new maplibregl.Map({
        container: holder,
        // Our style type is structural; MapLibre's is the full spec. `as never`
        // hands it over without dragging the spec generics into this file.
        style: style as never,
        center,
        zoom: first?.zoom ?? 9,
        pitch: first?.pitch ?? 55,
        bearing: first?.bearing ?? 0,
        maxPitch: 85,
        // v5 moved the GL context flags off MapOptions and into their own bag;
        // MSAA is what keeps the corridor line from crawling on the terrain.
        // Terrain is fragment-bound: at Retina density a moving camera fell
        // to ~40 fps, capped at 1.25× it holds 70+. MSAA is a second full
        // terrain pass for a line that is 3 px wide; not worth the frames.
        canvasContextAttributes: { antialias: false },
        pixelRatio: Math.min(typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1, PLAYING_PIXEL_RATIO),
        attributionControl: { compact: true, customAttribution: VANTOR_ATTRIBUTION },
        // The desk owns the clock; MapLibre must not animate on its own.
        fadeDuration: 150,
      }),
    );
    if (!map) return undefined;
    mapRef.current = map;
    // Diagnostics handle for the desk's own browser checks (perf profiling of
    // terrain/hillshade cost); carries no data the page does not already hold.
    (window as unknown as { __opMap?: MapLibreMap }).__opMap = map;

    safe('error handler', () => {
      map.on('error', (e: unknown) => {
        const err = (e as { error?: unknown })?.error ?? e;
        console.warn('[OperationalPicture3D] map error:', err);
      });
    });

    // A reader who has taken the map is left alone: the director's camera is
    // suspended between dragstart and dragend.
    safe('drag handlers', () => {
      map.on('dragstart', () => {
        draggingRef.current = true;
      });
      map.on('dragend', () => {
        draggingRef.current = false;
      });
    });

    safe('load handler', () => {
      map.on('load', () => {
        safe('setTerrain', () => map.setTerrain({ source: TERRAIN_SOURCE, exaggeration: TERRAIN_EXAGGERATION }));
        installLayers(map, palette);
        readyRef.current = true;
        setReady(true);
        onReadyRef.current?.();
      });
    });

    return () => {
      readyRef.current = false;
      setReady(false);
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
      markersRef.current.forEach((m) => safe('marker remove', () => m.remove()));
      markersRef.current = [];
      safe('map remove', () => map.remove());
      mapRef.current = null;
      cameraKeyRef.current = '';
      beatCountRef.current = -1;
      snapshotRef.current = -2;
      gibsDayRef.current = '';
    };
    // Mount-only: the map is built once and every later change is an update.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ------------------------------------------------------------ static data

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    setData(map, SRC.beats, fc(beatFeatures));
    setData(map, SRC.damage, fc(damageFeatures));
    setData(map, SRC.gauges, fc(gaugeFeatures));
    setData(map, SRC.origin, fc(originFeatures));
    // The channel is ONE line feature, uploaded once. The replay never touches
    // its geometry again: what the front has crossed is painted with a
    // line-gradient over line-progress, which is a paint update, not a re-upload.
    if (path.length > 1) {
      setData(map, SRC.corridor, fc([line(path.map((v) => [v.lng, v.lat] as [number, number]), { part: 'channel' })]));
    } else {
      setData(map, SRC.corridor, EMPTY as FeatureCollection<Geometry, Props>);
    }
    // The collapse marker sits off the channel (its exact coordinates are not
    // published); a dashed connector says "the water came from up here" without
    // claiming a mapped course above the source zone.
    const originPt = originFeatures[0]?.geometry.coordinates as [number, number] | undefined;
    if (originPt && path.length) {
      setData(map, SRC.originLink, fc([line([originPt, [path[0].lng, path[0].lat]], { part: 'schematic' })]));
    } else {
      setData(map, SRC.originLink, EMPTY as FeatureCollection<Geometry, Props>);
    }
    // Force the derived layers to recompute against the new payload.
    beatCountRef.current = -1;
    snapshotRef.current = -2;
  }, [ready, beatFeatures, damageFeatures, gaugeFeatures, originFeatures, path]);

  // Place labels ride as DOM markers rather than symbol layers: the style
  // carries no glyph server, and the desk's own label grammar (9px mono, upper)
  // is CSS the map cannot express in a text-field.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return undefined;
    const palette = paletteRef.current;
    const labels: Array<{ lng: number; lat: number; text: string; tone: string; kind: 'damage' | 'origin' }> = [];
    originFeatures.forEach((f) => {
      const [lng, lat] = f.geometry.coordinates as [number, number];
      labels.push({ lng, lat, text: String(f.properties.name ?? ''), tone: palette?.critical ?? '#ef4444', kind: 'origin' });
    });
    const originNames = new Set(originFeatures.map((f) => String(f.properties.name ?? '').toLowerCase()));
    damageFeatures.forEach((f) => {
      const [lng, lat] = f.geometry.coordinates as [number, number];
      const name = String(f.properties.name ?? '');
      // The collapse origin is also catalogued as a damage site; one label is enough.
      if (originNames.has(name.toLowerCase()) || /langtang/i.test(name)) return;
      labels.push({ lng, lat, text: name, tone: palette?.sub ?? '#a1a1aa', kind: 'damage' });
    });

    labels.forEach((l) => {
      safe('marker add', () => {
        const el = document.createElement('div');
        el.dataset.kind = l.kind;
        el.textContent = l.text.toUpperCase();
        el.style.cssText = [
          'font-family: var(--font-mono, monospace)',
          'font-size: 9px',
          'letter-spacing: 0.08em',
          'text-transform: uppercase',
          'white-space: nowrap',
          'pointer-events: none',
          'transform: translateX(6px)',
          `color: ${l.tone}`,
          // A halo, not a card shadow: imagery underneath is photographic and
          // 9px type disappears into it without one.
          `text-shadow: 0 0 3px ${paletteRef.current?.base ?? '#0a0a0b'}, 0 0 6px ${paletteRef.current?.base ?? '#0a0a0b'}`,
        ].join(';');
        const marker = new maplibregl.Marker({ element: el, anchor: 'left' }).setLngLat([l.lng, l.lat]).addTo(map);
        markersRef.current.push(marker);
      });
    });

    // Collision pass. Labels are DOM markers, so MapLibre's symbol placement
    // never sees them; without this, a low camera stacks every name in the
    // gorge into one knot. Greedy by priority — origin, then damage sites in
    // km order, then Vantor captions — a label whose box meets one already
    // placed is hidden until the camera moves.
    const layout = () => {
      safe('label layout', () => {
        const placed: Array<[number, number, number, number]> = [];
        const consider = (el: HTMLElement, m: MapLibreMarker) => {
          if (el.dataset.gated === 'hidden') { el.style.visibility = 'hidden'; return; }
          const pt = map.project(m.getLngLat());
          const w = el.offsetWidth || el.textContent!.length * 6.2;
          const h = el.offsetHeight || 12;
          const box: [number, number, number, number] = [pt.x, pt.y - h / 2, pt.x + w + 8, pt.y + h / 2];
          const hit = placed.some((b) => box[0] < b[2] && box[2] > b[0] && box[1] < b[3] && box[3] > b[1]);
          el.style.visibility = hit ? 'hidden' : 'visible';
          if (!hit) placed.push(box);
        };
        markersRef.current.forEach((m) => {
          const el = m.getElement() as HTMLElement;
          if (el.dataset.kind === 'origin') consider(el, m);
        });
        markersRef.current.forEach((m) => {
          const el = m.getElement() as HTMLElement;
          if (el.dataset.kind !== 'origin') consider(el, m);
        });
        vantorRef.current.forEach((entry) => consider(entry.label, entry.marker));
      });
    };
    labelLayoutRef.current = layout;
    layout();
    const onMove = () => layout();
    safe('label layout hooks', () => {
      map.on('moveend', onMove);
      map.on('zoomend', onMove);
    });

    return () => {
      safe('label layout hooks off', () => {
        map.off('moveend', onMove);
        map.off('zoomend', onMove);
      });
      labelLayoutRef.current = null;
      markersRef.current.forEach((m) => safe('marker remove', () => m.remove()));
      markersRef.current = [];
    };
  }, [ready, originFeatures, damageFeatures]);

  // ------------------------------------------------------------------ vantor

  // Same-frame Vantor exports, one PRE and one POST raster per damage site,
  // draped on the terrain. Installed once per payload; the clock effect only
  // moves opacity, so the GPU never re-uploads a texture during the replay.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return undefined;
    const installed = vantorRef.current;
    const palette = paletteRef.current;
    const sites = (data.damage_sites ?? []).filter((d) => Array.isArray(d.levels) && d.levels.length > 0);

    sites.forEach((site) => {
      const level = site.levels!.find((l) => l.level === VANTOR_LEVEL) ?? site.levels![0];
      if (!level || !Array.isArray(level.bbox) || level.bbox.length !== 4) return;
      const [minx, miny, maxx, maxy] = level.bbox;
      const corners: [[number, number], [number, number], [number, number], [number, number]] = [
        [minx, maxy],
        [maxx, maxy],
        [maxx, miny],
        [minx, miny],
      ];
      (['pre', 'post'] as const).forEach((phase) => {
        const url = level[phase]?.export_url;
        if (!url) return;
        addSource(map, vantorId(site.key, phase), { type: 'image', url, coordinates: corners });
        const before = map.getLayer(LYR.districtFill) ? LYR.districtFill : undefined;
        safe(`vantor layer ${site.key} ${phase}`, () => {
          if (map.getLayer(vantorId(site.key, phase))) return;
          map.addLayer(
            {
              id: vantorId(site.key, phase),
              type: 'raster',
              source: vantorId(site.key, phase),
              paint: {
                'raster-opacity': phase === 'pre' ? 1 : 0,
                'raster-fade-duration': 0,
                'raster-resampling': 'linear',
              },
            } as never,
            before,
          );
        });
      });

      // The frame's own caption: which pass is on screen, when it was flown,
      // at what resolution and under how much cloud — read from the catalogue.
      const el = document.createElement('div');
      el.dataset.kind = 'vantor';
      el.textContent = vantorLabel(site, level, 0);
      el.style.cssText = [
        'font-family: var(--font-mono, monospace)',
        'font-size: 9px',
        'letter-spacing: 0.08em',
        'text-transform: uppercase',
        'white-space: nowrap',
        'pointer-events: none',
        `color: ${palette?.info ?? '#3b82f6'}`,
        `text-shadow: 0 0 3px ${palette?.base ?? '#0a0a0b'}, 0 0 6px ${palette?.base ?? '#0a0a0b'}`,
      ].join(';');
      const marker = new maplibregl.Marker({ element: el, anchor: 'top-left', offset: [0, 6] }).setLngLat([minx, miny]).addTo(map);
      installed.set(site.key, { site, level, label: el, marker, mix: 0 });
    });

    // Captions are site-scale intelligence: at corridor zooms they stack into
    // a knot over each other, so they show only once the camera is close.
    const VANTOR_LABEL_MIN_ZOOM = 11.5;
    const onZoom = () => {
      const show = map.getZoom() >= VANTOR_LABEL_MIN_ZOOM;
      installed.forEach((entry) => {
        entry.label.dataset.gated = show ? 'shown' : 'hidden';
        entry.label.style.visibility = show ? 'visible' : 'hidden';
      });
      labelLayoutRef.current?.();
    };
    safe('vantor zoom gate', () => {
      map.on('zoom', onZoom);
      onZoom();
    });

    return () => {
      safe('vantor zoom gate off', () => map.off('zoom', onZoom));
      installed.forEach((entry, key) => {
        safe('vantor marker remove', () => entry.marker.remove());
        (['pre', 'post'] as const).forEach((phase) => {
          safe(`vantor layer remove ${key}`, () => {
            if (map.getLayer(vantorId(key, phase))) map.removeLayer(vantorId(key, phase));
            if (map.getSource(vantorId(key, phase))) map.removeSource(vantorId(key, phase));
          });
        });
      });
      installed.clear();
    };
  }, [ready, data.damage_sites]);

  // ---------------------------------------------------------------- toggles

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    setVisible(map, [LAYER_GIBS], layers.gibs);
    setVisible(map, [LYR.gauges], layers.gauges);
    setVisible(map, [LYR.districtFill, LYR.districtLine], layers.districts);
    setVisible(map, [LYR.damage], layers.damage);
    vantorRef.current.forEach((entry, key) => {
      setVisible(map, [vantorId(key, 'pre'), vantorId(key, 'post')], layers.vantor);
      entry.label.style.display = layers.vantor ? '' : 'none';
    });
    markersRef.current.forEach((m) =>
      safe('marker toggle', () => {
        const el = m.getElement?.() as HTMLElement | undefined;
        if (el && el.dataset.kind === 'damage') el.style.display = layers.damage ? '' : 'none';
      }),
    );
  }, [ready, layers.gibs, layers.gauges, layers.districts, layers.damage, layers.vantor]);

  // ------------------------------------------------------------------ clock

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;

    // --- director effects
    fxRef.current = clock.film && clock.film.scene.fx ? clock.film.scene.fx : null;
    fxOriginRef.current = path.length ? [path[0].lng, path[0].lat] : null;

    // --- the front itself
    const front = clock.front;
    if (front && isNum(front.lng) && isNum(front.lat)) {
      setData(
        map,
        SRC.front,
        fc([
          point(front.lng, front.lat, {
            confidence: front.confidence,
            km: isNum(clock.frontKm) ? clock.frontKm : null,
          }),
        ]),
      );
    } else {
      setData(map, SRC.front, EMPTY as FeatureCollection<Geometry, Props>);
    }

    // --- corridor: crossed stretch solid red to the last PUBLISHED fix the
    //     clock has reached, orange (estimated) from there to the front, nothing
    //     beyond. Expressed as a gradient over line-progress so each frame is one
    //     cheap paint update on a line the GPU already holds.
    const startKm = path.length ? path[0].km : 0;
    const endKm = path.length ? path[path.length - 1].km : 1;
    const frontKm = isNum(clock.frontKm) ? clock.frontKm : startKm;
    const publishedKm = data.keyframes
      .filter((k) => k.confidence === 'published' && isNum(k.km) && ms(k.t_npt) <= clock.t)
      .reduce<number>((acc, k) => (k.km > acc ? k.km : acc), startKm);
    const span = Math.max(1e-6, endKm - startKm);
    const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
    const pPub = clamp01((Math.min(publishedKm, frontKm) - startKm) / span);
    const pFront = Math.max(pPub + 1e-4, clamp01((frontKm - startKm) / span));
    const gradKey = `${pPub.toFixed(4)}|${pFront.toFixed(4)}`;
    if (gradKey !== gradientKeyRef.current) {
      gradientKeyRef.current = gradKey;
      safe('corridor gradient', () => {
        if (!map.getLayer(LYR.corridorRun)) return;
        const pal = paletteRef.current;
        map.setPaintProperty(LYR.corridorRun, 'line-gradient', [
          'step',
          ['line-progress'],
          pal?.critical ?? '#ef4444',
          pPub,
          pal?.high ?? '#f97316',
          Math.min(1, pFront),
          'rgba(0,0,0,0)',
        ] as never);
      });
    }

    // --- beats appear as the clock reaches them; the engine decides when.
    if (clock.visibleBeatCount !== beatCountRef.current) {
      beatCountRef.current = clock.visibleBeatCount;
      const visible = beatFeatures.filter((f) => Number(f.properties.idx) < clock.visibleBeatCount);
      setData(map, SRC.beats, fc(visible));
    }
    safe('active beat', () => {
      if (map.getLayer(LYR.beatsActive)) {
        map.setFilter(LYR.beatsActive, ['==', ['get', 'idx'], clock.activeBeatIndex] as never);
      }
    });

    // --- district fills step between published breakdowns
    const snapIdx = snapshotIndexAt(snapshots, clock.t);
    if (snapIdx !== snapshotRef.current) {
      snapshotRef.current = snapIdx;
      setData(map, SRC.districts, districtsAt(snapIdx));
    }

    // --- Vantor: the POST pass fades in as the front passes each site. The
    //     pass itself was flown a day or more later (its date is on the label);
    //     what the crossfade times is the moment the water reached the frame.
    vantorRef.current.forEach((entry, key) => {
      const km = entry.site.km_mark;
      const mix = isNum(km) && isNum(frontKm) ? Math.max(0, Math.min(1, (frontKm - km) / VANTOR_FADE_KM)) : 0;
      if (Math.abs(mix - entry.mix) < 0.01) return;
      entry.mix = mix;
      safe(`vantor mix ${key}`, () => {
        if (map.getLayer(vantorId(key, 'post'))) map.setPaintProperty(vantorId(key, 'post'), 'raster-opacity', mix as never);
      });
      entry.label.textContent = vantorLabel(entry.site, entry.level, mix);
    });

    const day = nptDay(clock.t);
    if (day !== gibsDayRef.current && /^\d{4}-\d{2}-\d{2}$/.test(day)) {
      gibsDayRef.current = day;
      safe('gibs date', () => {
        const src = map.getSource(GIBS_SOURCE) as unknown as { setTiles?: (t: string[]) => void } | undefined;
        if (src && typeof src.setTiles === 'function') src.setTiles(gibsTiles(day));
      });
    }

    // --- camera: the director's cut, unless the reader has the map
    //
    // The engine does not hand out discrete shots: while a move is running it
    // interpolates a fresh camera on EVERY tick. Easing each of those over
    // 900 ms would restart the ease sixty times a second, so the map would
    // crawl a sixtieth of the way toward each target and trail the replay by
    // seconds. The ease is therefore spent where it belongs — on a CUT, which
    // is any camera that arrives after a quiet gap (a scrub, a beat step, a
    // shot change while paused). A camera arriving mid-stream is applied
    // immediately and the engine's own easing carries the motion.
    const cam = clock.camera;
    if (cam && isNum(cam.zoom) && Array.isArray(cam.center)) {
      const key = `${cam.center[0]},${cam.center[1]},${cam.zoom},${cam.pitch},${cam.bearing}`;
      if (key !== cameraKeyRef.current && !draggingRef.current) {
        const now = Date.now();
        const cut = now - cameraAtRef.current > CAMERA_CUT_GAP_MS;
        cameraKeyRef.current = key;
        cameraAtRef.current = now;
        safe('easeTo', () =>
          map.easeTo({
            center: cam.center,
            zoom: cam.zoom,
            pitch: cam.pitch,
            bearing: cam.bearing,
            duration: cut ? CAMERA_EASE_MS : 0,
            essential: true,
          }),
        );
      }
    }
  }, [ready, clock, data.keyframes, path, beatFeatures, snapshots, districtsAt]);

  // ------------------------------------------------------------- density

  // Frames while it moves, pixels while it stands still. The switch happens
  // on play/pause only, so the map is never re-sized mid-motion.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const dpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1;
    const target = Math.min(dpr, playing ? PLAYING_PIXEL_RATIO : PAUSED_PIXEL_RATIO);
    safe('pixel ratio', () => {
      const m = map as unknown as { getPixelRatio?: () => number; setPixelRatio?: (r: number) => void };
      if (typeof m.setPixelRatio === 'function' && (typeof m.getPixelRatio !== 'function' || Math.abs(m.getPixelRatio() - target) > 0.01)) {
        m.setPixelRatio(target);
      }
    });
  }, [ready, playing]);

  // ------------------------------------------------------------------ pulse

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return undefined;
    let stopped = false;
    let last = 0;
    const tick = () => {
      if (stopped) return;
      const now = Date.now();
      // Half rate: the halo reads the same and the map is not asked for sixty
      // repaints a second for the life of the widget.
      if (now - last >= 32) {
        last = now;
        const phase = (now % 1600) / 1600;
        safe('pulse', () => {
          if (!map.getLayer(LYR.frontHalo)) return;
          map.setPaintProperty(LYR.frontHalo, 'circle-radius', (10 + phase * 26) as never);
          map.setPaintProperty(LYR.frontHalo, 'circle-opacity', (0.32 * (1 - phase)) as never);
        });
        safe('fx', () => {
          const src = map.getSource(SRC.fx) as unknown as { setData?: (d: unknown) => void } | undefined;
          if (!src || typeof src.setData !== 'function') return;
          const origin = fxOriginRef.current;
          if (fxRef.current !== 'collapse' || !origin) {
            if (fxWasOnRef.current) {
              src.setData(EMPTY);
              fxWasOnRef.current = false;
            }
            return;
          }
          fxWasOnRef.current = true;
          const period = 3200;
          const rings = [0, 1, 2].map((k) => {
            const ph = ((now + (k * period) / 3) % period) / period;
            return point(origin[0], origin[1], { r: 6 + ph * 140, o: 0.85 * (1 - ph) });
          });
          src.setData(fc(rings));
        });
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      stopped = true;
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    };
  }, [ready]);

  // ----------------------------------------------------------------- resize

  useEffect(() => {
    const holder = holderRef.current;
    if (!holder || typeof ResizeObserver === 'undefined') return undefined;
    const ro = new ResizeObserver(() => {
      const map = mapRef.current;
      if (map) safe('resize', () => map.resize());
    });
    ro.observe(holder);
    return () => ro.disconnect();
  }, []);

  // ------------------------------------------------------------------ handle

  useImperativeHandle(
    ref,
    (): OperationalPicture3DHandle => ({
      flyTo: (camera, durationMs) => {
        const map = mapRef.current;
        if (!map || !camera) return;
        cameraKeyRef.current = `${camera.center[0]},${camera.center[1]},${camera.zoom},${camera.pitch},${camera.bearing}`;
        cameraAtRef.current = Date.now();
        safe('flyTo', () =>
          map.easeTo({
            center: camera.center,
            zoom: camera.zoom,
            pitch: camera.pitch,
            bearing: camera.bearing,
            duration: durationMs ?? CAMERA_EASE_MS,
            essential: true,
          }),
        );
      },
      getMap: () => mapRef.current,
    }),
    [],
  );

  return <div ref={holderRef} style={{ position: 'absolute', inset: 0, overflow: 'hidden' }} />;
}

// ------------------------------------------------------------------- layers

/**
 * Sources and layers, created once at load. Colours are the desk's own tokens;
 * widths and radii are the only numbers in this file and they are geometry, not
 * intelligence.
 */
function installLayers(map: MapLibreMap, p: MapPalette) {
  const geo = (): StyleSourceDef => ({ type: 'geojson', data: EMPTY });

  addSource(map, SRC.districts, geo());
  addSource(map, SRC.corridor, { type: 'geojson', data: EMPTY, lineMetrics: true });
  addSource(map, SRC.originLink, geo());
  addSource(map, SRC.fx, geo());
  addSource(map, SRC.damage, geo());
  addSource(map, SRC.gauges, geo());
  addSource(map, SRC.beats, geo());
  addSource(map, SRC.origin, geo());
  addSource(map, SRC.front, geo());

  // Districts: outline first, a wash of colour only where a figure exists.
  addLayer(map, {
    id: LYR.districtFill,
    type: 'fill',
    source: SRC.districts,
    paint: {
      'fill-color': [
        'case',
        ['<', ['get', 'recovered'], 0],
        'transparent',
        [
          'interpolate',
          ['linear'],
          ['get', 'recovered'],
          0,
          p.medium,
          25,
          p.high,
          100,
          p.critical,
        ],
      ],
      'fill-opacity': ['case', ['<', ['get', 'recovered'], 0], 0, 0.16],
    },
  });
  addLayer(map, {
    id: LYR.districtLine,
    type: 'line',
    source: SRC.districts,
    paint: { 'line-color': p.hairline, 'line-width': 0.8, 'line-opacity': 0.85 },
  });

  // Channel: the whole course dim and dashed underneath; on top, the run the
  // water has made — a single gradient line the clock repaints each frame.
  addLayer(map, {
    id: LYR.corridorBase,
    type: 'line',
    source: SRC.corridor,
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': p.muted, 'line-width': 1.4, 'line-opacity': 0.5, 'line-dasharray': [1, 2] },
  });
  addLayer(map, {
    id: LYR.corridorRun,
    type: 'line',
    source: SRC.corridor,
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: {
      'line-width': 3,
      'line-opacity': 0.92,
      'line-gradient': ['step', ['line-progress'], 'rgba(0,0,0,0)', 1, 'rgba(0,0,0,0)'],
    },
  });
  // Schematic connector from the collapse marker to the mapped source zone.
  addLayer(map, {
    id: LYR.originLink,
    type: 'line',
    source: SRC.originLink,
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': p.critical, 'line-width': 1.6, 'line-opacity': 0.7, 'line-dasharray': [0.6, 2.2] },
  });

  addLayer(map, {
    id: LYR.gauges,
    type: 'circle',
    source: SRC.gauges,
    paint: {
      'circle-radius': ['case', ['in', ['get', 'alert'], ['literal', ['danger', 'warning']]], 4, 2.6],
      'circle-color': [
        'match',
        ['get', 'alert'],
        'danger',
        p.critical,
        'warning',
        p.medium,
        'normal',
        p.info,
        p.muted,
      ],
      'circle-opacity': ['case', ['get', 'stale'], 0.45, 0.9],
      'circle-stroke-color': p.base,
      'circle-stroke-width': 0.6,
    },
  });

  addLayer(map, {
    id: LYR.damage,
    type: 'circle',
    source: SRC.damage,
    paint: {
      'circle-radius': 4.5,
      'circle-color': 'transparent',
      'circle-stroke-color': p.sub,
      'circle-stroke-width': 1.4,
      'circle-opacity': 0,
    },
  });

  addLayer(map, {
    id: LYR.beats,
    type: 'circle',
    source: SRC.beats,
    paint: {
      'circle-radius': 4,
      'circle-color': [
        'match',
        ['get', 'kind'],
        'trigger',
        p.critical,
        'impact',
        p.high,
        'response',
        p.info,
        'warning',
        p.medium,
        'assessment',
        p.low,
        p.sub,
      ],
      'circle-opacity': 0.85,
      'circle-stroke-color': p.base,
      'circle-stroke-width': 1,
    },
  });
  addLayer(map, {
    id: LYR.beatsActive,
    type: 'circle',
    source: SRC.beats,
    filter: ['==', ['get', 'idx'], -1],
    paint: {
      'circle-radius': 9,
      'circle-color': 'transparent',
      'circle-opacity': 0,
      'circle-stroke-color': p.text,
      'circle-stroke-width': 1.2,
      'circle-stroke-opacity': 0.9,
    },
  });

  addLayer(map, {
    id: LYR.origin,
    type: 'circle',
    source: SRC.origin,
    paint: {
      'circle-radius': 6,
      'circle-color': 'transparent',
      'circle-opacity': 0,
      'circle-stroke-color': p.critical,
      'circle-stroke-width': 2,
    },
  });

  // The front: a halo that breathes (see the pulse effect) under a hard core.
  // Collapse effect: three rings that swell out of the source zone while the
  // film's opening chapter plays. Geometry is the channel's first vertex; the
  // rings carry no data and are only drawn when the director asks for them.
  addLayer(map, {
    id: LYR.fxRing,
    type: 'circle',
    source: SRC.fx,
    paint: {
      'circle-radius': ['get', 'r'],
      'circle-color': 'transparent',
      'circle-stroke-color': p.critical,
      'circle-stroke-width': 1.5,
      'circle-stroke-opacity': ['get', 'o'],
      'circle-pitch-alignment': 'map',
    },
  });
  addLayer(map, {
    id: LYR.frontHalo,
    type: 'circle',
    source: SRC.front,
    paint: {
      'circle-radius': 12,
      'circle-color': p.critical,
      'circle-opacity': 0.25,
      'circle-blur': 0.6,
    },
  });
  addLayer(map, {
    id: LYR.frontCore,
    type: 'circle',
    source: SRC.front,
    paint: {
      'circle-radius': 5,
      // Published fixes are hard-edged; an interpolated position is hollow, so
      // the estimate reads as an estimate at a glance.
      'circle-color': ['case', ['==', ['get', 'confidence'], 'published'], p.critical, 'transparent'],
      'circle-opacity': ['case', ['==', ['get', 'confidence'], 'published'], 1, 0],
      'circle-stroke-color': p.critical,
      'circle-stroke-width': 2,
      'circle-stroke-opacity': 1,
    },
  });
}

const OperationalPicture3D = forwardRef<OperationalPicture3DHandle, OperationalPicture3DProps>(
  OperationalPicture3DInner,
);
OperationalPicture3D.displayName = 'OperationalPicture3D';

export default OperationalPicture3D;
export { OperationalPicture3D };
