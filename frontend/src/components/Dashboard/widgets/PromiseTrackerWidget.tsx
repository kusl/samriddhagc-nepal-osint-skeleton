import { memo, useMemo, useState, type CSSProperties } from 'react';
import { ClipboardCheck, FileCheck2, ChevronDown, ChevronUp, ExternalLink } from 'lucide-react';
import { useCabinetActionDetail, useCabinetActionItems, useCabinetActionSummary, usePromiseSummary } from '../../../api/hooks';
import { Widget } from '../Widget';
import { WidgetError, WidgetSkeleton } from './shared';

type PromiseStatus = 'not_started' | 'in_progress' | 'partially_fulfilled' | 'fulfilled' | 'stalled';
type TrackerMode = 'cabinet' | 'manifesto';
type CabinetViewFilter = 'all' | 'due_soon' | 'overdue' | 'completed' | 'non_scored';

interface ManifestoPromise {
  promise_id: string;
  promise: string;
  category: string;
  status: PromiseStatus;
  detail?: string;
  source?: string;
  status_detail?: string;
  last_checked_at?: string;
}

const STATUS_CONFIG: Record<PromiseStatus, { label: string; color: string; bg: string }> = {
  not_started: { label: 'Not Started', color: 'var(--text-muted)', bg: 'rgba(113,113,122,0.12)' },
  in_progress: { label: 'In Progress', color: 'var(--accent-primary)', bg: 'rgba(59,130,246,0.12)' },
  partially_fulfilled: { label: 'Partial', color: 'var(--status-medium)', bg: 'rgba(234,179,8,0.12)' },
  fulfilled: { label: 'Fulfilled', color: 'var(--status-low)', bg: 'rgba(34,197,94,0.12)' },
  stalled: { label: 'Stalled', color: 'var(--status-high)', bg: 'rgba(249,115,22,0.12)' },
};

const CATEGORY_TONES: Record<string, string> = {
  Governance: '#60a5fa',
  Economy: '#34d399',
  'Digital & IT': '#38bdf8',
  Agriculture: '#86efac',
  Education: '#fbbf24',
  Health: '#f472b6',
  Infrastructure: '#a78bfa',
  'Foreign Policy & Security': '#fb7185',
};

const CATEGORIES = [
  'Governance', 'Anti-Corruption', 'Judiciary', 'Economy',
  'Digital & IT', 'Financial Sector', 'Agriculture', 'Energy',
  'Tourism & Culture', 'Education', 'Health', 'Infrastructure',
  'Trade & Investment', 'Labor & Employment', 'Environment & Climate',
  'Social', 'Foreign Policy & Security',
] as const;

const FALLBACK_PROMISES: ManifestoPromise[] = [
  { promise_id: 'G1', category: 'Governance', status: 'not_started', promise: 'Constitutional amendment discussion paper', detail: 'Prepare a discussion paper for national consensus on constitutional amendments.', source: 'Point 10' },
  { promise_id: 'G2', category: 'Governance', status: 'not_started', promise: 'Limit federal ministries to 18 with expert ministers', detail: 'Cap ministries at 18 and use expertise-based administration.', source: 'Point 17' },
  { promise_id: 'AC1', category: 'Anti-Corruption', status: 'not_started', promise: 'Mandatory asset disclosure before and after office', detail: 'Full asset disclosure before office and independent audit of wealth change after term.', source: 'Point 16' },
  { promise_id: 'E1', category: 'Economy', status: 'not_started', promise: 'USD 3000 per-capita income and USD 100B economy target', detail: 'Raise per-capita income to minimum USD 3000 and grow the economy to USD 100B.', source: 'Citizen Contract §2' },
  { promise_id: 'ED1', category: 'Education', status: 'not_started', promise: 'Free universities from political interference', detail: 'Depoliticize university governance and protect institutional autonomy.', source: 'Point 67' },
  { promise_id: 'H1', category: 'Health', status: 'not_started', promise: 'Minimum health service standards nationwide', detail: 'Guarantee a baseline package of health services across all provinces.', source: 'Point 59' },
];

