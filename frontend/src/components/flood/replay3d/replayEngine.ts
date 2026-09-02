/**
 * REPLAY ENGINE — the clock behind OPERATIONAL PICTURE · 3D.
 *
 * The widget animates a published record. This file turns that record into a
 * function of time and nothing more: it invents no position, no figure and no
 * hour that the served script does not carry.
 *
 * Three honesty rules are compiled into the maths here:
 *
 *   1. A FRONT POSITION IS EITHER A PUBLISHED FIX OR AN INTERPOLATION, and the
 *      two are never confused. `frontKmAt` returns the keyframe's own
 *      confidence when the clock sits on a fix, and `estimated` — with the two
 *      places it is between — for every instant in between. The HUD prints
 *      that word; the map draws the estimated stretch dashed.
 *   2. THE TOLL STEPS, IT DOES NOT SLIDE. `tollAt` returns the last mark the
 *      authority published at or before the clock. Interpolating a death toll
 *      between two bulletins would be inventing casualties.
 *   3. TIME IS READ, NOT RE-ZONED. Every `t_npt` in the script carries the
 *      +05:45 offset, so `Date.parse` is exact. The parsed epoch ms is used for
 *      arithmetic only; every string that reaches the screen is formatted from
 *      the ORIGINAL published string via milspec's DTG helpers, or — for the
 *      free-running clock, which no source published — from `nptIso`, which
 *      rebuilds a fixed-offset string rather than consulting the browser zone.
 *
 * Nothing in this file is a literal figure from the event. The only constants
 * are UI presets (playback speeds, fallback camera framing).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { NPT_OFFSET_MS } from '../floodReplay';

// ------------------------------------------------------------------ payload
// These mirror `GET /api/v1/flood/replay`. The map component declares the same
// shapes; either module may be imported from, they are structurally identical.

export type ReplayConfidence = 'published' | 'derived' | 'estimated';

export interface ReplayPlace {
  key: string;
  name: string;
  name_ne?: string | null;
  lat: number;
  lng: number;
  /** Kilometres downstream of the corridor's km-0 waypoint. null = off-corridor. */
  km: number | null;
  elev_m?: number | null;
  role: string;
  source?: string | null;
  source_url?: string | null;
}

/** A time+place the record states the front reached. Nothing else is a fix. */
export interface ReplayKeyframe {
  t_npt: string;
  place_key: string;
  km: number;
  confidence: ReplayConfidence;
  source: string;
  source_url?: string | null;
  note?: string | null;
}

export interface ReplayBeat {
  t_npt: string;
  /** false = the source published a date only; the hour is ordering, not fact. */
  time_published: boolean;
  kind: string;
  headline: string;
  detail?: string | null;
  place_key?: string | null;
  source: string;
  source_url?: string | null;
  confidence: ReplayConfidence;
  note?: string | null;
}

export interface ReplayCameraRecord {
  t_npt: string;
  /** [lng, lat] */
  center: number[];
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
  rescued?: number | null;
  source: string;
  source_url?: string | null;
  note?: string | null;
}

export interface ReplaySourceRef {
  label: string;
  url: string;
  grade_hint?: string | null;
}

/** A corridor waypoint as `/flood/districts/geo` publishes it. */
export interface CorridorWaypoint {
  name: string;
  lat: number;
  lng: number;
  kind: string;
  km: number | null;
}

export interface ReplayPayload {
  event_key: string;
  title: string;
  t0_npt: string;
  t_end_npt: string;
  notes?: string[];
  places: ReplayPlace[];
  keyframes: ReplayKeyframe[];
  beats: ReplayBeat[];
  camera?: ReplayCameraRecord[];
  toll_marks?: ReplayTollMark[];
  sources?: ReplaySourceRef[];
  /** Merged in by the endpoint. Typed loosely: the engine reads only `corridor`. */
  corridor?: CorridorWaypoint[];
  film?: FilmRecord | null;
  damage_sites?: any[];
  gauges?: any[];
  chronology?: any[];
  districts?: any;
}

/** Which optional map layers are lit. Owned by the widget, read by the map. */
export interface LayerToggles {
  gibs: boolean;
  gauges: boolean;
  districts: boolean;
  damage: boolean;
}

// ------------------------------------------------------------------ timeline

/** A corridor waypoint that carries a km mark, so the front can be placed on it. */
export interface CorridorAnchor {
  name: string;
  lat: number;
  lng: number;
  km: number;
  kind: string;
}

export interface TimelineKeyframe extends ReplayKeyframe {
  /** Epoch ms, parsed from the offset-bearing `t_npt`. */
  t: number;
  place: ReplayPlace | null;
  /** The place's own published coordinates where known, else the corridor's. */
  lng: number;
  lat: number;
}

export interface TimelineBeat extends ReplayBeat {
  t: number;
  index: number;
  place: ReplayPlace | null;
}

export interface TimelineCamera {
  t: number;
  center: [number, number];
  zoom: number;
  pitch: number;
  bearing: number;
  /** Seconds of REAL playback to sit on this shot before easing to the next. */
  holdS: number;
  label?: string;
}

export interface TimelineTollMark extends ReplayTollMark {
  t: number;
}

