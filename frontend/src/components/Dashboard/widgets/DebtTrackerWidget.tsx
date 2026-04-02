import { memo, useMemo, useState } from 'react';
import { Landmark } from 'lucide-react';
import { Widget } from '../Widget';

type LoanKind = 'new_loan' | 'legacy_disbursement';

type LoanEntry = {
  id: string;
  government: string;
  lender: string;
  title: string;
  amountLabel: string;
  amountNumeric: number;
  approvedOn: string;
  kind: LoanKind;
  summary: string;
  sourceLabel: string;
  sourceUrl: string;
};

const VERIFIED_LOANS: LoanEntry[] = [
  {
    id: 'adb-pfm-2025',
    government: 'Sushila Karki Govt',
    lender: 'ADB',
    title: 'Public Financial Management and Debt Management Policy Loan',
    amountLabel: 'US$100M',
    amountNumeric: 100,
    approvedOn: 'Nov 28, 2025',
    kind: 'new_loan',
    summary:
      'Policy-based sovereign loan focused on expenditure efficiency, fiscal sustainability, and debt management.',
    sourceLabel: 'Kathmandu Post',
    sourceUrl:
      'https://kathmandupost.com/money/2025/11/28/adb-approves-100-million-loan-to-advance-nepal-s-public-financial-management-reforms',
  },
  {
    id: 'wb-sif-2026',
    government: 'Sushila Karki Govt',
    lender: 'World Bank',
    title: 'Sustainable and Inclusive Finance Project',
    amountLabel: 'US$95M',
    amountNumeric: 95,
    approvedOn: 'Jan 29, 2026',
    kind: 'new_loan',
    summary:
      'Board-approved financing to expand SME access to finance and strengthen Nepal’s financial inclusion architecture.',
    sourceLabel: 'World Bank Finances One',
    sourceUrl: 'https://financesone.worldbank.org/countries/nepal',
  },
  {
    id: 'wb-digital-2026',
    government: 'Sushila Karki Govt',
    lender: 'World Bank',
    title: 'Nepal Digital Transformation Project',
    amountLabel: 'US$50M',
    amountNumeric: 50,
    approvedOn: 'Feb 9, 2026',
    kind: 'new_loan',
    summary:
      'Sovereign financing for digital public infrastructure and public-service digitization.',
    sourceLabel: 'World Bank',
    sourceUrl:
      'https://www.worldbank.org/en/news/press-release/2026/02/09/nepal-world-bank-approves-50-million-digital-transformation-project',
  },
  {
    id: 'imf-ecf-2025',
    government: 'Sushila Karki Govt',
    lender: 'IMF',
    title: 'ECF Sixth-Review Disbursement',
    amountLabel: 'US$43.05M',
    amountNumeric: 43.05,
    approvedOn: 'Oct 2, 2025',
    kind: 'legacy_disbursement',
    summary:
      'Disbursement under Nepal’s existing 2022 Extended Credit Facility, not a brand-new sovereign program.',
    sourceLabel: 'IMF',
    sourceUrl:
      'https://www.imf.org/en/news/articles/2025/10/02/pr-25327-nepal-imf-executive-board-completes-the-sixth-review-under-the-ecf-arrangement',
  },
];

function kindLabel(kind: LoanKind): string {
  return kind === 'new_loan' ? 'New sovereign loan' : 'Legacy drawdown';
}

function kindAccent(kind: LoanKind) {
  if (kind === 'new_loan') {
    return {
      fg: '#60a5fa',
      bg: 'rgba(59,130,246,0.14)',
      border: 'rgba(59,130,246,0.22)',
    };
  }
  return {
    fg: '#f59e0b',
    bg: 'rgba(245,158,11,0.12)',
    border: 'rgba(245,158,11,0.22)',
  };
}

function governmentOptions(entries: LoanEntry[]): string[] {
  return ['all', ...Array.from(new Set(entries.map((entry) => entry.government)))];
}

function formatUsdMillions(value: number): string {
  const rounded = Number.isInteger(value) ? value.toFixed(0) : value.toFixed(2).replace(/0+$/, '').replace(/\.$/, '');
  return `$${rounded}M`;
}

function LoanRow({ entry }: { entry: LoanEntry }) {
  const accent = kindAccent(entry.kind);

  return (
    <div
      style={{
        padding: '9px 12px',
        borderBottom: '1px solid var(--border-subtle)',
        display: 'flex',
        flexDirection: 'column',
        gap: 7,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'flex-start' }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginBottom: 5 }}>
            <span
              style={{
                padding: '2px 6px',
                border: '1px solid var(--border-subtle)',
                background: 'rgba(255,255,255,0.04)',
                fontSize: 8,
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
                color: 'var(--text-secondary)',
              }}
            >
              {entry.lender}
            </span>
            <span
              style={{
                padding: '2px 6px',
                border: `1px solid ${accent.border}`,
                background: accent.bg,
                fontSize: 8,
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
                color: accent.fg,
              }}
            >
              {kindLabel(entry.kind)}
            </span>
          </div>
          <div
            style={{
              fontSize: 12,
              fontWeight: 700,
              color: 'var(--text-primary)',
              lineHeight: 1.35,
              marginBottom: 4,
            }}
          >
            {entry.title}
          </div>
          <div
            style={{
              fontSize: 10,
              color: 'var(--text-muted)',
              lineHeight: 1.4,
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
            }}
          >
            {entry.summary}
          </div>
        </div>

        <div style={{ minWidth: 96, textAlign: 'right', flexShrink: 0 }}>
          <div
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 16,
              lineHeight: 1.1,
              fontWeight: 700,
              color: 'var(--text-primary)',
              marginBottom: 3,
            }}
          >
            {entry.amountLabel}
          </div>
          <div style={{ fontSize: 9, color: 'var(--text-disabled)' }}>{entry.approvedOn}</div>
        </div>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', fontSize: 9, color: 'var(--text-disabled)' }}>
          <span>{entry.government}</span>
          <span>•</span>
          <a
            href={entry.sourceUrl}
            target="_blank"
            rel="noreferrer"
            style={{ color: 'var(--accent-primary)', textDecoration: 'none' }}
          >
            {entry.sourceLabel}
          </a>
        </div>
      </div>
    </div>
  );
}

