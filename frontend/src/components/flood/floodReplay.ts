/**
 * The replay clock for the district impact map.
 *
 * One honesty rule drives every derived value here: a record that carries only
 * a date becomes true when its Nepal-time date CLOSES; a record that carries a
 * published clock time becomes true at that time. Nothing is ever placed at an
 * hour the authority did not publish, and nothing is interpolated between two
 * bulletins — the toll and the district fills both step.
 *
 * All day arithmetic uses a fixed +05:45 offset. The browser's own timezone is
 * never consulted: a desk read from Kathmandu, London or a wall screen in
 * Geneva must agree on when 28 August ended.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import apiClient from '../../api/client';

export const NPT_OFFSET_MS = (5 * 60 + 45) * 60 * 1000;
const DAY_MS = 86_400_000;

/** Epoch ms of NPT midnight that opens the given NPT date. */
export const dayStartMs = (isoDate: string): number =>
  Date.parse(`${isoDate}T00:00:00Z`) - NPT_OFFSET_MS;

/** Epoch ms at which the given NPT date is over — the moment a date-only record becomes true. */
export const dayCloseMs = (isoDate: string): number => dayStartMs(isoDate) + DAY_MS;

const WEEKDAYS = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'];
const MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];

const nptParts = (t: number) => {
  const d = new Date(t + NPT_OFFSET_MS);
  return {
    y: d.getUTCFullYear(),
    m: d.getUTCMonth(),
    day: d.getUTCDate(),
    dow: d.getUTCDay(),
    hh: d.getUTCHours(),
    mm: d.getUTCMinutes(),
  };
};

/** "SAT 29 AUG · 14:15 NPT" */
export const formatNptClock = (t: number): string => {
  const p = nptParts(t);
  return `${WEEKDAYS[p.dow]} ${p.day} ${MONTHS[p.m]} · ${String(p.hh).padStart(2, '0')}:${String(p.mm).padStart(2, '0')} NPT`;
};

/** "29 AUG" from a date-only string, without Date's westward shift. */
export const formatDayShort = (isoDate: string): string => {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate);
  if (!m) return isoDate;
  return `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]}`;
};

// ------------------------------------------------------------------ sources

export interface ChronologyBeat {
  occurred_at: string;
  occurred_at_npt: string;
  /** false = the source gave a date only. The hour in occurred_at is then an
   *  internal ordering convenience and must never reach the screen. */
  time_published: boolean;
  kind: string;
  headline: string;
  detail: string;
  source: string;
  source_url: string | null;
}

interface ChronologyResponse {
  event_key: string;
  count: number;
  events: ChronologyBeat[];
}

export function useFloodChronology() {
  return useQuery<ChronologyResponse>({
    queryKey: ['flood', 'chronology'] as const,
    queryFn: async () => (await apiClient.get('/flood/chronology')).data,
    staleTime: 5 * 60 * 1000,
  });
}

export interface TrajectoryPoint {
  as_of: string;
  deaths: number | null;
  missing: number | null;
}

export interface DistrictSnapshot {
  as_of: string;
  authority: string | null;
  district_tolls: Record<string, Record<string, number> | number>;
}

// ------------------------------------------------------------------- model

export interface ActiveBeat extends ChronologyBeat {
  /** The moment this beat became true under the rule above. */
  activeAt: number;
  /** Rendered stamp: a clock only where one was published. */
  stamp: string;
  index: number;
}

export interface ReplaySweep {
  /** Kilometres downstream of Rasuwagadhi. The kilometres are the event
   *  record's own; the arrival time behind them is not published anywhere. */
  km: number;
}

