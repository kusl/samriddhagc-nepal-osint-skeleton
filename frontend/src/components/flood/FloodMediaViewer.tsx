/**
 * The imagery viewer that opens over the district map.
 *
 * It sits inside the map widget rather than in a gallery of its own because the
 * founder's ask was imagery IN the impact map: a picture of the destroyed
 * border post is evidence for the pin it opened from, not a separate exhibit.
 *
 * The attribution bar is not decoration. Two of these files are CC BY /
 * Attribution, so the author line is the condition on which they may be shown
 * at all; it is therefore always rendered, never truncated and never behind a
 * disclosure.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, ExternalLink, X } from 'lucide-react';

import { mediaSources, type FloodMediaItem } from './floodMedia';
import { formatDayShort } from './floodReplay';

interface Props {
  items: FloodMediaItem[];
  index: number;
  anchorLabel: string;
  /** Files that carry no renderable bytes here — the ECDM map sheet. */
  linkOuts: FloodMediaItem[];
  categoryUrl: string | null;
  onIndex: (index: number) => void;
  onClose: () => void;
  onFail: (id: string) => void;
}

const mono = 'var(--font-mono)';

const capLabel = (iso: string | null): string | null =>
  iso ? `${formatDayShort(iso)} ${iso.slice(0, 4)}` : null;

const chipStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 4,
  padding: '2px 6px',
  border: '1px solid var(--border-subtle)',
  background: 'var(--bg-elevated)',
  color: 'var(--status-info)',
  fontFamily: mono,
  fontSize: 9,
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
  textDecoration: 'none',
  whiteSpace: 'nowrap',
};

function MediaFrame({
  item,
  zoomed,
  onToggleZoom,
  onFail,
}: {
  item: FloodMediaItem;
  zoomed: boolean;
  onToggleZoom: () => void;
  onFail: (id: string) => void;
}) {
  const sources = useMemo(() => mediaSources(item), [item]);
  const [srcIdx, setSrcIdx] = useState(0);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    setSrcIdx(0);
    setLoaded(false);
  }, [item.id]);

  // Walk the mirrors before giving up. Only an exhausted list is a failure,
  // and a failure removes the item rather than showing a hole.
  const handleError = useCallback(() => {
    if (srcIdx + 1 < sources.length) setSrcIdx(srcIdx + 1);
    else onFail(item.id);
  }, [srcIdx, sources.length, onFail, item.id]);

  const src = sources[srcIdx];
  if (!src) return null;

  if (item.kind === 'video') {
    return (
      <video
        key={src}
        src={src}
        controls
        preload="none"
        poster={item.thumb_url ?? undefined}
        onError={handleError}
        style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain', background: 'var(--bg-base)' }}
      />
    );
  }

  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        overflow: zoomed ? 'auto' : 'hidden',
        display: zoomed ? 'block' : 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <img
        key={src}
        src={src}
        alt={item.title}
        loading="lazy"
        decoding="async"
        onLoad={() => setLoaded(true)}
        onError={handleError}
        onClick={onToggleZoom}
        style={{
          // Fit reads the gestalt; 1:1 is how the 1618 px border-post composite
          // is actually read — the scoured buildings are a few pixels at fit.
          maxWidth: zoomed ? 'none' : '100%',
          maxHeight: zoomed ? 'none' : '100%',
          width: zoomed ? `${item.width ?? 1280}px` : 'auto',
          objectFit: 'contain',
          display: 'block',
          cursor: zoomed ? 'zoom-out' : 'zoom-in',
          opacity: loaded ? 1 : 0,
          transition: 'opacity .18s ease-out',
        }}
      />
    </div>
  );
}