export interface ReplayTimeline {
  eventKey: string;
  title: string;
  t0: number;
  tEnd: number;
  durationMs: number;
  /** The original offset-bearing strings, for milspec DTGs. */
  t0Npt: string;
  tEndNpt: string;
  keyframes: TimelineKeyframe[];
  beats: TimelineBeat[];
  camera: TimelineCamera[];
  tollMarks: TimelineTollMark[];
  /** km-parameterised corridor polyline, ascending. */
  corridor: CorridorAnchor[];
  places: Record<string, ReplayPlace>;
  minKm: number;
  maxKm: number;
  sources: ReplaySourceRef[];
}

// ------------------------------------------------------------------ film

/** A card the director wants on screen during a scene. Resolved by the widget
 *  against the licensed media the desk already serves; never a URL typed here. */
export interface FilmCardRef {
  kind: 'commons' | 'video' | 'photo' | 'vantor' | 'cite' | 'end';
  /** Wikimedia Commons file title (commons / video). */
  file?: string;
  /** Substring of an official photograph's title (photo). */
  match?: string;
  /** Damage-site key + export level (vantor). */
  site?: string;
  level?: string;
  /** Chronology beat index (cite). */
  beat?: number;
  /** Show from this event time onward; absent = whole scene. */
  t_npt?: string;
  caption?: string;
}

export interface FilmNarrationRef {
  /** A chronology beat — headline + detail + source travel with it. */
  beat?: number;
  /** Or a sentence quoted from a cited document. */
  text?: string;
  source?: string;
  source_url?: string;
}

export interface FilmCameraRecord {
  center: [number, number];
  zoom: number;
  pitch: number;
  bearing: number;
}

export interface FilmFollowRecord {
  zoom: number;
  pitch: number;
  /** Degrees added to the direction of travel; 0 looks downstream. */
  bearingOffset?: number;
  /** km downstream of the front the camera centres on, so the water sits in the
   *  lower third of the frame instead of under the camera. */
  lead_km?: number;
}

export interface FilmSceneRecord {
  key: string;
  title: string;
  t_from: string;
  t_to: string;
  /** Real seconds the run from t_from to t_to takes on screen. */
  duration_s: number;
  /** Real seconds the clock freezes at t_to while the cards play. */
  hold_s?: number;
  camera?: FilmCameraRecord;
  follow?: FilmFollowRecord;
  /** Camera for the hold, when it differs from the run's. */
  hold_camera?: FilmCameraRecord;
  fx?: 'collapse' | null;
  narration?: FilmNarrationRef[];
  cards?: FilmCardRef[];
}

export interface FilmRecord {
  title: string;
  note?: string;
  scenes: FilmSceneRecord[];
}

export interface FilmNarration {
  text: string;
  detail: string | null;
  source: string | null;
  source_url: string | null;
  /** Event time the line becomes true; scene start for quoted sentences. */
  t: number;
  kind: string | null;
}

export interface FilmCard extends FilmCardRef {
  /** Event time the card appears; scene start when unstated. */
  t: number;
}

export interface FilmScene extends Omit<FilmSceneRecord, 'narration' | 'cards'> {
  index: number;
  tFrom: number;
  tTo: number;
  runS: number;
  holdS: number;
  /** Real-second offsets of the scene inside the film. */
  realStart: number;
  realRunEnd: number;
  realEnd: number;
  narration: FilmNarration[];
  cards: FilmCard[];
}

export interface Film {
  title: string;
  scenes: FilmScene[];
  totalS: number;
}

export interface FilmState {
  scene: FilmScene;
  phase: 'run' | 'hold';
  /** Event time the film clock maps to. */
  t: number;
  /** 0..1 through the whole scene (run + hold). */
  progress: number;
  holdRemainingS: number;
  atEnd: boolean;
}

/** The film resolved against the timeline: every beat reference becomes text,
 *  every scene gets its real-second offsets. null when the script has no film. */
export function buildFilm(payload: ReplayPayload | null, timeline: ReplayTimeline): Film | null {
  const rec = payload?.film;
  if (!rec || !Array.isArray(rec.scenes) || !rec.scenes.length) return null;
  const scenes: FilmScene[] = [];
  let cursor = 0;
  rec.scenes.forEach((sc, index) => {
    const tFrom = parseNpt(sc.t_from);
    const tTo = parseNpt(sc.t_to);
    if (tFrom === null || tTo === null || tTo < tFrom) return;
    const runS = Math.max(0, Number(sc.duration_s) || 0);
    const holdS = Math.max(0, Number(sc.hold_s) || 0);
    const narration: FilmNarration[] = (sc.narration ?? [])
      .map((n): FilmNarration | null => {
        if (typeof n.beat === 'number') {
          const b = timeline.beats[n.beat];
          if (!b) return null;
          return { text: b.headline, detail: b.detail ?? null, source: b.source ?? null, source_url: b.source_url ?? null, t: b.t, kind: b.kind };
        }
        if (!n.text) return null;
        return { text: n.text, detail: null, source: n.source ?? null, source_url: n.source_url ?? null, t: tFrom, kind: null };
      })
      .filter((n): n is FilmNarration => n !== null)
      .sort((a, b) => a.t - b.t);
    const cards: FilmCard[] = (sc.cards ?? []).map((c) => ({ ...c, t: (c.t_npt && parseNpt(c.t_npt)) || tFrom }));
    const realStart = cursor;
    const realRunEnd = realStart + runS;
    const realEnd = realRunEnd + holdS;
    cursor = realEnd;
    scenes.push({ ...sc, index: scenes.length, tFrom, tTo, runS, holdS, realStart, realRunEnd, realEnd, narration, cards });
  });
  if (!scenes.length) return null;
  return { title: rec.title, scenes, totalS: cursor };
}

