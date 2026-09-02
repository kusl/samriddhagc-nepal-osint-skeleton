/**
 * REPLAY HUD — the transport and readout band under OPERATIONAL PICTURE · 3D.
 *
 * A fixed 84 px band, two lines, no scroll ever. It is not a control panel: it
 * is the caption on the animation, and its job is to make every frame of the
 * map defensible without the reader leaving the widget.
 *
 *   LINE 1  transport — play, ±1 beat, speed, a scrubber whose tick marks ARE
 *           the record (front fixes above the line, beats below), and the DTG
 *           of the instant on screen in all three forms the desk uses.
 *   LINE 2  the two questions the map cannot answer by itself: WHAT beat is on
 *           screen and who published it, and WHERE the front is — with the word
 *           PUBLISHED or ESTIMATED, and, when estimated, the two published
 *           fixes the position was interpolated between.
 *
 * The clock's own DTG is built from `clock.nptIso` because no source published
 * that instant; every other time on this band is formatted from the ORIGINAL
 * `t_npt` string the record carries, so a day-only beat prints as a day.
 *
 * Keyboard (only while the band has focus — the widget owns the page's keys):
 *   SPACE play/pause · ← previous beat · → next beat
 */
import { useCallback, useMemo, type CSSProperties, type KeyboardEvent } from 'react';
import { ExternalLink, Pause, Play, SkipBack, SkipForward } from 'lucide-react';

import {
  F,
  Grade,
  HAIRLINE,
  LABEL_XS,
  MS,
  Status,
  Tag,
  clockNpt,
  dtgDay,
  dtgNpt,
  dtgZ,
  fmt,
  gradeFor,
  type Tone,
} from '../milspec';
import { SPEED_PRESETS, frontPlaceName, type ReplayClock, type ReplayConfidence, type FilmNarration } from './replayEngine';

/** The band's height. The map sits above it; nothing overlaps. */
export const HUD_HEIGHT = 122;
/** Height of the chapter strip that sits above the transport line. */
const FILM_ROW_H = 38;

const SCRUB_H = 14;

/**
 * The scrubber is drawn, not styled: the native track is made transparent so
 * the record's own tick marks show through, and the thumb is a 3 px playhead.
 */
const SCRUB_CSS = `
.replay3d-hud:focus{outline:none}
.replay3d-hud:focus-visible{outline:1px solid var(--status-info);outline-offset:-1px}
.replay3d-scrub{-webkit-appearance:none;appearance:none;position:absolute;left:0;top:0;width:100%;height:${SCRUB_H}px;background:transparent;padding:0;margin:0;cursor:pointer}
.replay3d-scrub::-webkit-slider-runnable-track{height:2px;background:transparent}
.replay3d-scrub::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;width:3px;height:${SCRUB_H}px;margin-top:-6px;background:var(--text-primary);border:0;border-radius:0}
.replay3d-scrub::-moz-range-track{height:2px;background:transparent}
.replay3d-scrub::-moz-range-thumb{width:3px;height:${SCRUB_H}px;background:var(--text-primary);border:0;border-radius:0}
.replay3d-scrub:focus{outline:none}
`;

const label: CSSProperties = { ...LABEL_XS, whiteSpace: 'nowrap' };

/** Shrinks to an ellipsis rather than pushing a neighbour off the band. */
const clipped: CSSProperties = {
  minWidth: 0,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
};

const btn: CSSProperties = {
  padding: '1px 4px',
  minHeight: 18,
  display: 'inline-flex',
  alignItems: 'center',
  flexShrink: 0,
};

const lineRow: CSSProperties = {
  display: 'flex',
  alignItems: 'baseline',
  gap: 6,
  minWidth: 0,
  overflow: 'hidden',
};

const Sep = () => (
  <span aria-hidden style={{ ...label, color: MS.rule, flexShrink: 0 }}>
    ·
  </span>
);

/** How a record's own confidence word is toned. Never a background, only text. */
const CONF_TONE: Record<string, Tone> = {
  published: 'low',
  derived: 'info',
  estimated: 'medium',
};

const confTone = (c: ReplayConfidence | string | null | undefined): Tone =>
  (c && CONF_TONE[String(c).toLowerCase()]) || 'muted';

const confWord = (c: ReplayConfidence | string | null | undefined): string =>
  c ? String(c).toUpperCase() : 'NOT STATED';

/** Beat kinds read as what they are; the tone is the desk's, not the source's. */
const KIND_TONE: Record<string, Tone> = {
  trigger: 'critical',
  impact: 'high',
  warning: 'medium',
  response: 'info',
  assessment: 'sub',
};

/** "26 AUG 26 · 0915 NPT · 260330Z" — the free-running clock, all three ways. */
const clamp01 = (v: number) => Math.min(1, Math.max(0, v));

