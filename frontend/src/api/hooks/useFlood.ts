import { useQuery } from '@tanstack/react-query';

import {
  getFloodDistricts,
  getFloodIncidents,
  getFloodOverview,
  getFloodRivers,
  getFloodTimeline,
  getOfficialSituation,
  getSatelliteLayers,
  type FloodDistrict,
  type FloodIncident,
  type FloodOverview,
  type RiverStation,
  type OfficialSituation,
  type SatelliteLayers,
} from '../flood';

export const floodKeys = {
  all: ['flood'] as const,
  overview: (days: number) => [...floodKeys.all, 'overview', days] as const,
  rivers: (alertsOnly: boolean) => [...floodKeys.all, 'rivers', alertsOnly] as const,
  districts: (days: number) => [...floodKeys.all, 'districts', days] as const,
  incidents: (days: number, district?: string, hazard?: string) =>
    [...floodKeys.all, 'incidents', days, district ?? 'all', hazard ?? 'all'] as const,
  timeline: (days: number) => [...floodKeys.all, 'timeline', days] as const,
  satellite: () => [...floodKeys.all, 'satellite'] as const,
};

// During an active emergency the page is left open on a wall screen, so these
// refresh on their own. Cadences match how fast each source actually moves:
// river gauges report every few minutes, casualty assessments take hours.
const RIVER_REFRESH = 2 * 60 * 1000;
const SITUATION_REFRESH = 5 * 60 * 1000;

export function useFloodOverview(days = 7) {
  return useQuery<FloodOverview>({
    queryKey: floodKeys.overview(days),
    queryFn: () => getFloodOverview(days),
    refetchInterval: SITUATION_REFRESH,
    staleTime: 60 * 1000,
  });
}

export function useFloodRivers(alertsOnly = false) {
  return useQuery<{ count: number; stations: RiverStation[] }>({
    queryKey: floodKeys.rivers(alertsOnly),
    queryFn: () => getFloodRivers(alertsOnly),
    refetchInterval: RIVER_REFRESH,
    staleTime: 30 * 1000,
  });
}

export function useFloodDistricts(days = 7) {
  return useQuery<{ count: number; districts: FloodDistrict[] }>({
    queryKey: floodKeys.districts(days),
    queryFn: () => getFloodDistricts(days),
    refetchInterval: SITUATION_REFRESH,
  });
}

export function useFloodIncidents(days = 7, district?: string, hazard?: string) {
  return useQuery<{ count: number; incidents: FloodIncident[] }>({
    queryKey: floodKeys.incidents(days, district, hazard),
    queryFn: () => getFloodIncidents(days, 300, district, hazard),
    refetchInterval: SITUATION_REFRESH,
  });
}

export function useFloodTimeline(days = 30) {
  return useQuery({
    queryKey: floodKeys.timeline(days),
    queryFn: () => getFloodTimeline(days),
    staleTime: 10 * 60 * 1000,
  });
}

export function useSatelliteLayers() {
  return useQuery<SatelliteLayers>({
    queryKey: floodKeys.satellite(),
    queryFn: () => getSatelliteLayers(10),
    // Imagery availability only changes once a day.
    staleTime: 60 * 60 * 1000,
  });
}

export function useOfficialSituation(days = 7) {
  return useQuery<OfficialSituation>({
    queryKey: [...floodKeys.all, 'official', days] as const,
    queryFn: () => getOfficialSituation(days),
    refetchInterval: SITUATION_REFRESH,
    staleTime: 60 * 1000,
  });
}
