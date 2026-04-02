import { memo, useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, Clock3, ExternalLink, FileCheck2 } from 'lucide-react';
import { useCabinetActionDetail, useCabinetActionItems, useCabinetActionSummary } from '../../../api/hooks';
import { Widget } from '../Widget';
import { WidgetError, WidgetSkeleton } from './shared';

function formatDueDate(value?: string | null) {
  if (!value) return 'No deadline parsed';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function statusTone(status: string) {
  switch (status) {
    case 'completed_on_time':
      return { color: '#34d399', border: 'rgba(52, 211, 153, 0.3)', bg: 'rgba(52, 211, 153, 0.12)' };
    case 'completed_late':
      return { color: '#f59e0b', border: 'rgba(245, 158, 11, 0.3)', bg: 'rgba(245, 158, 11, 0.12)' };
    case 'overdue':
      return { color: '#f87171', border: 'rgba(248, 113, 113, 0.32)', bg: 'rgba(248, 113, 113, 0.12)' };
    default:
      return { color: 'var(--accent-primary)', border: 'rgba(59, 130, 246, 0.3)', bg: 'rgba(59, 130, 246, 0.12)' };
  }
}

export const CabinetActionTrackerWidget = memo(function CabinetActionTrackerWidget() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const summaryQuery = useCabinetActionSummary();
  const itemsQuery = useCabinetActionItems({ limit: 18 });
  const detailQuery = useCabinetActionDetail(selectedId);

  const items = itemsQuery.data?.items || [];

  useEffect(() => {
    if (!selectedId && items.length > 0) {
      setSelectedId(items[0].id);
    }
  }, [items, selectedId]);

  if (summaryQuery.isLoading || itemsQuery.isLoading) {
    return (
      <Widget id="cabinet-action-tracker" icon={<FileCheck2 size={14} />}>
        <WidgetSkeleton />
      </Widget>
    );
  }

  if (summaryQuery.error || itemsQuery.error) {
    return (
      <Widget id="cabinet-action-tracker" icon={<FileCheck2 size={14} />}>
        <WidgetError message="Failed to load cabinet action tracker" onRetry={() => { summaryQuery.refetch(); itemsQuery.refetch(); }} />
      </Widget>
    );
  }

  const summary = summaryQuery.data;
  const selected = detailQuery.data || null;

  return (
    <Widget id="cabinet-action-tracker" icon={<FileCheck2 size={14} />} badge="100D">
      <div className="flex h-full min-h-0 flex-col bg-[radial-gradient(circle_at_top,rgba(59,130,246,0.08),transparent_48%)]">
        <div className="grid grid-cols-4 gap-2 border-b border-white/8 px-3 py-3">
          <div className="rounded-xl border border-white/8 bg-white/[0.03] px-3 py-2">
            <div className="text-[10px] uppercase tracking-[0.22em] text-white/35">Scored</div>
            <div className="mt-1 text-lg font-semibold text-white">{summary?.total_scored_actions ?? 0}</div>
          </div>
          <div className="rounded-xl border border-emerald-400/20 bg-emerald-500/[0.06] px-3 py-2">
            <div className="text-[10px] uppercase tracking-[0.22em] text-white/35">On Time</div>
            <div className="mt-1 text-lg font-semibold text-emerald-300">{summary?.completed_on_time ?? 0}</div>
          </div>
          <div className="rounded-xl border border-amber-400/20 bg-amber-500/[0.06] px-3 py-2">
            <div className="text-[10px] uppercase tracking-[0.22em] text-white/35">Late</div>
            <div className="mt-1 text-lg font-semibold text-amber-300">{summary?.completed_late ?? 0}</div>
          </div>
          <div className="rounded-xl border border-rose-400/20 bg-rose-500/[0.06] px-3 py-2">
            <div className="text-[10px] uppercase tracking-[0.22em] text-white/35">Overdue</div>
            <div className="mt-1 text-lg font-semibold text-rose-300">{summary?.overdue ?? 0}</div>
          </div>
        </div>

        <div className="grid min-h-0 flex-1 grid-cols-[320px_minmax(0,1fr)]">
          <div className="overflow-y-auto border-r border-white/8">
            {items.map((item) => {
              const tone = statusTone(item.status);
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setSelectedId(item.id)}
                  className={`w-full border-b border-white/8 px-3 py-3 text-left transition-colors ${selectedId === item.id ? 'bg-white/[0.05]' : 'hover:bg-white/[0.03]'}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-[10px] uppercase tracking-[0.18em] text-white/35">Item {item.itemNumber}</div>
                      <div className="mt-1 line-clamp-2 text-[13px] font-medium leading-5 text-white">{item.title}</div>
                    </div>
                    <span
                      className="rounded-full border px-2 py-1 text-[9px] font-semibold uppercase tracking-[0.18em]"
                      style={{ color: tone.color, borderColor: tone.border, background: tone.bg }}
                    >
                      {item.status.replace(/_/g, ' ')}
                    </span>
                  </div>
                  <div className="mt-2 flex items-center gap-2 text-[11px] text-white/45">
                    <Clock3 size={10} />
                    {formatDueDate(item.dueDateAd)}
                    <span className="text-white/20">|</span>
                    <span>{item.leadInstitution || item.sectionTitle}</span>
                  </div>
                </button>
              );
            })}
          </div>

          <div className="overflow-y-auto px-4 py-4">
            {!selected ? (
              <div className="flex h-full items-center justify-center text-[12px] text-white/40">
                Select a cabinet action item
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="text-[10px] uppercase tracking-[0.22em] text-white/35">
                      {selected.sectionTitle} | Item {selected.itemNumber}
                    </div>
                    <h3 className="mt-2 text-[18px] font-semibold leading-7 text-white">{selected.title}</h3>
                    <p className="mt-2 text-[12px] leading-6 text-white/62">{selected.summary}</p>
                  </div>
                  <div className="min-w-[140px] rounded-2xl border border-white/8 bg-white/[0.03] p-3 text-right">
                    <div className="text-[10px] uppercase tracking-[0.18em] text-white/35">Due</div>
                    <div className="mt-1 text-[16px] font-semibold text-white">{formatDueDate(selected.dueDateAd)}</div>
                    <div className="mt-1 text-[11px] text-white/45">{selected.dueDateBs || selected.deadlineTextNe || 'No BS date'}</div>
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-3">
                  <div className="rounded-2xl border border-white/8 bg-white/[0.03] p-3">
                    <div className="text-[10px] uppercase tracking-[0.18em] text-white/35">Lead Institution</div>
                    <div className="mt-1 text-[12px] leading-5 text-white">{selected.leadInstitution || 'Not yet assigned'}</div>
                  </div>
                  <div className="rounded-2xl border border-white/8 bg-white/[0.03] p-3">
                    <div className="text-[10px] uppercase tracking-[0.18em] text-white/35">Action Type</div>
                    <div className="mt-1 text-[12px] leading-5 text-white">{selected.actionType || 'Cabinet Action'}</div>
                  </div>
                  <div className="rounded-2xl border border-white/8 bg-white/[0.03] p-3">
                    <div className="text-[10px] uppercase tracking-[0.18em] text-white/35">Manifesto Links</div>
                    <div className="mt-1 text-[12px] leading-5 text-white">
                      {selected.relatedManifestoPromises.length ? selected.relatedManifestoPromises.join(', ') : 'Unlinked'}
                    </div>
                  </div>
                </div>

                {selected.milestones && selected.milestones.length > 0 && (
                  <div className="rounded-2xl border border-white/8 bg-white/[0.02]">
                    <div className="border-b border-white/8 px-4 py-3 text-[10px] uppercase tracking-[0.22em] text-white/35">
                      Milestones
                    </div>
                    <div className="divide-y divide-white/8">
                      {selected.milestones.map((milestone) => (
                        <div key={milestone.id} className="px-4 py-3">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <div className="text-[12px] font-medium text-white">{milestone.title}</div>
                              <div className="mt-1 text-[11px] leading-5 text-white/55">{milestone.summary}</div>
                            </div>
                            <span className="rounded-full border border-white/10 bg-white/[0.04] px-2 py-1 text-[9px] uppercase tracking-[0.18em] text-white/50">
                              {milestone.status.replace(/_/g, ' ')}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {selected.evidence && selected.evidence.length > 0 && (
                  <div className="rounded-2xl border border-white/8 bg-white/[0.02]">
                    <div className="border-b border-white/8 px-4 py-3 text-[10px] uppercase tracking-[0.22em] text-white/35">
                      Evidence Trail
                    </div>
                    <div className="divide-y divide-white/8">
                      {selected.evidence.slice(0, 5).map((entry) => (
                        <div key={entry.id} className="px-4 py-3">
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <div className="text-[12px] font-medium text-white">{entry.sourceTitle}</div>
                              <div className="mt-1 text-[11px] leading-5 text-white/50">{entry.note || 'No evidence note'}</div>
                              <div className="mt-2 flex items-center gap-2 text-[10px] text-white/40">
                                {entry.isOfficial ? <CheckCircle2 size={10} /> : <AlertTriangle size={10} />}
                                <span>{entry.sourceName || entry.sourceKind}</span>
                              </div>
                            </div>
                            {entry.sourceUrl && (
                              <a href={entry.sourceUrl} target="_blank" rel="noreferrer" className="text-white/45 hover:text-white">
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
        </div>
      </div>
    </Widget>
  );
});
