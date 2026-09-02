// Flood desk API client. Backend contract: app/api/v1/flood.py
import apiClient from './client';

export interface FloodCasualties {
  deaths: number;
  missing: number;
  injured: number;
  affected_families: number;
  people_affected: number;
  families_evacuated: number;
}

export interface FloodDamage {
  npr: number;
  /** null when we have no NRB rate — the desk shows NPR only rather than guess. */
  usd: number | null;
  usd_npr_rate: number | null;
  infrastructure_npr: number;
  agriculture_npr: number;
  houses_destroyed: number;
  houses_affected: number;
  roads_destroyed: number;
  bridges_destroyed: number;
  livestock_destroyed: number;
}

export interface FloodOverview {
  window_days: number;
  generated_at: string;
  casualties: FloodCasualties;
  damage: FloodDamage;
  incidents: {
    total: number;
    by_hazard: Record<string, number>;
    districts_affected: number;
    /** Incidents BIPAD has not yet assessed — the totals above exclude them. */
    awaiting_assessment: number;
  };
  rivers: {
    danger: number;
    warning: number;
    rising_at_risk: number;
    sensor_faults: number;
    offline: number;
    reporting: number;
    total: number;
  };
}

/** `offline` and `sensor_fault` are instrument states, never flood alarms. */
export type RiverAlert = 'danger' | 'warning' | 'normal' | 'sensor_fault' | 'offline';
export type RiverTrend = 'RISING' | 'FALLING' | 'STEADY' | 'UNKNOWN';

export interface RiverStation {
  station_id: number;
  name: string;
  basin: string | null;
  lat: number | null;
  lon: number | null;
  water_level: number;
  warning_level: number | null;
  danger_level: number | null;
  alert: RiverAlert;
  trend: RiverTrend;
  /** Metres below the danger line; negative means over it. */
  headroom_m: number | null;
  reading_at: string | null;
  age_hours: number | null;
  stale: boolean;
  critical: boolean;
}

export interface FloodDistrict {
  district: string;
  incidents: number;
  deaths: number;
  missing: number;
  injured: number;
  affected_families: number;
  estimated_loss_npr: number;
}

export interface FloodIncident {
  id: string;
  bipad_id: number;
  title: string;
  title_ne: string | null;
  hazard: string;
  district: string | null;
  lat: number | null;
  lon: number | null;
  deaths: number;
  missing: number;
  injured: number;
  affected_families: number;
  houses_destroyed: number;
  estimated_loss_npr: number;
  severity: string | null;
  verified: boolean;
  incident_on: string | null;
  /** false = BIPAD has not counted yet, so zeros mean "unknown", not "none". */
  assessed: boolean;
  source_url: string;
}

export interface SatelliteLayer {
  id: string;
  name: string;
  description: string;
  /** Contains {time}, {z}, {y}, {x} placeholders. */
  tile_url_template: string;
  kind: 'overlay' | 'base';
  max_zoom: number;
  attribution: string;
}

export interface SatelliteLayers {
  dates: string[];
  default_date: string;
  layers: SatelliteLayer[];
  note: string;
}

export const getFloodOverview = async (days = 7): Promise<FloodOverview> =>
  (await apiClient.get('/flood/overview', { params: { days } })).data;

export const getFloodRivers = async (alertsOnly = false): Promise<{ count: number; stations: RiverStation[] }> =>
  (await apiClient.get('/flood/rivers', { params: { alerts_only: alertsOnly } })).data;

export const getFloodDistricts = async (days = 7): Promise<{ count: number; districts: FloodDistrict[] }> =>
  (await apiClient.get('/flood/districts', { params: { days } })).data;

export const getFloodIncidents = async (
  days = 7, limit = 200, district?: string, hazard?: string,
): Promise<{ count: number; incidents: FloodIncident[] }> =>
  (await apiClient.get('/flood/incidents', { params: { days, limit, district, hazard } })).data;

export const getFloodTimeline = async (
  days = 30,
): Promise<{ days: number; series: { date: string; incidents: number; deaths: number }[] }> =>
  (await apiClient.get('/flood/timeline', { params: { days } })).data;

export const getSatelliteLayers = async (daysBack = 7): Promise<SatelliteLayers> =>
  (await apiClient.get('/flood/satellite/layers', { params: { days_back: daysBack } })).data;

/** Resolve a GIBS template for one date into a Leaflet-ready URL template. */
export const satelliteTileUrl = (layer: SatelliteLayer, date: string): string =>
  layer.tile_url_template.replace('{time}', date);

/**
 * Nepali-style money: lakh (10^5) and crore (10^7) are how damage is reported
 * and discussed locally, so plain millions would read as foreign.
 */
export const formatNPR = (amount: number): string => {
  if (!amount) return 'Rs 0';
  if (amount >= 1e7) return `Rs ${(amount / 1e7).toFixed(2)} cr`;
  if (amount >= 1e5) return `Rs ${(amount / 1e5).toFixed(2)} lakh`;
  return `Rs ${Math.round(amount).toLocaleString('en-IN')}`;
};

export const formatUSD = (amount: number | null): string => {
  if (amount === null || amount === undefined) return '—';
  if (amount >= 1e6) return `$${(amount / 1e6).toFixed(2)}M`;
  if (amount >= 1e3) return `$${(amount / 1e3).toFixed(1)}K`;
  return `$${Math.round(amount).toLocaleString('en-US')}`;
};

// ---------------------------------------------------------------- official

export interface OfficialToll {
  as_of: string;
  authority: string;
  deaths: number | null;
  missing: number | null;
  injured: number | null;
  rescued: number | null;
  people_affected: number | null;
  foreign_nationals_missing: number | null;
  damage_npr: number | null;
  damage_usd: number | null;
  damage_note: string | null;
  district_tolls: Record<string, Record<string, number>> | null;
  source_url: string | null;
  source_title: string | null;
  note: string | null;
}

export interface SituationPanel {
  key: string;
  title: string;
  subtitle: string | null;
  headline_value: string | null;
  headline_label: string | null;
  rows: { label: string; value: string }[];
  note: string | null;
  source: string | null;
  as_of: string | null;
}

export interface FloodEventMeta {
  key: string;
  name: string;
  started_on: string;
  cause: string;
  districts: string[];
  rivers: string[];
  status: string;
}

export interface OfficialSituation {
  event: FloodEventMeta;
  official: {
    available: boolean;
    latest?: OfficialToll;
    /** Same-day figures from other authorities that disagree — shown, not resolved. */
    conflicting_reports: OfficialToll[];
    trajectory: { as_of: string; deaths: number | null; missing: number | null }[];
    panels: SituationPanel[];
  };
  bipad_cross_check: {
    window_days: number;
    deaths: number;
    incidents: number;
    note: string;
  };
}

export const getOfficialSituation = async (days = 7): Promise<OfficialSituation> =>
  (await apiClient.get('/flood/official', { params: { days } })).data;
