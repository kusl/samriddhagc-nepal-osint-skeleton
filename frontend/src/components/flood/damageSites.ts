/**
 * The curated damage frames: same-bbox pre/post renders from the Esri Disaster
 * Response Program image service over the Vantor open-data collection.
 *
 * /flood/vantor is the catalogue of what was acquired and where its footprints
 * fall; this is the render list. Every frame here was framed, coverage-tested
 * and captioned by the backend against our own STAC footprints — the DRP
 * catalogue answers any geometry filter with all sixteen rasters and cannot say
 * what is actually in view, so nothing on this side may infer coverage.
 *
 * Declared here rather than in api/hooks/useFlood.ts because the shared flood
 * client is owned by another agent this run; the queryKey sits under the same
 * 'flood' root so it invalidates with the rest of the desk.
 */
import { useQuery } from '@tanstack/react-query';

import apiClient from '../../api/client';

export type DamageLevelKey = 'context' | 'site' | 'detail';
export type DamagePhaseKey = 'pre' | 'post';

/**
 * The raster the mosaic rule paints on top of this frame — the one the caption
 * speaks for. Chosen over the frame centre, so `full_frame` false means the
 * label describes the middle of the view and not its edges.
 */
export interface DamageTopFrame {
  id: string;
  /** Acquisition instant from the STAC item. Never the catalogue's event date. */
  datetime: string;
  /** eo:cloud_cover for the whole scene, not for this frame. See `note`. */
  cloud: number;
  off_nadir: number | null;
  gsd_m: number;
  platform: string;
  item_url: string;
  visual: string | null;
  full_frame: boolean;
}

export interface DamagePhase {
  /** null where no footprint of this phase intersects the frame. The service
   *  answers 200 with a transparent PNG for uncovered ground, so a null here is
   *  the only thing standing between the reader and a blank sold as evidence. */
  export_url: string | null;
  top: DamageTopFrame | null;
  in_view: number;
  /** Acquisition days present in the frame, ascending. */
  dates: string[];
  /** True when any frame corner lacks covered pixels: blank is no-data. */
  edge: boolean;
}

export interface DamageLevel {
  level: DamageLevelKey;
  /** Ground width of the frame in metres. Height is 0.6x — the 5:3 export. */
  width_m: number;
  bbox: number[];
  pre: DamagePhase;
  post: DamagePhase;
}

export interface DamageSite {
  key: string;
  name: string;
  lat: number;
  lng: number;
  /** Distance down the surge corridor. null at the collapse origin. */
  km_mark: number | null;
  finding: string | null;
  finding_source: string | null;
  /** Empty where no frame can be rendered — the absence is the intelligence. */
  levels: DamageLevel[];
}

export interface DamageSitesResponse {
  service_url: string;
  event: string;
  license: string;
  license_url: string;
  attribution: string;
  stac_attribution: string;
  /** Whether each half of the record answered just now, came from cache, or
   *  fell back to the vendored catalogue. Shown, not swallowed. */
  source: { stac: string; drp_catalog: string };
  catalog_fetched_at: string | null;
  export: { width: number; height: number; bbox_sr: number; image_sr: number; format: string };
  catalog: {
    count: number;
    pre: number;
    post: number;
    gsd_range_m: number[];
    platforms: string[];
    providers: string[];
  };
  sites: DamageSite[];
  note: string | null;
}

export function useDamageSites() {
  return useQuery<DamageSitesResponse>({
    queryKey: ['flood', 'damage-sites'] as const,
    queryFn: async () => (await apiClient.get('/flood/damage-sites')).data,
    // The endpoint holds its own hour-long STAC and catalogue caches and falls
    // back to a vendored record, so a shorter interval buys nothing.
    staleTime: 60 * 60 * 1000,
    retry: 1,
  });
}

const LEVEL_ORDER: DamageLevelKey[] = ['context', 'site', 'detail'];

/** Widest first, so the switch reads left-to-right as zooming in. */
export const orderedLevels = (levels: DamageLevel[]): DamageLevel[] =>
  [...levels].sort((a, b) => LEVEL_ORDER.indexOf(a.level) - LEVEL_ORDER.indexOf(b.level));

/** "3000" → "3.0 KM"; frames below a kilometre stay in metres. */
export const formatGroundWidth = (m: number): string =>
  m >= 1000 ? `${(m / 1000).toFixed(1)} KM` : `${m} M`;

/** "2026-08-27" → "27 AUG". The same locale spelling formatSceneDay uses, so a
 *  mosaic span and the acquisition date beside it never abbreviate a month two
 *  different ways. Year-free: the phase captions carry it. */
export const formatShortDay = (iso: string): string => {
  const d = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return iso;
  return d
    .toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' })
    .toUpperCase();
};

/** The span of acquisitions mosaicked into one frame: "27 AUG – 1 SEP". */
export const formatDateSpan = (dates: string[]): string | null => {
  if (dates.length === 0) return null;
  const first = formatShortDay(dates[0]);
  const last = formatShortDay(dates[dates.length - 1]);
  return first === last ? first : `${first} – ${last}`;
};
