/**
 * VERIFICATION DESK — /review. Owner-only through a shared review key sent as
 * X-Review-Key (the public deployment has no login). Left: the queue of
 * auto-extracted facts. Right: the selected fact — the sentence verbatim, the
 * machine's reading, the place on a mini map (drag the pin to correct it), the
 * seed sites nearby, the story link — and the decision: CONFIRM, or REJECT
 * with a reason. Every decision is stamped and kept with the original reading.
 *
 * Milspec throughout. Keyboard: V confirm, R reject, J/K move.
 */
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

import apiClient from '../api/client';
import { Body, CELL, F, FIGURE, Grade, HAIRLINE, LABEL, LABEL_XS, MS, Note, PROSE, Section, Stat, StatRow, Tag, dtgDay, fmt, gradeFor, type Tone } from '../components/flood/milspec';

const KEY_STORAGE = 'nepalosint:review-key';

interface Seed { key: string; name: string; kind: string; lat: number; lng: number; km: number }
interface Fact {
  id: string; fact_type: string; subject: string | null; subject_code: string | null;
  place_text: string | null; district: string | null; lat: number | null; lng: number | null; place_confidence: string | null;
  figure: number | null; unit: string | null; quote: string; language: string | null; outlet: string | null; url: string | null;
  published_at: string | null; extractor: string; confidence: number; status: string;
  reviewed_at: string | null; reviewer: string | null; review_note: string | null; review_reason: string | null;
  story_title?: string | null; nearby_seeds?: Seed[]; created_at?: string | null;
}
interface Queue { count: number; items: Fact[]; counts: Record<string, number>; reject_reasons: Record<string, string> }

const TYPES = ['burial', 'recovery', 'forensic', 'mortuary', 'transfer', 'team', 'aid', 'money', 'tunnel', 'road', 'toll'];
const TYPE_TONE: Record<string, Tone> = { burial: 'critical', recovery: 'info', forensic: 'high', mortuary: 'high', transfer: 'info', team: 'info', aid: 'low', money: 'low', tunnel: 'high', road: 'high', toll: 'muted' };

const readKey = () => { try { return localStorage.getItem(KEY_STORAGE) ?? ''; } catch { return ''; } };

const input: CSSProperties = { ...CELL, background: MS.surface, color: MS.text, border: `1px solid ${MS.rule}`, borderRadius: 2, padding: '4px 6px', outline: 'none' };
const btn = (tone: string, active = true): CSSProperties => ({ ...LABEL, color: active ? tone : MS.muted, background: 'transparent', border: `1px solid ${active ? tone : MS.hairline}`, borderRadius: 2, padding: '8px 12px', cursor: active ? 'pointer' : 'default', fontWeight: 700 });

