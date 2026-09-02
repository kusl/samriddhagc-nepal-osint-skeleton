/**
 * The one commercial collection this desk is licensed to DISPLAY.
 *
 * /flood/media is the ground media and /flood/imagery is the catalogue of what
 * other agencies acquired; this is neither. Vantor released the Nepal-Flooding
 * -Aug-2026 scenes under CC BY-NC 4.0, so their pixels may be shown here as long
 * as the attribution rides with them — which is why `attribution` and `license`
 * come down the wire per item and per response rather than being typed into a
 * component that could later be copied without them.
 *
 * Declared here rather than in api/hooks/useFlood.ts because the shared flood
 * client is owned by another agent this run; the queryKey is namespaced under
 * the same 'flood' root so it invalidates with the rest of the desk.
 */
import { useQuery } from '@tanstack/react-query';

import apiClient from '../../api/client';

/** The event the pre/post split is measured against — NPT date of the collapse. */
export const VANTOR_EVENT_DATE = '2026-08-26';

/** Above this the reader must be told the cloud figure before reading the scene. */
export const HEAVY_CLOUD_PCT = 50;

/** One scene as a pair member: enough to date it, frame it and link it out. */
export interface VantorSceneBrief {
  id: string;
  /** Full acquisition timestamp, UTC. Never a date the UI invented. */
  datetime: string;
  /** eo:cloud_cover, rounded by the API. Monsoon passes run 71–94. */
  cloud: number;
  off_nadir: number | null;
  /** 512 px browse strip. Not registered to map coordinates — see `note`. */
  thumbnail: string | null;
  /** The exact product: a Cloud-Optimized GeoTIFF. Needs GIS software. */
  visual: string | null;
  item_url: string;
  /** Display names of the sites this strip sees. */
  covers: string[];
}

export interface VantorItem extends VantorSceneBrief {
  azimuth: number | null;
  bbox: number[];
  /** The real, rotated footprint. The bbox is not the ground the sensor saw. */
  geometry: { type: string; coordinates: number[][][] } | null;
  license: string;
  phase: 'pre' | 'post';
  covers_keys: string[];
  attribution: string;
}

export interface VantorSitePair {
  key: string;
  name: string;
  lat: number;
  lng: number;
  scene_count: number;
  pre: VantorSceneBrief | null;
  /** null where Vantor has published no post-event pass. That absence is
   *  itself intelligence and must be stated, never hidden. */
  post: VantorSceneBrief | null;
}

export interface VantorResponse {
  event_key: string;
  collection: string;
  collection_url: string;
  license: string;
  license_url: string;
  attribution: string;
  /** live = STAC answered now; cache = a recent answer; fallback = the
   *  hand-verified manifest of `manifest_verified_on`. Shown, not swallowed. */
  source: 'live' | 'cache' | 'fallback';
  stac_fetched_at: string | null;
  manifest_verified_on: string | null;
  count: number;
  items: VantorItem[];
  sites: VantorSitePair[];
  note: string | null;
}

export function useVantorScenes() {
  return useQuery<VantorResponse>({
    queryKey: ['flood', 'vantor'] as const,
    queryFn: async () => (await apiClient.get('/flood/vantor')).data,
    // The endpoint holds its own hour-long STAC cache and falls back to a
    // bundled manifest, so a shorter interval here buys nothing but S3 traffic.
    staleTime: 60 * 60 * 1000,
    retry: 1,
  });
}

/** "2021-10-16T05:22:48Z" → "16 OCT 2021", in the acquisition's own UTC. */
export const formatSceneDay = (iso: string | null | undefined): string | null => {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d
    .toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' })
    .toUpperCase();
};

/**
 * How long before the collapse a baseline was taken, as plain calendar
 * arithmetic. The pre scenes are 2021 and 2024 archive passes, not event-eve
 * imagery, and a reader shown "PRE" beside "POST" will assume days unless the
 * gap is spelled out — so every surface that shows a pre scene shows this.
 */
export const baselineGap = (iso: string | null | undefined): string | null => {
  const d = iso ? new Date(iso) : null;
  if (!d || Number.isNaN(d.getTime())) return null;
  const event = new Date(`${VANTOR_EVENT_DATE}T00:00:00Z`);
  let months =
    (event.getUTCFullYear() - d.getUTCFullYear()) * 12 + (event.getUTCMonth() - d.getUTCMonth());
  if (event.getUTCDate() < d.getUTCDate()) months -= 1;
  if (months < 1) return null;
  const years = Math.floor(months / 12);
  const rest = months % 12;
  return [years > 0 ? `${years} YR` : null, rest > 0 ? `${rest} MO` : null]
    .filter(Boolean)
    .join(' ');
};

/**
 * The footprint ring as Leaflet latlngs. STAC gives [lng, lat]; the rings are
 * the published polygons unsimplified, because a smoothed ring would be a
 * different claim about which ground the sensor covered.
 */
export const footprintRing = (item: VantorItem): [number, number][] | null => {
  const ring = item.geometry?.coordinates?.[0];
  if (!ring || ring.length < 3) return null;
  return ring
    .filter((p): p is number[] => Array.isArray(p) && p.length >= 2)
    .map((p) => [p[1], p[0]] as [number, number]);
};
