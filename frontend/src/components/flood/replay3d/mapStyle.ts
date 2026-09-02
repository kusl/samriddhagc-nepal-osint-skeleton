/**
 * The MapLibre style the OPERATIONAL PICTURE · 3D renders on: terrain, imagery,
 * an optional NASA flood-water raster and the sky. Nothing event-specific lives
 * here — no coordinates, no dates, no figures. The style is the ground the
 * replay is drawn on; the replay itself is GeoJSON added by the component.
 *
 * Why the style is built in code rather than fetched:
 *   - a hosted style would pull a basemap whose colours fight the desk palette,
 *     and would put a third-party tile server between the reader and the
 *     picture with no attribution the desk controls;
 *   - the three raster sources here are the only ones the picture needs, and
 *     each carries its own attribution string so the map's own control credits
 *     them without a widget having to type the credit out.
 *
 * The palette is READ from the dashboard's CSS custom properties at runtime, so
 * the map's tints are the same tokens milspec.tsx paints text with. GL paint
 * properties cannot hold a `var()`, so the values are resolved once against a
 * live element and passed in; the fallbacks below are only for the case where
 * the stylesheet has not applied yet (a detached container during a test).
 */

// ------------------------------------------------------------------ ids

export const TERRAIN_SOURCE = 'terrain';
export const IMAGERY_SOURCE = 'imagery';
export const GIBS_SOURCE = 'gibs-flood';

export const LAYER_BACKGROUND = 'bg';
export const LAYER_IMAGERY = 'imagery-raster';
export const LAYER_GIBS = 'gibs-raster';
export const LAYER_HILLSHADE = 'terrain-hillshade';
export const LAYER_SKY = 'sky';

/** Exaggeration the picture is composed for: the corridor's relief is real but
 *  shallow at 1:1, and a flood front reads as a front only when the valley it
 *  runs down has walls. Stated on screen wherever the terrain is credited. */
export const TERRAIN_EXAGGERATION = 1.15;

export const TERRAIN_ATTRIBUTION = 'Terrain: Mapzen/AWS Terrain Tiles';
export const IMAGERY_ATTRIBUTION = 'Imagery: Esri, Maxar, Earthstar Geographics';
export const GIBS_ATTRIBUTION = 'Flood water: NASA GIBS VIIRS Combined Flood 3-Day';

const TERRAIN_TILES = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png';
const IMAGERY_TILES =
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';

/**
 * VIIRS Combined Flood 3-Day, WMTS/REST, EPSG:3857. The product is a DAILY
 * composite: the date segment is a day, never an instant, and the layer is a
 * three-day running combination — so what it paints at a given date includes
 * water seen up to two days earlier. The widget labels it as such.
 */
export function gibsTiles(date: string): string[] {
  return [
    `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_Combined_Flood_3-Day/default/${date}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.png`,
  ];
}

// ------------------------------------------------------------------ palette

export interface MapPalette {
  base: string;
  surface: string;
  hairline: string;
  text: string;
  sub: string;
  muted: string;
  critical: string;
  high: string;
  medium: string;
  low: string;
  info: string;
}

const FALLBACK: MapPalette = {
  base: '#0a0a0b',
  surface: '#111113',
  hairline: '#27272a',
  text: '#fafafa',
  sub: '#a1a1aa',
  muted: '#71717a',
  critical: '#ef4444',
  high: '#f97316',
  medium: '#eab308',
  low: '#22c55e',
  info: '#3b82f6',
};

const VARS: Record<keyof MapPalette, string> = {
  base: '--bg-base',
  surface: '--bg-surface',
  hairline: '--border-subtle',
  text: '--text-primary',
  sub: '--text-secondary',
  muted: '--text-muted',
  critical: '--status-critical',
  high: '--status-high',
  medium: '--status-medium',
  low: '--status-low',
  info: '--status-info',
};

/**
 * Resolve the desk tokens against a live element. Returns the fallbacks when
 * the document has no computed style to give (SSR, a detached node, a browser
 * that refuses the call) rather than throwing into map construction.
 */
export function readMapPalette(el: Element | null): MapPalette {
  if (!el || typeof window === 'undefined' || typeof window.getComputedStyle !== 'function') {
    return { ...FALLBACK };
  }
  try {
    const cs = window.getComputedStyle(el);
    const out = { ...FALLBACK };
    (Object.keys(VARS) as Array<keyof MapPalette>).forEach((k) => {
      const v = cs.getPropertyValue(VARS[k]).trim();
      if (v) out[k] = v;
    });
    return out;
  } catch {
    return { ...FALLBACK };
  }
}