/** "m:ss" of real playback. */
function fmtClock(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

function clockDtg(iso: string): string {
  if (!iso) return '—';
  const zulu = dtgZ(iso).split(' ')[0];
  return `${dtgDay(iso)} · ${clockNpt(iso)} · ${zulu}`;
}

export interface ReplayHudProps {
  clock: ReplayClock;
  style?: CSSProperties;
}

export function ReplayHud({ clock, style }: ReplayHudProps) {
  const { timeline, t, playing, speed, front, frontKm, tollNow, activeBeat, visibleBeatCount, film, filmScript, mode, filmR } = clock;

  // The narration line: the latest sentence of the chapter the clock has
  // reached. A beat-backed line carries the beat's source and grade; a quoted
  // sentence carries its document's.
  const narration = useMemo<FilmNarration | null>(() => {
    if (!film) return null;
    const lines = film.scene.narration.filter((n) => n.t <= t + 1);
    return lines.length ? lines[lines.length - 1] : film.scene.narration[0] ?? null;
  }, [film, t]);
  const { t0, tEnd, durationMs, beats, keyframes } = timeline;

  const scrubbable = durationMs > 0;
  const frac = scrubbable ? (t - t0) / durationMs : 0;

  // Past the last published fix the front is not moving because the record
  // stopped stating where it was — the band says so rather than letting a
  // stationary marker read as a sighting.
  const lastFix = keyframes.length ? keyframes[keyframes.length - 1] : null;
  const holding = !!lastFix && t > lastFix.t;

  const onKeyDown = useCallback(
    (e: KeyboardEvent<HTMLDivElement>) => {
      if (e.key === ' ' || e.key === 'Spacebar' || e.code === 'Space') {
        e.preventDefault();
        clock.toggle();
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        clock.stepBeat(-1);
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        clock.stepBeat(1);
      }
    },
    [clock],
  );

  const beatGrade = activeBeat ? gradeFor(activeBeat.source).code : null;

  return (
    <div
      className="replay3d-hud"
      tabIndex={0}
      role="group"
      aria-label="Replay transport. Space plays or pauses, left and right arrows step one beat."
      title="SPACE play/pause · ← → step one beat"
      onKeyDown={onKeyDown}
      style={{
        position: 'relative',
        flex: '0 0 auto',
        height: HUD_HEIGHT,
        boxSizing: 'border-box',
        display: 'flex',
        flexDirection: 'column',
        borderTop: HAIRLINE,
        background: MS.surface,
        overflow: 'hidden',
        ...style,
      }}
    >
      <style>{SCRUB_CSS}</style>

      {/* ---------------------------------------------------------- film row */}
      {filmScript && film && (
        <div
          style={{
            height: FILM_ROW_H,
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '0 12px',
            minWidth: 0,
            borderBottom: HAIRLINE,
          }}
        >
          <span style={{ display: 'inline-flex', gap: 3, flexShrink: 0 }}>
            <Tag active={mode === 'film'} tone={mode === 'film' ? 'text' : 'muted'} onClick={() => clock.setMode('film')}>FILM</Tag>
            <Tag active={mode === 'manual'} tone={mode === 'manual' ? 'text' : 'muted'} onClick={() => clock.setMode('manual')}>MANUAL</Tag>
          </span>

          {/* Chapter bar: one segment per scene, sized by its real length. */}
          <span
            style={{ display: 'flex', gap: 2, flex: '0 0 26%', minWidth: 120, height: 10, alignItems: 'stretch' }}
            title={`${filmScript.scenes.length} chapters · ${Math.round(filmScript.totalS / 60)} min`}
          >
            {filmScript.scenes.map((sc) => {
              const w = Math.max(1, sc.realEnd - sc.realStart);
              const cur = sc.index === film.scene.index;
              const done = mode === 'film' ? filmR >= sc.realEnd : t >= sc.tTo;
              const fill = cur ? (mode === 'film' ? clamp01((filmR - sc.realStart) / w) : film.progress) : done ? 1 : 0;
              return (
                <span
                  key={sc.key}
                  onClick={() => clock.jumpToScene(sc.index)}
                  title={`${String(sc.index + 1).padStart(2, '0')} ${sc.title}`}
                  style={{ flex: `${w} 1 0`, position: 'relative', background: MS.hairline, cursor: 'pointer', minWidth: 3 }}
                >
                  <span style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${fill * 100}%`, background: cur ? MS.critical : MS.sub, opacity: cur ? 1 : 0.7 }} />
                </span>
              );
            })}
          </span>

          <span style={{ ...label, color: MS.text, fontWeight: 600, whiteSpace: 'nowrap' }}>
            {String(film.scene.index + 1).padStart(2, '0')} / {String(filmScript.scenes.length).padStart(2, '0')} · {film.scene.title}
          </span>
          {film.phase === 'hold' && mode === 'film' && film.holdRemainingS > 0 && (
            <Status tone="medium">HOLD {Math.ceil(film.holdRemainingS)}S</Status>
          )}

          {narration && (
            <span style={{ ...lineRow, flex: '1 1 0', gap: 6 }}>
              <span
                style={{ ...clipped, fontFamily: MS.mono, fontSize: 11, lineHeight: 1.3, color: MS.sub }}
                title={narration.detail ? `${narration.text} — ${narration.detail}` : narration.text}
              >
                {narration.text}
              </span>
              {narration.source && <span style={{ ...label, ...clipped, color: MS.muted, maxWidth: 220 }}>{narration.source}</span>}
              {narration.source && <Grade code={gradeFor(narration.source).code} />}
              {narration.source_url && (
                <a href={narration.source_url} target="_blank" rel="noreferrer noopener" style={{ ...label, color: MS.info, display: 'inline-flex', alignItems: 'center', gap: 3, textDecoration: 'none', flexShrink: 0 }}>
                  SOURCE <ExternalLink size={9} />
                </a>
              )}
            </span>
          )}
          <span style={{ ...label, color: MS.muted, whiteSpace: 'nowrap', marginLeft: 'auto' }}>
            {mode === 'film' ? `${fmtClock(filmR)} / ${fmtClock(filmScript.totalS)}` : 'MANUAL · SCRUB FREELY'}
          </span>
        </div>
      )}

      {/* ---------------------------------------------------------- line 1 */}
      <div style={{ height: 28, display: 'flex', alignItems: 'center', gap: 8, padding: '0 12px', minWidth: 0 }}>
        <button
          type="button"
          className="widget-action"
          style={btn}
          onClick={clock.toggle}
          disabled={!scrubbable}
          title={playing ? 'Pause' : 'Play'}
          aria-label={playing ? 'Pause replay' : 'Play replay'}
        >
          {playing ? <Pause size={11} /> : <Play size={11} />}
        </button>
        <button
          type="button"
          className="widget-action"
          style={btn}
          onClick={() => clock.stepBeat(-1)}
          disabled={!beats.length}
          title="Previous beat"
          aria-label="Step back one beat"
        >
          <SkipBack size={11} />
        </button>
        <button
          type="button"
          className="widget-action"
          style={btn}
          onClick={() => clock.stepBeat(1)}
          disabled={!beats.length}
          title="Next beat"
          aria-label="Step forward one beat"
        >
          <SkipForward size={11} />
        </button>

        <span style={{ display: 'inline-flex', gap: 3, flexShrink: 0 }}>
          {SPEED_PRESETS.map((p) => (
            <Tag key={p.value} active={mode !== 'film' && p.value === speed} tone={mode === 'film' ? 'muted' : undefined} onClick={() => { clock.setMode('manual'); clock.setSpeed(p.value); }}>
              {p.label}
            </Tag>
          ))}
        </span>

        {/* Scrubber. Front fixes tick above the line, beats below: the marks are
            the record, so the reader can see how sparse the evidence is. */}
        <span style={{ position: 'relative', flex: '1 1 0', minWidth: 40, height: SCRUB_H }}>
          <span
            aria-hidden
            style={{ position: 'absolute', left: 0, right: 0, top: 6, height: 2, background: MS.hairline }}
          />
          <span
            aria-hidden
            style={{
              position: 'absolute',
              left: 0,
              top: 6,
              height: 2,
              width: `${Math.max(0, Math.min(1, frac)) * 100}%`,
              background: MS.sub,
            }}
          />
          {scrubbable &&
            keyframes.map((k) => (
              <span
                key={`kf-${k.t}-${k.place_key}`}
                aria-hidden
                title={`FRONT FIX · ${dtgNpt(k.t_npt)} · ${k.place?.name ?? k.place_key}`}
                style={{
                  position: 'absolute',
                  left: `${((k.t - t0) / durationMs) * 100}%`,
                  top: 1,
                  width: 1,
                  height: 4,
                  background: MS.rule,
                }}
              />
            ))}
          {scrubbable &&
            beats.map((b) => (
              <span
                key={`beat-${b.index}`}
                aria-hidden
                title={`${dtgNpt(b.t_npt, b.time_published)} · ${b.headline}`}
                style={{
                  position: 'absolute',
                  left: `${((b.t - t0) / durationMs) * 100}%`,
                  top: 10,
                  width: 1,
                  height: 4,
                  background: b.index <= clock.activeBeatIndex ? MS.sub : MS.hairline,
                }}
              />
            ))}
          <input
            type="range"
            className="replay3d-scrub"
            min={t0}
            max={tEnd}
            step={1000}
            value={t}
            disabled={!scrubbable}
            // The band owns the arrow keys; the slider must not steal them.
            tabIndex={-1}
            onChange={(e) => {
              clock.setPlaying(false);
              clock.setT(Number(e.target.value));
            }}
            aria-label="Replay time"
          />
        </span>

        <span
          style={{
            ...label,
            ...clipped,
            color: MS.text,
            fontVariantNumeric: 'tabular-nums',
            letterSpacing: '0.06em',
          }}
        >
          {clockDtg(clock.nptIso)}
        </span>
      </div>

      {/* ---------------------------------------------------------- line 2 */}
      <div
        style={{
          flex: 1,
          minHeight: 0,
          display: 'flex',
          alignItems: 'stretch',
          gap: 14,
          padding: '3px 12px 6px',
          borderTop: HAIRLINE,
          overflow: 'hidden',
        }}
      >
        {/* WHAT is on screen, and who published it. */}
        <div
          style={{
            flex: '1 1 0',
            minWidth: 0,
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            gap: 3,
          }}
        >
          {activeBeat ? (
            <>
              <div style={lineRow}>
                <Tag tone={KIND_TONE[activeBeat.kind] ?? 'muted'}>{activeBeat.kind}</Tag>
                <span style={{ ...label, color: MS.muted, fontVariantNumeric: 'tabular-nums' }}>
                  {dtgNpt(activeBeat.t_npt, activeBeat.time_published)}
                </span>
                <span
                  style={{
                    ...clipped,
                    fontFamily: MS.mono,
                    fontSize: 11,
                    lineHeight: 1.3,
                    color: MS.text,
                  }}
                  title={activeBeat.detail ?? activeBeat.headline}
                >
                  {activeBeat.headline}
                </span>
              </div>
              <div style={lineRow}>
                <span style={{ ...label, color: MS.muted }}>
                  BEAT {fmt(visibleBeatCount)}/{fmt(beats.length)}
                </span>
                <Sep />
                <span style={{ ...label, ...clipped, color: MS.sub }}>{activeBeat.source}</span>
                {beatGrade && <Grade code={beatGrade} />}
                <Status tone={confTone(activeBeat.confidence)}>{confWord(activeBeat.confidence)}</Status>
                {!activeBeat.time_published && (
                  <span style={{ ...label, color: MS.muted }}>TIME NOT PUBLISHED</span>
                )}
                {activeBeat.source_url && (
                  <a
                    href={activeBeat.source_url}
                    target="_blank"
                    rel="noreferrer noopener"
                    style={{
                      ...label,
                      color: MS.info,
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 3,
                      textDecoration: 'none',
                      flexShrink: 0,
                    }}
                  >
                    SOURCE <ExternalLink size={9} />
                  </a>
                )}
              </div>
            </>
          ) : (
            <div style={lineRow}>
              <Status tone="muted">
                {beats.length ? 'NOTHING PUBLISHED YET AT THIS MOMENT' : 'NO BEATS IN THE RECORD'}
              </Status>
            </div>
          )}
        </div>

        {/* WHERE the front is, and what the authority had counted by then. */}
        <div
          style={{
            flex: '0 1 auto',
            minWidth: 0,
            maxWidth: '46%',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            alignItems: 'flex-end',
            gap: 3,
          }}
        >
          <div style={{ ...lineRow, justifyContent: 'flex-end' }}>
            {tollNow ? (
              <>
                <F tone="critical">{fmt(tollNow.deaths)}</F>
                <Status tone="critical">DEAD</Status>
                <Sep />
                <F tone="high">{fmt(tollNow.missing)}</F>
                <Status tone="high">MISSING</Status>
                <span style={{ ...label, color: MS.muted }}>AS OF {dtgNpt(tollNow.t_npt)}</span>
                <Grade code={gradeFor(tollNow.source).code} />
              </>
            ) : (
              <Status tone="muted">NO OFFICIAL TOLL PUBLISHED YET</Status>
            )}
          </div>
          <div style={{ ...lineRow, justifyContent: 'flex-end' }}>
            <span style={{ ...label, color: MS.muted }}>FRONT</span>
            <span style={{ ...label, ...clipped, color: MS.sub }}>
              {frontPlaceName(timeline, frontKm) || '—'}
            </span>
            <Sep />
            <span style={{ ...label, color: MS.text, fontVariantNumeric: 'tabular-nums' }}>
              KM {frontKm.toFixed(1)}
            </span>
            <Sep />
            <Status tone={confTone(front.confidence)}>{confWord(front.confidence)}</Status>
            {front.between && (
              <span style={{ ...label, ...clipped, color: MS.muted }}>
                BETWEEN {front.between[0]} AND {front.between[1]}
              </span>
            )}
            {holding && (
              <span style={{ ...label, color: MS.muted }} title={`Last published fix: ${dtgNpt(lastFix.t_npt)}`}>
                HOLDING AT LAST FIX
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default ReplayHud;
