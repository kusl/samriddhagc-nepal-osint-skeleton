/**
 * FactCheckWidget — Fact-check results + custom statement submission.
 * Signed-in users can submit up to 5 custom statements per month.
 */
import { memo, useState } from 'react';
import { Widget } from '../Widget';
import { ChevronDown, ExternalLink, AlertTriangle, CheckCircle, XCircle, HelpCircle, Send, Loader2 } from 'lucide-react';
import { useFactCheckResults, useUserStatements, useSubmitStatement, useMyStoryRequests } from '../../../api/hooks';
import { WidgetSkeleton, WidgetError } from './shared';
import { useAuthStore } from '../../../store/slices/authSlice';
import type { FactCheckResult } from '../../../api/factCheck';
import type { StatementFactCheck, PendingStoryRequest } from '../../../api/factCheck';

const MONTHLY_LIMIT = 5;

const VERDICT_CONFIG: Record<string, { label: string; color: string; icon: typeof CheckCircle; bg: string }> = {
  true:           { label: 'TRUE',           color: '#238551', icon: CheckCircle,   bg: 'rgba(35,133,81,0.12)' },
  mostly_true:    { label: 'MOSTLY TRUE',    color: '#238551', icon: CheckCircle,   bg: 'rgba(35,133,81,0.08)' },
  partially_true: { label: 'PARTLY TRUE',    color: '#D1980B', icon: HelpCircle,    bg: 'rgba(209,152,11,0.10)' },
  misleading:     { label: 'MISLEADING',     color: '#C87619', icon: AlertTriangle, bg: 'rgba(200,118,25,0.10)' },
  false:          { label: 'FALSE',          color: '#CD4246', icon: XCircle,       bg: 'rgba(205,66,70,0.12)' },
  unverifiable:   { label: 'UNVERIFIABLE',   color: '#738091', icon: HelpCircle,    bg: 'rgba(115,128,145,0.10)' },
  satire:         { label: 'SATIRE',         color: '#7961DB', icon: HelpCircle,    bg: 'rgba(121,97,219,0.10)' },
};

