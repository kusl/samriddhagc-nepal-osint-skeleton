/**
 * The licensed-media record behind the district map's imagery pins.
 *
 * Declared here rather than in api/hooks/useFlood.ts because the shared flood
 * client is owned by another agent this run; the queryKey is namespaced under
 * the same 'flood' root so it invalidates with the rest of the desk.
 */
import { useQuery } from '@tanstack/react-query';

import apiClient from '../../api/client';

export interface FloodMediaLocation {
  name: string;
  lat: number;
  lng: number;
  district: string | null;
}

export interface FloodMediaItem {
  id: string;
  title: string;
  caption: string | null;
  provider: string | null;
  /** Commons' own Artist string. Never omitted from the UI: CC BY and
   *  Attribution files are only licensed to us while it is on screen. */
  author: string | null;
  license: string | null;
  license_url: string | null;
  kind: 'image' | 'video' | 'pdf' | string;
  mime: string | null;
  thumb_url: string | null;
  /** The hand-verified upload.wikimedia.org URL. The API prefers thumb.* because
   *  upload.* rate-limits our server, but a browser fetches from the reader's own
   *  address, so the alternate is a real second chance rather than a duplicate. */
  thumb_url_alt: string | null;
  file_url: string | null;
  page_url: string;
  width: number | null;
  height: number | null;
  capture_date: string | null;
  /** NPT date from which this file exists. Drives replay visibility. */
  available_from: string | null;
  anchor: string | null;
  lat: number | null;
  lng: number | null;
  location: FloodMediaLocation | null;
  display_order: number;
}

export interface FloodMediaResponse {
  event_key: string;
  count: number;
  items: FloodMediaItem[];
  category_url: string | null;
  commons_ok: boolean;
  source: string;
  note: string | null;
}

export function useFloodMedia() {
  return useQuery<FloodMediaResponse>({
    queryKey: ['flood', 'media'] as const,
    queryFn: async () => (await apiClient.get('/flood/media')).data,
    // The endpoint holds its own hour-long Commons cache; asking more often
    // only spends the rate limit that keeps these files on screen.
    staleTime: 60 * 60 * 1000,
    retry: 1,
  });
}

/**
 * Sources to try in order. Images degrade thumb -> verified thumb -> original
 * file; a video has only its own bytes. Exhausting the list is what marks an
 * item unloadable, which is how a failure stays invisible instead of leaving a
 * broken-image box on a rescue desk.
 */
export const mediaSources = (item: FloodMediaItem): string[] => {
  const raw = item.kind === 'video'
    ? [item.file_url]
    : [item.thumb_url, item.thumb_url_alt, item.file_url];
  return raw.filter((u): u is string => Boolean(u)).filter((u, i, all) => all.indexOf(u) === i);
};

/** PDFs are link-out only; anything with no bytes to fetch cannot be framed. */
export const isViewable = (item: FloodMediaItem): boolean =>
  (item.kind === 'image' || item.kind === 'video') && mediaSources(item).length > 0;