// ------------------------------------------------------------------ style

/** Loose structural types: the component casts this once when handing it to
 *  MapLibre, so the style spec's own generics never leak into the widget. */
export type StyleLayerDef = Record<string, unknown>;
export type StyleSourceDef = Record<string, unknown>;

export interface ReplayMapStyle {
  version: 8;
  name: string;
  glyphs?: string;
  sources: Record<string, StyleSourceDef>;
  layers: StyleLayerDef[];
  terrain?: { source: string; exaggeration: number };
  light?: Record<string, unknown>;
  sky?: Record<string, unknown>;
}

export interface ReplayStyleOptions {
  /** Day (YYYY-MM-DD) the GIBS composite is requested for. The source exists
   *  from the first frame so a toggle never has to rebuild the style. */
  gibsDate: string;
  /** Resolved desk tokens — see readMapPalette. */
  palette?: MapPalette;
  /** GIBS starts hidden: it is a 250 m regional product and would otherwise be
   *  read as the flood's extent at the metre scale the terrain implies. */
  gibsVisible?: boolean;
}

export function buildReplayStyle(opts: ReplayStyleOptions): ReplayMapStyle {
  const p = opts.palette ?? FALLBACK;
  return {
    version: 8,
    name: 'operational-picture-3d',
    sources: {
      [TERRAIN_SOURCE]: {
        type: 'raster-dem',
        tiles: [TERRAIN_TILES],
        encoding: 'terrarium',
        tileSize: 256,
        // 13 is ~10 m at this latitude; finer mesh tiles cost frames and show nothing the imagery does not.
        maxzoom: 13,
        attribution: TERRAIN_ATTRIBUTION,
      },
      [IMAGERY_SOURCE]: {
        type: 'raster',
        tiles: [IMAGERY_TILES],
        tileSize: 256,
        maxzoom: 19,
        attribution: IMAGERY_ATTRIBUTION,
      },
      [GIBS_SOURCE]: {
        type: 'raster',
        tiles: gibsTiles(opts.gibsDate),
        tileSize: 256,
        maxzoom: 9,
        attribution: GIBS_ATTRIBUTION,
      },
    },
    // Terrain is declared in the style as well as set imperatively after load:
    // declaring it here means the first painted frame is already in relief
    // instead of popping flat-to-3D a beat later.
    terrain: { source: TERRAIN_SOURCE, exaggeration: TERRAIN_EXAGGERATION },
    light: { anchor: 'viewport', color: '#ffffff', intensity: 0.35, position: [1.2, 200, 40] },
    // MapLibre (unlike Mapbox GL) has NO `sky` LAYER type — sky is a top-level
    // style property. Declaring it as a layer fails style validation and the
    // whole style is rejected, which paints nothing at all.
    sky: {
      'sky-color': p.base,
      'sky-horizon-blend': 0.55,
      'horizon-color': p.hairline,
      'horizon-fog-blend': 0.6,
      'fog-color': p.base,
      'fog-ground-blend': 0.72,
      'atmosphere-blend': ['interpolate', ['linear'], ['zoom'], 0, 0, 6, 0.5, 12, 0.15],
    },
    layers: [
      {
        id: LAYER_BACKGROUND,
        type: 'background',
        paint: { 'background-color': p.base },
      },
      {
        id: LAYER_IMAGERY,
        type: 'raster',
        source: IMAGERY_SOURCE,
        paint: {
          'raster-opacity': 1,
          // Imagery under a dark desk palette is otherwise the brightest thing
          // on the screen and the overlay reads as decoration on top of a
          // photograph. Held back so the drawn intelligence stays first.
          'raster-saturation': -0.35,
          'raster-contrast': 0.05,
          'raster-brightness-max': 0.86,
          'raster-fade-duration': 220,
        },
      },
      {
        id: LAYER_GIBS,
        type: 'raster',
        source: GIBS_SOURCE,
        layout: { visibility: opts.gibsVisible ? 'visible' : 'none' },
        paint: { 'raster-opacity': 0.55, 'raster-fade-duration': 0 },
      },
      {
        id: LAYER_HILLSHADE,
        type: 'hillshade',
        source: TERRAIN_SOURCE,
        paint: {
          'hillshade-exaggeration': 0.45,
          'hillshade-shadow-color': p.base,
          'hillshade-highlight-color': p.text,
          'hillshade-accent-color': p.hairline,
          'hillshade-illumination-anchor': 'viewport',
          'hillshade-illumination-direction': 315,
        },
      },
    ],
  };
}
