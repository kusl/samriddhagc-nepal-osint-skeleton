/**
 * The Vantor pixels, registered — what the browse strips could never be.
 *
 * Esri's Disaster Response Program publishes the same sixteen Nepal-Flooding
 * -Aug-2026 rasters our STAC already indexes behind an ImageServer that renders
 * an arbitrary bbox on demand. That is the whole difference: a browse strip is
 * a rotated scene squeezed into an axis-aligned frame and cannot be laid on a
 * basemap without asserting a registration we do not have, while exportImage
 * resamples into the projection we ask for and comes back registered by
 * construction. So the map can finally carry pixels.
 *
 * Every request here is made in EPSG:3857 — the CRS Leaflet already draws in —
 * rather than in 4326. The service pads a bbox whose aspect does not match the
 * requested pixel size, and a padded frame placed on the map at the bounds we
 * asked for would be off by the padding. Projected bounds against the map's own
 * pixel box match exactly, so nothing is padded and nothing shifts.
 *
 * The service is queried directly from the browser rather than proxied: the
 * images are large, public, unauthenticated and already cached by Esri's CDN,
 * and the one thing the backend has that we need — which scene the mosaic will
 * put on top — is answered here from footprints the desk already holds.
 *
 * The catalogue itself comes from our own /flood/imagery-catalog rather than
 * from the ImageServer: the DRP /query endpoint ignores geometry filters, and
 * its event_start_date is the date of the flood stamped on every raster, not an
 * acquisition date. Acquisition instants and cloud figures reach this file
 * through the STAC join the backend already made.
 */
import { useQuery } from '@tanstack/react-query';

import apiClient from '../../api/client';

/**
 * Below this the ground sample distance is thrown away — at zoom 13 a screen
 * pixel is ~19 m and the 0.3 m product resolves to nothing — and each pan would
 * cost a full-frame render off a shared disaster-response service for a picture
 * the reader cannot read. The overlay stays unrequested until the frame can
 * carry it.
 */
export const DRP_MIN_ZOOM = 14;

/** maxImageWidth/Height on the service is 5000; this leaves headroom. */
export const DRP_MAX_PIXELS = 4000;

export type DrpPhase = 'pre' | 'post';

export interface DrpRaster {
  objectid: number;
  /** The STAC id, parsed out of the raster name by the backend — the join key
   *  to the footprints and cloud figures in /flood/vantor. */
  stac_id: string;
  image_type: DrpPhase;
  /** lowps: the field the mosaic sorts on, so also the tie-break for which
   *  raster ends up on top of a frame. */
  gsd_m: number;
  platform: string | null;
  provider: string | null;
  /** From the STAC item. Never the catalog's event_start_date. */
  acquired: string | null;
  cloud: number | null;
  covers: string[];
  stac_matched: boolean;
}

export interface DrpCatalog {
  service_url: string;
  event: string;
  license: string;
  license_url: string;
  attribution: string;
  stac_attribution: string;
  source: { stac: string; drp_catalog: string };
  catalog_fetched_at: string | null;
  count: number;
  pre: number;
  post: number;
  gsd_range_m: [number, number];
  platforms: string[];
  providers: string[];
  rasters: DrpRaster[];
  note: string | null;
}

export function useDrpCatalog() {
  return useQuery<DrpCatalog>({
    queryKey: ['flood', 'imagery-catalog'] as const,
    queryFn: async () => (await apiClient.get('/flood/imagery-catalog')).data,
    // Sixteen rasters of a closed collection. The endpoint holds its own hour
    // cache and a vendored fallback, so refetching buys nothing.
    staleTime: 60 * 60 * 1000,
    retry: 1,
  });
}

/** Projected metres, [minX, minY, maxX, maxY], EPSG:3857. */
export type Bbox3857 = [number, number, number, number];

/**
 * The mosaic rule is the whole trick: one attribute filter over the event
 * separates the archive baseline from the post-event passes, and sorting the
 * survivors by lowps ascending puts the sharpest raster on top. Swap `phase`
 * over an unchanged bbox and the two frames are the same ground.
 */
export function exportImageUrl(opts: {
  serviceUrl: string;
  event: string;
  phase: DrpPhase;
  bbox: Bbox3857;
  width: number;
  height: number;
}): string {
  const { serviceUrl, event, phase, bbox, width, height } = opts;
  const mosaicRule = JSON.stringify({
    mosaicMethod: 'esriMosaicAttribute',
    where: `event='${event}' AND image_type='${phase}'`,
    sortField: 'lowps',
    ascending: true,
  });
  const params = new URLSearchParams({
    bbox: bbox.map((n) => n.toFixed(3)).join(','),
    bboxSR: '3857',
    imageSR: '3857',
    size: `${width},${height}`,
    // jpgpng, not jpg: where a frame runs past the edge of every footprint the
    // service returns a PNG with alpha there, so no-data stays transparent and
    // the basemap shows through instead of a black wedge claiming ground.
    format: 'jpgpng',
    f: 'image',
    mosaicRule,
  });
  return `${serviceUrl}/exportImage?${params.toString()}`;
}

