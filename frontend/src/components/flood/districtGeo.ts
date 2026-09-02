/**
 * The district choropleth's own record: NDRRMA's per-district figures already
 * resolved against the Survey Department boundaries.
 *
 * /flood/districts/geo does the join server-side because two district names
 * differ between the two sources (Nawalparasi East/Nawalpur,
 * Makwanpur/Makawanpur), and re-deriving it in React would only reintroduce the
 * name bug the endpoint exists to fix. Both the tactical map and the written
 * assessment read the same features, so the join happens once per session and
 * neither surface can hold a different Rasuwa figure from the other.
 *
 * Declared here rather than in api/hooks/useFlood.ts because the shared flood
 * client is owned by another agent this run; the queryKey sits under the same
 * 'flood' root so it invalidates with the rest of the desk.
 */
import { useQuery } from '@tanstack/react-query';
import type { Feature, FeatureCollection, Geometry } from 'geojson';

import apiClient from '../../api/client';
import type { DistrictSnapshot } from './floodReplay';

export interface DistrictProperties {
  /** NDRRMA's spelling — the join key the bulletin uses. */
  name: string;
  /** Survey Department spelling, kept so a reader can trace the boundary. */
  geo_name: string;
  province: string | null;
  code: string | null;
  centroid: { lat: number; lng: number } | null;
  /** null means NDRRMA published no figure, never that the figure is zero. */
  bodies_recovered: number | null;
  missing: number | null;
  position: string;
  authority: string | null;
  as_of: string | null;
}

export interface CorridorWaypoint {
  name: string;
  lat: number;
  lng: number;
  kind: string;
  km: number | null;
}

export interface DistrictGeoResponse {
  event_key: string;
  count: number;
  districts: FeatureCollection<Geometry, DistrictProperties>;
  corridor: CorridorWaypoint[];
  unresolved: string[];
  note: string;
  /** Every dated district breakdown the primary authority has published.
   *  Absent until the endpoint serialises them; the map carries a fallback. */
  toll_snapshots?: DistrictSnapshot[];
}

export type DistrictFeature = Feature<Geometry, DistrictProperties>;

export function useFloodDistrictGeo() {
  return useQuery<DistrictGeoResponse>({
    queryKey: ['flood', 'district-geo'] as const,
    queryFn: async () => (await apiClient.get('/flood/districts/geo')).data,
    staleTime: 5 * 60 * 1000,
    // Must track useOfficialSituation's cadence. The figures ride along with
    // the geometry, so a slower interval here would let the map's labels hold a
    // superseded bulletin while the toll widgets showed the revision.
    refetchInterval: 5 * 60 * 1000,
  });
}