function MiniMap({ lat, lng, seeds, onMove }: { lat: number | null; lng: number | null; seeds: Seed[]; onMove: (lat: number, lng: number) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const pinRef = useRef<L.Marker | null>(null);
  const seedsRef = useRef<L.LayerGroup | null>(null);
  useEffect(() => {
    if (!ref.current || mapRef.current) return;
    const map = L.map(ref.current, { zoomControl: true, attributionControl: true }).setView([27.9, 85.0], 7);
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', { attribution: 'Esri, HERE, Garmin, © OpenStreetMap contributors', maxZoom: 16 }).addTo(map);
    seedsRef.current = L.layerGroup().addTo(map);
    mapRef.current = map;
    return () => { pinRef.current = null; seedsRef.current = null; map.remove(); mapRef.current = null; };
  }, []);
  useEffect(() => {
    const map = mapRef.current; if (!map || !seedsRef.current) return;
    seedsRef.current.clearLayers();
    seeds.forEach((s) => {
      L.circleMarker([s.lat, s.lng], { radius: 4, color: '#f97316', weight: 1, fillColor: '#f97316', fillOpacity: 0.8 })
        .bindTooltip(`${s.name} · ${s.km} km`, { direction: 'top', className: 'review-tip' }).addTo(seedsRef.current!);
    });
    if (pinRef.current) { pinRef.current.remove(); pinRef.current = null; }
    if (lat != null && lng != null) {
      const pin = L.marker([lat, lng], { draggable: true, icon: L.divIcon({ className: '', html: '<div style="width:12px;height:12px;border:2px solid #ef4444;background:rgba(239,68,68,.35)"></div>', iconSize: [12, 12], iconAnchor: [6, 6] }) }).addTo(map);
      pin.on('dragend', () => { const p = pin.getLatLng(); onMove(p.lat, p.lng); });
      pinRef.current = pin;
      map.setView([lat, lng], 10);
    } else {
      map.setView([27.9, 85.0], 7);
    }
  }, [lat, lng, seeds, onMove]);
  return <div ref={ref} style={{ height: 260, border: HAIRLINE, background: '#0b0d10' }} />;
}

export default function ReviewDesk() {
  const [key, setKey] = useState<string>(() => readKey());
  const [draft, setDraft] = useState('');
  const [status, setStatus] = useState<'auto' | 'verified' | 'rejected'>('auto');
  const [sel, setSel] = useState<string | null>(null);
  const [edit, setEdit] = useState<{ fact_type: string; figure: string; unit: string; place_text: string; lat: number | null; lng: number | null; note: string; reason: string }>({ fact_type: '', figure: '', unit: '', place_text: '', lat: null, lng: null, note: '', reason: 'wrong_place' });
  const qc = useQueryClient();
  const headers = useMemo(() => ({ 'X-Review-Key': key }), [key]);

  useEffect(() => { document.title = 'NepalOSINT · verification desk'; }, []);

  const q = useQuery<Queue>({
    queryKey: ['review', 'queue', status, key],
    queryFn: async () => (await apiClient.get(`/flood/review/queue?status=${status}&limit=80`, { headers })).data as Queue,
    enabled: Boolean(key),
    retry: false,
    refetchInterval: 60 * 1000,
  });

  const items = q.data?.items ?? [];
  const current = items.find((f) => f.id === sel) ?? items[0] ?? null;
  useEffect(() => {
    if (!current) return;
    setEdit({ fact_type: current.fact_type, figure: current.figure != null ? String(current.figure) : '', unit: current.unit ?? '', place_text: current.place_text ?? '', lat: current.lat, lng: current.lng, note: '', reason: 'wrong_place' });
  }, [current?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const decide = useMutation({
    mutationFn: async (body: { id: string; action: 'verify' | 'reject' | 'reopen'; note?: string; reason?: string; corrections?: Record<string, unknown> }) =>
      (await apiClient.post(`/flood/review/${body.id}`, body, { headers })).data,
    onSuccess: (_d, vars) => {
      const idx = items.findIndex((f) => f.id === vars.id);
      const next = items[idx + 1] ?? items[idx - 1] ?? null;
      setSel(next?.id ?? null);
      qc.invalidateQueries({ queryKey: ['review'] });
      qc.invalidateQueries({ queryKey: ['flood'] });
    },
  });

  const confirm = useCallback(() => {
    if (!current) return;
    const corrections: Record<string, unknown> = {};
    if (edit.fact_type && edit.fact_type !== current.fact_type) corrections.fact_type = edit.fact_type;
    if (edit.figure !== '' && Number(edit.figure) !== current.figure) corrections.figure = Number(edit.figure);
    if (edit.unit && edit.unit !== current.unit) corrections.unit = edit.unit;
    if (edit.place_text && edit.place_text !== current.place_text) corrections.place_text = edit.place_text;
    if (edit.lat != null && edit.lng != null && (edit.lat !== current.lat || edit.lng !== current.lng)) { corrections.lat = edit.lat; corrections.lng = edit.lng; }
    decide.mutate({ id: current.id, action: 'verify', note: edit.note || undefined, corrections });
  }, [current, edit, decide]);
  const reject = useCallback(() => {
    if (!current) return;
    decide.mutate({ id: current.id, action: 'reject', reason: edit.reason, note: edit.note || undefined });
  }, [current, edit, decide]);

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === 'INPUT' || (e.target as HTMLElement)?.tagName === 'TEXTAREA' || (e.target as HTMLElement)?.tagName === 'SELECT') return;
      if (e.key === 'v' || e.key === 'V') confirm();
      if (e.key === 'r' || e.key === 'R') reject();
      if (e.key === 'j' || e.key === 'k') {
        const idx = items.findIndex((f) => f.id === current?.id);
        const n = items[e.key === 'j' ? idx + 1 : idx - 1];
        if (n) setSel(n.id);
      }
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [confirm, reject, items, current]);

  const onMove = useCallback((lat: number, lng: number) => setEdit((e) => ({ ...e, lat, lng })), []);

  if (!key) {
    return (
      <div style={{ minHeight: '100dvh', background: MS.surface, color: MS.text, fontFamily: MS.mono, padding: '40px 32px', maxWidth: 560 }}>
        <div style={{ ...LABEL_XS, letterSpacing: '0.16em' }}>NEPALOSINT · VERIFICATION DESK</div>
        <div style={{ ...FIGURE, fontSize: 22, marginTop: 12 }}>Owner access</div>
        <div style={{ ...PROSE, color: MS.sub, marginTop: 8 }}>Paste the review key from the server's environment. It is kept in this browser only.</div>
        <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="REVIEW_KEY" style={{ ...input, width: '100%', marginTop: 16 }} />
        <button type="button" onClick={() => { try { localStorage.setItem(KEY_STORAGE, draft.trim()); } catch { /* private mode */ } setKey(draft.trim()); }} style={{ ...btn(MS.info), marginTop: 12 }}>OPEN THE DESK</button>
      </div>
    );
  }

  const counts = q.data?.counts ?? {};
  const reasons = q.data?.reject_reasons ?? {};
  const err = q.error as { response?: { status?: number } } | null;

  return (
    <div style={{ minHeight: '100dvh', background: MS.surface, color: MS.text, fontFamily: MS.mono, display: 'flex', flexDirection: 'column' }}>
      <style>{`.review-tip{font-family:var(--font-mono);font-size:10px;background:#0b0d10;color:#e5e7eb;border:1px solid #3f3f46}`}</style>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, padding: '10px 16px', borderBottom: `1px solid ${MS.rule}` }}>
        <span style={{ ...LABEL, color: MS.text, fontWeight: 700 }}>VERIFICATION DESK</span>
        <span style={LABEL_XS}>AUTO-EXTRACTED FACTS · CONFIRM OR REJECT · EVERY DECISION IS KEPT WITH THE MACHINE'S ORIGINAL READING</span>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
          {(['auto', 'verified', 'rejected'] as const).map((s) => (
            <Tag key={s} active={status === s} onClick={() => { setStatus(s); setSel(null); }}>{s.toUpperCase()} {fmt(counts[s] ?? 0)}</Tag>
          ))}
          <Tag onClick={() => { try { localStorage.removeItem(KEY_STORAGE); } catch { /* */ } setKey(''); }}>LOCK</Tag>
        </span>
      </div>
      {err?.response?.status === 403 && (
        <div style={{ padding: '12px 16px', color: MS.critical, ...LABEL }}>REVIEW KEY REFUSED BY THE SERVER · LOCK AND PASTE IT AGAIN</div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: '38% minmax(0, 1fr)', gap: 0, flex: 1, minHeight: 0 }}>
        <div style={{ borderRight: `1px solid ${MS.rule}`, overflowY: 'auto', minHeight: 0 }}>
          {items.length === 0 && !q.isLoading && <div style={{ ...LABEL_XS, padding: 16 }}>QUEUE EMPTY</div>}
          {items.map((f) => (
            <div key={f.id} onClick={() => setSel(f.id)} style={{ padding: '8px 14px', borderBottom: HAIRLINE, cursor: 'pointer', background: current?.id === f.id ? MS.hairline : 'transparent' }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
                <Tag tone={TYPE_TONE[f.fact_type] ?? 'muted'}>{f.fact_type.toUpperCase()}</Tag>
                <F tone={f.figure != null ? 'text' : 'muted'}>{f.figure != null ? `${fmt(f.figure)} ${f.unit ?? ''}` : 'no figure'}</F>
                <span style={{ ...LABEL_XS, flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.place_text ?? f.subject_code ?? '—'}{f.district ? ` · ${f.district}` : ''}{f.lat == null && f.place_text ? ' · NOT GEOCODED' : ''}</span>
                <span style={{ ...LABEL_XS, whiteSpace: 'nowrap' }}>{dtgDay(f.published_at)}</span>
              </div>
              <div style={{ ...CELL, color: MS.sub, marginTop: 3, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{f.quote}</div>
              <div style={{ ...LABEL_XS, marginTop: 2, display: 'flex', gap: 8 }}>
                <span>{f.outlet ?? 'OUTLET NOT STATED'}</span>
                <Grade code={gradeFor(f.outlet).code} />
                <span>{f.extractor.toUpperCase()} · {Math.round(f.confidence * 100)}%</span>
              </div>
            </div>
          ))}
        </div>
        <div style={{ overflowY: 'auto', minHeight: 0, padding: '12px 18px' }}>
          {!current ? (
            <div style={LABEL_XS}>SELECT A FACT</div>
          ) : (
            <Body>
              <StatRow columns={4}>
                <Stat label="TYPE" value={<Tag tone={TYPE_TONE[current.fact_type] ?? 'muted'}>{current.fact_type.toUpperCase()}</Tag>} size={14} />
                <Stat label="FIGURE" value={current.figure != null ? fmt(current.figure) : '—'} sub={current.unit ?? undefined} size={20} />
                <Stat label="PLACE" value={current.place_text ?? '—'} sub={current.lat != null ? `${current.lat.toFixed(4)}, ${current.lng!.toFixed(4)} · ${current.place_confidence ?? ''}` : 'not geocoded'} size={14} />
                <Stat label="EXTRACTOR" value={current.extractor.toUpperCase()} sub={`${Math.round(current.confidence * 100)}% · ${current.language ?? ''}`} size={14} />
              </StatRow>

              <Section n={1} title="THE SENTENCE" meta="VERBATIM · THE ONLY THING THE MACHINE READ" />
              <div style={{ ...PROSE, fontSize: 13, color: MS.text, lineHeight: 1.6 }}>{current.quote}</div>
              <div style={{ ...LABEL_XS, marginTop: 6, display: 'flex', gap: 10, alignItems: 'baseline' }}>
                <span>{current.outlet ?? 'OUTLET NOT STATED'}</span>
                <Grade code={gradeFor(current.outlet).code} />
                <span>{dtgDay(current.published_at)}</span>
                {current.url && <a href={current.url} target="_blank" rel="noreferrer noopener" style={{ color: MS.info, textDecoration: 'none' }}>OPEN THE STORY ↗</a>}
                {current.story_title && <span style={{ color: MS.sub, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{current.story_title}</span>}
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: 24 }}>
                <div>
                  <Section n={2} title="THE READING" meta="CORRECT ANYTHING WRONG, THEN CONFIRM" />
                  <div style={{ display: 'grid', gridTemplateColumns: '90px 1fr', gap: '6px 10px', alignItems: 'center' }}>
                    <span style={LABEL_XS}>TYPE</span>
                    <select value={edit.fact_type} onChange={(e) => setEdit({ ...edit, fact_type: e.target.value })} style={input}>
                      {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                    </select>
                    <span style={LABEL_XS}>FIGURE</span>
                    <input value={edit.figure} onChange={(e) => setEdit({ ...edit, figure: e.target.value })} style={input} />
                    <span style={LABEL_XS}>UNIT</span>
                    <input value={edit.unit} onChange={(e) => setEdit({ ...edit, unit: e.target.value })} style={input} />
                    <span style={LABEL_XS}>PLACE</span>
                    <input value={edit.place_text} onChange={(e) => setEdit({ ...edit, place_text: e.target.value })} style={input} />
                    <span style={LABEL_XS}>PIN</span>
                    <span style={{ ...CELL, color: MS.sub }}>{edit.lat != null ? `${edit.lat.toFixed(4)}, ${edit.lng!.toFixed(4)}` : 'drag the pin on the map, or leave unplaced'}</span>
                    <span style={LABEL_XS}>NOTE</span>
                    <input value={edit.note} onChange={(e) => setEdit({ ...edit, note: e.target.value })} placeholder="optional, kept in the trail" style={input} />
                  </div>
                  {(current.nearby_seeds ?? []).length > 0 && (
                    <>
                      <Section n={3} title="SEED SITES NEARBY" meta="A MATCH WITHIN 3 KM FOLDS INTO THE SEED" />
                      {current.nearby_seeds!.map((s) => (
                        <div key={s.key} style={{ display: 'flex', gap: 8, alignItems: 'baseline', padding: '3px 0', borderBottom: HAIRLINE }}>
                          <Tag tone={s.km <= 3 ? 'high' : 'muted'}>{s.kind.toUpperCase()}</Tag>
                          <span style={{ ...CELL, color: MS.text, flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.name}</span>
                          <F tone={s.km <= 3 ? 'high' : 'muted'}>{s.km} km</F>
                          <Tag onClick={() => setEdit((e) => ({ ...e, lat: s.lat, lng: s.lng, place_text: e.place_text || s.name }))}>SNAP</Tag>
                        </div>
                      ))}
                    </>
                  )}
                </div>
                <div>
                  <Section n={4} title="THE PLACE" meta="RED = THIS FACT · ORANGE = SEED SITES · DRAG TO CORRECT" />
                  <MiniMap lat={edit.lat} lng={edit.lng} seeds={current.nearby_seeds ?? []} onMove={onMove} />
                </div>
              </div>

              <Section n={5} title="DECISION" meta="V = CONFIRM · R = REJECT · J/K = NEXT/PREVIOUS" />
              <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                <button type="button" onClick={confirm} disabled={decide.isPending || status === 'verified'} style={btn(MS.low, status !== 'verified')}>CONFIRM AS VERIFIED</button>
                <select value={edit.reason} onChange={(e) => setEdit({ ...edit, reason: e.target.value })} style={input}>
                  {Object.entries(reasons).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
                <button type="button" onClick={reject} disabled={decide.isPending || status === 'rejected'} style={btn(MS.critical, status !== 'rejected')}>REJECT</button>
                {status !== 'auto' && (
                  <button type="button" onClick={() => decide.mutate({ id: current.id, action: 'reopen' })} disabled={decide.isPending} style={btn(MS.sub)}>REOPEN</button>
                )}
                {decide.isError && <span style={{ ...LABEL_XS, color: MS.critical }}>DECISION FAILED · CHECK THE KEY</span>}
              </div>
              {current.reviewed_at && (
                <Note>
                  Reviewed {dtgDay(current.reviewed_at)} by {current.reviewer}{current.review_reason ? ` · ${reasons[current.review_reason] ?? current.review_reason}` : ''}{current.review_note ? ` · "${current.review_note}"` : ''}.
                </Note>
              )}
              <Note>
                Confirming makes this a verified row on the public boards, marked "verified by the desk". Rejecting stops the extractor from storing the same reading again from any outlet's reprint.
              </Note>
            </Body>
          )}
        </div>
      </div>
    </div>
  );
}
