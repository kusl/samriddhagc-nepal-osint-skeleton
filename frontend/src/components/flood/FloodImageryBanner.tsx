/**
 * The caption that rides on the high-resolution overlay.
 *
 * Pixels on a map are the most persuasive thing this desk draws and the easiest
 * to misread, so this block is permanent ink over the canvas rather than a
 * hover: a screenshot of the frame keeps the phase, the acquisition date, the
 * ground sample distance and the licence, or it keeps nothing.
 *
 * Four honesty lines live here and each answers a specific way the picture
 * lies. PRE is a 2021–2024 archive pass, not the eve of the flood. Cloud is a
 * whole-scene figure, so a 79%-cloud scene can still be clear over this frame
 * and a white patch is unassessed ground rather than undamaged ground. Where
 * more than one scene is in the frame the caption speaks only for the one the
 * mosaic put on top. And where the frame runs past every footprint the blank is
 * absence of imagery, not absence of damage.
 */
import { ExternalLink } from 'lucide-react';

import type { DrpPhase } from './drpImagery';

const C = {
  elevated: 'var(--bg-elevated)',
  border: 'var(--border-subtle)',
  text: 'var(--text-primary)',
  sub: 'var(--text-secondary)',
  muted: 'var(--text-muted)',
  info: 'var(--status-info)',
  medium: 'var(--status-medium)',
  mono: 'var(--font-mono)',
};

const line: React.CSSProperties = {
  fontFamily: C.mono,
  fontSize: 9,
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
  lineHeight: 1.45,
  color: C.muted,
};

export type ImageryStatus = 'zoom' | 'nocover' | 'loading' | 'ok' | 'failed';

export interface ImageryCaption {
  id: string;
  day: string | null;
  gsdM: number | null;
  platform: string | null;
  cloud: number | null;
  inView: number;
  fullFrame: boolean;
  /** "4 YR 10 MO", pre frames only. */
  baselineGap: string | null;
}

