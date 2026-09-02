/**
 * Response sites for the impact map — GET /flood/sites. Burial grounds, DNA
 * hubs, mortuaries, transfer points, recovery reaches, the highway cut, the
 * airhead, and the flooded tunnels (mirrored from the tunnel ledger).
 *
 * Every figure carries the document it was read from; photographs are matched
 * by caption, never by geotag, and the payload says so.
 */
import { useQuery } from '@tanstack/react-query';

import apiClient from '../../api/client';
import { floodKeys } from '../../api/hooks/useFlood';

export type SiteKind =
  | 'burial' | 'forensic' | 'mortuary' | 'transfer' | 'recovery' | 'collection'
  | 'road_cut' | 'airhead' | 'tunnel_active' | 'tunnel_suspended' | 'tunnel_unreported';

export interface SiteFigure {
  kind: string;
  value: number;
  as_of: string;
  source: string;
  url?: string | null;
  note?: string | null;
}
export interface SiteNote {
  t_npt: string;
  text: string;
  source: string;
  url?: string | null;
}
export interface SitePhoto {
  id: string;
  title: string;
  title_ne: string | null;
  credit: string | null;
  outlet: string | null;
  page_url: string | null;
  image_url: string;
  licence_tier: 'display' | 'link_preview' | string;
  published_at: string | null;
  match: string;
}
export interface SiteEvidence {
  title: string;
  outlet: string | null;
  url: string | null;
  published_at: string | null;
}
export interface ResponseSite {
  key: string;
  kind: SiteKind | string;
  name: string;
  district: string | null;
  lat: number;
  lng: number;
  coord_confidence: 'published' | 'place' | 'municipality' | 'approximate' | string;
  km?: number | null;
  status?: string | null;
  status_line?: string | null;
  status_source?: string | null;
  teams?: string[];
  figures: SiteFigure[];
  notes: SiteNote[];
  photos: SitePhoto[];
  evidence: SiteEvidence[];
  auto: boolean;
}
export interface SitesPayload {
  event_key: string;
  as_of: string;
  truth_verified_on: string | null;
  kinds: Record<string, string>;
  sites: ResponseSite[];
  counts: { sites: number; burial: number; with_photos: number; photos: number; tunnels: number; buried_published: number };
  note: string | null;
}

export function useFloodSites() {
  return useQuery<SitesPayload | null>({
    queryKey: [...floodKeys.all, 'sites'] as const,
    queryFn: async () => {
      try {
        return (await apiClient.get('/flood/sites')).data as SitesPayload;
      } catch (err) {
        const status = (err as { response?: { status?: number } }).response?.status;
        if (status === 404) return null;
        throw err;
      }
    },
    staleTime: 5 * 60 * 1000,
    refetchInterval: 10 * 60 * 1000,
  });
}

/** Chip text and colour token per kind. The figure, when one is published, rides on the chip. */
export function siteChip(site: ResponseSite): { label: string; tone: 'critical' | 'high' | 'info' | 'low' | 'muted' } {
  const fig = (k: string) => site.figures.find((f) => f.kind === k)?.value;
  switch (site.kind) {
    case 'burial': {
      const n = fig('buried') ?? fig('managed_unidentified') ?? fig('buried_shared');
      return { label: n != null ? `BURIED ${n}` : 'BURIAL', tone: 'critical' };
    }
    case 'forensic': return { label: 'DNA HUB', tone: 'high' };
    case 'mortuary': { const n = fig('received'); return { label: n != null ? `MORTUARY ${n}` : 'MORTUARY', tone: 'high' }; }
    case 'transfer': return { label: 'HELI LIFT', tone: 'info' };
    case 'collection': { const n = fig('collected'); return { label: n != null ? `COLLECTED ${n}` : 'COLLECTION', tone: 'info' }; }
    case 'recovery': { const n = fig('recovered'); return { label: n != null ? `RECOVERED ${n}` : 'RECOVERY', tone: 'info' }; }
    case 'road_cut': return { label: 'ROAD CUT', tone: 'high' };
    case 'airhead': return { label: 'AIRHEAD', tone: 'info' };
    case 'tunnel_active': return { label: 'TUNNEL · DIGGING', tone: 'low' };
    case 'tunnel_suspended': return { label: 'TUNNEL · SUSPENDED', tone: 'critical' };
    case 'tunnel_unreported': return { label: 'TUNNEL · N/P', tone: 'muted' };
    default: return { label: site.kind.toUpperCase(), tone: 'muted' };
  }
}