function formatTimeAgo(dateStr: string | null | undefined): string {
  if (!dateStr) return '';
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

function VerdictBadge({ verdict }: { verdict: string }) {
  const config = VERDICT_CONFIG[verdict] || VERDICT_CONFIG.unverifiable;
  const Icon = config.icon;
  return (
    <span style={{
      fontSize: '9px', padding: '2px 8px', fontWeight: 700,
      background: config.bg, color: config.color,
      display: 'inline-flex', alignItems: 'center', gap: '4px',
      letterSpacing: '0.5px', borderRadius: '4px',
    }}>
      <Icon size={10} />
      {config.label}
    </span>
  );
}

function FactCheckCard({ result }: { result: FactCheckResult }) {
  const [expanded, setExpanded] = useState(false);
  const config = VERDICT_CONFIG[result.verdict] || VERDICT_CONFIG.unverifiable;

  return (
    <div
      style={{
        padding: '10px 12px', cursor: 'pointer',
        borderBottom: '1px solid var(--border-subtle)',
        borderLeft: `3px solid ${config.color}`,
      }}
      onClick={() => setExpanded(v => !v)}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap', marginBottom: '6px' }}>
        <VerdictBadge verdict={result.verdict} />
        <span style={{ fontSize: '10px', color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}>
          {Math.round(result.confidence * 100)}%
        </span>
        <span style={{ marginLeft: 'auto', fontSize: '10px', color: 'var(--text-muted)' }}>
          {formatTimeAgo(result.checked_at)}
        </span>
      </div>

      <div style={{
        fontSize: '12px', fontWeight: 600, lineHeight: 1.4,
        overflow: 'hidden', display: '-webkit-box',
        WebkitLineClamp: expanded ? 'unset' : 2, WebkitBoxOrient: 'vertical' as const,
        color: 'var(--text-primary)',
      }}>
        {result.story_title || 'Untitled Story'}
      </div>

      {expanded && (
        <div style={{ marginTop: '8px', borderTop: '1px solid var(--border-subtle)', paddingTop: '8px' }}>
          {result.verdict_summary && (
            <div style={{ fontSize: '11px', color: 'var(--text-secondary)', lineHeight: 1.5, marginBottom: '6px' }}>
              {result.verdict_summary}
            </div>
          )}
          {result.key_finding && (
            <div style={{
              fontSize: '10px', padding: '6px 8px',
              borderLeft: `2px solid ${config.color}`, background: config.bg,
              color: 'var(--text-secondary)', lineHeight: 1.4, borderRadius: '4px',
              marginBottom: '6px',
            }}>
              {result.key_finding}
            </div>
          )}
          {result.claims_analyzed?.map((claim, i) => {
            const cc = VERDICT_CONFIG[claim.verdict] || VERDICT_CONFIG.unverifiable;
            return (
              <div key={i} style={{ padding: '4px 0', borderBottom: i < result.claims_analyzed!.length - 1 ? '1px solid var(--border-subtle)' : 'none' }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: '6px', marginBottom: '2px' }}>
                  <span style={{ fontSize: '8px', padding: '1px 5px', fontWeight: 600, background: cc.bg, color: cc.color, flexShrink: 0, marginTop: '2px' }}>{cc.label}</span>
                  <span style={{ fontSize: '10px', color: 'var(--text-primary)', lineHeight: 1.3 }}>{claim.claim}</span>
                </div>
                {claim.evidence && (
                  <div style={{ fontSize: '10px', color: 'var(--text-muted)', lineHeight: 1.3, paddingLeft: '40px' }}>{claim.evidence}</div>
                )}
              </div>
            );
          })}
          {result.story_url && (
            <a href={result.story_url} target="_blank" rel="noopener noreferrer"
              onClick={e => e.stopPropagation()}
              style={{ fontSize: '10px', color: 'var(--accent-primary)', display: 'inline-flex', alignItems: 'center', gap: '3px', textDecoration: 'none', marginTop: '4px' }}>
              <ExternalLink size={10} /> source
            </a>
          )}
        </div>
      )}
    </div>
  );
}

function StatementCard({ stmt }: { stmt: StatementFactCheck }) {
  const [expanded, setExpanded] = useState(false);
  const isPending = stmt.status === 'pending';
  const config = stmt.verdict ? (VERDICT_CONFIG[stmt.verdict] || VERDICT_CONFIG.unverifiable) : null;

  return (
    <div
      style={{
        padding: '10px 12px', cursor: 'pointer',
        borderBottom: '1px solid var(--border-subtle)',
        borderLeft: `3px solid ${isPending ? '#738091' : config?.color || '#738091'}`,
      }}
      onClick={() => setExpanded(v => !v)}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap', marginBottom: '6px' }}>
        {isPending ? (
          <span style={{
            fontSize: '9px', padding: '2px 8px', fontWeight: 700,
            background: 'rgba(115,128,145,0.12)', color: '#738091',
            display: 'inline-flex', alignItems: 'center', gap: '4px',
            letterSpacing: '0.5px', borderRadius: '4px',
          }}>
            <Loader2 size={10} className="animate-spin" />
            CHECKING
          </span>
        ) : stmt.verdict ? (
          <VerdictBadge verdict={stmt.verdict} />
        ) : null}
        <span style={{
          fontSize: '9px', padding: '2px 6px', fontWeight: 600,
          background: 'rgba(45,114,210,0.1)', color: '#4C90F0',
          borderRadius: '4px', letterSpacing: '0.3px',
        }}>
          CUSTOM
        </span>
        <span style={{ marginLeft: 'auto', fontSize: '10px', color: 'var(--text-muted)' }}>
          {formatTimeAgo(stmt.created_at)}
        </span>
      </div>

      <div style={{
        fontSize: '12px', fontWeight: 500, lineHeight: 1.4,
        overflow: 'hidden', display: '-webkit-box',
        WebkitLineClamp: expanded ? 'unset' : 2, WebkitBoxOrient: 'vertical' as const,
        color: 'var(--text-primary)',
      }}>
        {stmt.statement}
      </div>

      {expanded && stmt.verdict_summary && (
        <div style={{ marginTop: '8px', borderTop: '1px solid var(--border-subtle)', paddingTop: '8px' }}>
          <div style={{ fontSize: '11px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
            {stmt.verdict_summary}
          </div>
          {stmt.key_finding && (
            <div style={{
              fontSize: '10px', padding: '6px 8px', marginTop: '6px',
              borderLeft: `2px solid ${config?.color || '#738091'}`, background: config?.bg || 'rgba(115,128,145,0.08)',
              color: 'var(--text-secondary)', lineHeight: 1.4, borderRadius: '4px',
            }}>
              {stmt.key_finding}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function PendingStoryCard({ req }: { req: PendingStoryRequest }) {
  return (
    <div
      style={{
        padding: '10px 12px',
        borderBottom: '1px solid var(--border-subtle)',
        borderLeft: '3px solid #738091',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap', marginBottom: '6px' }}>
        <span style={{
          fontSize: '9px', padding: '2px 8px', fontWeight: 700,
          background: 'rgba(115,128,145,0.12)', color: '#738091',
          display: 'inline-flex', alignItems: 'center', gap: '4px',
          letterSpacing: '0.5px', borderRadius: '4px',
        }}>
          <Loader2 size={10} className="animate-spin" />
          CHECKING
        </span>
        {req.story_source && (
          <span style={{ fontSize: '9px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.3px' }}>
            {req.story_source}
          </span>
        )}
        <span style={{ marginLeft: 'auto', fontSize: '10px', color: 'var(--text-muted)' }}>
          {formatTimeAgo(req.created_at)}
        </span>
      </div>

      <div style={{
        fontSize: '12px', fontWeight: 500, lineHeight: 1.4,
        overflow: 'hidden', display: '-webkit-box',
        WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' as const,
        color: 'var(--text-primary)',
      }}>
        {req.story_title || 'Untitled Story'}
      </div>

      {req.request_count > 1 && (
        <div style={{ fontSize: '9px', color: 'var(--text-muted)', marginTop: '4px' }}>
          {req.request_count} users requested
        </div>
      )}
    </div>
  );
}

function StatementInput({ remaining }: { remaining: number }) {
  const [value, setValue] = useState('');
  const submitMutation = useSubmitStatement();
  const canSubmit = value.trim().length >= 10 && remaining > 0 && !submitMutation.isPending;

  const handleSubmit = () => {
    if (!canSubmit) return;
    submitMutation.mutate(value.trim(), {
      onSuccess: () => setValue(''),
    });
  };

  return (
    <div style={{
      padding: '8px 10px',
      borderBottom: '1px solid var(--border-subtle)',
      background: 'var(--bg-surface, #111113)',
    }}>
      <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
        <input
          type="text"
          value={value}
          onChange={e => setValue(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') handleSubmit(); }}
          placeholder="Enter a statement to fact-check..."
          disabled={remaining <= 0}
          style={{
            flex: 1, padding: '6px 10px', fontSize: '11px',
            background: 'var(--bg-elevated, #18181b)',
            border: '1px solid var(--border-subtle, #27272a)',
            borderRadius: '4px', color: 'var(--text-primary, #fafafa)',
            outline: 'none',
          }}
        />
        <button
          onClick={handleSubmit}
          disabled={!canSubmit}
          style={{
            padding: '6px 12px', fontSize: '10px', fontWeight: 600,
            background: canSubmit ? 'rgba(45,114,210,0.15)' : 'transparent',
            border: `1px solid ${canSubmit ? 'rgba(45,114,210,0.3)' : 'var(--border-subtle)'}`,
            borderRadius: '4px',
            color: canSubmit ? '#4C90F0' : 'var(--text-disabled, #52525b)',
            cursor: canSubmit ? 'pointer' : 'default',
            display: 'flex', alignItems: 'center', gap: '4px',
            textTransform: 'uppercase', letterSpacing: '0.04em',
          }}
        >
          {submitMutation.isPending ? <Loader2 size={10} className="animate-spin" /> : <Send size={10} />}
          Check
        </button>
      </div>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginTop: '4px', fontSize: '9px', color: 'var(--text-muted, #71717a)',
      }}>
        <span>{remaining}/{MONTHLY_LIMIT} remaining this month</span>
        {submitMutation.isError && (
          <span style={{ color: '#CD4246' }}>
            {(submitMutation.error as any)?.response?.status === 429
              ? 'Monthly limit reached'
              : 'Failed to submit'}
          </span>
        )}
      </div>
    </div>
  );
}

export const FactCheckWidget = memo(function FactCheckWidget() {
  const { isAuthenticated, isGuest } = useAuthStore();
  const isSignedIn = isAuthenticated && !isGuest;

  const { data: results, isLoading: resultsLoading, error: resultsError, refetch } = useFactCheckResults({ limit: 20, hours: 720 });
  const { data: statements } = useUserStatements();
  const { data: pendingRequests } = useMyStoryRequests();

  if (resultsLoading) {
    return (
      <Widget id="fact-check">
        <WidgetSkeleton />
      </Widget>
    );
  }

  if (resultsError) {
    return (
      <Widget id="fact-check">
        <WidgetError message="Failed to load fact-checks" onRetry={() => refetch()} />
      </Widget>
    );
  }

  const storyResults = results || [];
  const userStatements = statements || [];
  const storyPending = pendingRequests || [];

  // Count this month's usage (both story requests + custom statements, matching backend quota)
  const monthStart = new Date();
  monthStart.setDate(1);
  monthStart.setHours(0, 0, 0, 0);
  const statementsThisMonth = userStatements.filter(s => new Date(s.created_at) >= monthStart).length;
  const storyRequestsThisMonth = storyPending.filter(r => new Date(r.created_at) >= monthStart).length;
  const completedRequestsThisMonth = storyResults.filter(r => new Date(r.checked_at) >= monthStart).length;
  const monthlyUsed = statementsThisMonth + storyRequestsThisMonth + completedRequestsThisMonth;
  const remaining = Math.max(0, MONTHLY_LIMIT - monthlyUsed);

  const totalCount = storyResults.length + userStatements.length + storyPending.length;
  const falseCount = storyResults.filter(r => r.verdict === 'false' || r.verdict === 'misleading').length;

  return (
    <Widget
      id="fact-check"
      badge={totalCount > 0 ? (falseCount > 0 ? `${falseCount} flagged` : `${totalCount}`) : undefined}
    >
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        {isSignedIn && <StatementInput remaining={remaining} />}

        <div style={{ flex: 1, overflowY: 'auto' }}>
          {/* Pending story requests first */}
          {storyPending.map(req => (
            <PendingStoryCard key={`pending-${req.story_id}`} req={req} />
          ))}

          {/* Custom statements */}
          {userStatements.map(stmt => (
            <StatementCard key={stmt.id} stmt={stmt} />
          ))}

          {/* Completed story-based results */}
          {storyResults.map(result => (
            <FactCheckCard key={result.id} result={result} />
          ))}

          {totalCount === 0 && (
            <div style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
              padding: '32px 16px', color: 'var(--text-muted)',
              textAlign: 'center', fontSize: '11px', gap: '8px',
            }}>
              <HelpCircle size={20} style={{ opacity: 0.4 }} />
              {isSignedIn
                ? 'No fact-checks yet. Submit a statement above or request one from the live feed!'
                : 'Sign in to submit custom fact-check requests.'}
            </div>
          )}
        </div>
      </div>
    </Widget>
  );
});
