/**
 * ParliamentSessionWidget — Parliamentary Summary
 *
 * Shows the latest analyzed parliamentary session. Falls back to the
 * pre-session placeholder if no session has been published yet.
 */
import { memo, useEffect, useState } from 'react';
import axios from 'axios';
import { Building2, CalendarDays, Clock, FileText, ArrowRight } from 'lucide-react';

import { useAuthStore } from '../../../store/slices/authSlice';
import { Widget } from '../Widget';

interface SessionSummary {
  id: string;
  title_ne: string | null;
  session_date: string | null;
  session_date_bs: string | null;
  meeting_no: number | null;
  speech_count: number;
  session_summary: string | null;
  key_topics: string[] | null;
  bills_discussed: string[] | null;
  agenda_items: {
    topic?: string;
    description?: string;
    outcome?: string;
    intensity?: string;
  }[] | null;
  is_analyzed: boolean;
  chamber: string | null;
}

function chamberLabel(chamber: string | null): string {
  if (chamber === 'hor') return 'House of Representatives';
  if (chamber === 'na') return 'National Assembly';
  return 'Federal Parliament';
}

function outcomeColor(outcome: string | undefined): { bg: string; border: string; color: string } {
  switch (outcome) {
    case 'presented':
      return { bg: 'rgba(45, 114, 210, 0.10)', border: 'rgba(45, 114, 210, 0.22)', color: '#2D72D2' };
    case 'scheduled':
      return { bg: 'rgba(209, 152, 11, 0.12)', border: 'rgba(209, 152, 11, 0.24)', color: 'var(--status-medium)' };
    case 'procedural':
      return { bg: 'rgba(92, 112, 128, 0.12)', border: 'rgba(92, 112, 128, 0.24)', color: 'var(--text-muted)' };
    default:
      return { bg: 'rgba(35, 133, 81, 0.12)', border: 'rgba(35, 133, 81, 0.24)', color: '#238551' };
  }
}

function summaryParagraphs(text: string | null | undefined): string[] {
  return (text || '')
    .split(/\n\s*\n/)
    .map(part => part.trim())
    .filter(Boolean);
}

