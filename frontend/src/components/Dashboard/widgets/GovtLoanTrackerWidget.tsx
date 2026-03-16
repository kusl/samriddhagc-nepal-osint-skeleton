import { memo, useMemo, useState } from 'react';
import { Landmark, ExternalLink } from 'lucide-react';
import { Widget } from '../Widget';

type LoanEntry = {
  id: string;
  government: string;
  lender: string;
  title: string;
  amountLabel: string;
  amountNumeric: number;
  approvedOn: string;
  kind: 'new_loan' | 'legacy_disbursement';
  summary: string;
  sourceLabel: string;
  sourceUrl: string;
};

const VERIFIED_LOANS: LoanEntry[] = [
  {
    id: 'adb-pfm-2025',
    government: 'Karki Govt',
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
    government: 'Karki Govt',
    lender: 'World Bank',
    title: 'Sustainable and Inclusive Finance Project',
    amountLabel: 'US$95M',
    amountNumeric: 95,
    approvedOn: 'Jan 29, 2026',
    kind: 'new_loan',
    summary:
      'Board-approved World Bank financing to expand SME access to finance and strengthen Nepal’s financial inclusion architecture.',
    sourceLabel: 'World Bank Finances One',
    sourceUrl: 'https://financesone.worldbank.org/countries/nepal',
  },
  {
    id: 'wb-digital-2026',
    government: 'Karki Govt',
    lender: 'World Bank',
    title: 'Nepal Digital Transformation Project',
    amountLabel: 'US$50M',
    amountNumeric: 50,
    approvedOn: 'Feb 9, 2026',
    kind: 'new_loan',
    summary:
      'World Bank financing for digital public infrastructure and public-service digitization. The separate ADB co-financing was not yet Board-approved in that announcement.',
    sourceLabel: 'World Bank',
    sourceUrl:
      'https://www.worldbank.org/en/news/press-release/2026/02/09/nepal-world-bank-approves-50-million-digital-transformation-project',
  },
  {
    id: 'imf-ecf-2025',
    government: 'Karki Govt',
    lender: 'IMF',
    title: 'ECF Sixth-Review Disbursement',
    amountLabel: 'US$43.05M',
    amountNumeric: 43.05,
    approvedOn: 'Oct 2, 2025',
    kind: 'legacy_disbursement',
    summary:
      'Disbursement under Nepal’s pre-existing 2022 Extended Credit Facility, not a brand-new sovereign program initiated by the Karki government.',
    sourceLabel: 'IMF',
    sourceUrl:
      'https://www.imf.org/en/news/articles/2025/10/02/pr-25327-nepal-imf-executive-board-completes-the-sixth-review-under-the-ecf-arrangement',
  },
];

function kindLabel(kind: LoanEntry['kind']): string {
  return kind === 'new_loan' ? 'New sovereign loan' : 'Legacy IMF drawdown';
}

function governmentOptions(entries: LoanEntry[]): string[] {
  return ['all', ...Array.from(new Set(entries.map((entry) => entry.government)))];
}

function badgeColors(kind: LoanEntry['kind']) {
  return kind === 'new_loan'
    ? { bg: 'rgba(45,114,210,0.14)', fg: '#2D72D2' }
    : { bg: 'rgba(209,152,11,0.14)', fg: '#D1980B' };
}

