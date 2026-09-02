/**
 * One DHM gauge-site photograph, opened from its pin on the district map.
 *
 * The frame carries the station's facts whether or not the picture arrives, so
 * a dead DHM link degrades to a record rather than to a broken-image icon. The
 * caption never dates the photograph — DHM publishes no capture time — and the
 * gauge reading beside it is stamped as the reading's own time so the two are
 * not read as one.
 */
import { useEffect, useState } from 'react';
import { X } from 'lucide-react';

import { fetchStationPhoto, formatReadingStamp, type StationPhoto } from './stationPhotos';

const C = {
  base: 'var(--bg-base)',
  elevated: 'var(--bg-elevated)',
  border: 'var(--border-subtle)',
  text: 'var(--text-primary)',
  sub: 'var(--text-secondary)',
  muted: 'var(--text-muted)',
  mono: 'var(--font-mono)',
};

const label: React.CSSProperties = {
  fontFamily: C.mono,
  fontSize: 9,
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
  color: C.muted,
  lineHeight: 1.5,
};

export function FloodStationPhotoViewer({
  station,
  attribution,
  note,
  onClose,
}: {
  station: StationPhoto;
  attribution: string;
  note: string;
  onClose: () => void;
}) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    // Capture phase: the dashboard shell claims keys further down the tree.
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [onClose]);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    setSrc(null);
    setFailed(false);
    fetchStationPhoto(station.photo_url)
      .then((url) => {
        objectUrl = url;
        // Revoke immediately rather than hold a leaked blob when the reader
        // clicked past this station before its bytes arrived.
        if (cancelled) URL.revokeObjectURL(url);
        else setSrc(url);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [station.photo_url]);

  const place = [station.basin ? `${station.basin} basin` : null, station.district]
    .filter(Boolean)
    .join(' · ');

  const reading = formatReadingStamp(station.reading_at);
  // Stated in the gauge's own words. 'offline' is a sensor that stopped
  // reporting; rendering it in a status colour would read as a river warning.
  const gaugeLine = [
    station.alert ? `GAUGE ${station.alert.toUpperCase()}` : null,
    station.water_level != null ? `${station.water_level.toFixed(2)} M` : null,
    reading ? `READING ${reading}` : null,
    station.stale ? 'READING STALE' : null,
  ]
    .filter(Boolean)
    .join(' · ');

  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        zIndex: 1100,
        background: C.base,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <div
        style={{
          flexShrink: 0,
          height: 26,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '0 8px',
          borderBottom: `1px solid ${C.border}`,
        }}
      >
        <span
          style={{
            flex: '1 1 0',
            minWidth: 0,
            fontSize: 12,
            color: C.text,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          {station.name}
        </span>
        <span style={{ ...label, flexShrink: 0, fontSize: 10 }}>DHM {station.bipad_id}</span>
        <button
          type="button"
          className="widget-action"
          style={{ padding: '2px 4px', minHeight: 18 }}
          onClick={onClose}
          aria-label="Close station photograph"
        >
          <X size={12} />
        </button>
      </div>

      <div
        style={{
          flex: '1 1 0',
          minHeight: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 4,
        }}
      >
        {failed ? (
          <div style={{ textAlign: 'center', padding: '0 12px' }}>
            <div style={{ ...label, fontSize: 10, color: C.sub }}>Photograph unavailable</div>
            <div style={{ marginTop: 4, fontSize: 10, lineHeight: 1.5, color: C.muted }}>
              The DHM link for this station did not return image bytes.
            </div>
          </div>
        ) : !src ? (
          <div style={{ ...label, fontSize: 10 }}>Loading photograph…</div>
        ) : (
          <img
            src={src}
            alt={`DHM gauge site, ${station.name}`}
            decoding="async"
            onError={() => setFailed(true)}
            style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain', display: 'block' }}
          />
        )}
      </div>

      <div
        style={{
          flexShrink: 0,
          padding: '6px 10px',
          borderTop: `1px solid ${C.border}`,
          background: C.elevated,
        }}
      >
        <div style={{ ...label, fontSize: 10, color: C.sub }}>{place || 'DHM gauge station'}</div>
        {gaugeLine && <div style={{ ...label, marginTop: 2 }}>{gaugeLine}</div>}
        {/* The one caption this picture must never be given is a date. */}
        <div style={{ marginTop: 4, fontSize: 9, lineHeight: 1.5, color: C.muted }}>{note}</div>
        <div style={{ ...label, marginTop: 3 }}>{attribution}</div>
      </div>
    </div>
  );
}
