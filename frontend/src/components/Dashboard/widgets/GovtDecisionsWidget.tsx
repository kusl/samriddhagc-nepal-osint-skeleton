import { memo, useMemo, useState } from 'react';
import { Gavel, Clock, ExternalLink, ChevronDown, ChevronUp, Building2 } from 'lucide-react';
import { useLatestGovtDecisions } from '../../../api/hooks';
import { Widget } from '../Widget';
import { WidgetError, WidgetSkeleton } from './shared';

function getTimeAgo(dateString: string): string {
  const date = new Date(dateString);
  if (Number.isNaN(date.getTime())) return '';
  const diffMs = Date.now() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function getStatusStyles(status?: string | null) {
  switch (status) {
    case 'Active':
      return {
        color: 'var(--status-low)',
        background: 'rgba(16, 185, 129, 0.12)',
        border: '1px solid rgba(16, 185, 129, 0.28)',
      };
    case 'Under Review':
      return {
        color: 'var(--status-high)',
        background: 'rgba(245, 158, 11, 0.12)',
        border: '1px solid rgba(245, 158, 11, 0.28)',
      };
    default:
      return {
        color: 'var(--text-muted)',
        background: 'var(--bg-elevated)',
        border: '1px solid var(--border-subtle)',
      };
  }
}

export const GovtDecisionsWidget = memo(function GovtDecisionsWidget() {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const { data, isLoading, error, refetch } = useLatestGovtDecisions(500, false);

  const decisions = useMemo(
    () => [...(data?.items || [])].sort((a, b) => Date.parse(b.publishedAt || '') - Date.parse(a.publishedAt || '')),
    [data?.items],
  );

  if (isLoading) {
    return (
      <Widget id="govt-decisions" icon={<Gavel size={14} />}>
        <WidgetSkeleton />
      </Widget>
    );
  }

  if (error) {
    return (
      <Widget id="govt-decisions" icon={<Gavel size={14} />}>
        <WidgetError message="Failed to load government decisions" onRetry={() => refetch()} />
      </Widget>
    );
  }

  return (
    <Widget id="govt-decisions" icon={<Gavel size={14} />} badge={decisions.length}>
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{
          padding: '6px 12px',
          borderBottom: '1px solid var(--border-subtle)',
          fontSize: 9,
          color: 'var(--text-muted)',
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
        }}>
          {decisions.length} approved decisions in archive
        </div>
        <div style={{ flex: 1, overflow: 'auto' }}>
          {decisions.length === 0 ? (
            <div style={{ padding: 24, textAlign: 'center', fontSize: 11, color: 'var(--text-muted)' }}>
              No recent government decisions
            </div>
          ) : decisions.map((item) => {
            const expanded = expandedId === item.id;
            return (
              <div
                key={item.id}
                onClick={() => setExpandedId(expanded ? null : item.id)}
                style={{
                  padding: '8px 12px',
                  borderBottom: '1px solid var(--border-subtle)',
                  cursor: 'pointer',
                  transition: 'background 0.1s',
                }}
                onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-hover)')}
                onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
              >
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                  <Building2 size={12} style={{ color: 'var(--text-disabled)', marginTop: 2, flexShrink: 0 }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1.4 }}>
                      {item.title}
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--text-muted)', lineHeight: 1.45, marginTop: 4 }}>
                      {item.decision}
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 3, flexWrap: 'wrap' }}>
                      {item.office && (
                        <span style={{
                          fontSize: 8, fontWeight: 600, padding: '1px 5px',
                          background: 'rgba(45, 114, 210, 0.12)', color: 'var(--accent-primary)',
                          border: '1px solid rgba(45, 114, 210, 0.24)',
                          textTransform: 'uppercase', letterSpacing: '0.03em',
                        }}>
                          {item.office}
                        </span>
                      )}
                      {item.implementingMinistry && (
                        <span style={{
                          fontSize: 8, fontWeight: 600, padding: '1px 5px',
                          background: 'var(--bg-elevated)', color: 'var(--text-muted)',
                          border: '1px solid var(--border-subtle)',
                          textTransform: 'uppercase', letterSpacing: '0.03em',
                        }}>
                          {item.implementingMinistry}
                        </span>
                      )}
                      {item.decisionType && (
                        <span style={{
                          fontSize: 8, fontWeight: 600, padding: '1px 5px',
                          background: 'rgba(168, 85, 247, 0.12)', color: '#c084fc',
                          border: '1px solid rgba(168, 85, 247, 0.28)',
                          textTransform: 'uppercase', letterSpacing: '0.03em',
                        }}>
                          {item.decisionType}
                        </span>
                      )}
                      {item.status && (
                        <span style={{
                          fontSize: 8, fontWeight: 700, padding: '1px 5px',
                          textTransform: 'uppercase', letterSpacing: '0.03em',
                          ...getStatusStyles(item.status),
                        }}>
                          {item.status}
                        </span>
                      )}
                      {item.publishedAt && (
                        <span style={{ fontSize: 9, color: 'var(--text-disabled)', display: 'flex', alignItems: 'center', gap: 3 }}>
                          <Clock size={8} />
                          {getTimeAgo(item.publishedAt)}
                        </span>
                      )}
                    </div>
                    {expanded && (
                      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 6, lineHeight: 1.5 }}>
                        <div style={{ marginBottom: 6 }}>
                          <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>Implementing ministry: </span>
                          {item.implementingMinistry || 'Not set'}
                        </div>
                        <div style={{ marginBottom: 6 }}>
                          <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>Decision type: </span>
                          {item.decisionType || 'Not set'}
                        </div>
                        <div style={{ marginBottom: 6 }}>
                          <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>Status: </span>
                          {item.status || 'Not set'}
                        </div>
                        <div>
                          <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>Evidence note: </span>
                          {item.evidenceNote || 'No evidence note'}
                        </div>
                      </div>
                    )}
                    {expanded && item.sourceUrl && (
                      <a
                        href={item.sourceUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={e => e.stopPropagation()}
                        style={{
                          display: 'inline-flex', alignItems: 'center', gap: 4,
                          fontSize: 9, color: 'var(--accent-primary)', marginTop: 4,
                          textDecoration: 'none',
                        }}
                      >
                        {item.sourceName || 'Source'} <ExternalLink size={8} />
                      </a>
                    )}
                  </div>
                  {expanded
                    ? <ChevronUp size={12} style={{ color: 'var(--text-disabled)', flexShrink: 0, marginTop: 2 }} />
                    : <ChevronDown size={12} style={{ color: 'var(--text-disabled)', flexShrink: 0, marginTop: 2 }} />}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </Widget>
  );
});