export function FloodImageryBanner({
  phase,
  onPhase,
  status,
  caption,
  credit,
  licenseUrl,
  minZoom,
  onGoToSite,
  compact,
  narrow,
}: {
  phase: DrpPhase;
  onPhase: (phase: DrpPhase) => void;
  status: ImageryStatus;
  caption: ImageryCaption | null;
  credit: string;
  licenseUrl: string;
  minZoom: number;
  onGoToSite: (() => void) | null;
  compact: boolean;
  /** A pane too narrow for a floating card. The caption then spans the bottom
   *  of the map instead of covering two thirds of it. */
  narrow: boolean;
}) {
  const stamp = caption
    ? [
        phase.toUpperCase(),
        caption.day,
        caption.gsdM != null ? `${caption.gsdM.toFixed(2)} M` : null,
        caption.platform,
      ]
        .filter(Boolean)
        .join(' · ')
    : null;

  return (
    <div
      style={{
        position: 'absolute',
        zIndex: 800,
        ...(narrow
          ? { left: 0, right: 0, bottom: 0 }
          : { top: 6, right: 6, maxWidth: 268 }),
        padding: '5px 7px',
        background: C.elevated,
        border: `1px solid ${C.border}`,
        boxShadow: '0 6px 18px rgba(0, 0, 0, 0.6)',
      }}
    >
      {/* On a narrow pane the phase switch and the stamp share a row: every
          line here is taken out of the picture it describes. */}
      <div style={{ display: 'flex', alignItems: 'center', gap: narrow ? 6 : 3 }}>
        <div style={{ display: 'flex', gap: 3, flex: narrow ? '0 0 auto' : '1 1 0' }}>
          {(['pre', 'post'] as DrpPhase[]).map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => onPhase(p)}
              aria-pressed={phase === p}
              style={{
                flex: narrow ? '0 0 auto' : '1 1 0',
                padding: '2px 8px',
                fontFamily: C.mono,
                fontSize: 9,
                fontWeight: 600,
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
                cursor: 'pointer',
                border: `1px solid ${C.border}`,
                background: phase === p ? 'var(--bg-hover)' : 'transparent',
                color: phase === p ? C.text : C.muted,
              }}
            >
              {p}
            </button>
          ))}
        </div>
        {narrow && (
          <div
            style={{
              ...line,
              flex: '1 1 0',
              minWidth: 0,
              fontVariantNumeric: 'tabular-nums',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              color: status === 'ok' && phase === 'post' ? C.info : C.sub,
            }}
          >
            {status === 'ok' ? (
              stamp
            ) : status === 'zoom' ? (
              // The one-line layout has no room for a separate link, so the
              // whole line is the way in. Without it a phone reader can turn
              // the layer on and never reach ground it can draw.
              onGoToSite ? (
                <button
                  type="button"
                  onClick={onGoToSite}
                  style={{
                    padding: 0,
                    border: 'none',
                    background: 'none',
                    cursor: 'pointer',
                    font: 'inherit',
                    letterSpacing: 'inherit',
                    textTransform: 'inherit',
                    color: C.info,
                  }}
                >
                  Zoom {minZoom}+ · go to Rasuwagadhi
                </button>
              ) : (
                `Zoom to ${minZoom}+ for 30–60 cm`
              )
            ) : status === 'nocover' ? (
              `No ${phase}-event coverage here`
            ) : status === 'failed' ? (
              'Image service unreachable'
            ) : (
              'Rendering frame…'
            )}
          </div>
        )}
      </div>

      {!narrow && status === 'zoom' && (
        <div style={{ ...line, marginTop: 4, color: C.sub }}>
          Zoom to {minZoom}+ for 30–60 cm imagery
          {onGoToSite && (
            <>
              {' · '}
              <button
                type="button"
                onClick={onGoToSite}
                style={{
                  padding: 0,
                  border: 'none',
                  background: 'none',
                  cursor: 'pointer',
                  font: 'inherit',
                  letterSpacing: 'inherit',
                  textTransform: 'inherit',
                  color: C.info,
                }}
              >
                go to Rasuwagadhi
              </button>
            </>
          )}
        </div>
      )}

      {!narrow && status === 'nocover' && (
        // Absence stated, never a blank frame left to imply undamaged ground.
        <div style={{ ...line, marginTop: 4, color: C.sub }}>
          No {phase}-event Vantor coverage in this frame
        </div>
      )}

      {!narrow && status === 'failed' && (
        <div style={{ ...line, marginTop: 4, color: C.sub }}>Image service unreachable</div>
      )}

      {!narrow && status === 'loading' && <div style={{ ...line, marginTop: 4 }}>Rendering frame…</div>}

      {status === 'ok' && caption && (
        <>
          {!narrow && (
            <div
              style={{
                ...line,
                marginTop: 4,
                fontVariantNumeric: 'tabular-nums',
                color: phase === 'post' ? C.info : C.sub,
              }}
            >
              {stamp}
            </div>
          )}

          {/* Never dropped, at any width: a reader shown PRE beside POST reads
              days unless the four-year gap is on screen. */}
          {caption.baselineGap && (
            <div style={line}>Archive baseline — {caption.baselineGap} before the flood</div>
          )}

          {!compact && caption.cloud != null && (
            <div style={{ ...line, color: caption.cloud >= 50 ? C.medium : C.muted }}>
              Scene cloud {caption.cloud}% — whole-scene figure; white is cloud, not ground
            </div>
          )}

          {!compact && caption.inView > 1 && (
            <div style={line}>
              {caption.inView} frames in view · top frame labelled
            </div>
          )}

          {!compact && !caption.fullFrame && (
            <div style={line}>Frame runs past coverage — blank is no-data, not ground</div>
          )}
        </>
      )}

      {/* CC BY-NC 4.0 is the condition the pixels are shown on, so this line
          stays even at the compact height where every caveat above is cut. It
          is the short credit — licensor and licence — because it has to fit
          over a map pane; the full attribution string sits in the widget
          footer, which is what a screenshot of the whole desk keeps. */}
      <a
        href={licenseUrl}
        target="_blank"
        rel="noopener noreferrer"
        style={{
          ...line,
          display: 'block',
          marginTop: 4,
          paddingTop: 3,
          borderTop: `1px solid ${C.border}`,
          color: C.sub,
          textDecoration: 'none',
          whiteSpace: 'nowrap',
        }}
      >
        {credit} <ExternalLink size={8} style={{ verticalAlign: 'middle', color: C.info }} />
      </a>
    </div>
  );
}