export const GovtLoanTrackerWidget = memo(function GovtLoanTrackerWidget() {
  const [selectedGovernment, setSelectedGovernment] = useState<string>('all');

  const govOptions = useMemo(() => governmentOptions(VERIFIED_LOANS), []);
  const filteredLoans = useMemo(
    () =>
      selectedGovernment === 'all'
        ? VERIFIED_LOANS
        : VERIFIED_LOANS.filter((entry) => entry.government === selectedGovernment),
    [selectedGovernment],
  );

  const newLoanTotal = filteredLoans.filter((entry) => entry.kind === 'new_loan').reduce(
    (total, entry) => total + entry.amountNumeric,
    0,
  );
  const legacyDrawdownTotal = filteredLoans.filter((entry) => entry.kind === 'legacy_disbursement').reduce(
    (total, entry) => total + entry.amountNumeric,
    0,
  );
  const totalTracked = newLoanTotal + legacyDrawdownTotal;
  const selectedGovernmentLabel = selectedGovernment === 'all' ? 'All govts' : selectedGovernment;

  return (
    <Widget id="govt-loan-tracker" icon={<Landmark size={14} />} badge={filteredLoans.length}>
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div
          style={{
            padding: '8px 12px',
            borderBottom: '1px solid var(--border-subtle)',
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: 1,
            background: 'var(--border-subtle)',
          }}
        >
          <div style={{ background: 'var(--bg-surface)', padding: '8px 10px' }}>
            <div style={{ fontSize: 9, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Total loans
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', marginTop: 4 }}>
              US${totalTracked.toFixed(2)}M
            </div>
            <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 2 }}>{selectedGovernmentLabel}</div>
          </div>
          <div style={{ background: 'var(--bg-surface)', padding: '8px 10px' }}>
            <div style={{ fontSize: 9, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              New sovereign loans
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', marginTop: 4 }}>
              US${newLoanTotal.toFixed(2)}M
            </div>
            <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 2 }}>{filteredLoans.filter((entry) => entry.kind === 'new_loan').length} approved facilities</div>
          </div>
          <div style={{ background: 'var(--bg-surface)', padding: '8px 10px' }}>
            <div style={{ fontSize: 9, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              IMF drawdown
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', marginTop: 4 }}>
              US${legacyDrawdownTotal.toFixed(2)}M
            </div>
            <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 2 }}>older ECF arrangement</div>
          </div>
        </div>

        <div
          style={{
            padding: '6px 12px',
            borderBottom: '1px solid var(--border-subtle)',
            display: 'grid',
            gridTemplateColumns: '110px 82px 84px 1fr auto',
            gap: 8,
            alignItems: 'center',
            fontSize: 8,
            fontWeight: 700,
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
            color: 'var(--text-muted)',
            background: 'var(--bg-elevated)',
          }}
        >
          <span>Government</span>
          <span>Lender</span>
          <span>Amount</span>
          <span>Facility</span>
          <select
            value={selectedGovernment}
            onChange={(event) => setSelectedGovernment(event.target.value)}
            aria-label="Filter loans by government"
            style={{
              padding: '4px 8px',
              fontSize: 10,
              fontFamily: 'var(--font-sans)',
              background: 'var(--bg-surface)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 4,
              cursor: 'pointer',
              minHeight: 24,
              minWidth: 120,
              justifySelf: 'end',
            }}
          >
            {govOptions.map((option) => (
              <option key={option} value={option}>
                {option === 'all' ? 'All Govts' : option}
              </option>
            ))}
          </select>
        </div>

        <div style={{ flex: 1, overflow: 'auto' }}>
          {filteredLoans.map((entry) => {
            const colors = badgeColors(entry.kind);
            return (
              <div
                key={entry.id}
                style={{
                  padding: '9px 12px',
                  borderBottom: '1px solid var(--border-subtle)',
                  display: 'grid',
                  gridTemplateColumns: '110px 82px 84px 1fr',
                  gap: 8,
                  alignItems: 'start',
                }}
              >
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <span
                    style={{
                      fontSize: 8,
                      fontWeight: 700,
                      textTransform: 'uppercase',
                      letterSpacing: '0.04em',
                      padding: '1px 5px',
                      background: colors.bg,
                      color: colors.fg,
                      width: 'fit-content',
                    }}
                  >
                    {entry.government}
                  </span>
                  <span style={{ fontSize: 8, color: 'var(--text-disabled)', lineHeight: 1.4 }}>
                    {kindLabel(entry.kind)}
                  </span>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                  <span style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-primary)' }}>{entry.lender}</span>
                  <span style={{ fontSize: 8, color: 'var(--text-disabled)' }}>{entry.approvedOn}</span>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                  <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>
                    {entry.amountLabel}
                  </span>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-primary)', lineHeight: 1.45 }}>
                    {entry.title}
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--text-muted)', lineHeight: 1.5 }}>
                    {entry.summary}
                  </div>
                  <a
                    href={entry.sourceUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 4,
                      width: 'fit-content',
                      fontSize: 9,
                      color: 'var(--accent-primary)',
                      textDecoration: 'none',
                    }}
                  >
                    {entry.sourceLabel} <ExternalLink size={8} />
                  </a>
                </div>
              </div>
            );
          })}
        </div>

      </div>
    </Widget>
  );
});
