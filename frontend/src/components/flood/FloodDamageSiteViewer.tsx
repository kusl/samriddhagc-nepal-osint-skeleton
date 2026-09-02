/**
 * The damage pair opened over the map, hung off the point it depicts.
 *
 * This is the overlay half of the founder's tactical map: a chip on the
 * corridor is the position, and this is the imagery attached to it. It is the
 * same absolute-inset panel FloodMediaViewer uses over the same column, for the
 * same reason — the map keeps its frame, its zoom and its replay position
 * underneath, so closing the pair returns the reader to exactly the canvas they
 * left rather than to a re-fitted map.
 *
 * It carries its own licence footer rather than leaning on the map's. The
 * footer under the canvas credits the layers on the canvas; these are 30–60 cm
 * pixels drawn over the whole widget, and CC BY-NC 4.0 is the condition they
 * are shown on. A screenshot of this overlay must keep the credit without the
 * map being in the frame at all.
 */
import { useEffect, useMemo, useState } from 'react';
import { ExternalLink, X } from 'lucide-react';

import {
  C,
  Comparator,
  Emsr927Note,
  LEVEL_NAME,
  PhaseDossier,
  SiteStatement,
  chipStyle,
  figure,
  label,
} from './DamageComparator';
import {
  orderedLevels,
  formatGroundWidth,
  type DamageSite,
  type DamageSitesResponse,
  type DamageLevelKey,
} from './damageSites';

/** Below this the two dossiers stop fitting beside each other and stack. */
const STACK_FACTS_PX = 560;

/** Below this the header's controls take the whole row and the site name is
 *  squeezed to nothing, so the name takes a line of its own. */
const WRAP_HEADER_PX = 520;

/** Below this the frame, the frame facts and the licence footer cannot all fit
 *  — on a phone card the whole overlay is barely 150 px. Two things give way,
 *  in this order. The frame facts go first: every one of them is already on the
 *  comparator's own captions. Then the overlay scrolls, exactly as the archived
 *  explorer's narrow layout does, so the picture keeps a legible floor instead
 *  of being squeezed to a sliver — and the licence line, which is the condition
 *  the pixels are shown on, stays in the document rather than being dropped. */
const SHORT_PX = 250;

/** The least imagery worth calling a comparison. Below the pane's own height
 *  the overlay scrolls to reach it. */
const FRAME_FLOOR_PX = 150;

