/**
 * Flood map: NASA flood-extent imagery over a keyless dark basemap, with the
 * river gauges and incidents that the rest of the desk is reporting.
 *
 * Basemap note: the platform's other maps use CARTO tiles, which now require
 * an API key and render every tile stamped "API KEY REQUIRED". Esri's dark
 * canvas is still open and unauthenticated, so this map uses it.
 */
import { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

import type { FloodIncident, RiverStation } from '../../api/flood';

// Keyless. Esri publishes these basemaps for open use with attribution.
const BASEMAP_URL =
  'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}';
const BASEMAP_ATTRIBUTION = 'Esri, HERE, Garmin, © OpenStreetMap contributors';

// Nepal, framed to fill a wide panel.
const NEPAL_CENTER: L.LatLngExpression = [28.3949, 84.124];
const NEPAL_ZOOM = 7;

// Only three categorical fills, chosen to stay distinguishable for the common
// forms of colour-vision deficiency; everything else is conveyed by shape.
const COLORS = {
  danger: '#ef4444',
  warning: '#eab308',
  normal: '#22c55e',
  incidentFatal: '#ef4444',
  incident: '#3987e5',
  landslide: '#199e70',
};

interface Props {
  overlayUrl: string;
  overlayMaxZoom: number;
  stations: RiverStation[];
  incidents: FloodIncident[];
  /** CSS height. Pass '100%' inside a widget cell, which sizes its own children. */
  height?: number | string;
}

export function FloodMap({ overlayUrl, overlayMaxZoom, stations, incidents, height = 420 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const overlayRef = useRef<L.TileLayer | null>(null);
  const basemapRef = useRef<L.TileLayer | null>(null);
  const markersRef = useRef<L.LayerGroup | null>(null);

  // Create the map once. Leaflet owns the DOM node, so this must not re-run
  // on prop changes or it double-initialises and throws.
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = L.map(containerRef.current, {
      center: NEPAL_CENTER,
      zoom: NEPAL_ZOOM,
      zoomControl: true,
      attributionControl: true,
    });

    const basemap = L.tileLayer(BASEMAP_URL, {
      attribution: BASEMAP_ATTRIBUTION,
      maxZoom: 16,
    }).addTo(map);
    basemapRef.current = basemap;

    markersRef.current = L.layerGroup().addTo(map);
    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
      overlayRef.current = null;
      basemapRef.current = null;
      markersRef.current = null;
    };
  }, []);

  // Swap the satellite overlay whenever the layer or date changes.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (overlayRef.current) {
      map.removeLayer(overlayRef.current);
      overlayRef.current = null;
    }
    if (!overlayUrl) return;

    const layer = L.tileLayer(overlayUrl, {
      // GIBS publishes these products only to their native zoom; letting
      // Leaflet request deeper tiles returns 404s and a blank overlay, so
      // upscale the last real level instead.
      maxNativeZoom: overlayMaxZoom,
      maxZoom: 16,
      opacity: 0.75,
      attribution: 'NASA EOSDIS GIBS',
      // A day with no pass over Nepal simply has no tile; stay quiet about it.
      errorTileUrl: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=',
    });
    layer.addTo(map);
    // Imagery sits above the basemap but below the markers.
    basemapRef.current?.bringToBack();
    overlayRef.current = layer;
  }, [overlayUrl, overlayMaxZoom]);

  // Redraw markers when the underlying data changes.
  useEffect(() => {
    const group = markersRef.current;
    if (!group) return;
    group.clearLayers();

    // River gauges: circles, coloured by alert. Offline and faulty gauges are
    // deliberately not drawn — putting them on the map invites reading a dead
    // gauge's last value as a live one.
    stations.forEach(s => {
      if (s.lat == null || s.lon == null) return;
      if (s.alert === 'offline' || s.alert === 'sensor_fault') return;

      const color = s.alert === 'danger' ? COLORS.danger
        : s.alert === 'warning' ? COLORS.warning
        : COLORS.normal;
      const isAlert = s.alert === 'danger' || s.alert === 'warning';

      L.circleMarker([s.lat, s.lon], {
        radius: isAlert ? 7 : 3,
        color,
        weight: isAlert ? 2 : 1,
        fillColor: color,
        fillOpacity: isAlert ? 0.75 : 0.35,
      })
        .bindPopup(
          `<div style="font-family:system-ui;font-size:12px;min-width:180px">
             <strong>${s.name}</strong><br/>
             ${s.basin ?? 'unknown basin'}<br/>
             <span style="color:${color}">${s.alert.toUpperCase()}</span> ·
             ${s.water_level.toFixed(2)} m · ${s.trend}<br/>
             ${s.danger_level ? `danger at ${s.danger_level} m<br/>` : ''}
             <span style="opacity:.6">read ${s.reading_at?.slice(0, 16).replace('T', ' ') ?? 'unknown'}</span>
           </div>`,
        )
        .addTo(group);
    });

    // Incidents: square markers so they never read as gauges, sized by whether
    // there were deaths.
    incidents.forEach(i => {
      if (i.lat == null || i.lon == null) return;
      const fatal = i.deaths > 0;
      const color = fatal ? COLORS.incidentFatal
        : i.hazard === 'landslide' ? COLORS.landslide
        : COLORS.incident;
      const size = fatal ? 12 : 8;

      L.marker([i.lat, i.lon], {
        icon: L.divIcon({
          className: '',
          html: `<div style="width:${size}px;height:${size}px;background:${color};
                   opacity:.85;border:1px solid rgba(0,0,0,.5);
                   transform:rotate(45deg)"></div>`,
          iconSize: [size, size],
          iconAnchor: [size / 2, size / 2],
        }),
      })
        .bindPopup(
          `<div style="font-family:system-ui;font-size:12px;min-width:200px">
             <strong>${i.title}</strong><br/>
             ${i.district ?? 'district unknown'} · ${i.incident_on?.slice(0, 10) ?? ''}<br/>
             ${i.deaths ? `<span style="color:${COLORS.incidentFatal}">${i.deaths} dead</span> · ` : ''}
             ${i.affected_families ? `${i.affected_families} families · ` : ''}
             ${i.assessed ? '' : '<em>not yet assessed</em>'}<br/>
             <a href="${i.source_url}" target="_blank" rel="noreferrer">BIPAD record</a>
           </div>`,
        )
        .addTo(group);
    });
  }, [stations, incidents]);

  return (
    <div
      ref={containerRef}
      style={{
        height,
        width: '100%',
        borderRadius: 3,
        background: '#0a0a0b',
      }}
    />
  );
}
