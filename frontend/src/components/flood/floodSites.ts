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
  /** Read by the extractor from a press sentence; unreviewed. */
  auto?: boolean;
  confidence?: number;
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
  /** Earliest dated figure, note, photograph or press mention — when the site entered the record. */
  first_reported?: string | null;
}
export interface SitesPayload {
  event_key: string;
  as_of: string;
  truth_verified_on: string | null;
  kinds: Record<string, string>;
  sites: ResponseSite[];
  counts: { sites: number; burial: number; with_photos: number; photos: number; tunnels: number; buried_published: number; auto_sites?: number; auto_figures?: number };
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
      const n = fig('buried') ?? fig('managed_unidentified') ?? fig('buried_shared') ?? fig('burial');
      return { label: n != null ? `BURIED ${n}` : 'BURIAL', tone: 'critical' };
    }
    case 'forensic': { const n = fig('identified'); return { label: n != null ? `IDENTIFIED ${n}` : 'DNA HUB', tone: 'high' }; }
    case 'mortuary': { const n = fig('received') ?? fig('mortuary'); return { label: n != null ? `MORTUARY ${n}` : 'MORTUARY', tone: 'high' }; }
    case 'transfer': return { label: 'HELI LIFT', tone: 'info' };
    case 'collection': { const n = fig('collected'); return { label: n != null ? `COLLECTED ${n}` : 'COLLECTION', tone: 'info' }; }
    case 'recovery': { const n = fig('recovered') ?? fig('recovery'); return { label: n != null ? `RECOVERED ${n}` : 'RECOVERY', tone: 'info' }; }
    case 'road_cut': return { label: 'ROAD CUT', tone: 'high' };
    case 'airhead': return { label: 'AIRHEAD', tone: 'info' };
    case 'tunnel_active': return { label: 'TUNNEL · DIGGING', tone: 'low' };
    case 'tunnel_suspended': return { label: 'TUNNEL · SUSPENDED', tone: 'critical' };
    case 'tunnel_unreported': return { label: 'TUNNEL · N/P', tone: 'muted' };
    default: return { label: site.kind.toUpperCase(), tone: 'muted' };
  }
}

/** Day-close of a date-only stamp, or the instant of a full timestamp, in ms. A
 *  figure dated "2026-09-02" is not known until that day is over. */
export function siteStampMs(stamp: string | null | undefined): number | null {
  if (!stamp) return null;
  if (stamp.length <= 10) {
    const d = new Date(`${stamp}T23:59:59+05:45`);
    return Number.isNaN(d.getTime()) ? null : d.getTime();
  }
  const d = new Date(stamp);
  return Number.isNaN(d.getTime()) ? null : d.getTime();
}

/** The site as it was known at time t: only figures, notes, photographs and
 *  mentions dated at or before t. Null when nothing about it was known yet. */
export function siteAt(site: ResponseSite, t: number): ResponseSite | null {
  const first = siteStampMs(site.first_reported);
  if (first != null && first > t) return null;
  const keep = (stamp: string | null | undefined) => { const ms = siteStampMs(stamp); return ms == null || ms <= t; };
  return {
    ...site,
    figures: site.figures.filter((f) => keep(f.as_of)),
    notes: site.notes.filter((n) => keep(n.t_npt)),
    photos: site.photos.filter((p) => keep(p.published_at)),
    evidence: site.evidence.filter((e) => keep(e.published_at)),
  };
}