export interface ReplayState {
  available: boolean;
  t: number;
  t0: number;
  t1: number;
  isLive: boolean;
  playing: boolean;
  speed: number;
  setT: (t: number) => void;
  setSpeed: (minutesPerSecond: number) => void;
  toggle: () => void;
  pause: () => void;
  stepBack: () => void;
  stepForward: () => void;
  goLive: () => void;
  clock: string;
  toll: TrajectoryPoint | null;
  snapshotIdx: number;
  snapshot: DistrictSnapshot | null;
  beat: ActiveBeat | null;
  beatCount: number;
  beatTotal: number;
  /** null once the corridor is on screen; a sweep object only during 26 August. */
  sweep: ReplaySweep | null;
  /** True in the window before the trigger beat, when no surge had yet happened. */
  corridorHidden: boolean;
}

interface ReplayInput {
  beats: ChronologyBeat[];
  trajectory: TrajectoryPoint[];
  snapshots: DistrictSnapshot[];
}

// The sweep runs 0 -> 200 km between the published trigger time and 20:00 NPT
// on the same day. Only the endpoints are real: the collapse time is published
// and the 200 km is the corridor's own last waypoint. The rate between them is
// a drawing device, which is why the front carries a permanent label saying so.
const SWEEP_END_HOUR = 20;
export const SWEEP_MAX_KM = 200;

export const SPEEDS = [
  { label: '1H/S', minutesPerSecond: 60 },
  { label: '6H/S', minutesPerSecond: 360 },
  { label: '1D/S', minutesPerSecond: 1440 },
];

const DEFAULT_SPEED = 360;
const SCRUB_STEP_MS = 15 * 60 * 1000;

