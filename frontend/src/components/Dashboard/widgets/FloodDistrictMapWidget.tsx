/**
 * Where the water put the bodies, and when.
 *
 * The reason this map exists is an inversion no table makes obvious: the
 * recovered dead cluster ~160 km DOWNSTREAM in Chitwan, while the missing
 * cluster at the source in Rasuwa where the debris is deepest. So recovered
 * counts carry the choropleth — deepest red far from the collapse, faintest at
 * it — and missing is amber TEXT rather than a second ramp. NDRRMA breaks
 * missing out for only three of the nine districts; a second colour scale would
 * imply a completeness the bulletin does not have, and would fight the first.
 *
 * Two things ride on that base map.
 *
 * Imagery is pinned at the two coordinates the licensed files actually belong
 * to — the border post and the collapse origin — rather than shown as a strip
 * or a gallery. Seven files collapse to two points, so the marginal load on the
 * canvas is two chips, less ink than one district label, and each picture opens
 * as evidence for the place it is pinned to.
 *
 * The damage pairs are the second thing riding on it, and the reason the map
 * is now the desk's primary surface. Six curated sites along the corridor carry
 * a same-frame pre/post satellite pair each, and each opens from a chip pinned
 * at the coordinate the frames were rendered over — geography with the imagery
 * attached to the position, rather than a separate comparator below the map
 * that a reader has to re-locate by name. Blue-bordered chip = orbital pair,
 * grey-bordered chip = ground photograph; the two sets stay separate data
 * because one is a static curated render list and the other is replay-gated
 * Commons media that mutates as files fail, and merging them would re-derive in
 * React a join each endpoint already owns.
 *
 * At the province frame all eight of those points fall inside ~180 px of each
 * other, which is a pile rather than a map, and per-point pixel offsets cannot
 * fix it because the points are genuinely co-located at that scale. So marks
 * that land within a chip's width of each other collapse into one aggregate
 * that opens by zooming to the frame where they separate — the same greedy
 * pixel-space de-confliction the district labels already use. The grouping is
 * presentation only: it holds references into the two sets and never a join
 * between them, and no site is ever more than one click deeper than before.
 *
 * Nothing on this map opens a floating tooltip. Every hover feeds ONE fixed
 * readout panel in the bottom-left corner, so the canvas is never occluded and
 * two readouts are unrepresentable rather than merely defended against — see
 * the Readout union below.
 *
 * That layer is the one deliberate amendment to the doctrine below: it is ON at
 * load. It is the reason this widget grew to full width, and a toggle over a
 * map's own reason to exist would be a cut corner.
 *
 * Replay steps the map through 26 Aug -> 1 Sept. It interpolates nothing. The
 * national toll steps between the five dated bulletins; the district fills step
 * between the two dates NDRRMA published a district breakdown at all, and the
 * transport bar names which of the two is on screen; a chronology beat whose
 * source gave only a date becomes true when that Nepal-time date closes and is
 * flagged TIME NOT PUBLISHED rather than drawn at an invented hour. The one
 * animated thing on the canvas — the 26 August surge front — carries a
 * permanent label saying its kilometres are real and its arrival times are not.
 *
 * On load the widget is the live map exactly as before: paused, pinned to the
 * latest bulletin. An unrequested animation on a rescue desk is noise.
 *
 * Three more layers ride above that base map and all three are off on load, for
 * the same reason the replay is paused: opening the widget must show the map
 * the desk has always shown.
 *
 * The Vantor scene footprints draw the one claim an outline can make exactly —
 * which ground each 30–50 cm strip covered — and no pixels at all.
 *
 * The pixels are the second layer, and they became drawable only because Esri's
 * Disaster Response Program serves the same sixteen scenes through an
 * ImageServer that renders an arbitrary bbox on demand. A browse thumbnail
 * fills an axis-aligned frame while its scene sits rotated inside the bbox, so
 * laying one over the basemap would assert a registration we do not have; an
 * exportImage frame requested in the map's own projection is registered by
 * construction. It is gated to zoom 14 and above, where a screen pixel is
 * finally smaller than a building, and while it is on the choropleth keeps its
 * outlines but loses its fill — a translucent red wash over 30 cm evidence is a
 * false colour cast on the one thing on this canvas a reader may read literally.
 *
 * The DHM gauge photographs are the third. They are DHM's own pictures of its
 * station sites, held in this database since the BIPAD ingest and never once
 * shown, and they are UNDATED: a pin opens a photograph of a place, never an
 * image of this flood, and the frame that opens says so. They are drawn as
 * neutral grey squares rather than in a status colour, because a photograph is
 * not an alert.
 *
 * Drawn here instead of through FloodMap: that component owns a marker and
 * tile-overlay lifecycle for gauges and satellite imagery, and belongs to the
 * satellite widgets. A choropleth wants L.geoJSON, permanent centroid labels
 * and its own fit; merging the two lifecycles makes both harder to reason about.
 *
 * Figures are not joined here. /flood/districts/geo already resolves NDRRMA's
 * district names against the Survey Department geojson (two of them differ:
 * Nawalparasi East/Nawalpur, Makwanpur/Makawanpur) and reads the counts live
 * from the same record /flood/official serves, so re-deriving the join in React
 * would only reintroduce the name bug the endpoint exists to fix.
 */
import { memo, useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Camera, Crosshair, Layers, Locate, Map as MapIcon, Satellite } from 'lucide-react';
import type { FeatureCollection, Geometry } from 'geojson';

import { useOfficialSituation } from '../../../api/hooks/useFlood';
import { FloodImageryBanner, type ImageryCaption, type ImageryStatus } from '../../flood/FloodImageryBanner';
import { FloodDamageSiteViewer } from '../../flood/FloodDamageSiteViewer';
import { FloodMediaViewer } from '../../flood/FloodMediaViewer';
import { FloodReplayBar } from '../../flood/FloodReplayBar';
import { FloodStationPhotoViewer } from '../../flood/FloodStationPhotoViewer';
import {
  coverFrame,
  exportImageUrl,
  useDrpCatalog,
  DRP_MAX_PIXELS,
  DRP_MIN_ZOOM,
  type DrpPhase,
  type DrpRaster,
  type LatLngBox,
} from '../../flood/drpImagery';
import { useDamageSites, type DamageSite } from '../../flood/damageSites';
import {
  useFloodDistrictGeo,
  type CorridorWaypoint,
  type DistrictFeature,
  type DistrictProperties,
} from '../../flood/districtGeo';
import { isViewable, useFloodMedia, type FloodMediaItem } from '../../flood/floodMedia';
import { useStationPhotos, type StationPhoto } from '../../flood/stationPhotos';
import { siteChip, useFloodSites, type ResponseSite } from '../../flood/floodSites';
import {
  dayCloseMs,
  useFloodChronology,
  useFloodReplay,
  type DistrictSnapshot,
} from '../../flood/floodReplay';
import { HAIRLINE, LABEL_XS, MS, Note, SourceLine, dtgDay } from '../../flood/milspec';
import {
  baselineGap,
  footprintRing,
  formatSceneDay,
  useVantorScenes,
  type VantorItem,
} from '../../flood/vantorScenes';
import { Widget } from '../Widget';
import { WidgetEmpty, WidgetError, WidgetSkeleton } from './shared';

/** What a district looks like at the moment currently on screen. */
interface DistrictView {
  name: string;
  province: string | null;
  position: string;
  centroid: { lat: number; lng: number } | null;
  recovered: number | null;
  missing: number | null;
  /** false = no authority had broken this district out yet at this moment. */
  published: boolean;
  authority: string | null;
  asOf: string | null;
}

// Keyless, same basemap the rest of the flood desk uses: CARTO now stamps every
// tile "API KEY REQUIRED" and Esri's dark canvas is still open with attribution.
const BASEMAP_URL =
  'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}';
const BASEMAP_ATTRIBUTION = 'Esri, HERE, Garmin, © OpenStreetMap contributors';

// Leaflet writes vector styles as SVG presentation attributes, which do not
// resolve var(). These are the literal values of the theme tokens named beside
// them and must be changed together with dashboard.css. Everything rendered as
// HTML below uses the variables directly.
const CRITICAL = '#ef4444'; // --status-critical
const HIGH = '#f97316'; // --status-high
const INFO = '#3b82f6'; // --status-info
const BORDER_DEFAULT = '#3f3f46'; // --border-default
const TEXT_PRIMARY = '#fafafa'; // --text-primary

/**
 * Fixed breaks, not quantiles: the map must not re-colour itself every time
 * NDRRMA revises a district, or a reader comparing two days would see a shift
 * that is an artefact of the scale rather than of the recovery effort. The same
 * fixed scale is what makes the replay's two snapshots comparable at all.
 */
const FILL_STEPS: { min: number; alpha: number; label: string }[] = [
  { min: 300, alpha: 0.84, label: '300+' },
  { min: 200, alpha: 0.66, label: '200–299' },
  { min: 100, alpha: 0.48, label: '100–199' },
  { min: 50, alpha: 0.3, label: '50–99' },
  { min: 1, alpha: 0.15, label: '1–49' },
];

const fillAlpha = (recovered: number | null): number =>
  recovered == null ? 0 : FILL_STEPS.find((s) => recovered >= s.min)?.alpha ?? 0;

// Segment indices along the corridor, spaced so flow direction reads at the
// default frame without animating anything.
const CHEVRON_SEGMENTS = [1, 3, 5];

const HOME_PADDING: L.PointExpression = [12, 12];

const CHIP_W = 46;
const CHIP_H = 14;
const DMG_CHIP_W = 52;

// Every other collision on this map is now handled by zoom — a mark that
// overlaps another at this frame is grouped, and separates when the reader goes
// in. These two pairs are the exception the grouping cannot reach: each media
// anchor sits on EXACTLY the coordinate of a damage site (the border post at
// km 0, and the collapse origin), so no zoom ever pulls them apart. They are
// drawn side by side off the shared point instead — media west, site east — and
// exempted from grouping below. Every other offset in this table was
// compensation for the default-frame pile and is gone with it.
const CHIP_OFFSETS: Record<string, L.PointTuple> = {
  gyirong_port: [CHIP_W + 8, CHIP_H / 2],
  collapse_origin: [CHIP_W + 8, CHIP_H / 2],
};
const DEFAULT_CHIP_OFFSET: L.PointTuple = [CHIP_W / 2, CHIP_H / 2];
const DMG_CHIP_OFFSETS: Record<string, L.PointTuple> = {
  rasuwagadhi: [-8, CHIP_H / 2],
  langtang_origin: [-8, CHIP_H / 2],
};
const DEFAULT_DMG_CHIP_OFFSET: L.PointTuple = [DMG_CHIP_W / 2, CHIP_H / 2];

/** The two same-point pairs above, as a symmetric lookup. A group that is
 *  exactly one of these is drawn as its two offset chips rather than as an
 *  aggregate: an aggregate whose members can never separate by zoom would be a
 *  chip that swallows a site permanently. */
const CHIP_PAIRS: Record<string, string> = {
  'media:gyirong_port': 'site:rasuwagadhi',
  'site:rasuwagadhi': 'media:gyirong_port',
  'media:collapse_origin': 'site:langtang_origin',
  'site:langtang_origin': 'media:collapse_origin',
};

/** Grouping radius in world pixels — a little under two chip widths, which is
 *  the distance at which two chips stop overlapping each other's text. */
const CLUSTER_R = 48;
const CLUSTER_W = 84;
/** Where an aggregate stops trying to separate. Past this the corridor is a
 *  single village and the marks are already apart; a deeper jump would throw
 *  away the reader's context to gain nothing. */
const MAX_EXPANSION_ZOOM = 12;

const SWEEP_LABEL = 'FRONT ON THE OSM CHANNEL · TIMES INTERPOLATED BETWEEN PUBLISHED FIXES';
/** Chevrons along a dense channel: one every this many km, pointing downstream. */
const CHEVRON_EVERY_KM = 25;
const LOW = '#22c55e'; // --status-low
const PLACE_CLUSTER_PX = 40;

/** Its own pane so the imagery sits above the basemap and below every vector. */
const DRP_PANE = 'drpImagery';

/** What fits over a map pane. The full attribution string the API hands down
 *  is in the widget footer; this names the licensor, the server and the
 *  licence, which is what a crop of the canvas alone has to carry. */
const IMAGERY_CREDIT = '© Vantor · Esri DRP · CC BY-NC 4.0';

/** Roughly the 1.2 km site frame at a full-width pane — the border post and the
 *  debris channel in one screen, which is what the overlay exists to show. */
const SITE_ZOOM = 16;

const fmt = (n: number): string => n.toLocaleString('en-IN');

const esc = (s: string): string =>
  s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c] ?? c));

/**
 * "2026-08-26" → "26 AUG 26", read from the event record rather than typed in.
 * The DTG comes from milspec so the marker on the canvas stamps its date the
 * same way every other line on the desk does.
 */
const formatEventDate = (iso: string | null | undefined): string | null =>
  iso ? dtgDay(iso) : null;

/**
 * globals.css also forces pointer-events:auto onto every .leaflet-marker-icon,
 * so a passive label would swallow drags and block the district hover beneath
 * it; Leaflet's own interactive:false cannot beat an !important rule. The
 * imagery chips are the one marker on this map that wants the click, so they
 * are deliberately left alone.
 */
