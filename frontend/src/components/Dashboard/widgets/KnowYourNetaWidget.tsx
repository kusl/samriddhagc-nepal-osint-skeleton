/**
 * KnowYourNetaWidget — Know Your Parliamentarian
 *
 * Shows 2082 election winners from real election data.
 * Click → Performance Card that fetches parliament API data
 * (attendance, bills, committees, questions, performance score).
 * If no parliament session yet, shows graceful "awaiting" state.
 */
import { memo, useEffect, useState, useMemo, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { Widget } from '../Widget';
import {
  Landmark, Search, X, User, MapPin,
  BarChart3, FileText, Users, MessageSquare, Briefcase,
  Award, ChevronRight, AlertCircle,
} from 'lucide-react';
import { useElectionStore } from '../../../stores/electionStore';
import { loadElectionData } from '../../elections/electionDataLoader';
import { getPartyColor, getPartyShortLabel } from '../../../lib/partyColors';
import apiClient from '../../../api/client';

interface CandidateInfo {
  id: string;
  constituencyId: string;
  name: string;
  nameNe?: string;
  nameRoman?: string;
  party: string;
  constituency: string;
  district: string;
  province: string;
  votes: number;
  votePct: number;
  isWinner: boolean;
  photoUrl?: string;
  age?: number;
  gender?: string;
  biography?: string;
  biographySource?: string;
  electionType?: 'fptp' | 'pr';
}

type ElectionTypeFilter = 'all' | 'fptp' | 'pr';

function canonicalPartyKey(party: string): string {
  const shortLabel = getPartyShortLabel(party)?.trim();
  return shortLabel || party.trim();
}

// Parliament performance data from API
interface ParliamentRecord {
  performance_score?: number;
  performance_percentile?: number;
  performance_tier?: string;
  legislative_score?: number;
  participation_score?: number;
  accountability_score?: number;
  committee_score?: number;
  bills_introduced: number;
  bills_passed: number;
  session_attendance_pct?: number;
  questions_asked: number;
  speeches_count: number;
  committee_memberships: number;
  committee_leadership_roles: number;
  is_minister?: boolean;
  ministry_portfolio?: string;
  is_former_pm?: boolean;
  notable_roles?: string;
}

interface PublicParliamentSummaryResponse extends ParliamentRecord {
  id: string;
  name_en?: string;
  name_ne?: string;
  party?: string;
  chamber?: string;
}

// Performance card for an MP
function PerformanceCard({ mp, onClose }: { mp: CandidateInfo; onClose: () => void }) {
  const [record, setRecord] = useState<ParliamentRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [noData, setNoData] = useState(false);

  useEffect(() => {
    let isCancelled = false;

    const fetchRecord = async () => {
      setLoading(true);
      setNoData(false);
      setRecord(null);
      try {
        if (!mp.id.startsWith('pr-')) {
          const res = await apiClient.get<PublicParliamentSummaryResponse>(
            `/election-results/house-representatives/${mp.id}/parliamentary-summary`
          );
          if (!isCancelled) {
            setRecord(res.data);
            setNoData(false);
          }
          return;
        }
      } catch {
        // Public summary unavailable; fall through to no-data state.
      }
      if (!isCancelled) {
        setNoData(true);
      }
    };
    fetchRecord();

    return () => {
      isCancelled = true;
    };
  }, [mp.id, mp.name]);

  useEffect(() => {
    if (record || noData) {
      setLoading(false);
    }
  }, [record, noData]);

  const color = getPartyColor(mp.party);
  const tierLabel = (tier?: string) => {
    switch (tier) {
      case 'top10': return { text: 'Top 10%', color: '#22C55E' };
      case 'above_avg': return { text: 'Above Avg', color: '#3B82F6' };
      case 'average': return { text: 'Average', color: '#EAB308' };
      case 'below_avg': return { text: 'Below Avg', color: '#F97316' };
      case 'bottom10': return { text: 'Bottom 10%', color: '#EF4444' };
      default: return { text: 'Unranked', color: 'var(--text-muted)' };
    }
  };

  const modalHost = typeof document === 'undefined'
    ? null
    : (document.fullscreenElement instanceof HTMLElement ? document.fullscreenElement : document.body);

  if (!modalHost) {
    return null;
  }

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="bg-[#13161a] border border-white/10 rounded-xl shadow-2xl w-full max-w-[860px] max-h-[calc(100vh-64px)] flex flex-col overflow-hidden"
        onClick={e => e.stopPropagation()}
        style={{
          boxShadow: '0 32px 80px rgba(0, 0, 0, 0.55)',
        }}
      >
        {/* Header */}
        <div className="p-5 relative flex-shrink-0" style={{ background: `linear-gradient(135deg, ${color}22 0%, rgba(15, 18, 24, 0.92) 68%)` }}>
          <button onClick={onClose} className="absolute top-3 right-3 p-1.5 rounded-full bg-white/10 hover:bg-white/20 transition-colors">
            <X size={14} className="text-white" />
          </button>
          <div className="flex items-start gap-3">
            <div className="w-20 h-20 rounded-xl bg-slate-800 overflow-hidden flex-shrink-0 border-2 border-white/10">
              {mp.photoUrl ? (
                <img src={mp.photoUrl} alt="" className="w-full h-full object-cover"
                  onError={e => { (e.target as HTMLImageElement).style.display = 'none'; }} />
              ) : (
                <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-slate-700 to-slate-800">
                  <User size={30} className="text-slate-500" />
                </div>
              )}
            </div>
            <div className="flex-1 min-w-0 pt-0.5">
              <h3 className="text-[20px] font-bold text-white leading-tight">{mp.name}</h3>
              {mp.nameNe && mp.nameNe !== mp.name && (
                <div className="text-[12px] text-slate-400 mt-1">{mp.nameNe}</div>
              )}
              <div className="flex items-center gap-2 mt-2 flex-wrap">
                <span style={{
                  fontSize: 10, fontWeight: 700, padding: '3px 8px',
                  background: color, color: '#fff',
                  borderRadius: 999,
                  letterSpacing: '0.08em',
                }}>
                  {getPartyShortLabel(mp.party)}
                </span>
                <span className="text-[12px] text-slate-300">{mp.constituency}</span>
              </div>
              <div className="text-[11px] text-slate-500 mt-1">
                {mp.district}, {mp.province}
              </div>
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <div className="w-5 h-5 border-2 border-blue-500/30 border-t-blue-500 rounded-full animate-spin" />
            </div>
          ) : noData ? (
            // Public parliament linkage missing
            <div className="space-y-3">
              <div className="flex items-center gap-3 p-4 rounded-lg bg-amber-500/5 border border-amber-500/15">
                <AlertCircle size={20} className="text-amber-400 flex-shrink-0" />
                <div>
                  <div className="text-[12px] font-semibold text-amber-400">Parliamentary Record Unavailable</div>
                  <div className="text-[10px] text-slate-500 mt-1 leading-relaxed">
                    This public candidate profile does not yet have a linked parliamentary summary. Election, constituency, and biography data are available below, but attendance, bills, and committee metrics are not currently attached to this profile.
                  </div>
                </div>
              </div>

              {/* Bio if available */}
              {mp.biography && (
                <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wide mb-2 font-medium">About</div>
                  <div className="text-[11px] text-slate-300 leading-relaxed">
                    {mp.biography}
                  </div>
                </div>
              )}

              {/* Constituency */}
              <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
                <div className="text-[10px] text-slate-500 uppercase tracking-wide mb-2 font-medium">Constituency</div>
                <div className="flex items-center gap-2">
                  <MapPin size={12} className="text-slate-500" />
                  <span className="text-[12px] text-slate-300">{mp.constituency}</span>
                </div>
                <div className="text-[10px] text-slate-600 mt-1 ml-5">{mp.district}, {mp.province}</div>
              </div>
            </div>
          ) : record ? (
            // Full performance card
            <div className="space-y-3">
              {/* Overall Score */}
              {record.performance_score != null && record.performance_score > 0 && (
                <div className="p-3 rounded-lg bg-white/[0.03] border border-white/8">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[10px] text-slate-500 uppercase tracking-wide font-medium">Performance Score</span>
                    <span style={{ fontSize: 9, fontWeight: 700, padding: '2px 8px', background: `${tierLabel(record.performance_tier).color}20`, color: tierLabel(record.performance_tier).color }}>
                      {tierLabel(record.performance_tier).text}
                    </span>
                  </div>
                  <div className="flex items-end gap-3">
                    <span className="text-3xl font-bold text-white font-mono">{record.performance_score.toFixed(0)}</span>
                    <span className="text-[10px] text-slate-500 pb-1">/100</span>
                    {record.performance_percentile != null && (
                      <span className="text-[10px] text-slate-400 pb-1 ml-auto">
                        Top {100 - record.performance_percentile}%
                      </span>
                    )}
                  </div>
                  {/* Score bar */}
                  <div className="mt-2 h-1.5 bg-white/5 rounded-full overflow-hidden">
                    <div className="h-full rounded-full transition-all" style={{
                      width: `${record.performance_score}%`,
                      background: `linear-gradient(90deg, ${color}, ${tierLabel(record.performance_tier).color})`,
                    }} />
                  </div>
                </div>
              )}

              {/* Category breakdown */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {[
                  { label: 'Legislative', score: record.legislative_score, icon: FileText, detail: `${record.bills_introduced} bills introduced, ${record.bills_passed} passed` },
                  { label: 'Participation', score: record.participation_score, icon: BarChart3, detail: record.session_attendance_pct != null ? `${record.session_attendance_pct.toFixed(0)}% attendance` : 'No data' },
                  { label: 'Accountability', score: record.accountability_score, icon: MessageSquare, detail: `${record.questions_asked} questions asked` },
                  { label: 'Committee', score: record.committee_score, icon: Users, detail: `${record.committee_memberships} memberships${record.committee_leadership_roles > 0 ? `, ${record.committee_leadership_roles} leadership` : ''}` },
                ].map(cat => (
                  <div key={cat.label} className="p-4 rounded-xl bg-white/[0.02] border border-white/5">
                    <div className="flex items-center gap-2 mb-2">
                      <cat.icon size={12} className="text-slate-500" />
                      <span className="text-[10px] text-slate-500 uppercase tracking-wide">{cat.label}</span>
                    </div>
                    <div className="text-[20px] font-bold text-white font-mono">
                      {cat.score != null ? cat.score.toFixed(0) : '--'}
                    </div>
                    <div className="text-[10px] text-slate-500 mt-1.5 leading-relaxed">{cat.detail}</div>
                  </div>
                ))}
              </div>

              {/* Speeches */}
              {record.speeches_count > 0 && (
                <div className="p-2.5 rounded-lg bg-white/[0.02] border border-white/5 flex items-center gap-3">
                  <Briefcase size={12} className="text-slate-500" />
                  <span className="text-[10px] text-slate-400">{record.speeches_count} speeches in parliament</span>
                </div>
              )}

              {/* Minister badge */}
              {record.is_minister && record.ministry_portfolio && (
                <div className="p-2.5 rounded-lg bg-blue-500/8 border border-blue-500/15 flex items-center gap-3">
                  <Briefcase size={12} className="text-blue-400" />
                  <span className="text-[11px] text-blue-400 font-medium">{record.ministry_portfolio}</span>
                </div>
              )}

              {/* Notable roles */}
              {record.notable_roles && (
                <div className="p-2.5 rounded-lg bg-white/[0.02] border border-white/5">
                  <div className="text-[9px] text-slate-500 uppercase tracking-wide mb-1">Notable Roles</div>
                  <div className="text-[11px] text-slate-300">{record.notable_roles}</div>
                </div>
              )}

              {/* Bio */}
              {mp.biography && (
                <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
                  <div className="text-[10px] text-slate-500 uppercase tracking-wide mb-2 font-medium">About</div>
                  <div className="text-[11px] text-slate-300 leading-relaxed">
                    {mp.biography}
                  </div>
                </div>
              )}
            </div>
          ) : null}
        </div>
      </div>
    </div>
    ,
    modalHost,
  );
}

