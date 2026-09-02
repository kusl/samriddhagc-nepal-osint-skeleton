/**
 * Deaths by district of *recovery*, not of death: bodies travelled with the
 * water, so Chitwan — roughly 160 km downstream — holds the largest recovered
 * count while Rasuwa at the collapse site holds the fewest and by far the most
 * missing. That inversion is the whole reason this widget exists, and a ranked
 * list cannot show it: sorted by recovered, Rasuwa lands last, at the bottom of
 * the panel, which is the opposite of what the reader needs to take away.
 *
 * So the figures are drawn as a downstream profile — districts ordered by their
 * own kilometre mark, with recovered and missing as paired bars on ONE shared
 * scale. Rasuwa then reads as a short critical stub against a long high bar at
 * km 0, and Chitwan as the longest critical bar with no missing bar at all, 160
 * km down. The map beside this widget carries geography and paints missing as
 * text only; this one carries magnitude and is the only place the two
 * quantities are directly comparable.
 *
 * Every figure here comes from /flood/official. The geometry endpoint is read
 * for one thing only — which of the event record's own corridor waypoints fall
 * inside each district — so a kilometre mark is a published waypoint, never an
 * estimated river distance. Districts containing no waypoint are not placed on
 * the axis at all; they keep their bars under an OFF-CORRIDOR head.
 *
 * Rendered entirely through the MILSPEC grammar: hairlines and whitespace, tone
 * on text only, one source line at the foot.
 */
