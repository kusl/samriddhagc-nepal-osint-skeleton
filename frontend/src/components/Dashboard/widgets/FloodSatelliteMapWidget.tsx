/**
 * NASA flood-extent imagery over the affected corridor.
 *
 * The neighbouring Satellite Intelligence widget catalogues what the space
 * agencies have published — this one puts the actual imagery on the screen.
 * GIBS is the only source here that needs no credentials: Earth Engine,
 * Sentinel Hub and the Charter's own products all sit behind registration, so
 * a keyless WMTS layer is what makes live flood extent viewable at all.
 *
 * The date defaults to yesterday because GIBS publishes several hours after
 * overpass; today's tile is usually not there yet.
 */
import { memo, useMemo, useState } from 'react';
import { Layers, Satellite } from 'lucide-react';

import { useFloodRivers, useSatelliteLayers } from '../../../api/hooks/useFlood';
import { satelliteTileUrl, type SatelliteLayer } from '../../../api/flood';
import { FloodMap } from '../../flood/FloodMap';
import { Widget } from '../Widget';
import { WidgetEmpty, WidgetError, WidgetSkeleton } from './shared';

const C = {
  border: 'var(--border-subtle)',
  elevated: 'var(--bg-elevated)',
  text: 'var(--text-primary)',
  muted: 'var(--text-muted)',
  mono: 'var(--font-mono)',
};

const control: React.CSSProperties = {
  background: C.elevated,
  color: C.text,
  border: `1px solid ${C.border}`,
  borderRadius: 2,
  padding: '3px 6px',
  fontSize: 9,
  fontFamily: C.mono,
  letterSpacing: '0.04em',
};

export const FloodSatelliteMapWidget = memo(function FloodSatelliteMapWidget() {
  const [layerId, setLayerId] = useState('viirs_flood_3day');
  const [date, setDate] = useState<string | null>(null);

  const satellite = useSatelliteLayers();
  // Gauges ride along so the imagery can be read against instrument readings;
  // FloodMap already drops offline and faulty stations rather than drawing them.
  const rivers = useFloodRivers(false);

  const overlays = useMemo(
    () => (satellite.data?.layers ?? []).filter((l) => l.kind === 'overlay'),
    [satellite.data],
  );
  const overlay: SatelliteLayer | undefined = useMemo(
    () => overlays.find((l) => l.id === layerId) ?? overlays[0],
    [overlays, layerId],
  );
  const activeDate = date ?? satellite.data?.default_date ?? null;

  const icon = <Satellite size={14} />;

  if (satellite.isLoading) {
    return <Widget id="flood-satellite-map" icon={icon}><WidgetSkeleton /></Widget>;
  }
  if (satellite.error || !satellite.data) {
    return (
      <Widget id="flood-satellite-map" icon={icon}>
        <WidgetError message="Failed to load imagery catalogue" onRetry={() => satellite.refetch()} />
      </Widget>
    );
  }
  if (!overlay || !activeDate) {
    return (
      <Widget id="flood-satellite-map" icon={icon}>
        <WidgetEmpty message="No flood-extent imagery published for this window" />
      </Widget>
    );
  }

  return (
    <Widget
      id="flood-satellite-map"
      icon={icon}
      badge={activeDate}
      actions={
        <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
          <Layers size={11} style={{ color: C.muted }} />
          <select
            value={overlay.id}
            onChange={(e) => setLayerId(e.target.value)}
            style={control}
            aria-label="Imagery layer"
          >
            {overlays.map((l) => (
              <option key={l.id} value={l.id}>{l.name}</option>
            ))}
          </select>
          <select
            value={activeDate}
            onChange={(e) => setDate(e.target.value)}
            style={control}
            aria-label="Imagery date"
          >
            {satellite.data.dates.map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
        </div>
      }
    >
      <div style={{ flex: '1 1 0', minHeight: 0, display: 'flex', flexDirection: 'column' }}>
        <div style={{ flex: '1 1 0', minHeight: 0 }}>
          <FloodMap
            overlayUrl={satelliteTileUrl(overlay, activeDate)}
            overlayMaxZoom={overlay.max_zoom}
            stations={rivers.data?.stations ?? []}
            incidents={[]}
            height="100%"
          />
        </div>
        <div style={{
          padding: '6px 12px',
          borderTop: `1px solid ${C.border}`,
          fontSize: 9,
          lineHeight: 1.5,
          color: C.muted,
          flexShrink: 0,
        }}>
          {overlay.description} — {overlay.attribution}, {activeDate}. {satellite.data.note}
        </div>
      </div>
    </Widget>
  );
});