/** Where the film is at real second r. */
export function filmStateAt(film: Film, r: number): FilmState {
  const total = film.totalS;
  const rr = clamp(r, 0, total);
  let scene = film.scenes[film.scenes.length - 1];
  for (const sc of film.scenes) {
    if (rr < sc.realEnd || sc === film.scenes[film.scenes.length - 1]) {
      scene = sc;
      break;
    }
  }
  const inScene = rr - scene.realStart;
  const span = Math.max(1e-6, scene.realEnd - scene.realStart);
  if (inScene < scene.runS && scene.runS > 0) {
    const f = inScene / scene.runS;
    return { scene, phase: 'run', t: scene.tFrom + (scene.tTo - scene.tFrom) * f, progress: inScene / span, holdRemainingS: scene.holdS, atEnd: false };
  }
  const holdElapsed = inScene - scene.runS;
  return {
    scene,
    phase: 'hold',
    t: scene.tTo,
    progress: clamp(inScene / span, 0, 1),
    holdRemainingS: Math.max(0, scene.holdS - holdElapsed),
    atEnd: rr >= total,
  };
}

/** The real second a given event time corresponds to (start of its scene's
 *  run, proportionally), so a scrub in film mode lands inside the right chapter. */
export function realFromT(film: Film, t: number): number {
  for (const sc of film.scenes) {
    if (t <= sc.tTo) {
      if (sc.tTo <= sc.tFrom || sc.runS <= 0) return sc.realStart;
      const f = clamp((t - sc.tFrom) / (sc.tTo - sc.tFrom), 0, 1);
      return sc.realStart + f * sc.runS;
    }
  }
  return film.totalS;
}

/** The scene whose event window holds t (manual mode wants a chapter name too). */
export function sceneAtEventTime(film: Film, t: number): FilmScene {
  for (const sc of film.scenes) if (t <= sc.tTo) return sc;
  return film.scenes[film.scenes.length - 1];
}

/** Compass bearing (deg) from a to b. */
function bearingBetween(a: { lng: number; lat: number }, b: { lng: number; lat: number }): number {
  const toRad = Math.PI / 180;
  const φ1 = a.lat * toRad;
  const φ2 = b.lat * toRad;
  const Δλ = (b.lng - a.lng) * toRad;
  const y = Math.sin(Δλ) * Math.cos(φ2);
  const x = Math.cos(φ1) * Math.sin(φ2) - Math.sin(φ1) * Math.cos(φ2) * Math.cos(Δλ);
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
}

/** Direction of flow at a km mark, from the corridor a kilometre either side. */
export function headingAtKm(timeline: ReplayTimeline, km: number): number | null {
  const a = positionAtKm(km - 0.75, timeline.corridor);
  const b = positionAtKm(km + 0.75, timeline.corridor);
  if (!a || !b || (a.lng === b.lng && a.lat === b.lat)) return null;
  return bearingBetween(a, b);
}

// ------------------------------------------------------------------ clock view

export interface FrontPosition {
  lng: number;
  lat: number;
  confidence: ReplayConfidence;
  /** Named endpoints of the interpolation. null when the clock sits on a fix. */
  between: [string, string] | null;
}

export interface ReplayCameraView {
  center: [number, number];
  zoom: number;
  pitch: number;
  bearing: number;
  label?: string;
}

/** What the map reads off the clock. The hook returns this plus the controls. */
export type ReplayMode = 'film' | 'manual';

export interface ReplayClockView {
  /** Epoch ms. */
  t: number;
  mode: ReplayMode;
  /** Film state when a film is loaded — in manual mode the scene is the one
   *  whose window holds t, so the chapter name still reads. */
  film: FilmState | null;
  frontKm: number;
  front: FrontPosition;
  camera: ReplayCameraView;
  /** Index into `timeline.beats` of the last beat that has happened; -1 before. */
  activeBeatIndex: number;
  tollNow: TimelineTollMark | null;
  visibleBeatCount: number;
}

export interface ReplayClock extends ReplayClockView {
  timeline: ReplayTimeline;
  filmScript: Film | null;
  setMode: (mode: ReplayMode) => void;
  jumpToScene: (index: number) => void;
  /** Real seconds into the film (film mode). */
  filmR: number;
  setT: (t: number) => void;
  playing: boolean;
  setPlaying: (playing: boolean) => void;
  toggle: () => void;
  speed: number;
  setSpeed: (speed: number) => void;
  stepBeat: (delta: number) => void;
  seekToBeat: (index: number) => void;
  restart: () => void;
  atEnd: boolean;
  activeBeat: TimelineBeat | null;
  /** The clock as a fixed-offset NPT string — feed to milspec dtgNpt/dtgZ. */
  nptIso: string;
}

// ------------------------------------------------------------------ time

const pad2 = (v: number) => String(Math.trunc(Math.abs(v))).padStart(2, '0');

const OFFSET_SUFFIX = `${NPT_OFFSET_MS < 0 ? '-' : '+'}${pad2(NPT_OFFSET_MS / 3_600_000)}:${pad2(
  (NPT_OFFSET_MS / 60_000) % 60,
)}`;