export const KnowYourNetaWidget = memo(function KnowYourNetaWidget() {
  const { electionYear } = useElectionStore();
  const [candidates, setCandidates] = useState<CandidateInfo[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedParty, setSelectedParty] = useState<string | null>(null);
  const [selectedElectionType, setSelectedElectionType] = useState<ElectionTypeFilter>('all');
  const [selectedMP, setSelectedMP] = useState<CandidateInfo | null>(null);

  // Load winners
  useEffect(() => {
    const loadData = async () => {
      setIsLoading(true);
      try {
        const combinedResponse = await apiClient.get('/election-results/house-representatives').catch(() => null);

        if (combinedResponse?.data?.members?.length) {
          const combinedMembers: CandidateInfo[] = combinedResponse.data.members.map((member: any) => ({
            id: member.id,
            constituencyId: member.constituency_id,
            name: member.name,
            nameNe: member.name_ne,
            nameRoman: member.name_roman,
            party: member.party,
            constituency: member.constituency,
            district: member.district,
            province: member.province,
            votes: member.votes || 0,
            votePct: member.vote_pct || 0,
            isWinner: true,
            photoUrl: member.photo_url || undefined,
            age: member.age || undefined,
            gender: member.gender,
            biography: member.biography,
            biographySource: member.biography_source,
            electionType: member.election_type,
          }));
          setCandidates(combinedMembers);
          return;
        }

        const [data, prResponse] = await Promise.all([
          loadElectionData(electionYear),
          apiClient.get('/election-results/pr-members').catch(() => null),
        ]);

        const winners: CandidateInfo[] = [];
        if (data) {
          for (const c of data.constituencies) {
            const sorted = [...c.candidates].sort((a, b) => b.votes - a.votes);
            for (const candidate of sorted) {
              if (!candidate.is_winner) continue;
              winners.push({
                id: candidate.id || `${c.constituency_id}-${candidate.name_en}`,
                constituencyId: c.constituency_id,
                name: candidate.name_en_roman || candidate.name_en,
                nameNe: candidate.name_ne || candidate.name_en,
                nameRoman: candidate.name_en_roman,
                party: candidate.party,
                constituency: c.name_en,
                district: c.district,
                province: c.province,
                votes: candidate.votes,
                votePct: candidate.vote_pct,
                isWinner: true,
                photoUrl: candidate.photo_url || undefined,
                age: candidate.age || undefined,
                gender: candidate.gender,
                biography: candidate.biography,
                biographySource: candidate.biography_source,
                electionType: 'fptp',
              });
            }
          }
        }

        const prMembers = (prResponse?.data?.members || []).map((member: any) => ({
          id: member.id,
          constituencyId: `pr-${member.party_code || member.party}`,
          name: member.name_roman || member.name_ne,
          nameNe: member.name_ne,
          nameRoman: member.name_roman,
          party: member.party_code || member.party,
          constituency: 'PR - Party List',
          district: member.district || 'Party List',
          province: 'PR',
          votes: 0,
          votePct: 0,
          isWinner: true,
          electionType: 'pr' as const,
        }));
        setCandidates([...winners, ...prMembers].sort((a, b) => a.name.localeCompare(b.name)));
      } catch (err) {
        console.error('Failed to load parliamentarians:', err);
      } finally {
        setIsLoading(false);
      }
    };
    loadData();
  }, [electionYear]);

  // Party counts
  const typeScopedCandidates = useMemo(() => {
    if (selectedElectionType === 'all') return candidates;
    return candidates.filter((candidate) => candidate.electionType === selectedElectionType);
  }, [candidates, selectedElectionType]);

  const parties = useMemo(() => {
    const counts = new Map<string, { count: number; colorParty: string }>();
    for (const candidate of typeScopedCandidates) {
      const key = canonicalPartyKey(candidate.party);
      const existing = counts.get(key);
      if (existing) {
        existing.count += 1;
      } else {
        counts.set(key, { count: 1, colorParty: candidate.party });
      }
    }

    return Array.from(counts.entries())
      .map(([party, value]) => ({
        party,
        count: value.count,
        colorParty: value.colorParty,
      }))
      .sort((a, b) => b.count - a.count || a.party.localeCompare(b.party));
  }, [typeScopedCandidates]);

  // Filter
  const filtered = useMemo(() => {
    let result = candidates;
    if (selectedElectionType !== 'all') {
      result = result.filter((candidate) => candidate.electionType === selectedElectionType);
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(c =>
        c.name.toLowerCase().includes(q) ||
        (c.nameRoman && c.nameRoman.toLowerCase().includes(q)) ||
        c.nameNe?.includes(searchQuery) ||
        c.constituency.toLowerCase().includes(q) ||
        c.district.toLowerCase().includes(q)
      );
    }
    if (selectedParty) {
      result = result.filter((candidate) => canonicalPartyKey(candidate.party) === selectedParty);
    }
    return result;
  }, [candidates, searchQuery, selectedParty, selectedElectionType]);

  const electionTypeCounts = useMemo(() => ({
    all: candidates.length,
    fptp: candidates.filter((candidate) => candidate.electionType === 'fptp').length,
    pr: candidates.filter((candidate) => candidate.electionType === 'pr').length,
  }), [candidates]);

  useEffect(() => {
    if (selectedParty && !parties.some((party) => party.party === selectedParty)) {
      setSelectedParty(null);
    }
  }, [parties, selectedParty]);

  return (
    <Widget id="neta" icon={<Landmark size={14} />} badge={candidates.length}>
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Search & Filter */}
        <div style={{ padding: '8px 10px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 6,
              background: 'var(--bg-elevated)', padding: '4px 8px',
              border: '1px solid var(--border-subtle)',
              minWidth: 220,
              flex: '1 1 220px',
            }}>
              <Search size={11} style={{ color: 'var(--text-disabled)', flexShrink: 0 }} />
              <input
                type="text" value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                placeholder="Search name, constituency, district..."
                style={{
                  flex: 1, background: 'transparent', border: 'none', outline: 'none',
                  fontSize: 11, color: 'var(--text-primary)', fontFamily: 'var(--font-sans)',
                }}
              />
              {searchQuery && (
                <button onClick={() => setSearchQuery('')} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                  <X size={11} style={{ color: 'var(--text-muted)' }} />
                </button>
              )}
            </div>
            <div style={{
              display: 'inline-flex',
              border: '1px solid var(--border-subtle)',
              background: 'var(--bg-elevated)',
              overflow: 'hidden',
            }}>
              {([
                { id: 'all', label: 'All', count: electionTypeCounts.all },
                { id: 'fptp', label: 'FPTP', count: electionTypeCounts.fptp },
                { id: 'pr', label: 'PR', count: electionTypeCounts.pr },
              ] as const).map((option) => {
                const active = selectedElectionType === option.id;
                return (
                  <button
                    key={option.id}
                    onClick={() => setSelectedElectionType(option.id)}
                    style={{
                      padding: '4px 8px',
                      fontSize: 9,
                      fontWeight: 700,
                      background: active ? 'rgba(59,130,246,0.18)' : 'transparent',
                      color: active ? 'var(--text-primary)' : 'var(--text-muted)',
                      border: 'none',
                      borderRight: option.id !== 'pr' ? '1px solid var(--border-subtle)' : 'none',
                      cursor: 'pointer',
                      fontFamily: 'var(--font-sans)',
                      letterSpacing: '0.04em',
                    }}
                  >
                    {option.label} ({option.count})
                  </button>
                );
              })}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
            <button
              onClick={() => setSelectedParty(null)}
              style={{
                padding: '2px 7px', fontSize: 9, fontWeight: 600,
                background: !selectedParty ? 'var(--accent-primary)' : 'var(--bg-elevated)',
                color: !selectedParty ? '#fff' : 'var(--text-muted)',
                border: `1px solid ${!selectedParty ? 'var(--accent-primary)' : 'var(--border-subtle)'}`,
                cursor: 'pointer', fontFamily: 'var(--font-sans)',
              }}
            >
              All ({typeScopedCandidates.length})
            </button>
            {parties.map(({ party, count, colorParty }) => {
              const active = selectedParty === party;
              const pColor = getPartyColor(colorParty);
              return (
                <button key={party}
                  onClick={() => setSelectedParty(active ? null : party)}
                  style={{
                    padding: '2px 7px', fontSize: 9, fontWeight: 600,
                    background: active ? pColor : 'var(--bg-elevated)',
                    color: active ? '#fff' : 'var(--text-muted)',
                    border: `1px solid ${active ? pColor : 'var(--border-subtle)'}`,
                    cursor: 'pointer', fontFamily: 'var(--font-sans)',
                  }}
                >
                  {party} ({count})
                </button>
              );
            })}
          </div>
        </div>

        {/* Count */}
        <div style={{
          padding: '4px 10px', fontSize: 9, color: 'var(--text-disabled)',
          borderBottom: '1px solid var(--border-subtle)',
        }}>
          {filtered.length} elected representatives
        </div>

        {/* MP List */}
        <div style={{ flex: 1, overflow: 'auto' }}>
          {isLoading ? (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
              <div className="w-5 h-5 border-2 border-blue-500/30 border-t-blue-500 rounded-full animate-spin" />
            </div>
          ) : filtered.length === 0 ? (
            <div style={{ padding: 24, textAlign: 'center', fontSize: 11, color: 'var(--text-muted)' }}>
              No parliamentarians found
            </div>
          ) : filtered.map(mp => {
            const pColor = getPartyColor(mp.party);
            return (
              <div
                key={mp.id}
                onClick={() => setSelectedMP(mp)}
                style={{
                  padding: '8px 10px',
                  borderBottom: '1px solid var(--border-subtle)',
                  cursor: 'pointer',
                  transition: 'background 0.1s',
                  borderLeft: `3px solid ${pColor}`,
                  display: 'flex', alignItems: 'center', gap: 8,
                }}
                onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-hover)')}
                onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
              >
                {/* Photo */}
                <div style={{
                  width: 30, height: 30, borderRadius: 4, overflow: 'hidden', flexShrink: 0,
                  background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  {mp.photoUrl ? (
                    <img src={mp.photoUrl} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                      onError={e => { (e.target as HTMLImageElement).style.display = 'none'; }} />
                  ) : (
                    <User size={14} style={{ color: 'var(--text-disabled)' }} />
                  )}
                </div>

                {/* Info */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {mp.name}
                    </span>
                    <span style={{ fontSize: 8, fontWeight: 700, padding: '1px 4px', background: pColor, color: '#fff', flexShrink: 0 }}>
                      {getPartyShortLabel(mp.party)}
                    </span>
                    <span style={{
                      fontSize: 8,
                      fontWeight: 700,
                      padding: '1px 4px',
                      background: 'var(--bg-elevated)',
                      color: mp.electionType === 'pr' ? '#60A5FA' : 'var(--text-muted)',
                      border: '1px solid var(--border-subtle)',
                      flexShrink: 0,
                    }}>
                      {mp.electionType === 'pr' ? 'PR' : 'FPTP'}
                    </span>
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 1, display: 'flex', alignItems: 'center', gap: 4 }}>
                    <MapPin size={9} style={{ flexShrink: 0 }} />
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{mp.constituency}</span>
                  </div>
                </div>

                <ChevronRight size={14} style={{ color: 'var(--text-disabled)', flexShrink: 0 }} />
              </div>
            );
          })}
        </div>
      </div>

      {/* Performance Card Modal */}
      {selectedMP && <PerformanceCard mp={selectedMP} onClose={() => setSelectedMP(null)} />}
    </Widget>
  );
});