/** A geographic box, in the order Leaflet reports bounds. */
export interface LatLngBox {
  south: number;
  west: number;
  north: number;
  east: number;
}

/** Ring vertices as [lat, lng] — what footprintRing() in vantorScenes returns. */
export type LatLngRing = [number, number][];

/** Ray casting on the raw published ring. The footprints are small enough and
 *  far enough from the antimeridian that planar arithmetic is exact here. */
export function pointInRing(lat: number, lng: number, ring: LatLngRing): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i, i += 1) {
    const [ai, aj] = [ring[i][0], ring[i][1]];
    const [bi, bj] = [ring[j][0], ring[j][1]];
    if (ai > lat !== bi > lat && lng < ((bj - aj) * (lat - ai)) / (bi - ai) + aj) inside = !inside;
  }
  return inside;
}

const segmentsCross = (
  p1: [number, number],
  p2: [number, number],
  q1: [number, number],
  q2: [number, number],
): boolean => {
  const cross = (o: [number, number], a: [number, number], b: [number, number]) =>
    (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const d1 = cross(q1, q2, p1);
  const d2 = cross(q1, q2, p2);
  const d3 = cross(p1, p2, q1);
  const d4 = cross(p1, p2, q2);
  return d1 * d2 < 0 && d3 * d4 < 0;
};

const boxCorners = (box: LatLngBox): [number, number][] => [
  [box.south, box.west],
  [box.south, box.east],
  [box.north, box.east],
  [box.north, box.west],
];

/**
 * Whether any of the ring's ground is inside the frame. All three cases are
 * tested rather than only the cheap one: a footprint far larger than a zoom-16
 * frame contains every corner and has no vertex in view, a footprint sliver
 * has vertices in view and contains no corner, and a strip crossing the frame
 * corner-to-corner does neither.
 */
export function ringIntersectsBox(ring: LatLngRing, box: LatLngBox): boolean {
  if (ring.length < 3) return false;
  if (ring.some(([lat, lng]) => lat >= box.south && lat <= box.north && lng >= box.west && lng <= box.east)) {
    return true;
  }
  const corners = boxCorners(box);
  if (corners.some(([lat, lng]) => pointInRing(lat, lng, ring))) return true;
  for (let i = 0; i < corners.length; i += 1) {
    const c1 = corners[i];
    const c2 = corners[(i + 1) % corners.length];
    for (let j = 0, k = ring.length - 1; j < ring.length; k = j, j += 1) {
      if (segmentsCross(c1, c2, ring[k], ring[j])) return true;
    }
  }
  return false;
}

export interface FrameCoverage<T> {
  /** The scene the mosaic rule will paint on top of this frame, or null when
   *  no scene of this phase covers any of it. */
  top: T | null;
  gsd: number | null;
  /** Every scene of this phase with ground in the frame — the mosaic under the
   *  top one. A caption speaks for `top` alone, so the count has to be shown. */
  inView: number;
  /** false when a corner of the frame falls outside every footprint: part of
   *  what renders will be no-data, which is absence of imagery and not ground. */
  fullFrame: boolean;
}

/**
 * Which scene ends up on top of this frame, computed the way the service will
 * compute it: filter to the phase, keep what covers the frame, sharpest wins.
 *
 * Scenes covering the centre are preferred over scenes that merely graze a
 * corner, because the caption is read as describing the middle of the picture.
 * A 0.34 m strip clipping one corner would otherwise date and grade a frame
 * whose subject it never saw.
 */
export function coverFrame<T extends { id: string; phase: string }>(
  items: T[],
  ringOf: (item: T) => LatLngRing | null,
  gsdOf: (item: T) => number | null,
  phase: DrpPhase,
  box: LatLngBox,
): FrameCoverage<T> {
  const candidates: { item: T; ring: LatLngRing; gsd: number }[] = [];
  items.forEach((item) => {
    if (item.phase !== phase) return;
    const ring = ringOf(item);
    if (!ring || !ringIntersectsBox(ring, box)) return;
    // Missing from the DRP catalogue means the service will not draw it, so it
    // cannot be the top raster; sorted last rather than dropped, since it still
    // proves the ground was flown.
    candidates.push({ item, ring, gsd: gsdOf(item) ?? Number.POSITIVE_INFINITY });
  });

  if (candidates.length === 0) return { top: null, gsd: null, inView: 0, fullFrame: false };

  const centreLat = (box.south + box.north) / 2;
  const centreLng = (box.west + box.east) / 2;
  const ranked = [...candidates].sort((a, b) => {
    const ac = pointInRing(centreLat, centreLng, a.ring) ? 0 : 1;
    const bc = pointInRing(centreLat, centreLng, b.ring) ? 0 : 1;
    if (ac !== bc) return ac - bc;
    return a.gsd - b.gsd;
  });

  const corners = boxCorners(box);
  const fullFrame = corners.every(([lat, lng]) =>
    candidates.some((c) => pointInRing(lat, lng, c.ring)));

  const winner = ranked[0];
  return {
    top: winner.item,
    gsd: Number.isFinite(winner.gsd) ? winner.gsd : null,
    inView: candidates.length,
    fullFrame,
  };
}