const makePassive = (marker: L.Marker): void => {
  marker.getElement()?.style.setProperty('pointer-events', 'none', 'important');
};

/**
 * `muteFill` is the high-resolution overlay talking. The choropleth is a
 * district-scale claim and its fill is a translucent red wash; over 30 cm
 * imagery that wash is a colour cast on evidence, and a reader cannot tell a
 * tinted roof from a red one. The outline stays either way, so the district is
 * never silently removed from the canvas — only its fill steps aside.
 */
const districtStyle = (v: DistrictView, muteFill = false): L.PathOptions => {
  if (!v.published) {
    // No bulletin had broken this district out yet. Outline in the neutral
    // border colour: amber would claim a missing count and a fill would claim
    // a recovery count of zero.
    return { color: BORDER_DEFAULT, weight: 1, dashArray: '4 3', fillOpacity: 0, fillColor: BORDER_DEFAULT };
  }
  if (v.recovered == null) {
    // Missing-only district: outlined, never filled.
    return { color: HIGH, weight: 1, dashArray: '4 3', fillOpacity: 0, fillColor: HIGH };
  }
  return {
    color: BORDER_DEFAULT,
    weight: 1,
    dashArray: undefined,
    fillColor: CRITICAL,
    fillOpacity: muteFill ? 0 : fillAlpha(v.recovered),
  };
};

const hoverStyle = (v: DistrictView, muteFill = false): L.PathOptions => ({
  ...districtStyle(v, muteFill),
  color: TEXT_PRIMARY,
  weight: 1.5,
  fillOpacity: muteFill || v.recovered == null ? 0 : fillAlpha(v.recovered) + 0.1,
});

const districtLabel = (v: DistrictView): string => `
  <div style="text-align:center;line-height:1.15;text-shadow:0 1px 3px rgba(0,0,0,.95)">
    <div style="font-family:var(--font-mono);font-size:9px;letter-spacing:.08em;text-transform:uppercase;color:var(--text-secondary)">${esc(v.name)}</div>
    ${v.recovered != null
      ? `<div style="font-family:var(--font-mono);font-variant-numeric:tabular-nums;font-size:13px;font-weight:600;color:var(--text-primary)">${fmt(v.recovered)}</div>`
      : ''}
    ${v.missing != null
      ? `<div style="font-family:var(--font-mono);font-variant-numeric:tabular-nums;font-size:10px;color:var(--status-high)">${fmt(v.missing)} MISSING</div>`
      : ''}
  </div>`;

/** The gauge-photo pin. Deliberately not a status colour: this marker says a
 *  picture exists here, and nothing at all about the river.
 *
 *  Thirty-one identical squares at the province frame are undifferentiated
 *  noise over the one thing this map is for, so below the detail zoom the pin
 *  recedes to a 5 px hairline: present, countable, and not competing. It comes
 *  back to full weight at the scale where a reader is actually working a
 *  station. Nothing about the pin's meaning changes with its size — the readout
 *  says what it is either way.
 */
const DHM_PIN = 7;
const DHM_PIN_QUIET = 5;
const DHM_DETAIL_ZOOM = 11;
const dhmPinHtml = (detail: boolean): string =>
  detail
    ? `<div style="width:${DHM_PIN}px;height:${DHM_PIN}px;background:var(--bg-elevated);
                   border:1px solid var(--text-secondary);box-shadow:0 1px 3px rgba(0,0,0,.9)"></div>`
    : `<div style="width:${DHM_PIN_QUIET}px;height:${DHM_PIN_QUIET}px;background:var(--bg-elevated);
                   border:1px solid var(--border-default);opacity:.6"></div>`;

/** The chip mechanism both marker kinds are drawn with. The border colour is
 *  the whole visual grammar: grey is ground media, and blue is the satellite
 *  colour this map already uses for the corridor, the footprints and the DRP
 *  banner — so a reader learns "blue chip = orbital" once and it holds. */
const chipHtml = (label: string, border = 'var(--text-secondary)'): string => `
  <div style="display:inline-block;font-family:var(--font-mono);font-size:8px;letter-spacing:.06em;
              padding:1px 4px;background:var(--bg-elevated);border:1px solid ${border};
              color:var(--text-primary);white-space:nowrap">${esc(label)}</div>`;

/**
 * Position along the corridor by cumulative kilometre. The kilometres are the
 * event record's own; only the mapping from time to kilometre is schematic.
 */
const pointAtKm = (run: CorridorWaypoint[], km: number): L.LatLngTuple | null => {
  if (run.length === 0) return null;
  if (km <= (run[0].km ?? 0)) return [run[0].lat, run[0].lng];
  for (let i = 1; i < run.length; i += 1) {
    const a = run[i - 1];
    const b = run[i];
    const ak = a.km ?? 0;
    const bk = b.km ?? 0;
    if (km <= bk) {
      const span = bk - ak;
      const f = span > 0 ? (km - ak) / span : 0;
      return [a.lat + (b.lat - a.lat) * f, a.lng + (b.lng - a.lng) * f];
    }
  }
  const last = run[run.length - 1];
  return [last.lat, last.lng];
};

interface MediaAnchor {
  anchor: string;
  lat: number;
  lng: number;
  label: string;
  /** Files with bytes we can frame here, in the order the API ranked them. */
  viewable: FloodMediaItem[];
  /** Files that are only ever a link — the ECDM map sheet. */
  links: FloodMediaItem[];
}

/**
 * THE READOUT. One slot, one panel, and therefore never two.
 *
 * Five separate sources used to bind a Leaflet tooltip here — district paths,
 * corridor waypoints, media chips, damage chips, gauge pins — and Leaflet fires
 * mouseout per layer, so a cursor crossing several small polygons opened three
 * cards before any of them reported leaving. Three successive fixes (sticky
 * off, a per-path close-previous guard, a map-level tooltipopen guard) each made
 * it rarer without making it impossible, because floating cards over a dense
 * cluster is the wrong mechanism, not a buggy one.
 *
 * An operational map puts the hover readout in a known corner instead, where it
 * cannot occlude the thing being read and where a second readout has nowhere to
 * go. That is what this union is: hover writes the slot, and a stale mouseout
 * can only clear the slot it still owns. A fast sweep therefore overwrites; it
 * cannot stack, and it cannot blank the panel someone is reading.
 *
 * It is also the whole touch story. On tap Leaflet synthesises mouseover before
 * click, and every click handler writes the slot as well, so a device with no
 * hover still gets the readout for the last thing it touched.
 */
type Readout =
  | { kind: 'district'; name: string }
  | { kind: 'waypoint'; wp: CorridorWaypoint }
  | { kind: 'origin' }
  | { kind: 'site'; key: string }
  | { kind: 'place'; key: string }
  | { kind: 'media'; anchor: string }
  | { kind: 'cluster'; members: MarkMember[] }
  | { kind: 'gauge'; id: number }
  | { kind: 'footprint'; item: VantorItem };

/** Identity, not equality: a mouseout builds a fresh object for the same thing
 *  it entered, so the clear guard has to compare what the readout is ABOUT. */
const readoutKey = (r: Readout): string => {
  switch (r.kind) {
    case 'district': return `district:${r.name}`;
    case 'waypoint': return `waypoint:${r.wp.name}:${r.wp.km ?? ''}`;
    case 'origin': return 'origin';
    case 'site': return `site:${r.key}`;
    case 'place': return `place:${r.key}`;
    case 'media': return `media:${r.anchor}`;
    case 'cluster': return `cluster:${r.members.map((m) => `${m.kind}/${m.key}`).join(',')}`;
    case 'gauge': return `gauge:${r.id}`;
    case 'footprint': return `footprint:${r.item.id}`;
  }
};

interface MarkMember {
  kind: 'site' | 'media';
  key: string;
}

/** A mark before it is drawn. Carries its source record so the placer can build
 *  the chip without re-looking-it-up, and so a group never has to join. */
type MarkPoint =
  | { kind: 'site'; key: string; lat: number; lng: number; site: DamageSite }
  | { kind: 'media'; key: string; lat: number; lng: number; anchor: MediaAnchor };

/** What actually reached the canvas, for the label placer to route around. */
interface RenderedMark {
  lat: number;
  lng: number;
  offset: L.PointTuple;
  w: number;
}

const markId = (m: { kind: string; key: string }): string => `${m.kind}:${m.key}`;

/**
 * Seed order is the whole determinism of the grouping: origin first, then the
 * corridor downstream, then the media anchors. Reading the map top-down means a
 * group is always seeded by the most upstream thing in it, so the same frame
 * produces the same marks every time it is drawn.
 */
const markPoints = (sites: DamageSite[], anchors: MediaAnchor[]): MarkPoint[] => {
  const ordered = [...sites].sort((a, b) => {
    if (a.km_mark === null) return b.km_mark === null ? 0 : -1;
    if (b.km_mark === null) return 1;
    return a.km_mark - b.km_mark;
  });
  return [
    ...ordered.map((site): MarkPoint => ({ kind: 'site', key: site.key, lat: site.lat, lng: site.lng, site })),
    ...anchors.map((anchor): MarkPoint => ({
      kind: 'media', key: anchor.anchor, lat: anchor.lat, lng: anchor.lng, anchor,
    })),
  ];
};

/**
 * Greedy, in WORLD pixels at a stated zoom rather than container pixels: what
 * overlaps depends on scale alone, so panning must not re-group the map under
 * the reader's cursor. Same shape as the district label placer above — first
 * claim wins, everything inside the radius joins it.
 */
const groupMarks = (map: L.Map, pts: MarkPoint[], zoom: number): MarkPoint[][] => {
  const proj = pts.map((p) => map.project([p.lat, p.lng], zoom));
  const claimed = pts.map(() => false);
  const groups: MarkPoint[][] = [];
  pts.forEach((p, i) => {
    if (claimed[i]) return;
    claimed[i] = true;
    const group = [p];
    pts.forEach((q, j) => {
      if (j <= i || claimed[j]) return;
      if (proj[i].distanceTo(proj[j]) < CLUSTER_R) {
        claimed[j] = true;
        group.push(q);
      }
    });
    groups.push(group);
  });
  return groups;
};

/** The two chips that share a coordinate exactly. Drawn side by side, never
 *  aggregated — see CHIP_PAIRS. */
const isOffsetPair = (group: MarkPoint[]): boolean =>
  group.length === 2 && CHIP_PAIRS[markId(group[0])] === markId(group[1]);

/**
 * The frame this group stops being a pile at: the first zoom past the current
 * one where re-running the grouping splits it. Computed rather than tabulated,
 * so it stays true when the replay adds or removes a member.
 */
const expansionZoom = (map: L.Map, group: MarkPoint[], from: number): number => {
  for (let z = Math.floor(from) + 1; z <= MAX_EXPANSION_ZOOM; z += 1) {
    if (groupMarks(map, group, z).length >= 2) return z;
  }
  return MAX_EXPANSION_ZOOM;
};

// The panel's type scale. Labels 10px uppercase, figures mono and tabular,
// everything secondary 9px mono — the desk's own rules, stated once.
const RO_LABEL: CSSProperties = {
  fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '.08em',
  textTransform: 'uppercase', color: 'var(--text-muted)', lineHeight: 1.4,
};
const RO_TITLE: CSSProperties = {
  fontSize: 11, fontWeight: 600, letterSpacing: '.04em', textTransform: 'uppercase',
  color: 'var(--text-primary)', lineHeight: 1.3,
};
const RO_FIG: CSSProperties = {
  fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums',
  fontSize: 13, fontWeight: 600, color: 'var(--text-primary)',
};
const RO_MONO: CSSProperties = {
  fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '.06em',
  lineHeight: 1.45, color: 'var(--text-muted)',
};
const RO_RULE: CSSProperties = {
  marginTop: 6, paddingTop: 5, borderTop: HAIRLINE,
};

const ReadoutRow = ({ label, value, tone }: { label: string; value: string; tone?: string }) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 14, alignItems: 'baseline' }}>
    <span style={RO_LABEL}>{label}</span>
    <span style={{ ...RO_FIG, color: tone ?? 'var(--text-primary)' }}>{value}</span>
  </div>
);

interface ReadoutPanelProps {
  readout: Readout | null;
  view: Map<string, DistrictView>;
  sites: DamageSite[];
  places: ResponseSite[];
  kindText: Record<string, string>;
  anchors: MediaAnchor[];
  stations: StationPhoto[];
  eventName: string | null;
  eventCause: string | null;
  eventStarted: string | null;
  /** Pixels actually drawn, not the toggle: the fill ramp explains ink. */
  imageryDrawn: boolean;
  footprintsOn: boolean;
  dhmCount: number;
}

/**
 * The panel body. At rest it IS the legend, which is why the corner never goes
 * blank and never jumps: a reader learns one place to look and it is always
 * saying something. The old four-line prose legend is gone with it — each
 * layer's full story now lives in its own hover, and the licences stay in the
 * footer where a screenshot of the whole widget keeps them.
 */
