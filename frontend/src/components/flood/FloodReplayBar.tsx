/**
 * The replay transport for the district impact map: two 24 px lines docked
 * between the map canvas and its footer.
 *
 * Line 1 is the transport. Line 2 is the honesty line — it names, at every
 * moment, which bulletin the fills came from. That readout is the reason the
 * replay is defensible: NDRRMA published a district breakdown twice, so the
 * map steps between two dated states and says which one is on screen instead
 * of implying a daily series nobody published.
 */
import { Pause, Play, RotateCcw, SkipBack, SkipForward } from 'lucide-react';

import { SCRUB_STEP, SPEEDS, type ReplayState } from './floodReplay';
import { F, HAIRLINE, LABEL_XS, MS, Status, dtgDay, fmt } from './milspec';

const mono = MS.mono;

const SCRUB_CSS = `
.flood-replay-scrub{-webkit-appearance:none;appearance:none;background:transparent;height:14px;padding:0;margin:0;cursor:pointer}
.flood-replay-scrub::-webkit-slider-runnable-track{height:2px;background:var(--border-default)}
.flood-replay-scrub::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;width:10px;height:10px;margin-top:-4px;background:var(--text-primary);border:0;border-radius:0}
.flood-replay-scrub::-moz-range-track{height:2px;background:var(--border-default)}
.flood-replay-scrub::-moz-range-thumb{width:10px;height:10px;background:var(--text-primary);border:0;border-radius:0}
.flood-replay-scrub:focus-visible{outline:1px solid var(--status-info);outline-offset:2px}
`;

const line: React.CSSProperties = {
  height: 24,
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  padding: '0 12px',
  minWidth: 0,
  // Nothing may escape the widget at a phone width: the segments below shrink
  // in reverse order of importance instead.
  overflow: 'hidden',
};

/** Shrinks to an ellipsis rather than pushing its neighbours off the widget. */
const clipped: React.CSSProperties = {
  minWidth: 0,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
};

const btn: React.CSSProperties = {
  padding: '1px 4px',
  minHeight: 18,
  display: 'inline-flex',
  alignItems: 'center',
};

/** The transport speaks in the desk's one label voice and nothing else. */
const label: React.CSSProperties = { ...LABEL_XS, whiteSpace: 'nowrap' };

/** The HUD is four facts on one line; without a divider they read as one. */
const Sep = () => (
  <span aria-hidden style={{ ...label, color: MS.rule, flexShrink: 0 }}>·</span>
);

interface Props {
  replay: ReplayState;
  /** Named exactly as the bulletin names itself, or the sentence that says no
   *  breakdown had been published yet. */
  fillsLabel: string;
}

export function FloodReplayBar({ replay, fillsLabel }: Props) {
  const { toll, beat } = replay;

  return (
    <div
      style={{
        flexShrink: 0,
        borderTop: HAIRLINE,
        background: MS.surface,
      }}
    >
      <style>{SCRUB_CSS}</style>

      <div style={line}>
        <button
          type="button"
          className="widget-action"
          style={btn}
          onClick={replay.toggle}
          title={replay.playing ? 'Pause replay' : 'Play replay'}
          aria-label={replay.playing ? 'Pause replay' : 'Play replay'}
        >
          {replay.playing ? <Pause size={11} /> : <Play size={11} />}
        </button>
        <button
          type="button"
          className="widget-action"
          style={btn}
          onClick={replay.stepBack}
          title="Previous published moment"
          aria-label="Step back to the previous published moment"
        >
          <SkipBack size={11} />
        </button>
        <button
          type="button"
          className="widget-action"
          style={btn}
          onClick={replay.stepForward}
          title="Next published moment"
          aria-label="Step forward to the next published moment"
        >
          <SkipForward size={11} />
        </button>

        <select
          value={replay.speed}
          onChange={(e) => replay.setSpeed(Number(e.target.value))}
          aria-label="Replay speed"
          style={{
            background: MS.elevated,
            color: MS.text,
            border: HAIRLINE,
            borderRadius: 2,
            padding: '2px 4px',
            fontSize: 9,
            fontFamily: mono,
            letterSpacing: '0.04em',
          }}
        >
          {SPEEDS.map((s) => (
            <option key={s.minutesPerSecond} value={s.minutesPerSecond}>
              {s.label}
            </option>
          ))}
        </select>

        <input
          type="range"
          className="flood-replay-scrub"
          min={replay.t0}
          max={replay.t1}
          step={SCRUB_STEP}
          value={replay.t}
          onChange={(e) => {
            replay.pause();
            replay.setT(Number(e.target.value));
          }}
          aria-label="Replay time"
          style={{ flex: '1 1 0', minWidth: 40 }}
        />

        <span
          style={{
            ...label,
            ...clipped,
            color: MS.sub,
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          {replay.isLive ? 'LIVE · ALL RECORDS TO DATE' : replay.clock}
        </span>
      </div>

      <div style={{ ...line, borderTop: HAIRLINE }}>
        {replay.isLive ? (
          <Status tone="muted">LIVE</Status>
        ) : (
          <button
            type="button"
            className="widget-action"
            style={{ ...btn, gap: 3, ...label, color: MS.info }}
            onClick={replay.goLive}
            title="Return to the latest bulletin"
          >
            <RotateCcw size={9} /> REPLAY
          </button>
        )}

        <Sep />

        <span
          style={{
            ...label,
            ...clipped,
            color: MS.sub,
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          {toll ? (
            <>
              {/* An unpublished death count reads as a dash, never as a zero. */}
              <F tone="critical">{fmt(toll.deaths)}</F> <Status tone="critical">DEAD</Status>
              {toll.missing != null && (
                <>
                  {' · '}
                  <F tone="high">{fmt(toll.missing)}</F> <Status tone="high">MISSING</Status>
                </>
              )}
              {` · AS OF ${dtgDay(toll.as_of)}`}
            </>
          ) : (
            <Status tone="muted">NO OFFICIAL TOLL YET</Status>
          )}
        </span>

        <Sep />

        <span style={{ ...label, ...clipped }}>{fillsLabel}</span>

        <Sep />

        <span
          style={{
            ...label,
            ...clipped,
            // Lowest priority: the beat headline is narrative, the two figures
            // to its left are the record.
            flex: '1 1 0',
            color: MS.sub,
            textTransform: 'none',
            letterSpacing: '0.02em',
          }}
          title={beat ? `${beat.stamp} — ${beat.headline}` : undefined}
        >
          {beat ? (
            <>
              <span style={{ ...label, color: 'var(--text-muted)' }}>
                {replay.beatCount}/{replay.beatTotal} {beat.kind}
              </span>
              {' '}
              {beat.headline}
              {!beat.time_published && (
                <span style={{ ...label, color: 'var(--text-muted)' }}> · TIME NOT PUBLISHED</span>
              )}
            </>
          ) : (
            <span style={label}>NOTHING PUBLISHED YET AT THIS MOMENT</span>
          )}
        </span>
      </div>
    </div>
  );
}
