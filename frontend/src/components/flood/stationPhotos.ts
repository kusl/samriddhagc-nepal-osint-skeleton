/**
 * DHM's own photographs of its gauge sites — data this desk has held since the
 * BIPAD ingest and never once shown.
 *
 * Two things make this layer awkward and both are handled on the wire rather
 * than here. The upstream URLs are http:// and would be blocked as mixed
 * content the moment the desk is served over TLS, so every photograph reaches
 * the browser through the API's own proxy. And DHM serves its images as
 * application/octet-stream, so the backend verifies by magic bytes: a station
 * is listed only once its URL actually returned image bytes. `verified` here is
 * therefore a probe result, not an assumption — a station that is absent is a
 * link that failed, which is worth knowing.
 *
 * The photographs are UNDATED. DHM publishes no capture time with them, so
 * nothing in this desk may caption one as an image of this flood; the API says
 * so in `note` and every surface that shows one repeats it.
 *
 * Declared here rather than in api/hooks/useFlood.ts because the shared flood
 * client is owned by another agent this run; the queryKey sits under the same
 * 'flood' root so it invalidates with the rest of the desk.
 */
import { useQuery } from '@tanstack/react-query';

import apiClient from '../../api/client';

export interface StationPhoto {
  bipad_id: number;
  name: string;
  basin: string | null;
  lat: number;
  lng: number;
  district: string | null;
  in_affected_district: boolean;
  is_active: boolean;
  /** The last probe returned image bytes. Only these are rendered. */
  verified: boolean;
  media_type: string | null;
  /** API-relative; carries auth, so it is fetched rather than put in a src. */
  photo_url: string;
  /** DHM's own URL, kept as provenance. Never linked: it is http and would be
   *  blocked, and the browser cannot read it anyway. */
  source_url: string;
  /** The gauge's live classification from the same record /flood/rivers
   *  serves. 'offline' is a dead sensor, never a danger state. */
  alert: string | null;
  trend: string | null;
  water_level: number | null;
  reading_at: string | null;
  stale: boolean;
}

export interface StationPhotosResponse {
  count: number;
  /** Stations holding a URL at all, before probing. */
  candidate_count: number;
  verified_count: number;
  /** Probes the bounded pass did not finish; they resolve on a later call. */
  probe_pending: number;
  affected_districts: string[];
  stations: StationPhoto[];
  attribution: string;
  note: string;
  /** Present only while nothing verifies — the honest statement of a dead feed. */
  probe_note?: string | null;
}

/**
 * Scoped to the nine districts the bulletin names. The other 224 stations are
 * real, but a photograph of a gauge in Ilam is not evidence about this flood
 * and would put 200 pins on a corridor map.
 */
export function useStationPhotos() {
  return useQuery<StationPhotosResponse>({
    queryKey: ['flood', 'station-photos', 'affected'] as const,
    queryFn: async () =>
      (await apiClient.get('/flood/station-photos', { params: { affected_only: true } })).data,
    // The backend caches its probe verdicts for six hours and the first call
    // pays for a bounded probe pass; anything shorter re-pays for nothing.
    staleTime: 30 * 60 * 1000,
    retry: 1,
  });
}

/**
 * The proxy is authenticated, so the photograph cannot simply be an <img src>:
 * a bare request would 401 and paint a broken-image icon. Fetched as bytes
 * through the client that holds the token and handed on as an object URL.
 */
export async function fetchStationPhoto(photoUrl: string): Promise<string> {
  const path = photoUrl.replace(/^\/api\/v1/, '');
  const response = await apiClient.get(path, { responseType: 'blob' });
  return URL.createObjectURL(response.data as Blob);
}

/** "2026-08-26T03:05:00+00:00" → "26 AUG 2026 03:05 UTC". The gauge reading's
 *  own stamp — never the photograph's, which has none. */
export const formatReadingStamp = (iso: string | null | undefined): string | null => {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const day = d
    .toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' })
    .toUpperCase();
  const hh = String(d.getUTCHours()).padStart(2, '0');
  const mm = String(d.getUTCMinutes()).padStart(2, '0');
  return `${day} ${hh}:${mm} UTC`;
};