/**
 * Epoch ms from a script timestamp. Every `t_npt` carries `+05:45`, so
 * `Date.parse` is exact and no zone assumption is made. NaN → null.
 */
export function parseNpt(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isFinite(t) ? t : null;
}

/**
 * A fixed-offset NPT string for an arbitrary instant — used only for the
 * free-running clock, which no source published. Formatted by hand rather than
 * with toISOString so the browser's own zone is never consulted.
 */
export function nptIso(t: number): string {
  if (!Number.isFinite(t)) return '';
  const d = new Date(t + NPT_OFFSET_MS);
  return (
    `${d.getUTCFullYear()}-${pad2(d.getUTCMonth() + 1)}-${pad2(d.getUTCDate())}` +
    `T${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())}:${pad2(d.getUTCSeconds())}${OFFSET_SUFFIX}`
  );
}

// ------------------------------------------------------------------ helpers

const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);

const clamp = (v: number, lo: number, hi: number) => (v < lo ? lo : v > hi ? hi : v);

const lerp = (a: number, b: number, f: number) => a + (b - a) * f;

/** Shortest-arc angle interpolation, so a 350°→010° pan does not spin 340°. */
const lerpAngle = (a: number, b: number, f: number) => {
  const d = ((((b - a) % 360) + 540) % 360) - 180;
  return (((a + d * f) % 360) + 360) % 360;
};

const easeInOutCubic = (x: number) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);

/**
 * Index of the last item whose `t` is <= t, or -1. Binary search: this runs on
 * every animation frame.
 */