export function FloodMediaViewer({
  items,
  index,
  anchorLabel,
  linkOuts,
  categoryUrl,
  onIndex,
  onClose,
  onFail,
}: Props) {
  const [zoomed, setZoomed] = useState(false);
  const safeIndex = Math.min(Math.max(index, 0), Math.max(items.length - 1, 0));
  const item = items[safeIndex];

  useEffect(() => setZoomed(false), [item?.id]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
        return;
      }
      if (items.length < 2) return;
      if (e.key === 'ArrowRight') onIndex((safeIndex + 1) % items.length);
      if (e.key === 'ArrowLeft') onIndex((safeIndex - 1 + items.length) % items.length);
    };
    // Capture phase: the dashboard shell claims the arrow keys for its own
    // navigation further down the tree, and an open viewer owns them.
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [items.length, safeIndex, onIndex, onClose]);

  if (!item) return null;

  const credit = [
    item.author,
    item.license,
    capLabel(item.capture_date),
    item.location?.name ?? anchorLabel,
  ]
    .filter(Boolean)
    .join(' · ');

  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        // Above Leaflet's 1000-level controls, below nothing else in the widget.
        zIndex: 1100,
        background: 'var(--bg-base)',
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
          borderBottom: '1px solid var(--border-subtle)',
        }}
      >
        {items.length > 1 && (
          <button
            type="button"
            className="widget-action"
            style={{ padding: '2px 4px', minHeight: 18 }}
            onClick={() => onIndex((safeIndex - 1 + items.length) % items.length)}
            aria-label="Previous image"
          >
            <ChevronLeft size={11} />
          </button>
        )}
        <span
          style={{
            flex: '1 1 0',
            minWidth: 0,
            fontSize: 12,
            color: 'var(--text-primary)',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          {item.title}
        </span>
        <span
          style={{
            flexShrink: 0,
            fontFamily: mono,
            fontVariantNumeric: 'tabular-nums',
            fontSize: 10,
            color: 'var(--text-muted)',
          }}
        >
          {safeIndex + 1} / {items.length}
        </span>
        {items.length > 1 && (
          <button
            type="button"
            className="widget-action"
            style={{ padding: '2px 4px', minHeight: 18 }}
            onClick={() => onIndex((safeIndex + 1) % items.length)}
            aria-label="Next image"
          >
            <ChevronRight size={11} />
          </button>
        )}
        <button
          type="button"
          className="widget-action"
          style={{ padding: '2px 4px', minHeight: 18 }}
          onClick={onClose}
          aria-label="Close imagery viewer"
        >
          <X size={12} />
        </button>
      </div>

      <div style={{ flex: '1 1 0', minHeight: 0, position: 'relative', background: 'var(--bg-base)' }}>
        <MediaFrame item={item} zoomed={zoomed} onToggleZoom={() => setZoomed((z) => !z)} onFail={onFail} />
      </div>

      {item.caption && (
        <div
          style={{
            flexShrink: 0,
            padding: '5px 10px 0',
            fontSize: 10,
            lineHeight: 1.5,
            color: 'var(--text-secondary)',
          }}
        >
          {item.caption}
        </div>
      )}

      <div
        style={{
          flexShrink: 0,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          flexWrap: 'wrap',
          padding: '6px 10px',
          borderTop: '1px solid var(--border-subtle)',
        }}
      >
        <span
          style={{
            flex: '1 1 auto',
            minWidth: 0,
            fontFamily: mono,
            fontSize: 9,
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            color: 'var(--text-muted)',
            lineHeight: 1.5,
          }}
        >
          {credit}
        </span>
        <a href={item.page_url} target="_blank" rel="noopener noreferrer" style={chipStyle}>
          Commons <ExternalLink size={9} />
        </a>
        {linkOuts.map((doc) => (
          <a key={doc.id} href={doc.page_url} target="_blank" rel="noopener noreferrer" style={chipStyle}>
            {doc.title} · PDF <ExternalLink size={9} />
          </a>
        ))}
        {categoryUrl && (
          <a href={categoryUrl} target="_blank" rel="noopener noreferrer" style={chipStyle}>
            All files on Commons <ExternalLink size={9} />
          </a>
        )}
      </div>
    </div>
  );
}