export const DebtTrackerWidget = memo(function DebtTrackerWidget() {
  const [governmentFilter, setGovernmentFilter] = useState<string>('all');

  const governmentFilters = useMemo(() => governmentOptions(VERIFIED_LOANS), []);

  const visibleLoans = useMemo(() => {
    return VERIFIED_LOANS.filter((entry) => governmentFilter === 'all' || entry.government === governmentFilter).sort(
      (a, b) => b.amountNumeric - a.amountNumeric,
    );
  }, [governmentFilter]);

  const trackerSummary = useMemo(() => {
    const newLoans = visibleLoans.filter((entry) => entry.kind === 'new_loan');
    const legacy = visibleLoans.filter((entry) => entry.kind === 'legacy_disbursement');
    return {
      totalCount: visibleLoans.length,
      totalAmount: visibleLoans.reduce((sum, entry) => sum + entry.amountNumeric, 0),
      newLoanAmount: newLoans.reduce((sum, entry) => sum + entry.amountNumeric, 0),
      legacyAmount: legacy.reduce((sum, entry) => sum + entry.amountNumeric, 0),
      legacyCount: legacy.length,
    };
  }, [visibleLoans]);

  return (
    <Widget id="debt-tracker" icon={<Landmark size={14} />} badge="VERIFIED">
      <div
        style={{
          height: '100%',
          border: '1px solid transparent',
          background: 'var(--bg-surface)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            padding: '9px 12px 8px',
            borderBottom: '1px solid var(--border-subtle)',
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'space-between',
            gap: 12,
          }}
        >
          <div style={{ minWidth: 0, flex: 1 }}>
            <div
              style={{
                fontSize: 9,
                color: 'var(--text-muted)',
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
                marginBottom: 3,
              }}
            >
              Debt Tracker
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-primary)', fontWeight: 700 }}>
              Tracked sovereign facilities
            </div>
          </div>
          <div style={{ fontSize: 10, color: 'var(--text-disabled)', fontFamily: 'var(--font-mono)' }}>
            VERIFIED
          </div>
        </div>

        <div
          style={{
            padding: '7px 12px',
            borderBottom: '1px solid var(--border-subtle)',
            display: 'flex',
            gap: 6,
            flexWrap: 'wrap',
          }}
        >
          {governmentFilters.map((option) => {
            const active = option === governmentFilter;
            const label = option === 'all' ? 'All Govts' : option;
            return (
              <button
                key={option}
                onClick={() => setGovernmentFilter(option)}
                style={{
                  border: '1px solid var(--border-subtle)',
                  background: active ? 'rgba(45,114,210,0.16)' : 'rgba(255,255,255,0.03)',
                  color: active ? 'var(--text-primary)' : 'var(--text-muted)',
                  fontSize: 9,
                  textTransform: 'uppercase',
                  letterSpacing: '0.06em',
                  padding: '4px 7px',
                  cursor: 'pointer',
                }}
              >
                {label}
              </button>
            );
          })}
        </div>

        <div
          style={{
            padding: '7px 12px',
            borderBottom: '1px solid var(--border-subtle)',
            display: 'grid',
            gridTemplateColumns: 'repeat(4, minmax(0, 1fr))',
            gap: 6,
          }}
        >
          {[
            { label: 'Total Loans', value: `${trackerSummary.totalCount}`, meta: 'Tracked facilities' },
            { label: 'Total Received', value: formatUsdMillions(trackerSummary.totalAmount), meta: 'During selected period', accent: '#f59e0b' },
            { label: 'New Loans', value: formatUsdMillions(trackerSummary.newLoanAmount), meta: 'Fresh sovereign commitments', accent: '#60a5fa' },
            { label: 'Legacy Draws', value: trackerSummary.legacyCount > 0 ? formatUsdMillions(trackerSummary.legacyAmount) : '$0M', meta: `${trackerSummary.legacyCount} facility${trackerSummary.legacyCount === 1 ? '' : 'ies'}` },
          ].map((item) => (
            <div
              key={item.label}
              style={{
                border: '1px solid var(--border-subtle)',
                background: 'rgba(255,255,255,0.02)',
                padding: '7px 9px',
                minWidth: 0,
              }}
            >
              <div
                style={{
                  fontSize: 8,
                  color: 'var(--text-muted)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.08em',
                  marginBottom: 5,
                }}
              >
                {item.label}
              </div>
              <div
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 16,
                  lineHeight: 1.1,
                  fontWeight: 700,
                  color: item.accent || 'var(--text-primary)',
                  marginBottom: 4,
                  wordBreak: 'break-word',
                }}
              >
                {item.value}
              </div>
              <div style={{ fontSize: 9, color: 'var(--text-disabled)', lineHeight: 1.25 }}>
                {item.meta}
              </div>
            </div>
          ))}
        </div>

        <div style={{ flex: 1, overflow: 'auto' }}>
          {visibleLoans.map((entry) => (
            <LoanRow key={entry.id} entry={entry} />
          ))}
        </div>
      </div>
    </Widget>
  );
});
