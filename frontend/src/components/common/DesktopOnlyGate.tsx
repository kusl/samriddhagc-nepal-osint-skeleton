/**
 * The phone page. The desk is a wall of instruments built for a wide screen —
 * a 3D terrain replay, a 12-column grid, mono tables — and squeezing it into
 * 390 px produced the old "mobile experience" the founder retired. Phones now
 * get this instead: the headline figures the desk is currently publishing,
 * read live from the same official series, and a plain instruction to open
 * the desk on a computer. Anyone who insists can force the desktop layout;
 * the choice is remembered on that device only.
 *
 * Milspec throughout: mono, uppercase labels, hairlines, no cards-in-cards.
 */
import { useEffect, useState, type CSSProperties } from 'react';
import { useQuery } from '@tanstack/react-query';

import apiClient from '../../api/client';
import { FIGURE, HAIRLINE, LABEL, LABEL_XS, MS, PROSE, dtgDay } from '../flood/milspec';

export const FORCE_DESKTOP_KEY = 'nepalosint:force-desktop';

export function readForceDesktop(): boolean {
  try {
    return localStorage.getItem(FORCE_DESKTOP_KEY) === '1';
  } catch {
    return false;
  }
}

interface TollLatest {
  as_of: string;
  authority: string;
  deaths: number | null;
  missing: number | null;
  rescued: number | null;
}

const n = (v: number | null | undefined) => (typeof v === 'number' ? v.toLocaleString('en-IN') : '—');

const stat: CSSProperties = { padding: '10px 0', borderBottom: HAIRLINE };

export function DesktopOnlyGate({ onForceDesktop }: { onForceDesktop: () => void }) {
  const [copied, setCopied] = useState(false);

  // The figures come from the same endpoint the desk's own tiles read. The
  // anonymous bootstrap may not have run yet on a cold visit, so a failure
  // simply leaves the figures out rather than blocking the page.
  const toll = useQuery<TollLatest | null>({
    queryKey: ['flood', 'official', 'gate'],
    queryFn: async () => {
      try {
        const r = await apiClient.get('/flood/official');
        return (r.data?.official?.latest as TollLatest | undefined) ?? null;
      } catch {
        return null;
      }
    },
    staleTime: 5 * 60 * 1000,
    retry: 2,
    retryDelay: 1500,
  });

  useEffect(() => {
    document.title = 'NepalOSINT · open on a desktop';
  }, []);

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.origin);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  const t = toll.data;

  return (
    <div
      style={{
        minHeight: '100dvh',
        background: MS.surface,
        color: MS.text,
        fontFamily: MS.mono,
        display: 'flex',
        flexDirection: 'column',
        padding: '28px 22px 32px',
        boxSizing: 'border-box',
      }}
    >
      <div style={{ ...LABEL_XS, letterSpacing: '0.16em', color: MS.sub }}>NEPALOSINT · OPEN SOURCE INTELLIGENCE DESK</div>
      <div style={{ ...FIGURE, fontSize: 26, marginTop: 14, lineHeight: 1.15 }}>
        This desk is built for a wide screen.
      </div>
      <div style={{ ...PROSE, fontSize: 13, marginTop: 10, color: MS.sub }}>
        The situation map, the 3D flood replay and the intelligence tables need a desktop or laptop browser. Open
        nepalosint.com on a computer, or use your browser&rsquo;s &ldquo;Request Desktop Website&rdquo; option.
      </div>

      <div style={{ marginTop: 26 }}>
        <div style={{ ...LABEL, color: MS.text, fontWeight: 600, paddingBottom: 6, borderBottom: `1px solid ${MS.rule}` }}>
          TRISHULI FLOOD · OFFICIAL FIGURES
        </div>
        {t ? (
          <>
            <div style={stat}>
              <div style={LABEL}>CONFIRMED DEAD</div>
              <div style={{ ...FIGURE, fontSize: 30, color: MS.critical, marginTop: 4 }}>{n(t.deaths)}</div>
            </div>
            <div style={stat}>
              <div style={LABEL}>MISSING</div>
              <div style={{ ...FIGURE, fontSize: 30, color: MS.high, marginTop: 4 }}>{n(t.missing)}</div>
            </div>
            <div style={stat}>
              <div style={LABEL}>RESCUED</div>
              <div style={{ ...FIGURE, fontSize: 30, color: MS.low, marginTop: 4 }}>{n(t.rescued)}</div>
            </div>
            <div style={{ ...LABEL_XS, marginTop: 8 }}>
              {t.authority} · AS OF {dtgDay(t.as_of)}
            </div>
          </>
        ) : (
          <div style={{ ...LABEL_XS, padding: '10px 0' }}>
            {toll.isLoading ? 'READING THE OFFICIAL SERIES…' : 'FIGURES UNAVAILABLE ON THIS CONNECTION'}
          </div>
        )}
      </div>

      <div style={{ flex: 1 }} />

      <button
        type="button"
        onClick={copyLink}
        style={{
          ...LABEL,
          color: MS.text,
          background: 'transparent',
          border: `1px solid ${MS.rule}`,
          borderRadius: 2,
          padding: '12px 14px',
          textAlign: 'left',
          cursor: 'pointer',
          marginTop: 18,
        }}
      >
        {copied ? 'LINK COPIED' : 'COPY THE LINK FOR YOUR COMPUTER'}
      </button>
      <button
        type="button"
        onClick={onForceDesktop}
        style={{
          ...LABEL_XS,
          color: MS.muted,
          background: 'transparent',
          border: 'none',
          padding: '14px 0 0',
          textAlign: 'left',
          cursor: 'pointer',
        }}
      >
        OPEN THE DESKTOP DESK ON THIS PHONE ANYWAY →
      </button>
    </div>
  );
}

export default DesktopOnlyGate;