const ReadoutBody = (props: ReadoutPanelProps) => {
  const { readout } = props;

  if (readout?.kind === 'district') {
    // Read live rather than frozen at hover time, so a replay step under an
    // open readout updates the figures instead of lying about them.
    const v = props.view.get(readout.name);
    if (v) {
      const place = [v.province, v.position === 'source' ? 'at collapse source' : 'downstream']
        .filter(Boolean).join(' · ');
      const provenance = [v.authority, v.asOf].filter(Boolean).join(' · ');
      return (
        <>
          <div style={RO_TITLE}>{v.name}</div>
          <div style={{ fontSize: 9, color: 'var(--text-muted)', marginBottom: 6 }}>{place}</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            {!v.published ? (
              <div style={RO_LABEL}>No district breakdown published at this point</div>
            ) : (
              <>
                {v.recovered != null ? (
                  <ReadoutRow label="Bodies recovered" value={fmt(v.recovered)} />
                ) : (
                  <div style={RO_LABEL}>No recovery count published</div>
                )}
                {v.missing != null ? (
                  <ReadoutRow label="Missing" value={fmt(v.missing)} tone="var(--status-high)" />
                ) : (
                  // Stated, not omitted: without this a reader reasonably
                  // concludes that a deep-red district has nobody unaccounted for.
                  <div style={RO_LABEL}>Missing not broken out for this district</div>
                )}
              </>
            )}
          </div>
          {provenance && <div style={{ ...RO_MONO, ...RO_RULE }}>{provenance}</div>}
        </>
      );
    }
  }

  if (readout?.kind === 'waypoint') {
    return (
      <>
        <div style={RO_TITLE}>{readout.wp.name}</div>
        {readout.wp.km != null && (
          <div style={{ ...RO_MONO, fontVariantNumeric: 'tabular-nums', marginTop: 3 }}>
            {fmt(readout.wp.km)} KM DOWNSTREAM OF RASUWAGADHI
          </div>
        )}
      </>
    );
  }

  if (readout?.kind === 'origin' && props.eventCause) {
    return (
      <>
        <div style={RO_LABEL}>Cause{props.eventName ? ` · ${props.eventName}` : ''}</div>
        <div style={{ fontSize: 11, lineHeight: 1.5, color: 'var(--text-secondary)', marginTop: 4 }}>
          {props.eventCause}
        </div>
        {props.eventStarted && <div style={{ ...RO_MONO, marginTop: 5 }}>{props.eventStarted}</div>}
      </>
    );
  }

  if (readout?.kind === 'site') {
    const site = props.sites.find((s) => s.key === readout.key);
    if (site) {
      return (
        <>
          <div style={RO_TITLE}>{site.name}</div>
          <div style={{ ...RO_MONO, fontVariantNumeric: 'tabular-nums', marginTop: 2 }}>
            {site.km_mark === null ? 'ORIGIN' : `KM ${site.km_mark}`}
          </div>
          {/* A site with no levels has nothing to compare, and the readout must
              not promise a pair it cannot open. Its statement is the finding. */}
          <div style={{
            fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '.06em',
            lineHeight: 1.4, color: 'var(--status-info)', marginTop: 4,
          }}>
            {site.levels.length === 0
              ? 'NO POST-EVENT PASS — STATEMENT'
              : 'SAME-FRAME PRE/POST · VANTOR CC BY-NC 4.0'}
          </div>
          {/* A tooltip beside the cursor never had to say this. A panel in a
              fixed corner does: nothing else connects it to the mark. */}
          <div style={{ ...RO_MONO, marginTop: 4 }}>CLICK TO COMPARE</div>
        </>
      );
    }
  }

  if (readout?.kind === 'place') {
    const site = props.places.find((s) => s.key === readout.key);
    if (site) {
      const chip = siteChip(site);
      const tone = chip.tone === 'critical' ? 'var(--status-critical)' : chip.tone === 'high' ? 'var(--status-high)'
        : chip.tone === 'low' ? 'var(--status-low)' : chip.tone === 'info' ? 'var(--status-info)' : 'var(--text-muted)';
      const latest = site.notes[0] ?? null;
      const figures = site.figures.slice(0, 4);
      const stills = site.photos.filter((p) => p.licence_tier === 'display').slice(0, 3);
      const leads = site.photos.filter((p) => p.licence_tier !== 'display').slice(0, 2);
      const sources = Array.from(new Set([...site.figures, ...site.notes].map((x) => x.source.split(',')[0]))).slice(0, 2);
      const conf = site.coord_confidence === 'published' ? 'FACILITY LOCATED'
        : site.coord_confidence === 'place' ? 'LOCALITY LOCATED · PLOT NOT PUBLISHED'
          : site.coord_confidence === 'municipality' ? 'MUNICIPALITY CENTRE · WARD ONLY PUBLISHED' : 'APPROXIMATE PLACEMENT';
      return (
        <>
          <div style={RO_TITLE}>{site.name}</div>
          <div style={{ ...RO_MONO, color: tone, marginTop: 2 }}>
            {chip.label}{site.district ? ` · ${site.district.toUpperCase()}` : ''}{site.teams && site.teams.length ? ` · ${site.teams.join(' + ')}` : ''}
          </div>
          <div style={{ ...RO_MONO, fontSize: 8, marginTop: 1 }}>{conf}</div>
          {figures.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2, marginTop: 5 }}>
              {figures.map((f) => (
                <ReadoutRow key={f.kind} label={f.kind.replace(/_/g, ' ')} value={fmt(f.value)} tone={f.kind === 'identified' || f.kind === 'rescued' ? 'var(--status-low)' : undefined} />
              ))}
            </div>
          )}
          {(latest || site.status_line) && (
            <div style={{ fontSize: 10, lineHeight: 1.45, color: 'var(--text-secondary)', marginTop: 5, display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
              {latest?.text ?? site.status_line}
            </div>
          )}
          {(stills.length > 0 || leads.length > 0) && (
            <div style={{ display: 'flex', gap: 4, marginTop: 6 }}>
              {stills.map((ph) => (
                <a key={ph.id} href={ph.page_url ?? ph.image_url} target="_blank" rel="noreferrer noopener" title={`${ph.title} · ${ph.credit ?? ''}`} style={{ display: 'block', width: 64, height: 44, overflow: 'hidden', border: HAIRLINE, background: 'var(--bg-elevated)' }}>
                  <img src={ph.image_url} alt={ph.title} loading="lazy" onError={(e) => { (e.currentTarget as HTMLImageElement).style.visibility = 'hidden'; }} style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
                </a>
              ))}
              {leads.map((ph) => (
                <a key={ph.id} href={ph.page_url ?? '#'} target="_blank" rel="noreferrer noopener" title={`${ph.outlet ?? 'press'} · ${ph.title}`} style={{ display: 'block', width: 44, height: 44, overflow: 'hidden', border: `1px solid var(--status-info)`, background: 'var(--bg-elevated)', position: 'relative' }}>
                  <img src={ph.image_url} alt={ph.title} loading="lazy" onError={(e) => { (e.currentTarget as HTMLImageElement).style.visibility = 'hidden'; }} style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block', opacity: 0.85 }} />
                  <span style={{ position: 'absolute', left: 0, right: 0, bottom: 0, fontFamily: 'var(--font-mono)', fontSize: 7, letterSpacing: '.04em', background: 'rgba(0,0,0,.75)', color: 'var(--status-info)', padding: '1px 2px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{(ph.outlet ?? 'PRESS').toUpperCase()}</span>
                </a>
              ))}
            </div>
          )}
          <div style={{ ...RO_MONO, ...RO_RULE }}>
            {sources.join(' · ')}{site.photos.length ? ` · ${site.photos.length} PHOTO${site.photos.length === 1 ? '' : 'S'} BY CAPTION MATCH` : ''}
          </div>
        </>
      );
    }
  }

  if (readout?.kind === 'media') {
    const anchor = props.anchors.find((a) => a.anchor === readout.anchor);
    if (anchor) {
      return (
        <>
          <div style={RO_TITLE}>
            {anchor.viewable.length} licensed file{anchor.viewable.length === 1 ? '' : 's'} · {anchor.label}
          </div>
          <div style={{ ...RO_MONO, marginTop: 4 }}>WIKIMEDIA COMMONS · CLICK TO VIEW</div>
        </>
      );
    }
  }

  if (readout?.kind === 'cluster') {
    const line = (m: MarkMember): string | null => {
      if (m.kind === 'site') {
        const site = props.sites.find((s) => s.key === m.key);
        if (!site) return null;
        const where = site.km_mark === null ? 'ORIGIN' : `KM ${site.km_mark}`;
        // NO POST stays NO POST inside the list: an aggregate must never round
        // a statement of absence up into a pair.
        return `${site.name.toUpperCase()} · ${where} · ${site.levels.length === 0 ? 'NO POST' : 'PRE|POST'}`;
      }
      const anchor = props.anchors.find((a) => a.anchor === m.key);
      if (!anchor) return null;
      return `${anchor.label.toUpperCase()} · IMG ${anchor.viewable.length}`;
    };
    const lines = readout.members.map(line).filter(Boolean) as string[];
    return (
      <>
        <div style={RO_LABEL}>{lines.length} marks at this point</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2, marginTop: 5 }}>
          {lines.map((text) => (
            <div key={text} style={{ ...RO_MONO, color: 'var(--text-secondary)' }}>{text}</div>
          ))}
        </div>
        <div style={{ ...RO_MONO, marginTop: 5 }}>CLICK TO SEPARATE</div>
      </>
    );
  }

  if (readout?.kind === 'gauge') {
    const station = props.stations.find((s) => s.bipad_id === readout.id);
    if (station) {
      return (
        <>
          <div style={RO_TITLE}>{station.name}</div>
          {station.basin && (
            <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 2 }}>{station.basin} basin</div>
          )}
          {/* Undated is provenance, not danger: a pin opens a photograph of a
              place, never an image of this flood. */}
          <div style={{
            fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '.06em',
            lineHeight: 1.4, color: 'var(--status-info)', marginTop: 4,
          }}>
            DHM STATION PHOTO · UNDATED · CLICK TO OPEN
          </div>
        </>
      );
    }
  }

  if (readout?.kind === 'footprint') {
    const item = readout.item;
    const day = formatSceneDay(item.datetime) ?? item.datetime.slice(0, 10);
    const gap = item.phase === 'pre' ? baselineGap(item.datetime) : null;
    return (
      <>
        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '.06em', color: 'var(--text-primary)',
        }}>
          VANTOR {item.id}
        </div>
        <div style={{
          fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', fontSize: 9,
          letterSpacing: '.06em', marginTop: 3,
          color: item.phase === 'post' ? 'var(--status-info)' : 'var(--text-secondary)',
        }}>
          {item.phase.toUpperCase()} · {day} · CLOUD {item.cloud}%
        </div>
        {/* The pre scenes are 2021–2024 archive passes, so the gap to the
            collapse is spelled out rather than left for a reader to infer. */}
        {gap && <div style={{ ...RO_MONO, marginTop: 2 }}>BASELINE — {gap} BEFORE THE FLOOD</div>}
        {item.cloud >= 50 && (
          <div style={{
            fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '.06em',
            color: 'var(--status-medium)', marginTop: 2,
          }}>
            MONSOON CLOUD — READS THROUGH GAPS
          </div>
        )}
        {item.covers.length > 0 ? (
          <div style={{ fontSize: 9, lineHeight: 1.5, color: 'var(--text-secondary)', marginTop: 5 }}>
            Sees {item.covers.join(' · ')}
            <span style={{ color: 'var(--text-muted)' }}> — footprint or approach</span>
          </div>
        ) : (
          <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 5 }}>
            No corridor site inside this footprint
          </div>
        )}
        {/* The attribution closes the card because it is the condition the
            licence is granted on: the footer is what a screenshot of the whole
            map keeps, this line is what a screenshot of one hover keeps. */}
        <div style={{ ...RO_MONO, ...RO_RULE, lineHeight: 1.4 }}>{item.attribution}</div>
      </>
    );
  }

  // Rest state — the legend.
  return (
    <>
      {props.imageryDrawn ? (
        // A legend explains ink that is on the canvas. While the imagery is on
        // the fill has stood aside, so its ramp goes with it.
        <div style={LABEL_XS}>DISTRICT FILL STANDS ASIDE WHILE IMAGERY IS ON · BLANK = NO-DATA, NOT GROUND</div>
      ) : (
        <>
          <div style={LABEL_XS}>Bodies recovered</div>
          {/* Swatch over its own break rather than beside it: five ranges laid
              out in a row do not fit 228 px of panel, and a ramp that wraps
              onto a second line stops reading as one ordered scale. */}
          <div style={{ display: 'flex', gap: 2, marginTop: 4 }}>
            {[...FILL_STEPS].reverse().map((s) => (
              <div key={s.label} style={{ flex: '1 1 0', minWidth: 0 }}>
                <div style={{
                  height: 8, background: `rgba(239,68,68,${s.alpha})`,
                  border: HAIRLINE,
                }} />
                <div style={{
                  ...LABEL_XS, fontVariantNumeric: 'tabular-nums', fontSize: 8,
                  letterSpacing: 0, textAlign: 'center', color: MS.sub, marginTop: 2,
                }}>
                  {s.label}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
      <div style={{ ...LABEL_XS, marginTop: 5 }}>
        AMBER = MISSING WHERE PUBLISHED · BLUE LINE = RIVER CHANNEL (OSM)
      </div>
      {props.footprintsOn && (
        <div style={{ ...LABEL_XS, marginTop: 3 }}>
          BLUE OUTLINE = VANTOR FOOTPRINT · SOLID POST · DASHED PRE · OUTLINES ONLY
        </div>
      )}
      {props.dhmCount > 0 && (
        <div style={{ ...LABEL_XS, marginTop: 3 }}>{props.dhmCount} DHM GAUGE PHOTOS · UNDATED</div>
      )}
      {props.places.length > 0 && (
        <div style={{ ...LABEL_XS, marginTop: 3 }}>
          <span style={{ color: 'var(--status-critical)' }}>■ BURIAL</span> · <span style={{ color: 'var(--status-high)' }}>■ DNA / MORTUARY / ROAD CUT</span> · <span style={{ color: 'var(--status-info)' }}>■ LIFT / RECOVERY / AIRHEAD</span> · <span style={{ color: 'var(--status-low)' }}>■ TUNNEL DIGGING</span>
        </div>
      )}
    </>
  );
};

/**
 * Bottom-left, where the legend control used to sit, and pointer-events:none so
 * the corner it covers still pans and hovers the map underneath. Top-right is
 * unavailable — FloodImageryBanner owns it. minHeight keeps the corner from
 * jittering as the reader sweeps between targets of different lengths.
 */
const ReadoutPanel = (props: ReadoutPanelProps) => (
  <div
    style={{
      position: 'absolute', left: 8, bottom: 8, width: 248, zIndex: 800,
      pointerEvents: 'none', boxSizing: 'border-box', minHeight: 96,
      // Not a card on the map: no rule, no rail, no elevation. Just enough of
      // the surface behind the type to stay readable over terrain.
      background: 'rgba(17, 17, 19, 0.85)', borderRadius: 2,
      padding: '6px 8px', fontFamily: MS.mono,
    }}
  >
    <ReadoutBody {...props} />
  </div>
);

export const FloodDistrictMapWidget = memo(function FloodDistrictMapWidget() {
  const geo = useFloodDistrictGeo();
  const situation = useOfficialSituation();
  const chronology = useFloodChronology();
  const media = useFloodMedia();
  const vantor = useVantorScenes();
  const catalog = useDrpCatalog();
  const photos = useStationPhotos();
  const damage = useDamageSites();
  const sitesQ = useFloodSites();
  const places = useMemo<ResponseSite[]>(() => sitesQ.data?.sites ?? [], [sitesQ.data]);
  const kindText = useMemo<Record<string, string>>(() => sitesQ.data?.kinds ?? {}, [sitesQ.data]);

  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const districtsRef = useRef<L.GeoJSON | null>(null);
  const pathsRef = useRef<Map<string, L.Path>>(new Map());
  const labelsRef = useRef<L.LayerGroup | null>(null);
  const corridorRef = useRef<L.LayerGroup | null>(null);
  const sweepRef = useRef<L.LayerGroup | null>(null);
  /** The media anchors and the damage sites draw into ONE group now, because
   *  whether a point is its own chip or part of an aggregate is decided across
   *  both sets at once. The data stays in two places; only the ink is merged. */
  const marksRef = useRef<L.LayerGroup | null>(null);
  const vantorRef = useRef<L.LayerGroup | null>(null);
  const drpRef = useRef<L.LayerGroup | null>(null);
  const drpImageRef = useRef<L.ImageOverlay | null>(null);
  const dhmRef = useRef<L.LayerGroup | null>(null);
  const placesRef = useRef<L.LayerGroup | null>(null);
  const homeBoundsRef = useRef<L.LatLngBounds | null>(null);
  const placeLabelsRef = useRef<(() => void) | null>(null);
  const placeMarksRef = useRef<(() => void) | null>(null);
  /** What the last placer actually put on the canvas. The label placer routes
   *  around THIS rather than around the raw point lists — six chips that
   *  collapsed into one aggregate must only cost the labels one rectangle. */
  const renderedMarksRef = useRef<RenderedMark[]>([]);
  const drawDhmRef = useRef<(() => void) | null>(null);
  const dhmDetailRef = useRef<boolean | null>(null);
  const sweepPartsRef = useRef<{ trail: L.Polyline; front: L.CircleMarker; label: L.Marker } | null>(null);

  // The one readout slot. See the Readout union above for why this replaced
  // seven bindTooltip calls rather than guarding them.
  const [readout, setReadout] = useState<Readout | null>(null);
  const showReadout = useCallback((next: Readout) => setReadout(next), []);
  /** Clears only if the slot still holds the thing that is leaving. A fast
   *  sweep therefore cannot blank the readout the cursor has already moved on
   *  to: B's enter overwrites, and A's late leave matches nothing. */
  const clearReadout = useCallback((mine: Readout) => {
    const key = readoutKey(mine);
    setReadout((prev) => (prev && readoutKey(prev) === key ? null : prev));
  }, []);

  const [showFootprints, setShowFootprints] = useState(false);

  // null = the overlay is off. When it is on the value is the phase on screen,
  // so one piece of state answers both "is there imagery" and "which imagery".
  const [imagery, setImagery] = useState<DrpPhase | null>(null);
  const [imageryStatus, setImageryStatus] = useState<ImageryStatus>('loading');
  const [imageryCaption, setImageryCaption] = useState<ImageryCaption | null>(null);
  /** The phase whose pixels are actually on the canvas, which is not the same
   *  as the phase the toggle asks for: below zoom 14, or off coverage, nothing
   *  is drawn. Read by the Leaflet callbacks, which outlive the render that
   *  bound them. */
  const imageryDrawnRef = useRef<DrpPhase | null>(null);

  /** The frame exportImage has to be asked for: bounds, zoom and pixel size.
   *  Sampled only while the overlay is on — see the sampling effect. */
  const [frame, setFrame] = useState<{ zoom: number; box: LatLngBox; w: number; h: number } | null>(null);

  const [showDhm, setShowDhm] = useState(false);
  /** Response sites (burials, DNA hubs, transfer points, tunnels). On by default: they are the point of an impact map. */
  const [showSites, setShowSites] = useState(true);
  const [photo, setPhoto] = useState<StationPhoto | null>(null);

  const features = useMemo<DistrictFeature[]>(
    () => geo.data?.districts?.features ?? [],
    [geo.data],
  );
  const corridor = useMemo<CorridorWaypoint[]>(() => geo.data?.corridor ?? [], [geo.data]);
  const ready = features.length > 0;
  const runKm = useMemo(
    () => corridor.filter((w) => w.km != null).sort((a, b) => (a.km ?? 0) - (b.km ?? 0)),
    [corridor],
  );

  const event = situation.data?.event;
  const latest = situation.data?.official?.latest;
  // NDRRMA's own explanation of the inversion, rendered verbatim rather than
  // paraphrased into an inference this widget is not entitled to make.
  const deathsNote =
    situation.data?.official?.panels?.find((p) => p.key === 'deaths')?.note ?? latest?.note ?? null;

  const snapshots = useMemo<DistrictSnapshot[]>(() => {
    const published = geo.data?.toll_snapshots;
    if (published && published.length > 0) {
      return [...published].sort((a, b) => a.as_of.localeCompare(b.as_of));
    }
    // Fallback while /flood/districts/geo carries only the latest figures: the
    // one breakdown we can prove is the one the features already hold. Missing
    // is deliberately NOT copied in — the per-district missing figures reach
    // the features from the situation panels rather than from the bulletin's
    // district table, so replaying them as bulletin rows would invent a
    // completeness that bulletin never had.
    const first = features[0]?.properties;
    if (!first?.as_of) return [];
    const tolls: Record<string, Record<string, number>> = {};
    features.forEach((f) => {
      const p = f.properties;
      if (p.bodies_recovered != null) tolls[p.name] = { bodies_recovered: p.bodies_recovered };
    });
    return Object.keys(tolls).length > 0
      ? [{ as_of: first.as_of, authority: first.authority, district_tolls: tolls }]
      : [];
  }, [geo.data, features]);

  const replay = useFloodReplay({
    beats: chronology.data?.events ?? [],
    trajectory: situation.data?.official?.trajectory ?? [],
    snapshots,
  });

  const view = useMemo(() => {
    const byName = new Map<string, DistrictView>();
    features.forEach((f) => {
      const p = f.properties;
      const base = {
        name: p.name,
        province: p.province,
        position: p.position,
        centroid: p.centroid,
      };
      if (replay.isLive) {
        // The live edge is the map as it has always rendered, figure for
        // figure, so opening the widget shows no trace of the replay.
        byName.set(p.name, {
          ...base,
          recovered: p.bodies_recovered,
          missing: p.missing,
          published: p.bodies_recovered != null || p.missing != null,
          authority: p.authority,
          asOf: p.as_of,
        });
        return;
      }
      const snap = replay.snapshot;
      const entry = snap ? snap.district_tolls[p.name] : undefined;
      const recovered = typeof entry === 'number' ? entry : entry?.bodies_recovered ?? null;
      const missing = typeof entry === 'number' ? null : entry?.missing ?? null;
      byName.set(p.name, {
        ...base,
        recovered,
        missing,
        published: recovered != null || missing != null,
        authority: snap?.authority ?? null,
        asOf: snap ? snap.as_of.slice(0, 10) : null,
      });
    });
    return byName;
  }, [features, replay.isLive, replay.snapshot]);

  // Leaflet callbacks outlive the render that bound them, so they read the
  // current view through a ref rather than a captured one.
  const viewRef = useRef(view);
  viewRef.current = view;

  const [failedMedia, setFailedMedia] = useState<Set<string>>(new Set());
  const markMediaFailed = useCallback((id: string) => {
    setFailedMedia((prev) => (prev.has(id) ? prev : new Set(prev).add(id)));
  }, []);

  const anchors = useMemo<MediaAnchor[]>(() => {
    const groups = new Map<string, MediaAnchor>();
    (media.data?.items ?? []).forEach((item) => {
      if (!item.anchor || item.lat == null || item.lng == null) return;
      // A file exists in the replay only once its own date has closed. Files
      // predating the collapse are therefore present from the first frame.
      if (item.available_from && replay.t < dayCloseMs(item.available_from)) return;
      const group = groups.get(item.anchor) ?? {
        anchor: item.anchor,
        lat: item.lat,
        lng: item.lng,
        label: item.location?.name ?? item.anchor,
        viewable: [],
        links: [],
      };
      if (isViewable(item)) {
        if (!failedMedia.has(item.id)) group.viewable.push(item);
      } else {
        group.links.push(item);
      }
      groups.set(item.anchor, group);
    });
    return [...groups.values()]
      .map((g) => ({
        ...g,
        viewable: [...g.viewable].sort((a, b) => a.display_order - b.display_order),
        links: [...g.links].sort((a, b) => a.display_order - b.display_order),
      }))
      .filter((g) => g.viewable.length > 0);
  }, [media.data, replay.t, failedMedia]);

  const anchorsRef = useRef(anchors);
  anchorsRef.current = anchors;
  // A discrete key so a playing scrubber only touches Leaflet at a transition.
  const anchorSignature = anchors.map((a) => `${a.anchor}:${a.viewable.length}`).join('|');

  const [viewer, setViewer] = useState<{ anchor: string; index: number } | null>(null);
  const [siteKey, setSiteKey] = useState<string | null>(null);
  const openViewer = useCallback((anchor: string) => {
    // Opening a picture pauses the clock without moving it: the reader asked to
    // look at one moment, not to lose their place in it.
    replay.pause();
    // One overlay at a time. Both are absolute over the same column and the
    // second would simply hide the first, leaving a close button that appears
    // to do nothing.
    setSiteKey(null);
    setViewer({ anchor, index: 0 });
  }, [replay]);
  const openViewerRef = useRef(openViewer);
  openViewerRef.current = openViewer;

  const allSites = useMemo<DamageSite[]>(() => damage.data?.sites ?? [], [damage.data]);

  /** The day the first post-event pass was flown over anything, read from the
   *  frames themselves. Before it closed, "no post-event pass over the origin"
   *  was not yet a finding — it was simply too early for one. */
  const firstPostDay = useMemo<string | null>(() => {
    let earliest: string | null = null;
    allSites.forEach((site) => {
      site.levels.forEach((level) => {
        const day = level.post.top?.datetime.slice(0, 10);
        if (day && (earliest === null || day < earliest)) earliest = day;
      });
    });
    return earliest;
  }, [allSites]);

  // Same rule the Commons files gate on: a frame exists in the replay only once
  // its own acquisition day has closed in Nepal time. The replay steps between
  // published moments and invents none, and a pair of pixels flown on the 27th
  // may not appear on the 26th's frame.
  const sites = useMemo<DamageSite[]>(() => {
    if (replay.isLive) return allSites;
    return allSites.filter((site) => {
      let day: string | null = null;
      site.levels.forEach((level) => {
        const d = level.post.top?.datetime.slice(0, 10);
        if (d && (day === null || d < day)) day = d;
      });
      // No post frame at all: the site's finding is the absence of one, which
      // becomes true only once some pass existed to be absent from.
      const gate = day ?? firstPostDay;
      return gate != null && replay.t >= dayCloseMs(gate);
    });
  }, [allSites, replay.isLive, replay.t, firstPostDay]);

  const sitesRef = useRef(sites);
  sitesRef.current = sites;
  const siteSignature = sites.map((s) => s.key).join('|');

  const openSiteViewer = useCallback((key: string) => {
    // Same rule as the media chips and the DHM pins: looking at a picture
    // pauses the clock without moving it.
    replay.pause();
    setViewer(null);
    setSiteKey(key);
  }, [replay]);
  const openSiteViewerRef = useRef(openSiteViewer);
  openSiteViewerRef.current = openSiteViewer;

  const activeSite = siteKey ? sites.find((s) => s.key === siteKey) ?? null : null;
  useEffect(() => {
    // The replay stepped back before this site's pass was flown. Close rather
    // than hold open a pair the frame on screen does not yet contain.
    if (siteKey && !activeSite) setSiteKey(null);
  }, [siteKey, activeSite]);

  const activeAnchor = viewer ? anchors.find((a) => a.anchor === viewer.anchor) ?? null : null;
  useEffect(() => {
    // Every file at this anchor failed to load, or the replay stepped back
    // before they existed. Close rather than hold an empty frame open.
    if (viewer && !activeAnchor) setViewer(null);
  }, [viewer, activeAnchor]);

  // Create the map once the geometry has arrived. Leaflet owns the container
  // node, so this must not re-run on data changes or it double-initialises.
  useEffect(() => {
    if (!ready || !containerRef.current || mapRef.current) return;

    const map = L.map(containerRef.current, {
      center: [27.9, 84.8],
      zoom: 8,
      zoomControl: true,
      attributionControl: true,
      // This widget sits mid-page: a wheel over it must scroll the dashboard
      // until a reader deliberately claims the map by clicking into it.
      scrollWheelZoom: false,
    });

    L.tileLayer(BASEMAP_URL, {
      attribution: BASEMAP_ATTRIBUTION,
      maxNativeZoom: 16,
      // Past 16 the basemap only upscales, which used to be reason enough to
      // stop there. It no longer is: the DRP frames are 30–60 cm and a reader
      // held at zoom 16 sees a twentieth of what the pixels hold, so the map is
      // allowed further in than its basemap can go.
      maxZoom: 19,
    }).addTo(map);

    // Between the tiles and the vector overlays. The imagery replaces the
    // basemap under it and nothing else: the corridor, the labels, the chips
    // and the footprints all stay readable on top of the pixels.
    map.createPane(DRP_PANE);
    const drpPane = map.getPane(DRP_PANE);
    if (drpPane) {
      drpPane.style.zIndex = '350';
      // globals.css forces pointer-events onto marker icons; an image layer has
      // no such rule, but a full-frame image that ate district hovers would be
      // the worst kind of regression, so it is stated rather than assumed.
      drpPane.style.pointerEvents = 'none';
    }

    map.on('click', () => map.scrollWheelZoom.enable());
    map.on('mouseout', () => {
      map.scrollWheelZoom.disable();
      // Leaving the canvas is the one leave a layer never reports for itself.
      // Unconditional, unlike the per-layer guard: the cursor is off the map,
      // so nothing can still be under it.
      setReadout(null);
    });

    labelsRef.current = L.layerGroup().addTo(map);
    corridorRef.current = L.layerGroup().addTo(map);
    sweepRef.current = L.layerGroup().addTo(map);
    // On the canvas from the first paint, unlike the three below it: the damage
    // pairs are what the map is for now, and grouped they cost it less ink than
    // one district label cluster.
    marksRef.current = L.layerGroup().addTo(map);
    // Built but deliberately not added: all three of these are opt-in layers,
    // and the map on load must be the map the desk has always shown.
    vantorRef.current = L.layerGroup();
    drpRef.current = L.layerGroup();
    dhmRef.current = L.layerGroup();
    placesRef.current = L.layerGroup().addTo(map);

    // The widget is resizable and starts inside a grid cell that has no height
    // on the first paint, so a fit computed then would be wrong.
    const observer = new ResizeObserver(() => map.invalidateSize());
    observer.observe(containerRef.current);

    mapRef.current = map;

    return () => {
      observer.disconnect();
      map.remove();
      mapRef.current = null;
      districtsRef.current = null;
      pathsRef.current = new Map();
      labelsRef.current = null;
      corridorRef.current = null;
      sweepRef.current = null;
      marksRef.current = null;
      vantorRef.current = null;
      drpRef.current = null;
      drpImageRef.current = null;
      dhmRef.current = null;
      sweepPartsRef.current = null;
      homeBoundsRef.current = null;
      placeLabelsRef.current = null;
      placeMarksRef.current = null;
      renderedMarksRef.current = [];
      drawDhmRef.current = null;
    };
  }, [ready]);

  // Districts and their permanent labels. Built once per geometry change: the
  // replay re-parameterises this layer rather than rebuilding it, so scrubbing
  // never re-runs a GeoJSON parse.
  useEffect(() => {
    const map = mapRef.current;
    const labels = labelsRef.current;
    if (!map || !labels || features.length === 0) return;

    if (districtsRef.current) {
      map.removeLayer(districtsRef.current);
      districtsRef.current = null;
    }
    labels.clearLayers();
    pathsRef.current = new Map();

    const layer = L.geoJSON<DistrictProperties>(
      { type: 'FeatureCollection', features } as FeatureCollection<Geometry, DistrictProperties>,
      {
        style: (feature) => {
          const v = feature ? viewRef.current.get(feature.properties.name) : undefined;
          return v ? districtStyle(v, imageryDrawnRef.current != null) : {};
        },
        onEachFeature: (feature, lyr) => {
          const name = (feature.properties as DistrictProperties).name;
          const path = lyr as L.Path;
          pathsRef.current.set(name, path);
          const current = () => viewRef.current.get(name);
          // Built once and reused: the readout is identified by what it is
          // about, and the panel reads the figures live from `view`.
          const mine: Readout = { kind: 'district', name };
          path.on('mouseover', () => {
            const now = current();
            if (now) path.setStyle(hoverStyle(now, imageryDrawnRef.current != null));
            showReadout(mine);
          });
          path.on('mouseout', () => {
            const now = current();
            if (now) path.setStyle(districtStyle(now, imageryDrawnRef.current != null));
            clearReadout(mine);
          });
          path.on('click', () => {
            // Also on click, so a tap — which has no hover to precede it —
            // still fills the panel.
            showReadout(mine);
            const bounds = (lyr as L.Polygon).getBounds();
            if (bounds.isValid()) map.fitBounds(bounds, { padding: [16, 16] });
          });
        },
      },
    ).addTo(map);
    districtsRef.current = layer;

    // Label placement is greedy and collision-aware. The affected districts
    // cluster tightly around the Trishuli, so placing a label at every centroid
    // stacks five of them into an unreadable knot at the default frame. Instead
    // the highest-impact districts claim their space first and any label that
    // would overlap one already placed is dropped — its figures remain on hover
    // and in the ranked toll list beside the map. Recomputed on every zoom
    // because what fits changes with scale; zoom in and the dropped labels
    // reappear.
    const LABEL_W = 110;
    const LABEL_H = 40;

    const placeLabels = () => {
      labels.clearLayers();
      const taken: { x1: number; y1: number; x2: number; y2: number }[] = [];

      const place = (f: DistrictFeature, dy = 0, force = false): boolean => {
        const v = viewRef.current.get(f.properties.name);
        if (!v?.centroid) return false;
        const pt = map.latLngToContainerPoint([v.centroid.lat, v.centroid.lng]);
        const box = {
          x1: pt.x - LABEL_W / 2,
          y1: pt.y - 10 + dy,
          x2: pt.x + LABEL_W / 2,
          y2: pt.y - 10 + dy + LABEL_H,
        };
        const clashes = taken.some((t) =>
          box.x1 < t.x2 && box.x2 > t.x1 && box.y1 < t.y2 && box.y2 > t.y1);
        if (clashes && !force) return false;
        taken.push(box);

        const marker = L.marker([v.centroid.lat, v.centroid.lng], {
          // Anchored a touch below the centroid: at the default frame the collapse
          // origin sits ~30 px above Rasuwa's centroid, and a centred label would
          // put "RASUWA / 27 / 865 MISSING" straight through the origin rings —
          // the one collision on the map a reader cannot afford.
          icon: L.divIcon({ className: '', html: districtLabel(v), iconSize: [LABEL_W, 44], iconAnchor: [LABEL_W / 2, 10 - dy] }),
          interactive: false,
          keyboard: false,
        }).addTo(labels);
        makePassive(marker);
        return true;
      };

      // Rasuwa first regardless of its low recovered count: it is the source and
      // holds the largest missing figure, so it is the one label the story
      // cannot lose. Everything after it ranks by bodies recovered.
      const ordered = [...features].sort((a, b) => {
        const ap = a.properties;
        const bp = b.properties;
        if (ap.position === 'source') return -1;
        if (bp.position === 'source') return 1;
        const av = viewRef.current.get(ap.name)?.recovered ?? 0;
        const bv = viewRef.current.get(bp.name)?.recovered ?? 0;
        return bv - av;
      });

      // Three passes, in priority order. The marks claim first now — they are
      // controls, and a label landing on one hides something the reader can
      // click — and they claim what was actually DRAWN, so a group of six that
      // collapsed into one aggregate costs the labels one rectangle instead of
      // six. Marks are never dropped.
      const claim = (lat: number, lng: number, offset: L.PointTuple, w: number) => {
        const [ax, ay] = offset;
        const pt = map.latLngToContainerPoint([lat, lng]);
        taken.push({
          x1: pt.x - ax - 2,
          y1: pt.y - ay - 2,
          x2: pt.x - ax + w + 2,
          y2: pt.y - ay + CHIP_H + 2,
        });
      };
      renderedMarksRef.current.forEach((m) => claim(m.lat, m.lng, m.offset, m.w));

      // Then the source label, which is the one label the story cannot lose. It
      // gets two candidate anchors because the upper aggregate's centroid lands
      // near Rasuwa's own label: above the centroid as always, and 34 px lower
      // if that box is taken. If both are taken it is forced into the lower one
      // — a source district with no name on it is not an option.
      ordered
        .filter((f) => f.properties.position === 'source')
        .forEach((f) => {
          if (!place(f)) place(f, 34, true);
        });

      // Everything else places around both, and is dropped rather than stacked.
      ordered.filter((f) => f.properties.position !== 'source').forEach((f) => place(f));
    };

    placeLabelsRef.current = placeLabels;
    placeLabels();
    map.on('zoomend moveend', placeLabels);

    const bounds = layer.getBounds();
    if (bounds.isValid()) {
      homeBoundsRef.current = bounds;
      map.invalidateSize();
      map.fitBounds(bounds, { padding: HOME_PADDING });
    }

    return () => { map.off('zoomend moveend', placeLabels); };
  }, [features]);

  // Re-parameterise the districts for the moment on screen. Keyed on the view
  // itself, which only changes when the active snapshot does — a scrubber
  // dragged through a day where nothing was published touches nothing here.
  // The imagery flag joins it because turning the overlay on and off is the
  // other thing that changes how a district is painted. Keyed on pixels
  // actually being on screen, not on the toggle: a reader who asks for imagery
  // from the province frame, where none can be drawn, must not lose the
  // choropleth in exchange for nothing.
  const muteFill = imagery != null && imageryStatus === 'ok';
  imageryDrawnRef.current = muteFill ? imagery : null;
  useEffect(() => {
    if (pathsRef.current.size === 0) return;
    view.forEach((v, name) => {
      const path = pathsRef.current.get(name);
      if (!path) return;
      path.setStyle(districtStyle(v, muteFill));
    });
    placeLabelsRef.current?.();
  }, [view, muteFill]);

  // The surge path. Rebuilt when the event record arrives so the origin marker
  // can carry NDRRMA's cause text verbatim.
  useEffect(() => {
    const group = corridorRef.current;
    if (!group || corridor.length === 0) return;
    group.clearLayers();

    const run = corridor.filter((w) => w.kind !== 'origin');
    const path: L.LatLngExpression[] = run.map((w) => [w.lat, w.lng]);
    // A dense channel (one vertex per 100 m from OSM) is drawn solid; the
    // schematic chord list keeps its dashes so nobody mistakes it for a river.
    const dense = run.some((w) => w.kind === 'channel');

    if (path.length > 1) {
      if (dense) {
        L.polyline(path, { color: INFO, weight: 5, opacity: 0.18 }).addTo(group);
        L.polyline(path, { color: INFO, weight: 1.8, opacity: 0.9 }).addTo(group);
      } else {
        L.polyline(path, { color: INFO, weight: 2, opacity: 0.65, dashArray: '6 6' }).addTo(group);
      }
    }

    run.filter((w) => !dense || w.name).forEach((w) => {
      const dot = L.circleMarker([w.lat, w.lng], {
        radius: 3,
        color: INFO,
        weight: 1,
        fillColor: INFO,
        fillOpacity: 0.85,
      }).addTo(group);
      const mine: Readout = { kind: 'waypoint', wp: w };
      dot.on('mouseover', () => showReadout(mine));
      dot.on('mouseout', () => clearReadout(mine));
    });

    // On the dense channel the chevrons sit every CHEVRON_EVERY_KM, oriented by
    // the vertices either side; on the schematic list they sit on fixed segments.
    const chevronPairs: [CorridorWaypoint, CorridorWaypoint][] = [];
    if (dense) {
      const kmRun = run.filter((w) => w.km != null);
      const maxKm = kmRun.length ? (kmRun[kmRun.length - 1].km ?? 0) : 0;
      for (let km = CHEVRON_EVERY_KM / 2; km < maxKm; km += CHEVRON_EVERY_KM) {
        const i = kmRun.findIndex((w) => (w.km ?? 0) >= km);
        if (i > 0 && kmRun[i + 1]) chevronPairs.push([kmRun[i - 1], kmRun[i + 1]]);
      }
    } else {
      CHEVRON_SEGMENTS.forEach((i) => { if (run[i] && run[i + 1]) chevronPairs.push([run[i], run[i + 1]]); });
    }
    chevronPairs.forEach(([a, b]) => {
      // Planar bearing with a cos(lat) correction. This only orients a
      // schematic chevron, so a great-circle bearing would be false precision.
      const dx = (b.lng - a.lng) * Math.cos((((a.lat + b.lat) / 2) * Math.PI) / 180);
      const dy = b.lat - a.lat;
      const deg = (Math.atan2(dx, dy) * 180) / Math.PI;
      const marker = L.marker([(a.lat + b.lat) / 2, (a.lng + b.lng) / 2], {
        icon: L.divIcon({
          className: '',
          html: `<div style="width:0;height:0;border-left:4px solid transparent;border-right:4px solid transparent;
                             border-bottom:7px solid ${INFO};opacity:.85;transform:rotate(${deg.toFixed(1)}deg)"></div>`,
          iconSize: [8, 8],
          iconAnchor: [4, 4],
        }),
        interactive: false,
        keyboard: false,
      }).addTo(group);
      makePassive(marker);
    });

    const origin = corridor.find((w) => w.kind === 'origin');
    if (origin) {
      L.circleMarker([origin.lat, origin.lng], {
        radius: 10,
        color: CRITICAL,
        weight: 1.5,
        fill: false,
      }).addTo(group);

      const core = L.circleMarker([origin.lat, origin.lng], {
        radius: 4,
        color: CRITICAL,
        weight: 0,
        fillColor: CRITICAL,
        fillOpacity: 1,
      }).addTo(group);

      if (event?.cause) {
        const mine: Readout = { kind: 'origin' };
        core.on('mouseover', () => showReadout(mine));
        core.on('mouseout', () => clearReadout(mine));
      }

      const started = formatEventDate(event?.started_on);
      const originLabel = L.marker([origin.lat, origin.lng], {
        icon: L.divIcon({
          className: '',
          html: `<div style="text-align:left;line-height:1.2;text-shadow:0 1px 3px rgba(0,0,0,.95);
                             font-family:var(--font-mono);font-size:9px;letter-spacing:.08em;color:var(--status-critical)">
                   COLLAPSE ORIGIN${started ? `<br/><span style="color:var(--text-muted)">${started}</span>` : ''}
                 </div>`,
          iconSize: [130, 26],
          // Up and to the right of the rings: Rasuwa's own label lies south-west
          // of this point, so any other direction collides with it.
          iconAnchor: [-10, 44],
        }),
        interactive: false,
        keyboard: false,
      }).addTo(group);
      makePassive(originLabel);
    }
  }, [corridor, event]);

  // Before the collapse there was no surge to draw. The corridor leaves the
  // canvas entirely rather than sitting there implying a path already run.
  useEffect(() => {
    const map = mapRef.current;
    const group = corridorRef.current;
    if (!map || !group) return;
    if (replay.corridorHidden) {
      if (map.hasLayer(group)) map.removeLayer(group);
    } else if (!map.hasLayer(group)) {
      group.addTo(map);
    }
  }, [replay.corridorHidden, ready]);

  // The 26 August sweep. Created once when the window opens and moved by
  // setLatLng afterwards, so a playing clock never churns layers.
  const sweepActive = replay.sweep != null;
  useEffect(() => {
    const group = sweepRef.current;
    if (!group) return;
    group.clearLayers();
    sweepPartsRef.current = null;
    if (!sweepActive || runKm.length < 2) return;

    const head: L.LatLngTuple = [runKm[0].lat, runKm[0].lng];
    const trail = L.polyline([head], { color: INFO, weight: 2, opacity: 0.95 }).addTo(group);
    const front = L.circleMarker(head, {
      radius: 6,
      color: INFO,
      weight: 1,
      fillColor: INFO,
      fillOpacity: 1,
    }).addTo(group);
    const label = L.marker(head, {
      icon: L.divIcon({
        className: '',
        // Permanent, not a tooltip: the schematic caveat has to be on screen in
        // any screenshot of the animation, not one hover away from it.
        html: `<div style="font-family:var(--font-mono);font-size:8px;letter-spacing:.06em;white-space:nowrap;
                           color:${INFO};text-shadow:0 1px 3px rgba(0,0,0,.95)">${SWEEP_LABEL}</div>`,
        iconSize: [280, 12],
        iconAnchor: [-8, -6],
      }),
      interactive: false,
      keyboard: false,
    }).addTo(group);
    makePassive(label);

    sweepPartsRef.current = { trail, front, label };
  }, [sweepActive, runKm, ready]);

  const sweepKm = replay.sweep?.km ?? null;
  useEffect(() => {
    const parts = sweepPartsRef.current;
    if (!parts || sweepKm == null) return;
    const head = pointAtKm(runKm, sweepKm);
    if (!head) return;
    const passed: L.LatLngTuple[] = runKm
      .filter((w) => (w.km ?? 0) <= sweepKm)
      .map((w) => [w.lat, w.lng] as L.LatLngTuple);
    parts.trail.setLatLngs([...passed, head]);
    parts.front.setLatLng(head);
    parts.label.setLatLng(head);
  }, [sweepKm, runKm]);

  /**
   * THE MARKS. One placer for both chip kinds, because whether a point gets its
   * own chip is a question about every other point on the canvas, not about
   * which endpoint it came from.
   *
   * Eight points fall inside ~180 px of each other at the province frame, and
   * per-point offsets cannot separate what is genuinely co-located at that
   * scale — the previous table of tuned pushes only moved the pile around and
   * buried the collapse origin under it. So marks within CLUSTER_R of each
   * other in world pixels collapse to one aggregate, and the aggregate opens by
   * zooming to the first frame where its members actually separate. Nothing is
   * lost: every site is at most one click deeper than it was.
   *
   * Grouping is in world pixels at a stated zoom, so it depends on scale alone
   * and this runs on zoomend only — a pan must never re-group the map under the
   * reader's cursor.
   */
  useEffect(() => {
    const map = mapRef.current;
    const group = marksRef.current;
    if (!map || !group) return;

    const placeMarks = () => {
      group.clearLayers();
      const rendered: RenderedMark[] = [];

      // Grouping reduces the pile to a handful; this settles the handful. Two
      // marks can still land on each other at an intermediate zoom — the origin
      // pair sits beside the border aggregate at z9 — and a mark may never be
      // dropped, so a residual clash is resolved downward into a readable
      // column instead. Container pixels are safe here because every mark moves
      // together under a pan: only zoom changes what overlaps.
      const taken: { x1: number; y1: number; x2: number; y2: number }[] = [];
      const slot = (lat: number, lng: number, offset: L.PointTuple, w: number): L.PointTuple => {
        const pt = map.latLngToContainerPoint([lat, lng]);
        const [ax] = offset;
        let ay = offset[1];
        // Lowering the anchor's y draws the icon further down the screen.
        for (let i = 0; i < 8; i += 1) {
          const box = { x1: pt.x - ax, y1: pt.y - ay, x2: pt.x - ax + w, y2: pt.y - ay + CHIP_H };
          const clash = taken.some((t) =>
            box.x1 < t.x2 && box.x2 > t.x1 && box.y1 < t.y2 && box.y2 > t.y1);
          if (!clash) {
            taken.push(box);
            return [ax, ay];
          }
          ay -= CHIP_H + 3;
        }
        return [ax, ay];
      };

      const drawSite = (site: DamageSite): RenderedMark => {
        const offset = slot(site.lat, site.lng, DMG_CHIP_OFFSETS[site.key] ?? DEFAULT_DMG_CHIP_OFFSET, DMG_CHIP_W);
        const marker = L.marker([site.lat, site.lng], {
          icon: L.divIcon({
            className: '',
            // The chip is the only surface a reader sees before touching
            // anything, so it must not promise a pair the record does not hold.
            // A site with no post-event pass says so here, not just in the panel.
            html: chipHtml(site.levels.length === 0 ? 'NO POST' : 'PRE|POST', INFO),
            iconSize: [DMG_CHIP_W, CHIP_H],
            iconAnchor: offset,
          }),
          // Deliberately interactive and deliberately not passivated: this
          // marker exists to be clicked.
          keyboard: false,
          // The native title makes the same promise the panel does: a site with
          // no frames opens onto a statement, not a pair. Kept because the
          // browser manages it, only ever shows one, and it is the long-press
          // affordance on touch.
          title: site.levels.length === 0
            ? `${site.name} · no post-event pass`
            : `${site.name} · same-frame pre/post satellite imagery`,
        }).addTo(group);
        const mine: Readout = { kind: 'site', key: site.key };
        marker.on('mouseover', () => showReadout(mine));
        marker.on('mouseout', () => clearReadout(mine));
        marker.on('click', () => {
          showReadout(mine);
          openSiteViewerRef.current(site.key);
        });
        return { lat: site.lat, lng: site.lng, offset, w: DMG_CHIP_W };
      };

      const drawMedia = (a: MediaAnchor): RenderedMark => {
        // The count is every file behind the chip, not just the stills, so the
        // number on the map is the number the viewer then pages through.
        const stills = a.viewable.filter((i) => i.kind === 'image').length;
        const chip = stills > 0 ? `IMG ${a.viewable.length}` : `VID ${a.viewable.length}`;
        const offset = slot(a.lat, a.lng, CHIP_OFFSETS[a.anchor] ?? DEFAULT_CHIP_OFFSET, CHIP_W);
        const marker = L.marker([a.lat, a.lng], {
          icon: L.divIcon({
            className: '',
            html: chipHtml(chip),
            iconSize: [CHIP_W, CHIP_H],
            iconAnchor: offset,
          }),
          keyboard: false,
          title: `${a.viewable.length} licensed files · ${a.label}`,
        }).addTo(group);
        const mine: Readout = { kind: 'media', anchor: a.anchor };
        marker.on('mouseover', () => showReadout(mine));
        marker.on('mouseout', () => clearReadout(mine));
        marker.on('click', () => {
          showReadout(mine);
          openViewerRef.current(a.anchor);
        });
        return { lat: a.lat, lng: a.lng, offset, w: CHIP_W };
      };

      const drawAggregate = (members: MarkPoint[]): RenderedMark => {
        const lat = members.reduce((s, p) => s + p.lat, 0) / members.length;
        const lng = members.reduce((s, p) => s + p.lng, 0) / members.length;
        const nSites = members.filter((p) => p.kind === 'site').length;
        const media = members.filter((p): p is Extract<MarkPoint, { kind: 'media' }> => p.kind === 'media');
        // "n SITES" and not "n PRE|POST": an aggregate may say how many marks
        // are under it and must not say what each of them holds, because some
        // of them hold the absence of a pass.
        const label = nSites === 0
          ? `IMG ${media.reduce((s, p) => s + p.anchor.viewable.length, 0)}`
          : `${nSites} SITE${nSites === 1 ? '' : 'S'}${media.length > 0 ? ' · IMG' : ''}`;
        const offset = slot(lat, lng, [CLUSTER_W / 2, CHIP_H / 2], CLUSTER_W);
        const marker = L.marker([lat, lng], {
          icon: L.divIcon({
            className: '',
            html: chipHtml(label, INFO),
            iconSize: [CLUSTER_W, CHIP_H],
            iconAnchor: offset,
          }),
          keyboard: false,
          title: `${members.length} marks at this point · click to separate`,
        }).addTo(group);
        const mine: Readout = {
          kind: 'cluster',
          members: members.map((p) => ({ kind: p.kind, key: p.key })),
        };
        marker.on('mouseover', () => showReadout(mine));
        marker.on('mouseout', () => clearReadout(mine));
        marker.on('click', () => {
          showReadout(mine);
          map.setView([lat, lng], expansionZoom(map, members, map.getZoom()));
        });
        return { lat, lng, offset, w: CLUSTER_W };
      };

      // Past MAX_EXPANSION_ZOOM an aggregate has nowhere left to expand to:
      // clicking it would setView to the zoom it is already at, fire no zoomend,
      // and strand its members behind a chip that does nothing. Beyond that
      // depth every mark is drawn individually and the slot() column below
      // absorbs any residual overlap. Offset pairs keep their pairing at all
      // zooms because they are genuinely the same point.
      const atMaxDepth = map.getZoom() >= MAX_EXPANSION_ZOOM;

      groupMarks(map, markPoints(sitesRef.current, anchorsRef.current), map.getZoom()).forEach((g) => {
        if (g.length === 1 || isOffsetPair(g) || atMaxDepth) {
          g.forEach((p) => {
            rendered.push(p.kind === 'site' ? drawSite(p.site) : drawMedia(p.anchor));
          });
          return;
        }
        rendered.push(drawAggregate(g));
      });

      renderedMarksRef.current = rendered;
      // Both of these read what was just drawn, so they run after it and in
      // this order: the gauge pins share the marker pane, and the labels are
      // placed around the marks.
      drawDhmRef.current?.();
      placeLabelsRef.current?.();
    };

    placeMarksRef.current = placeMarks;
    placeMarks();
    map.on('zoomend', placeMarks);
    // Keyed on both signatures so a replay step re-clusters: a group gains and
    // loses members as sites and files enter the window. `ready` is in the deps
    // because either query can resolve before the map exists.
    return () => { map.off('zoomend', placeMarks); };
  }, [anchorSignature, siteSignature, ready, showReadout, clearReadout]);

  // THE RESPONSE SITES. Burial grounds, DNA hubs, mortuaries, transfer points,
  // recovery reaches, the highway cut, the airhead and the flooded tunnels —
  // each a dot at its published position and a chip with its figure. Sites
  // that fall within PLACE_CLUSTER_PX of each other at the current zoom
  // (four sit inside Kathmandu) collapse to one chip that zooms to them.
  useEffect(() => {
    const map = mapRef.current;
    const group = placesRef.current;
    if (!map || !group) return;
    const placePlaces = () => {
      group.clearLayers();
      if (!showSites || places.length === 0) return;
      const pts = places.map((s) => ({ s, p: map.latLngToLayerPoint([s.lat, s.lng]) }));
      const clusters: { members: typeof pts; cx: number; cy: number }[] = [];
      pts.forEach((pt) => {
        const g = clusters.find((c) => Math.hypot(c.cx - pt.p.x, c.cy - pt.p.y) < PLACE_CLUSTER_PX);
        if (g) g.members.push(pt);
        else clusters.push({ members: [pt], cx: pt.p.x, cy: pt.p.y });
      });
      const toneColor = (t: ReturnType<typeof siteChip>['tone']) =>
        t === 'critical' ? CRITICAL : t === 'high' ? HIGH : t === 'low' ? LOW : t === 'info' ? INFO : BORDER_DEFAULT;
      clusters.forEach((c) => {
        if (c.members.length === 1) {
          const site = c.members[0].s;
          const chip = siteChip(site);
          const color = toneColor(chip.tone);
          const dot = L.circleMarker([site.lat, site.lng], {
            radius: site.coord_confidence === 'published' ? 3.5 : 3,
            color, weight: 1.2, fillColor: color,
            fillOpacity: site.coord_confidence === 'published' || site.coord_confidence === 'place' ? 0.95 : 0.35,
          }).addTo(group);
          const label = `${chip.label}${site.photos.length ? ` · IMG ${site.photos.length}` : ''}`;
          const w = Math.max(CHIP_W, label.length * 5.6 + 10);
          const marker = L.marker([site.lat, site.lng], {
            icon: L.divIcon({ className: '', html: chipHtml(label, color), iconSize: [w, CHIP_H], iconAnchor: [-6, -5] }),
            keyboard: false,
            title: site.name,
          }).addTo(group);
          const mine: Readout = { kind: 'place', key: site.key };
          [dot, marker].forEach((m) => {
            m.on('mouseover', () => showReadout(mine));
            m.on('mouseout', () => clearReadout(mine));
            m.on('click', () => { showReadout(mine); map.setView([site.lat, site.lng], Math.max(map.getZoom(), 11)); });
          });
        } else {
          const lat = c.members.reduce((a, m) => a + m.s.lat, 0) / c.members.length;
          const lng = c.members.reduce((a, m) => a + m.s.lng, 0) / c.members.length;
          const worst = c.members.some((m) => m.s.kind === 'burial') ? CRITICAL
            : c.members.some((m) => ['forensic', 'mortuary', 'road_cut', 'tunnel_suspended'].includes(m.s.kind)) ? HIGH : INFO;
          const label = `${c.members.length} RESP SITES`;
          const cw = label.length * 5.6 + 10;
          const marker = L.marker([lat, lng], {
            icon: L.divIcon({ className: '', html: chipHtml(label, worst), iconSize: [cw, CHIP_H], iconAnchor: [cw + 6, -5] }),
            keyboard: false,
            title: c.members.map((m) => m.s.name).join(' · '),
          }).addTo(group);
          marker.on('click', () => {
            map.fitBounds(L.latLngBounds(c.members.map((m) => [m.s.lat, m.s.lng] as L.LatLngTuple)), { padding: [40, 40], maxZoom: 13 });
          });
        }
      });
    };
    placePlaces();
    map.on('zoomend', placePlaces);
    return () => { map.off('zoomend', placePlaces); };
  }, [places, showSites, ready, showReadout, clearReadout]);

  // The Vantor footprints. Outlines and nothing else: this layer answers "which
  // ground did the 30–50 cm strips actually cover", which is the only claim a
  // browse image can support without a tile server behind it.
  const vantorItems = vantor.data?.items;
  useEffect(() => {
    const map = mapRef.current;
    const group = vantorRef.current;
    if (!map || !group) return;

    group.clearLayers();

    if (showFootprints && vantorItems) {
      vantorItems.forEach((item) => {
        const ring = footprintRing(item);
        if (!ring) return;
        const post = item.phase === 'post';
        const outline = L.polygon(ring, {
          color: INFO,
          weight: 1,
          // Post solid, pre dashed. Eleven post strips stack over the upper
          // corridor because that is how the collection was tasked; the layer
          // is opt-in and the hover disambiguates, so they are drawn as they are.
          opacity: post ? 0.7 : 0.4,
          dashArray: post ? undefined : '2 4',
          // fill:false rather than fillOpacity:0 — an SVG path that has a fill
          // is a pointer target across its whole interior however transparent
          // it is, and these polygons would then swallow every district hover
          // beneath the corridor. With no fill at all only the outline answers.
          fill: false,
        }).addTo(group);
        // The five-line card this outline needs — date, cloud, baseline gap,
        // what it sees and its attribution — never fitted beside the cursor at
        // the widget's shortest usable height. In the fixed panel it always
        // does, and the attribution line survives a screenshot of the hover,
        // which is the condition the licence is granted on.
        const mine: Readout = { kind: 'footprint', item };
        outline.on('mouseover', () => showReadout(mine));
        outline.on('mouseout', () => clearReadout(mine));
      });
      if (!map.hasLayer(group)) group.addTo(map);
    } else if (map.hasLayer(group)) {
      map.removeLayer(group);
    }
  }, [showFootprints, vantorItems, ready, showReadout, clearReadout]);

  /**
   * The map's frame, sampled only while the overlay is on. Every sample is a
   * full-frame render off a shared disaster-response service, so this is where
   * the cost is controlled: nothing is read when the layer is off, and a drag
   * or a wheel-zoom settles before anything is asked for.
   */
  const imageryOn = imagery != null;
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !imageryOn) {
      setFrame(null);
      return;
    }
    let timer: number | undefined;
    const sample = () => {
      const b = map.getBounds();
      const size = map.getSize();
      const next = {
        zoom: map.getZoom(),
        box: { south: b.getSouth(), west: b.getWest(), north: b.getNorth(), east: b.getEast() },
        w: size.x,
        h: size.y,
      };
      // Compared by value: a ResizeObserver tick that changed nothing must not
      // look like a new frame and re-request the same picture.
      setFrame((prev) =>
        prev &&
        prev.zoom === next.zoom &&
        prev.w === next.w &&
        prev.h === next.h &&
        prev.box.south === next.box.south &&
        prev.box.west === next.box.west &&
        prev.box.north === next.box.north &&
        prev.box.east === next.box.east
          ? prev
          : next);
    };
    const schedule = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(sample, 220);
    };
    sample();
    map.on('moveend zoomend resize', schedule);
    return () => {
      window.clearTimeout(timer);
      map.off('moveend zoomend resize', schedule);
    };
  }, [imageryOn, ready]);

  const rasters = catalog.data?.rasters;
  const rasterById = useMemo(() => {
    const byId = new Map<string, DrpRaster>();
    (rasters ?? []).forEach((r) => byId.set(r.stac_id, r));
    return byId;
  }, [rasters]);

  // The pixels. Registered by construction: the bbox is the map's own bounds
  // projected into the CRS Leaflet draws in, and the pixel size is an integer
  // multiple of the container, so the service pads nothing and the frame lands
  // exactly where it was asked for.
  useEffect(() => {
    const map = mapRef.current;
    const group = drpRef.current;
    if (!map || !group) return;

    const clearPixels = () => {
      group.clearLayers();
      drpImageRef.current = null;
      if (map.hasLayer(group)) map.removeLayer(group);
    };

    if (!imagery || !catalog.data) {
      clearPixels();
      return;
    }
    if (!frame) return;

    if (frame.zoom < DRP_MIN_ZOOM) {
      clearPixels();
      setImageryStatus('zoom');
      setImageryCaption(null);
      return;
    }

    const cover = coverFrame(
      vantorItems ?? [],
      footprintRing,
      (item) => rasterById.get(item.id)?.gsd_m ?? null,
      imagery,
      frame.box,
    );

    if (!cover.top) {
      // Coverage is decided here, from our own footprints, and never from the
      // response: a frame with nothing under it comes back as a fully
      // transparent PNG with HTTP 200, so onError never fires and a blank
      // canvas would read as ground with no damage on it.
      clearPixels();
      setImageryStatus('nocover');
      setImageryCaption(null);
      return;
    }

    const crs = map.options.crs ?? L.CRS.EPSG3857;
    const nw = crs.project(L.latLng(frame.box.north, frame.box.west));
    const se = crs.project(L.latLng(frame.box.south, frame.box.east));
    // An integer multiple of the container's pixel box, so the requested aspect
    // matches the projected bbox exactly. A ratio off by a rounded pixel makes
    // the service pad the bbox, and a padded frame drawn at the bounds we asked
    // for is a registration error.
    const dpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1;
    const retina = dpr >= 2 && frame.w * 2 <= DRP_MAX_PIXELS && frame.h * 2 <= DRP_MAX_PIXELS;
    const factor = retina ? 2 : 1;
    const url = exportImageUrl({
      serviceUrl: catalog.data.service_url,
      event: catalog.data.event,
      phase: imagery,
      bbox: [nw.x, se.y, se.x, nw.y],
      width: frame.w * factor,
      height: frame.h * factor,
    });

    const raster = rasterById.get(cover.top.id) ?? null;
    setImageryStatus('loading');
    setImageryCaption({
      id: cover.top.id,
      day: formatSceneDay(cover.top.datetime),
      gsdM: cover.gsd,
      platform: raster?.platform ?? null,
      cloud: cover.top.cloud,
      inView: cover.inView,
      fullFrame: cover.fullFrame,
      // Pre frames are 2021–2024 archive passes; a reader shown PRE beside POST
      // assumes days unless the gap is spelled out.
      baselineGap: imagery === 'pre' ? baselineGap(cover.top.datetime) : null,
    });

    // Decoded before it is placed. A frame that never arrives leaves the last
    // good one on the canvas and says so in the banner, rather than flashing a
    // broken image or a hole where the basemap used to be.
    let cancelled = false;
    const probe = new Image();
    probe.decoding = 'async';
    probe.onload = () => {
      if (cancelled) return;
      const bounds = L.latLngBounds(
        [frame.box.south, frame.box.west],
        [frame.box.north, frame.box.east],
      );
      const layer = L.imageOverlay(url, bounds, {
        pane: DRP_PANE,
        interactive: false,
      }).addTo(group);
      const previous = drpImageRef.current;
      drpImageRef.current = layer;
      if (previous) group.removeLayer(previous);
      if (!map.hasLayer(group)) group.addTo(map);
      setImageryStatus('ok');
    };
    probe.onerror = () => {
      if (!cancelled) setImageryStatus('failed');
    };
    probe.src = url;

    return () => {
      cancelled = true;
      probe.onload = null;
      probe.onerror = null;
    };
  }, [imagery, frame, catalog.data, vantorItems, rasterById, ready]);

  // The DHM gauge photographs. Verified upstream — a station reaches this list
  // only once its URL actually returned image bytes — so a pin never opens onto
  // a dead link that the desk had no way of knowing was dead.
  const verifiedStations = useMemo(
    () => (photos.data?.stations ?? []).filter((s) => s.verified),
    [photos.data],
  );
  const pauseRef = useRef(replay.pause);
  pauseRef.current = replay.pause;

  useEffect(() => {
    const map = mapRef.current;
    const group = dhmRef.current;
    if (!map || !group) return;

    const draw = () => {
      group.clearLayers();
      if (!showDhm || verifiedStations.length === 0) return;
      const detail = map.getZoom() >= DHM_DETAIL_ZOOM;
      dhmDetailRef.current = detail;
      const size = detail ? DHM_PIN : DHM_PIN_QUIET;
      verifiedStations.forEach((station) => {
        const marker = L.marker([station.lat, station.lng], {
          icon: L.divIcon({
            className: '',
            html: dhmPinHtml(detail),
            iconSize: [size, size],
            iconAnchor: [size / 2, size / 2],
          }),
          keyboard: false,
          // Under the chips. Both live in the marker pane and both want the
          // click; the chip is the one a reader came for, and Leaflet ranks
          // markers by latitude unless told otherwise.
          zIndexOffset: -1000,
          title: `${station.name} · DHM station photograph`,
        }).addTo(group);
        const mine: Readout = { kind: 'gauge', id: station.bipad_id };
        marker.on('mouseover', () => showReadout(mine));
        marker.on('mouseout', () => clearReadout(mine));
        marker.on('click', () => {
          showReadout(mine);
          // Same rule as the media chips: looking at a picture pauses the clock
          // without moving it.
          pauseRef.current();
          setPhoto(station);
        });
      });
    };

    draw();
    // Redrawn from the marks placer's zoomend tick rather than a listener of
    // its own — one listener, and the pins are already in that pass's pane.
    // Only when the size class actually changes: 31 markers rebuilt on every
    // wheel notch would churn the pane for nothing.
    drawDhmRef.current = () => {
      if (!showDhm) return;
      if ((map.getZoom() >= DHM_DETAIL_ZOOM) === dhmDetailRef.current) return;
      draw();
    };

    if (showDhm && verifiedStations.length > 0) {
      if (!map.hasLayer(group)) group.addTo(map);
    } else if (map.hasLayer(group)) {
      map.removeLayer(group);
    }

    return () => { drawDhmRef.current = null; };
  }, [showDhm, verifiedStations, ready, showReadout, clearReadout]);

  // On a phone card the widget is barely 160 px of content: map, transport and
  // two footer blocks cannot all fit, and splitting the difference gives a map
  // of zero height. Below this the footer goes — its authority and date are
  // already on the transport's own line, and the deaths note is the situation
  // widget's to carry — so the map keeps a usable frame.
  const COMPACT_BELOW = 220;
  // Below this the imagery caption cannot float in a corner without covering
  // most of the frame it is captioning.
  const NARROW_BELOW = 520;
  const columnRef = useRef<HTMLDivElement>(null);
  const [compact, setCompact] = useState(false);
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    const el = columnRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver((entries) => {
      const box = entries[0]?.contentRect;
      const height = box?.height ?? 0;
      const width = box?.width ?? 0;
      if (height > 0) setCompact(height < COMPACT_BELOW);
      if (width > 0) setNarrow(width < NARROW_BELOW);
    });
    observer.observe(el);
    return () => observer.disconnect();
    // Keyed on `ready`: the column does not exist during the loading state, so
    // a mount-only effect would observe nothing and never run again.
  }, [ready]);

  // At the compact height the map frame is ~100 px and a 248 px panel covers
  // most of it; on a narrow pane it covers the corner the imagery caption needs
  // and too much of the frame besides. Below either threshold the district
  // labels, the chip titles and the footer carry the same data.
  const showPanel = !compact && !narrow;

  const resetView = useCallback(() => {
    const map = mapRef.current;
    const bounds = homeBoundsRef.current;
    if (map && bounds?.isValid()) map.fitBounds(bounds, { padding: HOME_PADDING });
  }, []);

  // Km 0 of the corridor the endpoint serves — the border post — rather than a
  // coordinate typed in here. It is the one frame where the pre and post passes
  // both cover the ground and the difference between them is the whole event.
  const borderPost = useMemo(() => corridor.find((w) => w.km === 0) ?? null, [corridor]);
  const goToBorderPost = useCallback(() => {
    const map = mapRef.current;
    if (map && borderPost) map.setView([borderPost.lat, borderPost.lng], SITE_ZOOM);
  }, [borderPost]);

  const icon = <MapIcon size={14} />;

  if (geo.isLoading) {
    return (
      <Widget id="flood-district-map" icon={icon}>
        <WidgetSkeleton />
      </Widget>
    );
  }

  if (geo.error || !geo.data) {
    return (
      <Widget id="flood-district-map" icon={icon}>
        <WidgetError message="Failed to load district geometry" onRetry={() => geo.refetch()} />
      </Widget>
    );
  }

  if (!ready) {
    return (
      <Widget id="flood-district-map" icon={icon}>
        <WidgetEmpty message="No districts named in the current bulletin" />
      </Widget>
    );
  }

  const withCounts = features.filter((f) => f.properties.bodies_recovered != null).length;
  const mediaCount = (media.data?.items ?? []).filter((i) => i.anchor).length;
  const vantorCount = vantorItems?.length ?? 0;
  // CC BY-NC is a condition, not a courtesy: the moment Vantor geometry is on
  // the canvas the credit is on the page too.
  const vantorCredit = showFootprints && vantorCount > 0
    ? `${vantorCount} vantor scene footprints · ${vantor.data?.license ?? 'CC-BY-NC-4.0'}${
        vantor.data?.source === 'fallback' ? ' · stac unreachable, verified manifest' : ''
      }`
    : null;
  // The banner over the canvas carries the short credit; the full attribution
  // string the API hands down rides here, in the footer a screenshot of the
  // whole widget keeps.
  const imageryCredit = imagery && catalog.data
    ? `${imagery}-event imagery · ${catalog.data.attribution}`
    : null;
  const dhmCredit = showDhm && verifiedStations.length > 0
    ? `${verifiedStations.length} dhm gauge photographs · via bipad portal · undated`
    : null;
  // Every line a layer on the canvas is licensed on. Never truncated away.
  const layerCredits = [vantorCredit, imageryCredit, dhmCredit].filter(Boolean) as string[];

  // What the frame covers, counted off the same data the canvas drew from —
  // the metadata half of the source line, never a typed figure.
  const deskMeta = [
    `${withCounts} of ${features.length} districts carry a recovered count`,
    mediaCount > 0 ? `${mediaCount} licensed files · wikimedia commons` : null,
    sites.length > 0
      ? `${sites.length} damage sites · click a blue chip for the same-frame pre/post pair`
      : null,
    places.length > 0
      ? `${places.length} response sites · ${sitesQ.data?.counts.burial ?? 0} burial grounds · ${sitesQ.data?.counts.photos ?? 0} photographs by caption match`
      : null,
    corridor.some((w) => w.kind === 'channel') ? 'river: openstreetmap channel, odbl' : null,
    'boundaries: survey department reference',
  ]
    .filter(Boolean)
    .join(' · ');

  const gsdRange = catalog.data?.gsd_range_m;
  const imageryTitle = gsdRange
    ? `${imagery ? 'Hide' : 'Show'} Vantor imagery at ${Math.round(gsdRange[0] * 100)}–${Math.round(
        gsdRange[1] * 100,
      )} cm (zoom ${DRP_MIN_ZOOM}+, CC BY-NC 4.0)`
    : `${imagery ? 'Hide' : 'Show'} high-resolution Vantor imagery`;

  // The transport's honesty line: which dated bulletin the fills came from, or
  // the sentence that says no district breakdown existed yet.
  const fillsLabel = replay.isLive
    ? latest?.authority && latest?.as_of
      ? `FILLS: ${latest.authority} AS OF ${dtgDay(latest.as_of)}`
      : 'FILLS: LATEST BULLETIN'
    : replay.snapshot
      ? `FILLS: ${replay.snapshot.authority ?? 'NDRRMA'} AS OF ${dtgDay(replay.snapshot.as_of)}`
      : 'NO DISTRICT BREAKDOWN PUBLISHED YET';

  return (
    <Widget
      id="flood-district-map"
      icon={icon}
      badge={`${features.length} DISTRICTS`}
      badgeVariant="critical"
      actions={
        <>
          {(catalog.data?.count ?? 0) > 0 && (
            <button
              type="button"
              className="widget-action"
              // Opens on POST: the reader who asks for imagery on a flood desk
              // is asking what the water did, and the baseline is one click
              // away in the banner.
              onClick={() => setImagery((phase) => (phase ? null : 'post'))}
              title={imageryTitle}
              aria-label="Toggle high-resolution Vantor imagery"
              aria-pressed={imagery != null}
              style={imagery ? { color: 'var(--status-info)' } : undefined}
            >
              <Layers size={11} />
            </button>
          )}
          {places.length > 0 && (
            <button
              type="button"
              className="widget-action"
              onClick={() => setShowSites((on) => !on)}
              title={`${showSites ? 'Hide' : 'Show'} response sites (${places.length}: burials, DNA hubs, transfer points, tunnels)`}
              aria-label="Toggle response sites"
              aria-pressed={showSites}
              style={showSites ? { color: 'var(--status-info)' } : undefined}
            >
              <Crosshair size={11} />
            </button>
          )}
          {verifiedStations.length > 0 && (
            <button
              type="button"
              className="widget-action"
              onClick={() => setShowDhm((on) => !on)}
              // Only rendered when something verified: a toggle that could
              // never show anything would be a cut corner, and on the day DHM's
              // links go dead again this button goes with them.
              title={`${showDhm ? 'Hide' : 'Show'} DHM gauge photographs (${verifiedStations.length} verified)`}
              aria-label="Toggle DHM gauge-site photographs"
              aria-pressed={showDhm}
              style={showDhm ? { color: 'var(--status-info)' } : undefined}
            >
              <Camera size={11} />
            </button>
          )}
          {vantorCount > 0 && (
            <button
              type="button"
              className="widget-action"
              onClick={() => setShowFootprints((on) => !on)}
              // No control for a layer with nothing behind it: if the STAC
              // endpoint is down the map is complete without it and the
              // failure stays invisible.
              title={`${showFootprints ? 'Hide' : 'Show'} Vantor scene footprints (${vantorCount} scenes, CC BY-NC 4.0)`}
              aria-label="Toggle Vantor scene footprints"
              aria-pressed={showFootprints}
              style={showFootprints ? { color: 'var(--status-info)' } : undefined}
            >
              <Satellite size={11} />
            </button>
          )}
          <button
            type="button"
            className="widget-action"
            onClick={resetView}
            title="Reset to the corridor frame"
            aria-label="Reset map to the corridor frame"
          >
            <Locate size={11} />
          </button>
        </>
      }
    >
      <div
        ref={columnRef}
        style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0, position: 'relative' }}
      >
        {/* The banner is positioned against the map alone, never the column, so
            a bottom-anchored caption lands on the canvas rather than over the
            transport bar. */}
        <div style={{ position: 'relative', flex: '1 1 0', minHeight: 100, display: 'flex' }}>
          <div
            ref={containerRef}
            style={{ flex: '1 1 0', minWidth: 0, minHeight: 0, background: 'var(--bg-base)' }}
          />

        {/* Over the canvas rather than under it: a screenshot of the frame has
            to keep the phase, the acquisition date and the licence, or the
            picture leaves this desk uncaptioned. */}
        {imagery && catalog.data && (
          <FloodImageryBanner
            phase={imagery}
            onPhase={setImagery}
            status={imageryStatus}
            caption={imageryCaption}
            credit={IMAGERY_CREDIT}
            licenseUrl={catalog.data.license_url}
            minZoom={DRP_MIN_ZOOM}
            onGoToSite={borderPost ? goToBorderPost : null}
            compact={compact || narrow}
            narrow={narrow}
          />
        )}

        {/* The readout. Bottom-left, where the legend control used to sit, and
            at rest it IS that legend — so the corner never blanks and a reader
            only ever has to learn one place to look. */}
        {showPanel && (
          <ReadoutPanel
            readout={readout}
            view={view}
            sites={sites}
            places={places}
            kindText={kindText}
            anchors={anchors}
            stations={verifiedStations}
            eventName={event?.name ?? null}
            eventCause={event?.cause ?? null}
            eventStarted={formatEventDate(event?.started_on)}
            imageryDrawn={muteFill}
            footprintsOn={showFootprints}
            dhmCount={showDhm ? verifiedStations.length : 0}
          />
        )}
        </div>

        {replay.available && <FloodReplayBar replay={replay} fillsLabel={fillsLabel} />}

        {/* The viewers are inset overlays at z-index 1100, so they sit here —
            ahead of the footer in the DOM — only so the widget can end on its
            one source line. They cover the column either way. */}
        {activeAnchor && viewer && (
          <FloodMediaViewer
            items={activeAnchor.viewable}
            index={viewer.index}
            anchorLabel={activeAnchor.label}
            linkOuts={activeAnchor.links}
            categoryUrl={media.data?.commons_ok ? media.data.category_url : null}
            onIndex={(index) => setViewer({ anchor: activeAnchor.anchor, index })}
            onClose={() => setViewer(null)}
            onFail={markMediaFailed}
          />
        )}

        {activeSite && damage.data && (
          <FloodDamageSiteViewer
            site={activeSite}
            data={damage.data}
            onClose={() => setSiteKey(null)}
            onGoToMap={() => {
              setSiteKey(null);
              mapRef.current?.setView([activeSite.lat, activeSite.lng], SITE_ZOOM);
            }}
          />
        )}

        {photo && photos.data && (
          <FloodStationPhotoViewer
            station={photo}
            attribution={photos.data.attribution}
            note={photos.data.note}
            onClose={() => setPhoto(null)}
          />
        )}

        {/* NDRRMA's own explanation of the inversion, in its words. Dropped at
            phone height, where the map is the whole product. */}
        {!compact && deathsNote && (
          <div style={{ flexShrink: 0, padding: '0 12px' }}>
            <Note>{deathsNote}</Note>
          </div>
        )}

        {/* Every line a layer on the canvas is licensed on. Wrapped rather than
            clipped, and never dropped at phone height: the layers are on the
            canvas either way. */}
        {layerCredits.length > 0 && (
          <div style={{ flexShrink: 0, padding: '0 12px' }}>
            <Note>{layerCredits.join(' · ')}</Note>
          </div>
        )}

        <div style={{ flexShrink: 0, padding: '0 12px 6px' }}>
          <SourceLine
            source={latest?.authority ?? null}
            asOf={latest?.as_of ? dtgDay(latest.as_of) : null}
            url={latest?.source_url}
            right={
              compact ? undefined : (
                <span
                  title={deskMeta}
                  style={{
                    ...LABEL_XS,
                    minWidth: 0,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    textAlign: 'right',
                  }}
                >
                  {deskMeta}
                </span>
              )
            }
          />
        </div>
      </div>
    </Widget>
  );
});