export function FloodDamageSiteViewer({
  site,
  data,
  onClose,
  onGoToMap,
}: {
  site: DamageSite;
  data: DamageSitesResponse;
  onClose: () => void;
  /** Closes the overlay and drops the map on the site. null where the map
   *  cannot take the view — never a dead button. */
  onGoToMap: (() => void) | null;
}) {
  // Site, not context: the mid frame is the one the corridor's findings are
  // written about, and the reader arrived by clicking that exact place.
  const [levelKey, setLevelKey] = useState<DamageLevelKey>('site');
  const levels = useMemo(() => orderedLevels(site.levels), [site]);
  const level = useMemo(
    () => levels.find((l) => l.level === levelKey) ?? levels[levels.length - 1] ?? null,
    [levels, levelKey],
  );

  useEffect(() => {
    setLevelKey('site');
  }, [site.key]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    // Capture phase: the comparator's own divider claims the arrow keys and the
    // dashboard shell claims others further down the tree; Escape belongs to
    // whatever is open on top, which is this.
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [onClose]);

  // Measured on the overlay itself rather than on the facts row, which does not
  // exist to be measured at the size where the decision to drop it is made.
  const [box, setBox] = useState({ w: 0, h: 0 });
  const [rootNode, setRootNode] = useState<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!rootNode) return;
    const ro = new ResizeObserver(([entry]) => {
      const r = entry.contentRect;
      setBox({ w: r.width, h: r.height });
    });
    ro.observe(rootNode);
    return () => ro.disconnect();
  }, [rootNode]);
  const stackFacts = box.w > 0 && box.w < STACK_FACTS_PX;
  const wrapHeader = box.w > 0 && box.w < WRAP_HEADER_PX;
  const short = box.h > 0 && box.h < SHORT_PX;

  const postTop = level?.post.top ?? null;
  const emsr927 = site.key === 'syabrubesi';

  return (
    <div
      ref={setRootNode}
      style={{
        position: 'absolute',
        inset: 0,
        // Above Leaflet's 1000-level controls, level with the media viewer —
        // only one of the two is ever open.
        zIndex: 1100,
        background: C.base,
        display: 'flex',
        flexDirection: 'column',
        overflowY: short ? 'auto' : 'hidden',
      }}
    >
      <div
        style={{
          flexShrink: 0,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          flexWrap: wrapHeader ? 'wrap' : 'nowrap',
          padding: '5px 8px',
          borderBottom: `1px solid ${C.border}`,
        }}
      >
        <span
          style={{
            fontSize: 12,
            color: C.text,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            // Where the controls claim the whole row, the name takes its own
            // line rather than being squeezed out of the header entirely.
            flex: wrapHeader ? '1 1 100%' : '0 1 auto',
          }}
        >
          {site.name}
        </span>
        <span
          style={{
            ...figure,
            fontSize: 9,
            letterSpacing: '0.06em',
            color: C.muted,
            flexShrink: 0,
            whiteSpace: 'nowrap',
          }}
        >
          {site.km_mark === null ? 'ORIGIN' : `KM ${site.km_mark}`}
          {level ? ` · ${formatGroundWidth(level.width_m)} ACROSS` : ''}
        </span>

        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 3, flexShrink: 0 }}>
          {levels.map((l) => (
            <button
              key={l.level}
              type="button"
              onClick={() => setLevelKey(l.level)}
              title={`${formatGroundWidth(l.width_m)} across`}
              style={{
                padding: '2px 7px',
                fontSize: 9,
                fontWeight: 600,
                fontFamily: C.mono,
                letterSpacing: '0.06em',
                textTransform: 'uppercase',
                cursor: 'pointer',
                whiteSpace: 'nowrap',
                border: `1px solid ${C.border}`,
                background: l.level === level?.level ? C.elevated : 'transparent',
                color: l.level === level?.level ? C.text : C.muted,
              }}
            >
              {LEVEL_NAME[l.level]}
            </button>
          ))}
          {onGoToMap && (
            <button
              type="button"
              onClick={onGoToMap}
              title="Close and centre the map on this site"
              style={{
                marginLeft: 3,
                padding: '2px 7px',
                fontSize: 9,
                fontFamily: C.mono,
                letterSpacing: '0.06em',
                textTransform: 'uppercase',
                cursor: 'pointer',
                whiteSpace: 'nowrap',
                border: `1px solid ${C.border}`,
                background: 'transparent',
                color: C.info,
              }}
            >
              View on map
            </button>
          )}
          <button
            type="button"
            className="widget-action"
            style={{ padding: '2px 4px', minHeight: 18 }}
            onClick={onClose}
            aria-label="Close damage comparison"
            title="Close (Esc)"
          >
            <X size={11} />
          </button>
        </div>
      </div>

      {/* Basis 0 where there is height to divide, so the frame takes what is
          left after the footer. On a phone card there is none to divide: the
          frame claims its floor and the overlay scrolls around it. */}
      <div
        style={{
          flex: short ? '1 0 auto' : '1 1 0',
          minHeight: short ? FRAME_FLOOR_PX : 0,
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {level ? (
          // Keyed on site and level: the divider, the load states and the
          // measured box all belong to one pair of frames and must not carry
          // over to the next site's.
          <Comparator key={`${site.key}-${level.level}`} level={level} siteName={site.name} />
        ) : (
          // Levels empty is not an error state. Nothing has been flown over this
          // ground since the collapse, and saying so is the intelligence — so
          // the site opens like any other rather than refusing to open.
          <SiteStatement site={site} />
        )}
      </div>

      {level && !short && (
        <div
          style={{
            flexShrink: 0,
            display: 'flex',
            flexDirection: stackFacts ? 'column' : 'row',
            gap: stackFacts ? 4 : 16,
            padding: '6px 12px',
            borderTop: `1px solid ${C.border}`,
            background: C.surface,
            maxHeight: '40%',
            overflowY: 'auto',
          }}
        >
          {/* Copernicus graded this one site, and its count is the only
              authoritative damage figure the desk holds over any of these
              frames — so it travels with the pixels it was measured from. The
              site's own finding is the one-line form of that same count, and
              stating both side by side would read as two findings; the note
              wins because it carries the licence condition and the link. */}
          {emsr927 ? (
            <div style={{ flex: '1 1 0', minWidth: 0 }}>
              <Emsr927Note divider={false} />
            </div>
          ) : site.finding ? (
            <div style={{ flex: '1 1 0', minWidth: 0 }}>
              <div style={{ fontSize: 11, lineHeight: 1.45, color: C.text }}>{site.finding}</div>
              {site.finding_source && (
                <div style={{ ...label, fontSize: 9, letterSpacing: '0.06em', lineHeight: 1.45, marginTop: 2 }}>
                  {site.finding_source}
                </div>
              )}
            </div>
          ) : null}
          <div style={{ display: 'flex', gap: 16, flex: '1 1 0', minWidth: 0 }}>
            <PhaseDossier phase="PRE" frame={level.pre} compact />
            <PhaseDossier phase="POST" frame={level.post} compact />
          </div>
        </div>
      )}

      {/* Outside every scroll region and never truncated: CC BY-NC 4.0 makes
          this line the condition on which the pixels above may be shown. */}
      <div
        style={{
          flexShrink: 0,
          display: 'flex',
          alignItems: 'baseline',
          gap: 10,
          flexWrap: 'wrap',
          padding: '6px 12px',
          borderTop: `1px solid ${C.border}`,
          background: C.surface,
          fontSize: 9,
          lineHeight: 1.5,
          color: C.muted,
        }}
      >
        {/* The same short credit the map's own imagery banner carries, for the
            same reason: on a phone card the full sentence wraps to three lines
            and eats the picture, but the licensor, the server and the licence
            are what a crop of this frame has to keep either way. */}
        <span style={{ flex: '1 1 260px', minWidth: 0 }}>
          {short ? (
            <>© Vantor · Esri DRP · </>
          ) : (
            <>
              Satellite imagery © 2026 Vantor (formerly Maxar), Open Data program · served via Esri
              Disaster Response Program ·{' '}
            </>
          )}
          <a
            href={data.license_url}
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: C.info, textDecoration: 'none' }}
          >
            CC BY-NC 4.0
          </a>
        </span>
        {postTop && !short && (
          <a href={postTop.item_url} target="_blank" rel="noopener noreferrer" style={chipStyle}>
            STAC item <ExternalLink size={9} />
          </a>
        )}
        {postTop?.visual && !short && (
          <a href={postTop.visual} target="_blank" rel="noopener noreferrer" style={chipStyle}>
            COG .tif <ExternalLink size={9} />
          </a>
        )}
        {!short && (
          <a href={data.service_url} target="_blank" rel="noopener noreferrer" style={chipStyle}>
            Image service <ExternalLink size={9} />
          </a>
        )}
      </div>
    </div>
  );
}