import { memo, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { MapPin } from 'lucide-react';
import type { Feature, FeatureCollection, Geometry, Position } from 'geojson';

import apiClient from '../../../api/client';
import { Widget } from '../Widget';
import { useOfficialSituation } from '../../../api/hooks/useFlood';
import { WidgetSkeleton, WidgetError, WidgetEmpty } from './shared';
import {
  MS,
  LABEL_XS,
  FIGURE,
  CELL,
  HAIRLINE,
  Body,
  Scroll,
  Section,
  Stat,
  StatRow,
  SourceLine,
  Note,
  dtgDay,
  fmt,
  fmtDelta,
} from '../../flood/milspec';

/** District tolls are a free-form key→count dict; this is the count we rank on. */
const PRIMARY_KEYS = ['bodies_recovered', 'deaths', 'dead'];

/** Width of the kilometre gutter, and the gap that separates every column. */
const KM_W = 34;
const GAP = 8;
/** Bar height, per the desk standard. Two bars, one hairline of air between. */
const BAR_H = 6;

const humanizeKey = (key: string): string => key.replace(/_/g, ' ');

/** Corridor km observed inside a district polygon. Never interpolated. */
interface CorridorKm {
  min: number;
  max: number;
}

/**
 * Only the fields this widget reads. The endpoint also serves bodies_recovered
 * and missing per feature, deliberately not taken from here: every figure on
 * this panel comes from /flood/official so the header sum, the bars and the
 * provenance line can only ever quote one bulletin.
 */
interface DistrictProperties {
  name: string;
  geo_name: string;
  position: string | null;
  /**
   * Served once the geometry endpoint computes it server-side. Until then it is
   * absent and the same rule is applied here against the polygons it already
   * ships, so the two can never disagree — whichever arrives is the same test.
   */
  corridor_km?: CorridorKm | null;
}

interface CorridorWaypoint {
  name: string;
  lat: number;
  lng: number;
  kind: string;
  km: number | null;
}

interface DistrictGeoResponse {
  districts: FeatureCollection<Geometry, DistrictProperties>;
  corridor: CorridorWaypoint[];
}

/**
 * Declared inline because the shared flood client has no getFloodDistrictGeo
 * yet. The key, staleTime and interval are deliberately identical to the map
 * widget's copy so React Query serves both from one cache entry: the two
 * widgets sit side by side and must never hold different bulletins.
 */
function useFloodDistrictGeo() {
  return useQuery<DistrictGeoResponse>({
    queryKey: ['flood', 'district-geo'] as const,
    queryFn: async () => (await apiClient.get('/flood/districts/geo')).data,
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  });
}

const ringContains = (ring: Position[], lng: number, lat: number): boolean => {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i, i += 1) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if (yi > lat !== yj > lat && lng < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
};

/** Outer ring minus holes, the same test the geometry endpoint applies. */
const polygonContains = (rings: Position[][], lng: number, lat: number): boolean =>
  ringContains(rings[0] ?? [], lng, lat) && !rings.slice(1).some((r) => ringContains(r, lng, lat));

const featureContains = (feature: Feature<Geometry, DistrictProperties>, lng: number, lat: number): boolean => {
  const g = feature.geometry;
  if (g.type === 'Polygon') return polygonContains(g.coordinates, lng, lat);
  if (g.type === 'MultiPolygon') return g.coordinates.some((poly) => polygonContains(poly, lng, lat));
  return false;
};

type Row = {
  district: string;
  /** null where the authority publishes no recovery count for the district. */
  recovered: number | null;
  missing: number | null;
  km: CorridorKm | null;
  isSource: boolean;
  secondary: { key: string; value: number }[];
};

/** Where a district sits on the axis: its first waypoint, so Rasuwa reads 0. */
const kmAnchor = (km: CorridorKm): number => km.min;

const kmLabel = (km: CorridorKm): string => (km.min === km.max ? `${km.min}` : `${km.min}–${km.max}`);

export const FloodDistrictTollWidget = memo(function FloodDistrictTollWidget() {
  const situation = useOfficialSituation();
  const geo = useFloodDistrictGeo();

  const latest = situation.data?.official?.latest;
  const panels = situation.data?.official?.panels;

  const features = useMemo(() => geo.data?.districts?.features ?? [], [geo.data]);
  const corridor = useMemo(() => geo.data?.corridor ?? [], [geo.data]);

  // Which published waypoints lie inside each district. Derived from the two
  // records as they are: the km figures are the event record's, the polygons
  // the Survey Department's. Nothing between waypoints is interpolated, so a
  // district the corridor merely passes between two marks stays unplaced.
  const kmByDistrict = useMemo(() => {
    const out = new Map<string, CorridorKm>();
    if (features.length === 0) return out;
    const marks = corridor.filter((w) => w.km != null);

    features.forEach((f) => {
      const p = f.properties;
      if (p.corridor_km) {
        out.set(p.name, p.corridor_km);
        return;
      }
      const hits = marks.filter((w) => featureContains(f, w.lng, w.lat)).map((w) => w.km as number);
      if (hits.length > 0) out.set(p.name, { min: Math.min(...hits), max: Math.max(...hits) });
    });
    return out;
  }, [features, corridor]);

  const {
    rows,
    districtSum,
    primaryKey,
    withCount,
    missingSum,
    missingCount,
    maxValue,
    positioned,
    unplaced,
  } = useMemo(() => {
    const empty = {
      rows: [] as Row[],
      districtSum: 0,
      primaryKey: 'bodies_recovered',
      withCount: 0,
      missingSum: 0,
      missingCount: 0,
      maxValue: 1,
      positioned: [] as Row[],
      unplaced: [] as Row[],
    };
    const tolls = latest?.district_tolls;
    if (!tolls) return empty;

    // Pick the ranking key from the data rather than assuming NDRRMA keeps
    // calling it bodies_recovered in later bulletins.
    const keys = new Set<string>();
    Object.values(tolls).forEach((entry) => Object.keys(entry ?? {}).forEach((k) => keys.add(k)));
    const key = PRIMARY_KEYS.find((k) => keys.has(k)) ?? Array.from(keys)[0] ?? 'bodies_recovered';

    // The missing panel mixes districts with categories ("Foreign nationals",
    // "Linked to hydropower projects"), so a label counts as a district only on
    // exact equality with a name one of the two records already names. A label
    // we cannot match is left in the panel where it belongs.
    const known = new Map<string, string>();
    Object.keys(tolls).forEach((d) => known.set(d, d));
    features.forEach((f) => {
      known.set(f.properties.name, f.properties.name);
      known.set(f.properties.geo_name, f.properties.name);
    });

    const missingByDistrict = new Map<string, number>();
    (panels?.find((p) => p.key === 'missing')?.rows ?? []).forEach((r) => {
      const name = known.get(r.label);
      const value = Number(String(r.value).replace(/,/g, ''));
      if (name && Number.isFinite(value)) missingByDistrict.set(name, value);
    });

    const sourceNames = new Set(
      features.filter((f) => f.properties.position === 'source').map((f) => f.properties.name),
    );

    const built: Row[] = Object.entries(tolls).map(([district, entry]) => ({
      district,
      recovered: entry?.[key] != null ? Number(entry[key]) : null,
      missing: missingByDistrict.get(district) ?? null,
      km: kmByDistrict.get(district) ?? null,
      isSource: sourceNames.has(district),
      secondary: Object.entries(entry ?? {})
        .filter(([k]) => k !== key)
        .map(([k, v]) => ({ key: k, value: Number(v) })),
    }));

    // A district that appears only in the missing rows — Makwanpur today — is a
    // district the authority named. Dropping it because it has no recovery
    // count would print a shorter list than the map beside it shows.
    missingByDistrict.forEach((value, district) => {
      if (built.some((r) => r.district === district)) return;
      built.push({
        district,
        recovered: null,
        missing: value,
        km: kmByDistrict.get(district) ?? null,
        isSource: sourceNames.has(district),
        secondary: [],
      });
    });

    const byMagnitude = (a: Row, b: Row) =>
      (b.recovered ?? 0) - (a.recovered ?? 0) ||
      (b.missing ?? 0) - (a.missing ?? 0) ||
      a.district.localeCompare(b.district);

    const onAxis = built
      .filter((r) => r.km)
      .sort(
        (a, b) =>
          kmAnchor(a.km as CorridorKm) - kmAnchor(b.km as CorridorKm) ||
          (a.km as CorridorKm).max - (b.km as CorridorKm).max ||
          byMagnitude(a, b),
      );
    const offAxis = built.filter((r) => !r.km).sort(byMagnitude);

    return {
      rows: [...onAxis, ...offAxis],
      districtSum: built.reduce((acc, r) => acc + (r.recovered ?? 0), 0),
      primaryKey: key,
      withCount: built.filter((r) => r.recovered != null).length,
      // Summed only across the districts that actually carry a published
      // missing figure; the count beside it says how many those are, so the
      // total is never read as national.
      missingSum: built.reduce((acc, r) => acc + (r.missing ?? 0), 0),
      missingCount: built.filter((r) => r.missing != null).length,
      // One scale for both quantities: the comparison is the point, and a
      // second axis for missing would hide that the missing dwarf the recovered.
      maxValue: Math.max(1, ...built.map((r) => Math.max(r.recovered ?? 0, r.missing ?? 0))),
      positioned: onAxis,
      unplaced: offAxis,
    };
  }, [latest, panels, features, kmByDistrict]);

  const icon = <MapPin size={14} />;

  if (situation.isLoading || (geo.isLoading && !situation.data)) {
    return (
      <Widget id="flood-district-toll" icon={icon}>
        <WidgetSkeleton />
      </Widget>
    );
  }

  if (situation.error || !situation.data) {
    return (
      <Widget id="flood-district-toll" icon={icon}>
        <WidgetError
          message="Failed to load official district tolls"
          onRetry={() => {
            situation.refetch();
            geo.refetch();
          }}
        />
      </Widget>
    );
  }

  if (!latest || rows.length === 0) {
    return (
      <Widget id="flood-district-toll" icon={icon}>
        <WidgetEmpty message="No district-level toll published by the disaster authority" />
      </Widget>
    );
  }

  const nationalDeaths = latest.deaths;
  // The district figures and the national headline are attributed separately.
  // While they agree, restating the national total would print one number
  // twice; the gap is surfaced only on the day it exists, and never reconciled
  // by adjusting either figure.
  const unattributed =
    nationalDeaths !== null && nationalDeaths !== undefined ? nationalDeaths - districtSum : null;

  const scaleTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => ({
    frac: f,
    value: Math.round((maxValue * f) / 5) * 5,
  }));

  const sourceDistrict = rows.find((r) => r.isSource)?.district;

  const renderRow = (row: Row) => {
    // Everything the old hover card carried, kept on the row itself: the desk
    // states what is NOT published rather than letting a bare bar imply a zero.
    const detail = [
      row.km
        ? `${row.isSource ? 'At the collapse source' : 'Downstream'} · waypoints at km ${kmLabel(row.km)}`
        : 'No corridor waypoint published inside this district',
      `${humanizeKey(primaryKey)}: ${row.recovered != null ? fmt(row.recovered) : 'no recovery count published'}`,
      `Missing: ${row.missing != null ? fmt(row.missing) : 'not broken out for this district'}`,
      ...row.secondary.map((s) => `${humanizeKey(s.key)}: ${fmt(s.value)}`),
      [latest.authority, latest.as_of].filter(Boolean).join(' · '),
    ].join('\n');

    return (
      <div key={row.district} title={detail} style={{ padding: '4px 0 5px', borderBottom: HAIRLINE }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: GAP }}>
          <span style={{ ...LABEL_XS, flex: `0 0 ${KM_W}px`, textAlign: 'right' }}>
            {row.km ? kmLabel(row.km) : '—'}
          </span>
          <span
            style={{
              ...CELL,
              flex: 1,
              minWidth: 0,
              color: MS.text,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {row.district}
            {row.isSource && <span style={{ ...LABEL_XS, color: MS.critical, marginLeft: 6 }}>SOURCE</span>}
          </span>
          <span style={{ ...FIGURE, fontSize: 11, flex: '0 0 52px', textAlign: 'right', color: MS.critical }}>
            {fmt(row.recovered)}
          </span>
          <span style={{ ...FIGURE, fontSize: 11, flex: '0 0 52px', textAlign: 'right', color: MS.high }}>
            {fmt(row.missing)}
          </span>
        </div>

        {/* Two bars, one scale. A district with no published missing figure gets
            no second bar at all — absence is drawn as absence, never as a zero. */}
        <div style={{ position: 'relative', height: BAR_H * 2 + 1, marginTop: 3, marginLeft: KM_W + GAP }}>
          {row.recovered != null && (
            <span
              style={{
                position: 'absolute',
                left: 0,
                top: 0,
                height: BAR_H,
                width: `${Math.max((row.recovered / maxValue) * 100, row.recovered > 0 ? 0.8 : 0)}%`,
                background: MS.critical,
              }}
            />
          )}
          {row.missing != null && (
            <span
              style={{
                position: 'absolute',
                left: 0,
                top: BAR_H + 1,
                height: BAR_H,
                width: `${Math.max((row.missing / maxValue) * 100, row.missing > 0 ? 0.8 : 0)}%`,
                background: MS.high,
              }}
            />
          )}
        </div>
      </div>
    );
  };

  return (
    <Widget
      id="flood-district-toll"
      icon={icon}
      badge={`${rows.length} DISTRICTS`}
      badgeVariant="critical"
    >
      <Body>
        <StatRow columns={3}>
          <Stat
            label={humanizeKey(primaryKey)}
            value={fmt(districtSum)}
            tone="critical"
            size={22}
            sub={
              unattributed !== null && unattributed !== 0
                ? `${fmtDelta(unattributed)} unattributed vs ${latest.authority} ${fmt(nationalDeaths)}`
                : undefined
            }
          />
          <Stat label="DISTRICTS REPORTING" value={`${withCount} / ${rows.length}`} size={22} />
          <Stat
            label="MISSING WHERE PUBLISHED"
            value={missingCount > 0 ? fmt(missingSum) : '—'}
            tone="high"
            size={22}
            sub={missingCount > 0 ? `${missingCount} of ${rows.length} districts broken out` : undefined}
          />
        </StatRow>

        <Scroll>
          {/* Value ruler. Both bars are read against it, which is the only way
              a short recovery and a long missing figure compare by eye. */}
          <div style={{ display: 'flex', alignItems: 'baseline', gap: GAP, paddingTop: 6 }}>
            <span style={{ ...LABEL_XS, flex: `0 0 ${KM_W}px`, textAlign: 'right' }}>KM</span>
            <span
              style={{
                position: 'relative',
                flex: 1,
                minWidth: 0,
                height: 12,
                borderBottom: HAIRLINE,
                display: 'block',
              }}
            >
              {scaleTicks.map((t) => (
                <span
                  key={t.frac}
                  style={{
                    ...LABEL_XS,
                    position: 'absolute',
                    left: `${t.frac * 100}%`,
                    bottom: 1,
                    transform: t.frac === 1 ? 'translateX(-100%)' : t.frac === 0 ? 'none' : 'translateX(-50%)',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {fmt(t.value)}
                </span>
              ))}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: GAP, padding: '3px 0 2px' }}>
            <span style={{ ...LABEL_XS, flex: `0 0 ${KM_W}px`, textAlign: 'right' }}>
              {sourceDistrict ? 'FROM' : ''}
            </span>
            <span style={{ ...LABEL_XS, flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {sourceDistrict ? `DOWNSTREAM OF ${sourceDistrict}` : 'CORRIDOR KM'}
            </span>
            <span style={{ ...LABEL_XS, color: MS.critical, whiteSpace: 'nowrap' }}>{humanizeKey(primaryKey)}</span>
            <span style={{ ...LABEL_XS, color: MS.high, whiteSpace: 'nowrap' }}>MISSING</span>
          </div>

          {positioned.map((row) => renderRow(row))}

          {/* Stated in full: these districts hold real figures and the only
              thing missing is a position, so they keep their bars. */}
          {unplaced.length > 0 && (
            <Section
              title="OFF-CORRIDOR"
              meta={positioned.length > 0 ? 'NO WAYPOINT PUBLISHED' : 'CORRIDOR POSITIONS UNAVAILABLE'}
            />
          )}
          {unplaced.map((row) => renderRow(row))}

          {latest.note && <Note>{latest.note}</Note>}
        </Scroll>

        <SourceLine
          source={latest.authority}
          asOf={dtgDay(latest.as_of)}
          url={latest.source_url}
        />
      </Body>
    </Widget>
  );
});