export function useFloodReplay({ beats, trajectory, snapshots }: ReplayInput): ReplayState {
  const domain = useMemo(() => {
    if (beats.length === 0) return null;
    const dates = beats.map((b) => b.occurred_at_npt.slice(0, 10)).sort();
    const start = dayStartMs(dates[0]);
    const ends = [
      dayCloseMs(dates[dates.length - 1]),
      ...trajectory.map((p) => dayCloseMs(p.as_of)),
      ...snapshots.map((s) => dayCloseMs(s.as_of.slice(0, 10))),
    ];
    const end = Math.max(...ends);
    return end > start ? { t0: start, t1: end } : null;
  }, [beats, trajectory, snapshots]);

  const t0 = domain?.t0 ?? 0;
  const t1 = domain?.t1 ?? 0;

  const [t, setTState] = useState(t1);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(DEFAULT_SPEED);
  const tRef = useRef(t1);
  // Until a reader touches the scrubber the widget must stay pinned to the
  // latest bulletin, including across a refetch that extends the domain.
  const touchedRef = useRef(false);

  useEffect(() => {
    if (touchedRef.current) return;
    tRef.current = t1;
    setTState(t1);
  }, [t1]);

  const setT = useCallback((next: number) => {
    touchedRef.current = true;
    const clamped = Math.min(Math.max(next, t0), t1);
    tRef.current = clamped;
    setTState(clamped);
  }, [t0, t1]);

  const pause = useCallback(() => setPlaying(false), []);

  const toggle = useCallback(() => {
    setPlaying((was) => {
      if (was) return false;
      // Play from the top when the reader is sitting on the live edge: there is
      // nothing left to run forward into.
      if (tRef.current >= t1) {
        touchedRef.current = true;
        tRef.current = t0;
        setTState(t0);
      }
      return true;
    });
  }, [t0, t1]);

  const goLive = useCallback(() => {
    setPlaying(false);
    touchedRef.current = false;
    tRef.current = t1;
    setTState(t1);
  }, [t1]);

  useEffect(() => {
    if (!playing || !domain) return;
    let frame = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;
      const next = tRef.current + dt * speed * 60_000;
      touchedRef.current = true;
      if (next >= t1) {
        tRef.current = t1;
        setTState(t1);
        setPlaying(false);
        return;
      }
      tRef.current = next;
      setTState(next);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, speed, t1, domain]);

  // Beats carry their own activation moment so the rest of the model never has
  // to re-decide whether a time was published.
  const activations = useMemo<ActiveBeat[]>(
    () =>
      beats
        .map((b, index) => {
          const date = b.occurred_at_npt.slice(0, 10);
          const activeAt = b.time_published ? Date.parse(b.occurred_at) : dayCloseMs(date);
          const clock = b.occurred_at_npt.slice(11, 16);
          return {
            ...b,
            index,
            activeAt,
            stamp: b.time_published
              ? `${formatDayShort(date)} ${clock} NPT`
              : `${formatDayShort(date)} · TIME NOT PUBLISHED`,
          };
        })
        .sort((a, b) => a.activeAt - b.activeAt),
    [beats],
  );

  const keyframes = useMemo(() => {
    if (!domain) return [] as number[];
    const marks = new Set<number>([t0, t1]);
    activations.forEach((b) => {
      if (b.time_published && b.activeAt > t0 && b.activeAt < t1) marks.add(b.activeAt);
    });
    for (let d = t0 + DAY_MS; d < t1; d += DAY_MS) marks.add(d);
    return [...marks].sort((a, b) => a - b);
  }, [domain, t0, t1, activations]);

  const stepTo = useCallback(
    (direction: 1 | -1) => {
      setPlaying(false);
      const current = tRef.current;
      const next = direction === 1
        ? keyframes.find((k) => k > current + 1)
        : [...keyframes].reverse().find((k) => k < current - 1);
      if (next != null) setT(next);
    },
    [keyframes, setT],
  );

  const stepForward = useCallback(() => stepTo(1), [stepTo]);
  const stepBack = useCallback(() => stepTo(-1), [stepTo]);

  const isLive = !domain || t >= t1;

  const toll = useMemo(() => {
    // A plain loop, not reduce/forEach: the point must be the LAST bulletin
    // whose day has closed, and nothing between two bulletins is ever blended.
    let found: TrajectoryPoint | null = null;
    for (const p of trajectory) {
      if (dayCloseMs(p.as_of) <= t) found = p;
    }
    return found;
  }, [trajectory, t]);

  const snapshotIdx = useMemo(() => {
    let idx = -1;
    for (let i = 0; i < snapshots.length; i += 1) {
      if (dayCloseMs(snapshots[i].as_of.slice(0, 10)) <= t) idx = i;
    }
    return idx;
  }, [snapshots, t]);

  const beatsSoFar = useMemo(
    () => activations.filter((b) => b.activeAt <= t),
    [activations, t],
  );

  const sweep = useMemo<ReplaySweep | null>(() => {
    const trigger = activations.find((b) => b.kind === 'trigger' && b.time_published);
    if (!trigger || isLive) return null;
    const day = trigger.occurred_at_npt.slice(0, 10);
    const dayOpen = dayStartMs(day);
    if (t < trigger.activeAt || t >= dayOpen + DAY_MS) return null;
    const end = dayOpen + SWEEP_END_HOUR * 3_600_000;
    const span = end - trigger.activeAt;
    const fraction = span > 0 ? (t - trigger.activeAt) / span : 1;
    return { km: Math.min(Math.max(fraction, 0), 1) * SWEEP_MAX_KM };
  }, [activations, t, isLive]);

  const corridorHidden = useMemo(() => {
    if (isLive) return false;
    const trigger = activations.find((b) => b.kind === 'trigger' && b.time_published);
    return trigger ? t < trigger.activeAt : false;
  }, [activations, t, isLive]);

  return {
    available: Boolean(domain),
    t,
    t0,
    t1,
    isLive,
    playing,
    speed,
    setT,
    setSpeed,
    toggle,
    pause,
    stepBack,
    stepForward,
    goLive,
    clock: formatNptClock(t),
    toll,
    snapshotIdx,
    snapshot: snapshotIdx >= 0 ? snapshots[snapshotIdx] : null,
    beat: beatsSoFar.length ? beatsSoFar[beatsSoFar.length - 1] : null,
    beatCount: beatsSoFar.length,
    beatTotal: activations.length,
    sweep,
    corridorHidden,
  };
}

export const SCRUB_STEP = SCRUB_STEP_MS;