function lastIndexAtOrBefore<T extends { t: number }>(items: T[], t: number): number {
  let lo = 0;
  let hi = items.length - 1;
  let found = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (items[mid].t <= t) {
      found = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return found;
}

// ------------------------------------------------------------------ build

/** Roles that sit on the river run, when the corridor has to be built from places. */
const CORRIDOR_ROLES = /^(origin|corridor|impact)$/i;

/** Framing used only when the script ships no camera track. */
const FALLBACK_CAMERA = { zoom: 9.5, pitch: 55, bearing: 0 } as const;

/** Never let a hold eat more than this share of a segment, whatever the speed. */
const MAX_HOLD_FRACTION = 0.6;

/** Clamp a frame's real elapsed time: a backgrounded tab must not teleport the front. */
const MAX_FRAME_MS = 250;

export const EMPTY_TIMELINE: ReplayTimeline = {
  eventKey: '',
  title: '',
  t0: 0,
  tEnd: 0,
  durationMs: 0,
  t0Npt: '',
  tEndNpt: '',
  keyframes: [],
  beats: [],
  camera: [],
  tollMarks: [],
  corridor: [],
  places: {},
  minKm: 0,
  maxKm: 0,
  sources: [],
};

function buildCorridor(payload: ReplayPayload, keyframes: TimelineKeyframe[]): CorridorAnchor[] {
  const source: Array<{ name: string; lat: number; lng: number; km: number | null; kind: string }> =
    payload.corridor && payload.corridor.length
      ? payload.corridor.map((w) => ({ name: w.name, lat: w.lat, lng: w.lng, km: w.km, kind: w.kind }))
      : (payload.places ?? [])
          .filter((p) => CORRIDOR_ROLES.test(p.role ?? ''))
          .map((p) => ({ name: p.name, lat: p.lat, lng: p.lng, km: p.km, kind: p.role }));

  const anchors: CorridorAnchor[] = source
    .filter((p) => isNum(p.km) && isNum(p.lat) && isNum(p.lng))
    .map((p) => ({ name: p.name, lat: p.lat, lng: p.lng, km: p.km as number, kind: p.kind }))
    .sort((a, b) => a.km - b.km);

  // The collapse origin is published without a km mark — the corridor's km scale
  // starts at the border post. The record's own upstream keyframe supplies the
  // figure, so the origin is anchored from the data rather than typed here.
  const origin = source.find((p) => !isNum(p.km) && /origin/i.test(p.kind ?? ''));
  if (origin && isNum(origin.lat) && isNum(origin.lng) && keyframes.length) {
    const minKfKm = Math.min(...keyframes.map((k) => k.km));
    if (isNum(minKfKm) && (!anchors.length || minKfKm < anchors[0].km)) {
      anchors.unshift({ name: origin.name, lat: origin.lat, lng: origin.lng, km: minKfKm, kind: 'origin' });
    }
  }
  return anchors;
}

/**
 * The served script, sorted and time-stamped. Every record keeps its original
 * `t_npt` string alongside the parsed ms so the screen can print the published
 * form; records whose time will not parse are dropped rather than guessed at.
 */
export function buildTimeline(payload: ReplayPayload | null | undefined): ReplayTimeline {
  if (!payload) return EMPTY_TIMELINE;

  const places: Record<string, ReplayPlace> = {};
  for (const p of payload.places ?? []) if (p && p.key) places[p.key] = p;

  const keyframes: TimelineKeyframe[] = (payload.keyframes ?? [])
    .map((k) => {
      const t = parseNpt(k.t_npt);
      if (t === null || !isNum(k.km)) return null;
      const place = places[k.place_key] ?? null;
      return {
        ...k,
        t,
        place,
        lng: place && isNum(place.lng) ? place.lng : Number.NaN,
        lat: place && isNum(place.lat) ? place.lat : Number.NaN,
      } as TimelineKeyframe;
    })
    .filter((k): k is TimelineKeyframe => k !== null)
    .sort((a, b) => a.t - b.t);

  const corridor = buildCorridor(payload, keyframes);

  // A fix whose place carries no coordinates still has a km mark: put it on the
  // corridor rather than dropping the fix.
  for (const k of keyframes) {
    if (!isNum(k.lng) || !isNum(k.lat)) {
      const pos = positionAtKm(k.km, corridor);
      k.lng = pos ? pos.lng : Number.NaN;
      k.lat = pos ? pos.lat : Number.NaN;
    }
  }

  const beats: TimelineBeat[] = (payload.beats ?? [])
    .map((b) => {
      const t = parseNpt(b.t_npt);
      if (t === null) return null;
      return { ...b, t, index: 0, place: (b.place_key && places[b.place_key]) || null } as TimelineBeat;
    })
    .filter((b): b is TimelineBeat => b !== null)
    .sort((a, b) => a.t - b.t)
    .map((b, i) => {
      b.index = i;
      return b;
    });

  const camera: TimelineCamera[] = (payload.camera ?? [])
    .map((c) => {
      const t = parseNpt(c.t_npt);
      if (t === null || !Array.isArray(c.center) || !isNum(c.center[0]) || !isNum(c.center[1])) return null;
      return {
        t,
        center: [c.center[0], c.center[1]] as [number, number],
        zoom: isNum(c.zoom) ? c.zoom : FALLBACK_CAMERA.zoom,
        pitch: isNum(c.pitch) ? c.pitch : FALLBACK_CAMERA.pitch,
        bearing: isNum(c.bearing) ? c.bearing : FALLBACK_CAMERA.bearing,
        holdS: isNum(c.hold_s) ? c.hold_s : 0,
        label: c.label ?? undefined,
      } as TimelineCamera;
    })
    .filter((c): c is TimelineCamera => c !== null)
    .sort((a, b) => a.t - b.t);

  const tollMarks: TimelineTollMark[] = (payload.toll_marks ?? [])
    .map((m) => {
      const t = parseNpt(m.t_npt);
      return t === null ? null : ({ ...m, t } as TimelineTollMark);
    })
    .filter((m): m is TimelineTollMark => m !== null)
    .sort((a, b) => a.t - b.t);

  // The declared window wins; where it is absent the record's own extremes stand in.
  const stamps = [
    ...keyframes.map((k) => k.t),
    ...beats.map((b) => b.t),
    ...camera.map((c) => c.t),
    ...tollMarks.map((m) => m.t),
  ];
  const declaredT0 = parseNpt(payload.t0_npt);
  const declaredEnd = parseNpt(payload.t_end_npt);
  const t0 = declaredT0 ?? (stamps.length ? Math.min(...stamps) : 0);
  const tEndRaw = declaredEnd ?? (stamps.length ? Math.max(...stamps) : 0);
  const tEnd = Math.max(t0, tEndRaw);

  const kms = corridor.map((c) => c.km);
  const minKm = kms.length ? Math.min(...kms) : 0;
  const maxKm = kms.length ? Math.max(...kms) : 0;

  return {
    eventKey: payload.event_key ?? '',
    title: payload.title ?? '',
    t0,
    tEnd,
    durationMs: tEnd - t0,
    t0Npt: payload.t0_npt ?? '',
    tEndNpt: payload.t_end_npt ?? '',
    keyframes,
    beats,
    camera,
    tollMarks,
    corridor,
    places,
    minKm,
    maxKm,
    sources: payload.sources ?? [],
  };
}

// ------------------------------------------------------------------ front

export interface FrontFix {
  km: number;
  confidence: ReplayConfidence;
  /** The two published fixes this position was interpolated between, or null. */
  between: [string, string] | null;
}

const kfLabel = (k: TimelineKeyframe): string => k.place?.name ?? k.place_key ?? '';

/**
 * Where the front is at t, in km downstream.
 *
 * Before the first fix the front sits at the origin the record publishes. After
 * the last fix it HOLDS there and is downgraded to `derived`: the record stops
 * stating positions, and a position nobody published for that hour must not
 * keep wearing the word PUBLISHED just because an earlier one did. Between two
 * fixes the position is LINEAR IN KM OVER TIME, is labelled `estimated`, and
 * carries the two places it lies between. Only a clock sitting exactly on a fix
 * inherits that fix's own confidence.
 */
export function frontKmAt(timeline: ReplayTimeline, t: number): FrontFix {
  const kfs = timeline.keyframes;
  if (!kfs.length) return { km: timeline.minKm, confidence: 'estimated', between: null };

  const first = kfs[0];
  if (t <= first.t) return { km: first.km, confidence: first.confidence, between: null };

  const last = kfs[kfs.length - 1];
  if (t === last.t) return { km: last.km, confidence: last.confidence, between: null };
  if (t > last.t) return { km: last.km, confidence: 'derived', between: null };

  const i = lastIndexAtOrBefore(kfs, t);
  const a = kfs[i];
  if (t === a.t) return { km: a.km, confidence: a.confidence, between: null };

  const b = kfs[i + 1];
  const span = b.t - a.t;
  const f = span > 0 ? (t - a.t) / span : 0;
  return { km: lerp(a.km, b.km, f), confidence: 'estimated', between: [kfLabel(a), kfLabel(b)] };
}

/**
 * A km mark placed on the corridor polyline, linear along each segment.
 * Off the ends it clamps: the corridor is the whole extent the record draws.
 */
export function positionAtKm(km: number, corridor: CorridorAnchor[]): { lng: number; lat: number } | null {
  if (!corridor.length || !isNum(km)) return null;
  const first = corridor[0];
  if (km <= first.km) return { lng: first.lng, lat: first.lat };
  const last = corridor[corridor.length - 1];
  if (km >= last.km) return { lng: last.lng, lat: last.lat };
  for (let i = 0; i < corridor.length - 1; i += 1) {
    const a = corridor[i];
    const b = corridor[i + 1];
    if (km >= a.km && km <= b.km) {
      const span = b.km - a.km;
      const f = span > 0 ? (km - a.km) / span : 0;
      return { lng: lerp(a.lng, b.lng, f), lat: lerp(a.lat, b.lat, f) };
    }
  }
  return { lng: last.lng, lat: last.lat };
}

/** The corridor anchor nearest a km mark — what to call the front's position. */
export function frontPlaceName(timeline: ReplayTimeline, km: number): string {
  let best: CorridorAnchor | null = null;
  let bestD = Number.POSITIVE_INFINITY;
  for (const a of timeline.corridor) {
    // The channel is densified to 100 m vertices; only the named anchors are
    // places a reader can be told about.
    if (!a.name) continue;
    const d = Math.abs(a.km - km);
    if (d < bestD) {
      bestD = d;
      best = a;
    }
  }
  return best ? best.name : '';
}

/** The full front position at t: km, coordinates, and how it was arrived at. */
export function frontAt(timeline: ReplayTimeline, t: number): { km: number; front: FrontPosition } {
  const fix = frontKmAt(timeline, t);
  const pos = positionAtKm(fix.km, timeline.corridor);
  const fallback = timeline.keyframes.find((k) => isNum(k.lng) && isNum(k.lat));
  return {
    km: fix.km,
    front: {
      lng: pos ? pos.lng : fallback ? fallback.lng : 0,
      lat: pos ? pos.lat : fallback ? fallback.lat : 0,
      confidence: fix.confidence,
      between: fix.between,
    },
  };
}

// ------------------------------------------------------------------ camera

/**
 * The director's cut at t.
 *
 * `hold_s` is REAL seconds of playback — a shot the director wants held for six
 * seconds should hold for six seconds whether the desk is running at 5 min/s or
 * 6 h/s. `holdMsPerRealSecond` converts: pass `speed * 1000` (event ms per real
 * second) and the hold occupies the right slice of the segment at any speed.
 * A hold never eats more than MAX_HOLD_FRACTION of a segment.
 */
export function cameraAt(
  timeline: ReplayTimeline,
  t: number,
  holdMsPerRealSecond = 1000,
): ReplayCameraView {
  const cams = timeline.camera;
  if (!cams.length) {
    const { front } = frontAt(timeline, t);
    return { center: [front.lng, front.lat], ...FALLBACK_CAMERA };
  }
  const first = cams[0];
  if (t <= first.t) return camView(first);
  const last = cams[cams.length - 1];
  if (t >= last.t) return camView(last);

  const i = lastIndexAtOrBefore(cams, t);
  const a = cams[i];
  const b = cams[i + 1];
  const span = b.t - a.t;
  if (span <= 0) return camView(a);

  const holdMs = Math.min(Math.max(a.holdS, 0) * holdMsPerRealSecond, span * MAX_HOLD_FRACTION);
  const elapsed = t - a.t;
  if (elapsed <= holdMs) return camView(a);

  const f = easeInOutCubic(clamp((elapsed - holdMs) / (span - holdMs), 0, 1));
  return {
    center: [lerp(a.center[0], b.center[0], f), lerp(a.center[1], b.center[1], f)],
    zoom: lerp(a.zoom, b.zoom, f),
    pitch: lerp(a.pitch, b.pitch, f),
    bearing: lerpAngle(a.bearing, b.bearing, f),
    // The shot is named by whichever end of the move the camera is closer to.
    label: f < 0.5 ? a.label : b.label,
  };
}

const camView = (c: TimelineCamera): ReplayCameraView => ({
  center: [c.center[0], c.center[1]],
  zoom: c.zoom,
  pitch: c.pitch,
  bearing: c.bearing,
  label: c.label,
});

// ------------------------------------------------------------------ beats, toll

/** Every beat that has happened at t, in order. */
export function beatsUpTo(timeline: ReplayTimeline, t: number): TimelineBeat[] {
  const i = lastIndexAtOrBefore(timeline.beats, t);
  return i < 0 ? [] : timeline.beats.slice(0, i + 1);
}

/** Index of the beat currently on the card, or -1 before the first. */
export function activeBeatIndexAt(timeline: ReplayTimeline, t: number): number {
  return lastIndexAtOrBefore(timeline.beats, t);
}

/**
 * The toll as last PUBLISHED at or before t. It steps at bulletins and never
 * slides between them — there is no such thing as a partial death toll.
 */
export function tollAt(timeline: ReplayTimeline, t: number): TimelineTollMark | null {
  const i = lastIndexAtOrBefore(timeline.tollMarks, t);
  return i < 0 ? null : timeline.tollMarks[i];
}

// ------------------------------------------------------------------ speeds

export interface SpeedPreset {
  /** Event seconds per real second. */
  value: number;
  label: string;
}

/** 5 min/s, 15 min/s, 1 h/s, 6 h/s. */
export const SPEED_PRESETS: SpeedPreset[] = [
  { value: 300, label: '5M/S' },
  { value: 900, label: '15M/S' },
  { value: 3600, label: '1H/S' },
  { value: 21600, label: '6H/S' },
];

export const DEFAULT_SPEED = SPEED_PRESETS[0].value;

// ------------------------------------------------------------------ the hook

export interface UseReplayClockOptions {
  timeline: ReplayTimeline;
  /** The director's cut; when present the clock opens in film mode. */
  film?: Film | null;
  mode?: ReplayMode;
  /** Initial event-seconds per real second (manual mode). */
  speed?: number;
  /** Initial play state. The desk opens PAUSED; nothing animates unasked. */
  playing?: boolean;
}

/**
 * The clock. requestAnimationFrame advances event time by
 * `real ms × speed`, stops dead at tEnd, and starts paused.
 */
export function useReplayClock({
  timeline,
  film = null,
  mode: initialMode,
  speed: initialSpeed = DEFAULT_SPEED,
  playing: initialPlaying = false,
}: UseReplayClockOptions): ReplayClock {
  const [t, setTState] = useState<number>(timeline.t0);
  const [playing, setPlayingState] = useState<boolean>(initialPlaying);
  const [speed, setSpeed] = useState<number>(initialSpeed);
  const [mode, setModeState] = useState<ReplayMode>(initialMode ?? (film ? 'film' : 'manual'));
  const [filmR, setFilmRState] = useState<number>(0);

  const tRef = useRef<number>(timeline.t0);
  const speedRef = useRef<number>(initialSpeed);
  speedRef.current = speed;
  const modeRef = useRef<ReplayMode>(mode);
  modeRef.current = film ? mode : 'manual';
  const filmRef = useRef<Film | null>(film);
  filmRef.current = film;
  // The payload lands after the first render, so the film usually arrives
  // late. Until the reader picks a mode by hand, a film that appears takes it.
  const userChoseModeRef = useRef<boolean>(false);
  useEffect(() => {
    if (film && !userChoseModeRef.current) {
      modeRef.current = 'film';
      setModeState('film');
    }
  }, [film]);
  const filmRRef = useRef<number>(0);
  const headingRef = useRef<number | null>(null);

  const { t0, tEnd } = timeline;

  const setT = useCallback(
    (next: number) => {
      const v = clamp(Number.isFinite(next) ? next : t0, t0, tEnd);
      tRef.current = v;
      setTState(v);
      const f = filmRef.current;
      if (f) {
        const r = realFromT(f, v);
        filmRRef.current = r;
        setFilmRState(r);
      }
    },
    [t0, tEnd],
  );

  const setMode = useCallback((next: ReplayMode) => {
    userChoseModeRef.current = true;
    const f = filmRef.current;
    const m: ReplayMode = f ? next : 'manual';
    modeRef.current = m;
    setModeState(m);
    if (m === 'film' && f) {
      const r = realFromT(f, tRef.current);
      filmRRef.current = r;
      setFilmRState(r);
    }
  }, []);

  const jumpToScene = useCallback((index: number) => {
    const f = filmRef.current;
    if (!f) return;
    const sc = f.scenes[clamp(Math.round(index), 0, f.scenes.length - 1)];
    filmRRef.current = sc.realStart;
    setFilmRState(sc.realStart);
    tRef.current = sc.tFrom;
    setTState(sc.tFrom);
    if (modeRef.current !== 'film') {
      modeRef.current = 'film';
      setModeState('film');
    }
  }, []);

  // A new payload rewinds the desk rather than leaving the clock in the old
  // window. The first render is not a change, so an initial `playing` stands.
  const windowRef = useRef<string>(`${t0}/${tEnd}`);
  useEffect(() => {
    const key = `${t0}/${tEnd}`;
    if (windowRef.current === key) return;
    windowRef.current = key;
    tRef.current = t0;
    setTState(t0);
    filmRRef.current = 0;
    setFilmRState(0);
    setPlayingState(false);
  }, [t0, tEnd]);

  const atEnd = mode === 'film' && film ? filmR >= film.totalS : tEnd > t0 && t >= tEnd;

  const setPlaying = useCallback(
    (next: boolean) => {
      const f = filmRef.current;
      if (next && modeRef.current === 'film' && f) {
        if (filmRRef.current >= f.totalS) {
          filmRRef.current = 0;
          setFilmRState(0);
          tRef.current = t0;
          setTState(t0);
        }
        setPlayingState(true);
        return;
      }
      if (next && tEnd > t0 && tRef.current >= tEnd) {
        tRef.current = t0;
        setTState(t0);
      }
      setPlayingState(next && tEnd > t0);
    },
    [t0, tEnd],
  );

  const toggle = useCallback(() => setPlaying(!playing), [playing, setPlaying]);

  const restart = useCallback(() => {
    tRef.current = t0;
    setTState(t0);
    filmRRef.current = 0;
    setFilmRState(0);
  }, [t0]);

  useEffect(() => {
    if (!playing || tEnd <= t0) return undefined;
    let raf = 0;
    let last = performance.now();
    const step = (now: number) => {
      const dt = Math.min(now - last, MAX_FRAME_MS);
      last = now;
      const f = filmRef.current;
      if (modeRef.current === 'film' && f) {
        // Film mode: the clock is REAL time; event time is whatever the
        // current scene maps it to, holds included.
        const r = Math.min(filmRRef.current + dt / 1000, f.totalS);
        filmRRef.current = r;
        setFilmRState(r);
        const st = filmStateAt(f, r);
        tRef.current = st.t;
        setTState(st.t);
        if (r >= f.totalS) {
          setPlayingState(false);
          return;
        }
        raf = requestAnimationFrame(step);
        return;
      }
      const next = tRef.current + dt * speedRef.current;
      if (next >= tEnd) {
        tRef.current = tEnd;
        setTState(tEnd);
        setPlayingState(false);
        return;
      }
      tRef.current = next;
      setTState(next);
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [playing, t0, tEnd]);

  const seekToBeat = useCallback(
    (index: number) => {
      const beats = timeline.beats;
      if (!beats.length) return;
      const i = clamp(Math.round(index), 0, beats.length - 1);
      setT(beats[i].t);
    },
    [timeline, setT],
  );

  const stepBeat = useCallback(
    (delta: number) => {
      const beats = timeline.beats;
      if (!beats.length) return;
      const here = lastIndexAtOrBefore(beats, tRef.current);
      let next: number;
      if (delta > 0) {
        next = here + 1;
        if (next > beats.length - 1) return;
      } else {
        // Stepping back off a beat you are exactly on goes to the previous one;
        // stepping back mid-way rewinds to the beat you are inside.
        next = here < 0 ? 0 : beats[here].t === tRef.current ? here - 1 : here;
        if (next < 0) return;
      }
      setPlayingState(false);
      setT(beats[next].t);
    },
    [timeline, setT],
  );

  const { km: frontKm, front } = useMemo(() => frontAt(timeline, t), [timeline, t]);
  const filmState = useMemo<FilmState | null>(() => {
    if (!film) return null;
    if (mode === 'film') return filmStateAt(film, filmR);
    const sc = sceneAtEventTime(film, t);
    return { scene: sc, phase: t >= sc.tTo ? 'hold' : 'run', t, progress: sc.tTo > sc.tFrom ? clamp((t - sc.tFrom) / (sc.tTo - sc.tFrom), 0, 1) : 1, holdRemainingS: 0, atEnd: false };
  }, [film, mode, filmR, t]);
  const directorCamera = useMemo(() => cameraAt(timeline, t, speed * 1000), [timeline, t, speed]);
  const camera = useMemo<ReplayCameraView>(() => {
    if (mode !== 'film' || !filmState) return directorCamera;
    const sc = filmState.scene;
    const holdCam = filmState.phase === 'hold' ? sc.hold_camera ?? sc.camera : null;
    if (holdCam) return { center: [holdCam.center[0], holdCam.center[1]], zoom: holdCam.zoom, pitch: holdCam.pitch, bearing: holdCam.bearing, label: sc.title };
    if (sc.follow) {
      // The camera rides the front and looks down the valley. The heading is
      // smoothed so a bend in the channel turns the shot, not a vertex.
      const h = headingAtKm(timeline, frontKm);
      if (h !== null) {
        const prev = headingRef.current;
        headingRef.current = prev === null ? h : lerpAngle(prev, h, 0.08);
      }
      const bearing = ((headingRef.current ?? 0) + (sc.follow.bearingOffset ?? 0) + 360) % 360;
      const lead = sc.follow.lead_km ?? 1.5;
      const ahead = positionAtKm(frontKm + lead, timeline.corridor);
      const center: [number, number] = ahead ? [ahead.lng, ahead.lat] : [front.lng, front.lat];
      return { center, zoom: sc.follow.zoom, pitch: sc.follow.pitch, bearing, label: sc.title };
    }
    if (sc.camera) return { center: [sc.camera.center[0], sc.camera.center[1]], zoom: sc.camera.zoom, pitch: sc.camera.pitch, bearing: sc.camera.bearing, label: sc.title };
    return directorCamera;
  }, [mode, filmState, directorCamera, timeline, frontKm, front.lng, front.lat]);
  const activeBeatIndex = useMemo(() => activeBeatIndexAt(timeline, t), [timeline, t]);
  const tollNow = useMemo(() => tollAt(timeline, t), [timeline, t]);
  const iso = useMemo(() => nptIso(t), [t]);

  return {
    timeline,
    filmScript: film,
    mode: film ? mode : 'manual',
    film: filmState,
    filmR,
    setMode,
    jumpToScene,
    t,
    setT,
    playing,
    setPlaying,
    toggle,
    speed,
    setSpeed,
    stepBeat,
    seekToBeat,
    restart,
    atEnd,
    frontKm,
    front,
    camera,
    activeBeatIndex,
    activeBeat: activeBeatIndex >= 0 ? timeline.beats[activeBeatIndex] : null,
    tollNow,
    visibleBeatCount: activeBeatIndex + 1,
    nptIso: iso,
  };
}