function formatDueDate(value?: string | null) {
  if (!value) return 'No deadline parsed';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function cabinetStatusConfig(status: string) {
  switch (status) {
    case 'completed_on_time':
      return { label: 'Completed On Time', color: '#34d399', bg: 'rgba(52,211,153,0.12)' };
    case 'completed_late':
      return { label: 'Completed Late', color: '#f59e0b', bg: 'rgba(245,158,11,0.12)' };
    case 'overdue':
      return { label: 'Overdue', color: '#f87171', bg: 'rgba(248,113,113,0.12)' };
    case 'implementation_started':
      return { label: 'Implementation Started', color: '#60a5fa', bg: 'rgba(96,165,250,0.12)' };
    case 'partially_completed':
      return { label: 'Partial', color: '#eab308', bg: 'rgba(234,179,8,0.12)' };
    case 'declaratory_non_scored':
      return { label: 'Declaratory', color: 'var(--text-muted)', bg: 'rgba(255,255,255,0.05)' };
    default:
      return { label: 'Announced', color: 'var(--accent-primary)', bg: 'rgba(59,130,246,0.12)' };
  }
}

function HeaderToggle({ mode, onChange }: { mode: TrackerMode; onChange: (mode: TrackerMode) => void }) {
  return (
    <div style={{ display: 'inline-flex', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, overflow: 'hidden', background: 'rgba(255,255,255,0.02)' }}>
      {[
        { key: 'cabinet' as const, label: 'Cabinet' },
        { key: 'manifesto' as const, label: 'Manifesto' },
      ].map((entry) => {
        const active = mode === entry.key;
        return (
          <button
            key={entry.key}
            type="button"
            onClick={() => onChange(entry.key)}
            style={{
              border: 'none',
              background: active ? 'rgba(37,99,235,0.18)' : 'transparent',
              color: active ? '#93c5fd' : 'var(--text-muted)',
              padding: '7px 12px',
              fontSize: 9,
              fontWeight: 700,
              fontFamily: 'var(--font-mono)',
              letterSpacing: '0.03em',
              cursor: 'pointer',
            }}
          >
            {entry.label}
          </button>
        );
      })}
    </div>
  );
}

function CompactSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  onChange: (value: string) => void;
}) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
      <span style={{ fontSize: 8, color: 'var(--text-disabled)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        style={{
          minWidth: 0,
          height: 32,
          padding: '0 10px',
          borderRadius: 8,
          border: '1px solid rgba(255,255,255,0.08)',
          background: 'rgba(255,255,255,0.03)',
          color: 'var(--text-primary)',
          fontSize: 10,
          fontFamily: 'var(--font-mono)',
          outline: 'none',
          boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.03)',
        }}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value} style={{ background: '#12151c', color: '#e5e7eb' }}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function DistributionBar({
  segments,
}: {
  segments: Array<{ label: string; value: number; color: string }>;
}) {
  const total = segments.reduce((sum, segment) => sum + segment.value, 0);
  return (
    <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--border-subtle)', background: 'rgba(15,18,25,0.72)' }}>
      <div style={{ height: 9, width: '100%', display: 'flex', borderRadius: 999, overflow: 'hidden', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.04)' }}>
        {segments.map((segment) => (
          <div
            key={segment.label}
            style={{
              width: total > 0 ? `${(segment.value / total) * 100}%` : '0%',
              minWidth: segment.value > 0 ? 6 : 0,
              background: segment.color,
            }}
            title={`${segment.label}: ${segment.value}`}
          />
        ))}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px 14px', marginTop: 8 }}>
        {segments.map((segment) => (
          <div key={segment.label} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 9, color: 'var(--text-muted)' }}>
            <span style={{ width: 8, height: 8, borderRadius: 999, background: segment.color, flexShrink: 0 }} />
            <span>{segment.label}</span>
            <span style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{segment.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ManifestoPanel() {
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedStatus, setSelectedStatus] = useState<PromiseStatus | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const promiseSummaryQuery = usePromiseSummary('RSP', '2082');
  const promises = promiseSummaryQuery.data?.promises?.length
    ? promiseSummaryQuery.data.promises as ManifestoPromise[]
    : FALLBACK_PROMISES;
  const loading = promiseSummaryQuery.isLoading && !promiseSummaryQuery.data;
  const lastChecked = useMemo(() => (
    promiseSummaryQuery.data?.promises
      ?.map((promise) => promise.last_checked_at)
      .filter(Boolean)
      .sort()
      .pop() ?? null
  ), [promiseSummaryQuery.data?.promises]);

  const filtered = useMemo(() => {
    let next = [...promises];
    if (selectedCategory) next = next.filter((p) => p.category === selectedCategory);
    if (selectedStatus) next = next.filter((p) => p.status === selectedStatus);
    return next;
  }, [promises, selectedCategory, selectedStatus]);
  const ordered = useMemo(() => {
    const priority: Record<PromiseStatus, number> = {
      in_progress: 0,
      partially_fulfilled: 1,
      stalled: 2,
      not_started: 3,
      fulfilled: 4,
    };
    return [...filtered].sort((left, right) => {
      const delta = priority[left.status] - priority[right.status];
      if (delta !== 0) return delta;
      return left.promise_id.localeCompare(right.promise_id, 'en');
    });
  }, [filtered]);

  const byStatus = useMemo(() => promises.reduce((acc, promise) => {
    acc[promise.status] = (acc[promise.status] || 0) + 1;
    return acc;
  }, {} as Record<string, number>), [promises]);

  const total = promises.length;
  const fulfilled = byStatus.fulfilled || 0;
  const inProgress = byStatus.in_progress || 0;
  const partial = byStatus.partially_fulfilled || 0;
  const stalled = byStatus.stalled || 0;

  const categoryOptions = [
    { label: `All Promises (${total})`, value: null as string | null, count: total },
    ...CATEGORIES
      .map((category) => ({ label: category, value: category, count: promises.filter((p) => p.category === category).length }))
      .filter((entry) => entry.count > 0),
  ];
  const categorySelectOptions = categoryOptions.map((option) => ({
    value: option.value ?? '__all__',
    label: `${option.label}${option.value ? ` (${option.count})` : ''}`.replace(/\s+\((\d+)\) \((\d+)\)/, ' ($1)'),
  }));
  const statusSelectOptions = [
    { value: '__all__', label: `All Statuses (${total})` },
    { value: 'fulfilled', label: `Fulfilled (${fulfilled})` },
    { value: 'partially_fulfilled', label: `Partial (${partial})` },
    { value: 'in_progress', label: `In Progress (${inProgress})` },
    { value: 'stalled', label: `Stalled (${stalled})` },
    { value: 'not_started', label: `Not Started (${byStatus.not_started || 0})` },
  ];
  const manifestoSegments = [
    { label: 'Fulfilled', value: fulfilled, color: '#34d399' },
    { label: 'Partial', value: partial, color: '#fbbf24' },
    { label: 'Active', value: inProgress, color: '#3b82f6' },
    { label: 'Stalled', value: stalled, color: '#f97316' },
    { label: 'Not Started', value: byStatus.not_started || 0, color: 'rgba(148,163,184,0.75)' },
  ];

  return (
    <>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 1, background: 'rgba(255,255,255,0.06)', borderTop: '1px solid var(--border-subtle)', borderBottom: '1px solid var(--border-subtle)' }}>
        {[
          { label: 'Total Promises', value: total, meta: `${fulfilled} fulfilled / ${inProgress} active`, color: 'var(--text-primary)' },
          { label: 'Current Filter', value: selectedCategory || selectedStatus ? `${selectedCategory || 'All Categories'} · ${selectedStatus ? STATUS_CONFIG[selectedStatus].label : 'All Statuses'}` : 'All Promises', meta: `${ordered.length} visible`, color: 'var(--status-low)' },
          { label: 'Last Checked', value: lastChecked ? new Date(lastChecked).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : 'Fallback data', meta: `${partial} partial / ${stalled} stalled`, color: 'var(--text-primary)' },
        ].map((card) => (
          <div key={card.label} style={{ padding: '9px 12px', background: 'var(--bg-surface)' }}>
            <div style={{ fontSize: 8, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>{card.label}</div>
            <div style={{ marginTop: 6, fontSize: 13, fontWeight: 700, color: card.color }}>{card.value}</div>
            <div style={{ marginTop: 4, fontSize: 9, color: 'var(--text-disabled)' }}>{card.meta}</div>
          </div>
        ))}
      </div>
      <DistributionBar segments={manifestoSegments} />

      <div style={{ padding: '9px 12px', borderBottom: '1px solid var(--border-subtle)', display: 'grid', gridTemplateColumns: 'repeat(2, minmax(180px, 320px))', gap: 10 }}>
        <CompactSelect
          label="Category Filter"
          value={selectedCategory ?? '__all__'}
          options={categorySelectOptions}
          onChange={(value) => setSelectedCategory(value === '__all__' ? null : value)}
        />
        <CompactSelect
          label="Status Filter"
          value={selectedStatus ?? '__all__'}
          options={statusSelectOptions}
          onChange={(value) => setSelectedStatus(value === '__all__' ? null : (value as PromiseStatus))}
        />
      </div>

      <div style={{ flex: 1, minHeight: 0, overflow: 'auto', padding: '8px 12px 10px' }}>
        {loading ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 30 }}>
            <div className="w-5 h-5 border-2 border-blue-500/30 border-t-blue-500 rounded-full animate-spin" />
          </div>
        ) : ordered.map((promise) => {
          const expanded = expandedId === promise.promise_id;
          const status = STATUS_CONFIG[promise.status] || STATUS_CONFIG.not_started;
          const categoryAccent = CATEGORY_TONES[promise.category] || 'var(--text-muted)';
          return (
            <div key={promise.promise_id} onClick={() => setExpandedId(expanded ? null : promise.promise_id)} style={{ padding: '9px 12px', marginBottom: 6, border: '1px solid var(--border-subtle)', background: expanded ? 'rgba(20,23,30,0.98)' : 'var(--bg-surface)', cursor: 'pointer' }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginBottom: 4 }}>
                    <span style={{ fontSize: 8, color: 'var(--text-disabled)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>{promise.promise_id}</span>
                    <span style={{ fontSize: 8, color: categoryAccent, border: `1px solid ${categoryAccent}33`, background: `${categoryAccent}12`, padding: '2px 6px', borderRadius: 999 }}>{promise.category}</span>
                  </div>
                  <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-primary)', lineHeight: 1.35 }}>{promise.promise}</div>
                  <div style={{ fontSize: 9, color: 'var(--text-muted)', lineHeight: 1.35, marginTop: 3 }}>{promise.status_detail || promise.detail || 'No implementation detail recorded yet.'}</div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
                  <span style={{ fontSize: 8, fontWeight: 700, color: status.color, background: status.bg, border: `1px solid ${status.color}22`, padding: '3px 7px', borderRadius: 999, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{status.label}</span>
                  {expanded ? <ChevronUp size={12} style={{ color: 'var(--text-disabled)' }} /> : <ChevronDown size={12} style={{ color: 'var(--text-disabled)' }} />}
                </div>
              </div>
              {expanded && (
                <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid rgba(255,255,255,0.06)', display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 12 }}>
                  <div>
                    <div style={{ fontSize: 8, color: 'var(--text-disabled)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 5 }}>Manifesto Detail</div>
                    <div style={{ fontSize: 9, color: 'var(--text-muted)', lineHeight: 1.5 }}>{promise.detail || 'No manifesto detail recorded.'}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: 8, color: 'var(--text-disabled)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 5 }}>Tracking Note</div>
                    <div style={{ fontSize: 9, color: 'var(--text-muted)', lineHeight: 1.5 }}>{promise.status_detail || 'No live implementation note yet.'}</div>
                    {promise.source && <div style={{ fontSize: 9, color: 'var(--text-disabled)', fontFamily: 'var(--font-mono)', marginTop: 8 }}>Ref: {promise.source}</div>}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </>
  );
}

function CabinetPanel() {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [viewFilter, setViewFilter] = useState<CabinetViewFilter>('all');
  const [sectionFilter, setSectionFilter] = useState<string | null>(null);
  const [institutionFilter, setInstitutionFilter] = useState<string | null>(null);
  const summaryQuery = useCabinetActionSummary();
  const itemsQuery = useCabinetActionItems({ limit: 140 });
  const detailQuery = useCabinetActionDetail(expandedId);
  const summary = summaryQuery.data;
  const items = itemsQuery.data?.items || [];
  const detail = detailQuery.data || null;

  const sectionOptions = useMemo(() => {
    const seen = new Map<string, string>();
    items.forEach((item) => {
      if (item.sectionKey && item.sectionTitle && !seen.has(item.sectionKey)) {
        seen.set(item.sectionKey, item.sectionTitle);
      }
    });
    return [{ key: null as string | null, label: 'All Sections' }, ...Array.from(seen.entries()).map(([key, label]) => ({ key, label }))];
  }, [items]);

  const institutionOptions = useMemo(() => {
    const counts = new Map<string, number>();
    items.forEach((item) => {
      const lead = item.leadInstitution?.trim();
      if (!lead) return;
      counts.set(lead, (counts.get(lead) || 0) + 1);
    });
    return [
      { key: null as string | null, label: 'All Institutions', count: items.length },
      ...Array.from(counts.entries())
        .sort((a, b) => a[0].localeCompare(b[0], 'en'))
        .map(([key, count]) => ({ key, label: key, count })),
    ];
  }, [items]);

  const filteredItems = useMemo(() => {
    let next = [...items];
    if (institutionFilter) next = next.filter((item) => item.leadInstitution === institutionFilter);
    if (sectionFilter) next = next.filter((item) => item.sectionKey === sectionFilter);
    if (viewFilter === 'due_soon') {
      const now = new Date();
      const inSeven = new Date();
      inSeven.setDate(now.getDate() + 7);
      next = next.filter((item) => item.dueDateAd && new Date(item.dueDateAd) >= now && new Date(item.dueDateAd) <= inSeven && !['completed_on_time', 'completed_late'].includes(item.status));
    } else if (viewFilter === 'overdue') {
      next = next.filter((item) => item.status === 'overdue');
    } else if (viewFilter === 'completed') {
      next = next.filter((item) => ['completed_on_time', 'completed_late'].includes(item.status));
    } else if (viewFilter === 'non_scored') {
      next = next.filter((item) => item.status === 'declaratory_non_scored');
    }
    return next;
  }, [institutionFilter, items, sectionFilter, viewFilter]);

  if (summaryQuery.isLoading || itemsQuery.isLoading) {
    return <WidgetSkeleton />;
  }

  if (summaryQuery.error || itemsQuery.error) {
    return <WidgetError message="Failed to load cabinet action tracker" onRetry={() => { summaryQuery.refetch(); itemsQuery.refetch(); }} />;
  }

  const viewOptions = [
    { key: 'all' as const, label: 'All Actions', count: items.length },
    { key: 'due_soon' as const, label: 'Due Soon' },
    { key: 'overdue' as const, label: 'Overdue', count: items.filter((item) => item.status === 'overdue').length },
    { key: 'completed' as const, label: 'Completed', count: items.filter((item) => ['completed_on_time', 'completed_late'].includes(item.status)).length },
    { key: 'non_scored' as const, label: 'Non-Scored', count: items.filter((item) => item.status === 'declaratory_non_scored').length },
  ];
  const cabinetSegments = [
    { label: 'Completed On Time', value: summary?.completed_on_time ?? 0, color: '#34d399' },
    { label: 'Completed Late', value: summary?.completed_late ?? 0, color: '#fbbf24' },
    { label: 'Underway', value: summary?.underway ?? 0, color: '#3b82f6' },
    { label: 'Overdue', value: summary?.overdue ?? 0, color: '#f87171' },
    { label: 'Non-Scored', value: summary?.non_scored ?? 0, color: 'rgba(148,163,184,0.75)' },
  ];
  const viewSelectOptions = viewOptions.map((option) => ({
    value: option.key,
    label: `${option.label}${typeof option.count === 'number' ? ` (${option.count})` : ''}`,
  }));
  const institutionSelectOptions = institutionOptions.map((institution) => ({
    value: institution.key ?? '__all__',
    label: `${institution.label}${typeof institution.count === 'number' ? ` (${institution.count})` : ''}`,
  }));
  const sectionSelectOptions = sectionOptions.map((section) => ({
    value: section.key ?? '__all__',
    label: section.label,
  }));

  return (
    <>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 1, background: 'rgba(255,255,255,0.06)', borderTop: '1px solid var(--border-subtle)', borderBottom: '1px solid var(--border-subtle)' }}>
        {[
          { label: 'Total Actions', value: summary?.total_actions ?? items.length, meta: 'Canonical cabinet archive', color: 'var(--text-primary)' },
          { label: 'Scored', value: summary?.total_scored_actions ?? 0, meta: `${summary?.underway ?? 0} underway`, color: 'var(--accent-primary)' },
          { label: 'Overdue', value: summary?.overdue ?? 0, meta: `${summary?.completed_on_time ?? 0} on time / ${summary?.completed_late ?? 0} late`, color: '#f87171' },
          { label: 'Non-Scored', value: summary?.non_scored ?? 0, meta: 'Declaratory or contextual items', color: 'var(--text-muted)' },
        ].map((card) => (
          <div key={card.label} style={{ padding: '9px 12px', background: 'var(--bg-surface)' }}>
            <div style={{ fontSize: 8, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>{card.label}</div>
            <div style={{ marginTop: 6, fontSize: 13, fontWeight: 700, color: card.color }}>{card.value}</div>
            <div style={{ marginTop: 4, fontSize: 9, color: 'var(--text-disabled)' }}>{card.meta}</div>
          </div>
        ))}
      </div>
      <DistributionBar segments={cabinetSegments} />

      <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--border-subtle)', display: 'grid', gridTemplateColumns: 'repeat(3, minmax(180px, 1fr))', gap: 10 }}>
        <CompactSelect
          label="Status View"
          value={viewFilter}
          options={viewSelectOptions}
          onChange={(value) => setViewFilter(value as CabinetViewFilter)}
        />
        <CompactSelect
          label="Lead Institution"
          value={institutionFilter ?? '__all__'}
          options={institutionSelectOptions}
          onChange={(value) => setInstitutionFilter(value === '__all__' ? null : value)}
        />
        <CompactSelect
          label="Section"
          value={sectionFilter ?? '__all__'}
          options={sectionSelectOptions}
          onChange={(value) => setSectionFilter(value === '__all__' ? null : value)}
        />
      </div>

      <div style={{ flex: 1, minHeight: 0, overflow: 'auto', padding: '8px 12px 10px' }}>
        {filteredItems.map((item) => {
          const expanded = expandedId === item.id;
          const detailItem = expanded ? detail : null;
          const status = cabinetStatusConfig(item.status);
          const supporting = detailItem?.supportingInstitutions || item.supportingInstitutions || [];
          return (
            <div key={item.id} onClick={() => setExpandedId(expanded ? null : item.id)} style={{ padding: '9px 12px', marginBottom: 6, border: '1px solid var(--border-subtle)', background: expanded ? 'rgba(20,23,30,0.98)' : 'var(--bg-surface)', cursor: 'pointer' }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginBottom: 4 }}>
                    <span style={{ fontSize: 8, color: 'var(--text-disabled)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Item {item.itemNumber}</span>
                    <span style={{ fontSize: 8, color: 'var(--status-low)', border: '1px solid rgba(52,211,153,0.22)', background: 'rgba(52,211,153,0.10)', padding: '2px 6px', borderRadius: 999 }}>{item.sectionTitle || 'Unsectioned'}</span>
                  </div>
                  <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-primary)', lineHeight: 1.35 }}>{item.title}</div>
                  <div style={{ fontSize: 9, color: 'var(--text-muted)', lineHeight: 1.35, marginTop: 3 }}>{item.summary}</div>
                  <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 6, fontSize: 8, color: 'var(--text-disabled)' }}>
                    <span>Due {formatDueDate(item.dueDateAd)}</span>
                    <span>{item.leadInstitution || 'Lead institution pending'}</span>
                    <span>{item.actionType || 'Cabinet Action'}</span>
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
                  <span style={{ fontSize: 8, fontWeight: 700, color: status.color, background: status.bg, border: `1px solid ${status.color}22`, padding: '3px 7px', borderRadius: 999, textTransform: 'uppercase', letterSpacing: '0.06em', whiteSpace: 'nowrap' }}>{status.label}</span>
                  {expanded ? <ChevronUp size={12} style={{ color: 'var(--text-disabled)' }} /> : <ChevronDown size={12} style={{ color: 'var(--text-disabled)' }} />}
                </div>
              </div>

              {expanded && (
                <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid rgba(255,255,255,0.06)', display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 12 }}>
                  <div>
                    <div style={{ fontSize: 8, color: 'var(--text-disabled)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 5 }}>Lead And Supporting Institutions</div>
                    <div style={{ fontSize: 9, color: 'var(--text-muted)', lineHeight: 1.55 }}>
                      <div>{item.leadInstitution || 'Lead institution pending'}</div>
                      {supporting.length > 0 && <div style={{ marginTop: 6 }}>Supporting: {supporting.join(', ')}</div>}
                    </div>
                  </div>

                  <div>
                    <div style={{ fontSize: 8, color: 'var(--text-disabled)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 5 }}>Deadline And Source</div>
                    <div style={{ fontSize: 9, color: 'var(--text-muted)', lineHeight: 1.55 }}>
                      <div>AD: {formatDueDate(item.dueDateAd)}</div>
                      <div>BS: {item.dueDateBs || item.deadlineTextNe || 'Not parsed'}</div>
                      <div style={{ marginTop: 6 }}>PDF page: {item.sourcePdfPage ?? 'Unknown'}</div>
                    </div>
                  </div>

                  {detailItem?.milestones && detailItem.milestones.length > 0 && (
                    <div style={{ gridColumn: '1 / -1' }}>
                      <div style={{ fontSize: 8, color: 'var(--text-disabled)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6 }}>Milestones</div>
                      <div style={{ display: 'grid', gap: 8 }}>
                        {detailItem.milestones.map((milestone) => (
                          <div key={milestone.id} style={{ border: '1px solid rgba(255,255,255,0.08)', padding: '9px 10px', background: 'rgba(255,255,255,0.02)' }}>
                            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 }}>
                              <div>
                                <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-primary)' }}>{milestone.title}</div>
                                <div style={{ marginTop: 4, fontSize: 9, lineHeight: 1.5, color: 'var(--text-muted)' }}>{milestone.summary}</div>
                              </div>
                              <span style={{ fontSize: 8, color: 'var(--text-disabled)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{milestone.status.replace(/_/g, ' ')}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {detailItem?.evidence && detailItem.evidence.length > 0 && (
                    <div style={{ gridColumn: '1 / -1' }}>
                      <div style={{ fontSize: 8, color: 'var(--text-disabled)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6 }}>Evidence Trail</div>
                      <div style={{ display: 'grid', gap: 8 }}>
                        {detailItem.evidence.slice(0, 5).map((entry) => (
                          <div key={entry.id} style={{ border: '1px solid rgba(255,255,255,0.08)', padding: '9px 10px', background: 'rgba(255,255,255,0.02)' }}>
                            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 }}>
                              <div style={{ minWidth: 0 }}>
                                <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-primary)' }}>{entry.sourceTitle}</div>
                                <div style={{ marginTop: 4, fontSize: 9, lineHeight: 1.5, color: 'var(--text-muted)' }}>{entry.note || 'No evidence note yet.'}</div>
                                <div style={{ marginTop: 6, fontSize: 8, color: 'var(--text-disabled)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                                  {entry.isOfficial ? 'Official' : 'Reported'} | {entry.sourceName || entry.sourceKind}
                                </div>
                              </div>
                              {entry.sourceUrl && (
                                <a href={entry.sourceUrl} target="_blank" rel="noreferrer" style={{ color: 'var(--text-muted)' }}>
                                  <ExternalLink size={12} />
                                </a>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </>
  );
}

export const PromiseTrackerWidget = memo(function PromiseTrackerWidget() {
  const [mode, setMode] = useState<TrackerMode>('cabinet');

  return (
    <Widget id="promise-tracker" icon={mode === 'cabinet' ? <FileCheck2 size={14} /> : <ClipboardCheck size={14} />}>
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden', background: 'var(--bg-surface)' }}>
        <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', background: 'var(--bg-surface)' }}>
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '0.02em' }}>
              {mode === 'cabinet' ? 'Cabinet 100-Day Action Tracker' : 'Manifesto Promise Tracker'}
            </div>
            {mode !== 'cabinet' && (
              <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 3 }}>
                RSP manifesto commitments linked to the current government implementation phase
              </div>
            )}
          </div>
          <HeaderToggle mode={mode} onChange={setMode} />
        </div>

        {mode === 'cabinet' ? <CabinetPanel /> : <ManifestoPanel />}
      </div>
    </Widget>
  );
});