export const ParliamentSessionWidget = memo(function ParliamentSessionWidget() {
  const token = useAuthStore(s => s.token);
  const [latestSession, setLatestSession] = useState<SessionSummary | null>(null);

  useEffect(() => {
    if (!token) return;
    const api = axios.create({
      baseURL: import.meta.env.VITE_API_URL || '/api/v1',
      headers: { Authorization: `Bearer ${token}` },
    });

    api.get('/verbatim/summary')
      .then(r => {
        const session = r.data?.recent_sessions?.[0];
        if (session?.is_analyzed) setLatestSession(session);
      })
      .catch(() => {});
  }, [token]);

  const isInterim = latestSession?.session_summary?.toLowerCase().includes('pending official verbatim') ?? false;
  const summaryParts = summaryParagraphs(latestSession?.session_summary);

  return (
    <Widget id="parliament-session" icon={<Building2 size={14} />}>
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {latestSession ? (
          <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
              <div style={{ padding: '14px 14px 0' }}>
                <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                  {chamberLabel(latestSession.chamber)}
                </div>
              </div>
              <span style={{
                margin: '14px 14px 0 0',
                padding: '4px 8px',
                borderRadius: 999,
                background: isInterim ? 'rgba(209, 152, 11, 0.12)' : 'rgba(35, 133, 81, 0.12)',
                border: `1px solid ${isInterim ? 'rgba(209, 152, 11, 0.24)' : 'rgba(35, 133, 81, 0.24)'}`,
                color: isInterim ? 'var(--status-medium)' : '#238551',
                fontSize: 9,
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
              }}>
                {isInterim ? 'Interim: waiting for official verbatim' : 'Live'}
              </span>
            </div>

            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', fontSize: 10, color: 'var(--text-muted)', padding: '8px 14px 0' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <CalendarDays size={12} />
                {latestSession.session_date || latestSession.session_date_bs || 'Date pending'}
              </span>
              {latestSession.meeting_no ? (
                <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <FileText size={12} />
                  Meeting {latestSession.meeting_no}
                </span>
              ) : null}
              <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <Clock size={12} />
                {latestSession.speech_count} speeches captured
              </span>
            </div>

            <div style={{
              flex: 1,
              minHeight: 0,
              overflowY: 'auto',
              padding: '10px 14px 14px',
              display: 'flex',
              flexDirection: 'column',
              gap: 10,
            }}>
              <div style={{
                padding: '12px 12px 10px',
                background: 'rgba(255,255,255,0.02)',
                border: '1px solid var(--border-primary)',
                borderRadius: 4,
              }}>
                <div style={{
                  fontSize: 9,
                  fontWeight: 700,
                  color: 'var(--text-muted)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  marginBottom: 8,
                }}>
                  Summary
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
                  {summaryParts.map((part, idx) => (
                    <p
                      key={`summary-${idx}`}
                      style={{
                        margin: 0,
                        fontSize: 10,
                        color: idx === 0 ? 'var(--text-primary)' : 'var(--text-secondary)',
                        lineHeight: idx === 0 ? 1.7 : 1.65,
                      }}
                    >
                      {part}
                    </p>
                  ))}
                </div>
              </div>

              {latestSession.key_topics && latestSession.key_topics.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <div style={{ fontSize: 9, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    Key Points
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {latestSession.key_topics.slice(0, 6).map(topic => (
                      <span
                        key={topic}
                        style={{
                          fontSize: 8,
                          padding: '3px 7px',
                          borderRadius: 999,
                          background: 'rgba(255,255,255,0.04)',
                          border: '1px solid rgba(255,255,255,0.07)',
                          color: 'var(--text-secondary)',
                        }}
                      >
                        {topic}
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}

              {latestSession.agenda_items && latestSession.agenda_items.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <div style={{ fontSize: 9, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    Session Detail
                  </div>
                  {latestSession.agenda_items.slice(0, 5).map((item, idx) => {
                    const colors = outcomeColor(item.outcome);
                    return (
                      <div
                        key={`${item.topic || 'agenda'}-${idx}`}
                        style={{
                          padding: '9px 10px',
                          borderRadius: 4,
                          background: 'var(--bg-surface)',
                          border: '1px solid var(--border-primary)',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                          <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-primary)', lineHeight: 1.4 }}>
                            {item.topic || 'Agenda Item'}
                          </div>
                          {item.outcome ? (
                            <span style={{
                              fontSize: 8,
                              padding: '2px 6px',
                              borderRadius: 999,
                              background: colors.bg,
                              border: `1px solid ${colors.border}`,
                              color: colors.color,
                              fontWeight: 700,
                              textTransform: 'uppercase',
                              whiteSpace: 'nowrap',
                            }}>
                              {item.outcome}
                            </span>
                          ) : null}
                        </div>
                        {item.description ? (
                          <div style={{ marginTop: 5, fontSize: 9, color: 'var(--text-secondary)', lineHeight: 1.55 }}>
                            {item.description}
                          </div>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              ) : null}

              {latestSession.bills_discussed && latestSession.bills_discussed.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <div style={{ fontSize: 9, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    Immediate Follow-Ons
                  </div>
                  {latestSession.bills_discussed.slice(0, 3).map((bill) => (
                    <div
                      key={bill}
                      style={{
                        display: 'flex',
                        alignItems: 'flex-start',
                        gap: 6,
                        fontSize: 9,
                        color: 'var(--text-secondary)',
                        lineHeight: 1.55,
                        padding: '2px 0',
                      }}
                    >
                      <ArrowRight size={11} style={{ flex: '0 0 auto', marginTop: 1, color: 'var(--text-muted)' }} />
                      <span>{bill}</span>
                    </div>
                  ))}
                </div>
              ) : null}
              </div>
          </div>
        ) : (
          <div style={{
            flex: 1, display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center',
            padding: 24, textAlign: 'center', gap: 10,
          }}>
            <div style={{
              width: 36, height: 36, borderRadius: '50%',
              background: 'rgba(209, 152, 11, 0.1)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <Clock size={18} style={{ color: 'var(--status-medium)' }} />
            </div>
            <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>
              Parliament Session Not Started
            </div>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', lineHeight: 1.5, maxWidth: 260 }}>
              The 2082 House of Representatives has been elected but has not convened its first session yet. Session data, attendance, and legislative activity will appear here once parliament begins.
            </div>
            <div style={{
              marginTop: 4, padding: '4px 10px',
              background: 'rgba(209, 152, 11, 0.08)',
              border: '1px solid rgba(209, 152, 11, 0.15)',
              fontSize: 9, color: 'var(--status-medium)',
              fontWeight: 600, textTransform: 'uppercase',
              letterSpacing: '0.05em',
            }}>
              Awaiting First Session
            </div>
          </div>
        )}
      </div>
    </Widget>
  );
});
