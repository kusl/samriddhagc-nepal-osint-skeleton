import { memo } from 'react';
import { RefreshCw, TrendingUp, Fuel } from 'lucide-react';
import { useMarketSummary } from '../../../api/hooks';
import { Widget } from '../Widget';

export const MarketWidget = memo(function MarketWidget() {
  const { data, isLoading, error } = useMarketSummary();

  const formatValue = (value: number, unit: string): string => {
    if (unit === 'points') {
      return value.toLocaleString('en-NP', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    if (unit === 'NPR') {
      return value.toFixed(2);
    }
    if (unit === 'NPR/tola') {
      return `NRS ${value.toLocaleString('en-NP', { maximumFractionDigits: 0 })}`;
    }
    if (unit === 'NPR/litre') {
      return `NRS ${value.toFixed(2)}`;
    }
    return value.toString();
  };

  const formatChange = (change: number): string => {
    const prefix = change >= 0 ? '+' : '';
    return `${prefix}${change.toFixed(2)}%`;
  };

  const indicators = data ? [
    { label: 'NEPSE', value: data.nepse ? formatValue(data.nepse.value, data.nepse.unit) : '--', change: data.nepse ? formatChange(data.nepse.change) : '--', up: (data.nepse?.change ?? 0) >= 0 },
    {
      label: 'USD/NPR',
      value: data.usd_npr ? formatValue(data.usd_npr.value, data.usd_npr.unit) : '--',
      change: data.usd_npr ? formatChange(data.usd_npr.change) : '--',
      up: (data.usd_npr?.change ?? 0) >= 0,
      sublabel: data.usd_npr?.data_date
        ? `NRB forex · ${new Date(data.usd_npr.data_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`
        : 'NRB forex',
    },
    { label: 'Gold/Tola', value: data.gold ? formatValue(data.gold.value, data.gold.unit) : '--', change: data.gold ? formatChange(data.gold.change) : '--', up: (data.gold?.change ?? 0) >= 0 },
    { label: 'Silver/Tola', value: data.silver ? formatValue(data.silver.value, data.silver.unit) : '--', change: data.silver ? formatChange(data.silver.change) : '--', up: (data.silver?.change ?? 0) >= 0 },
    {
      label: 'Petrol/L',
      value: data.petrol ? formatValue(data.petrol.value, 'NPR/litre') : '--',
      change: data.petrol ? formatChange(data.petrol.change) : '--',
      up: (data.petrol?.change ?? 0) >= 0,
      icon: <Fuel size={10} />,
      sublabel: data.petrol?.data_date
        ? `NOC · ${new Date(data.petrol.data_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`
        : 'Nepal Oil Corporation',
    },
    {
      label: 'Diesel/L',
      value: data.diesel ? formatValue(data.diesel.value, 'NPR/litre') : '--',
      change: data.diesel ? formatChange(data.diesel.change) : '--',
      up: (data.diesel?.change ?? 0) >= 0,
      icon: <Fuel size={10} />,
      sublabel: data.diesel?.data_date
        ? `NOC · ${new Date(data.diesel.data_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`
        : 'Nepal Oil Corporation',
    },
  ] : [];

  if (isLoading) {
    return (
      <Widget id="market" icon={<TrendingUp size={14} />}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)' }}>
          <RefreshCw size={16} style={{ animation: 'spin 1s linear infinite' }} />
          <span style={{ marginLeft: '8px', fontSize: '12px' }}>Loading market data...</span>
        </div>
      </Widget>
    );
  }

  if (error) {
    return (
      <Widget id="market" icon={<TrendingUp size={14} />}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--status-critical)', fontSize: '12px' }}>
          Failed to load market data
        </div>
      </Widget>
    );
  }

  return (
    <Widget id="market" icon={<TrendingUp size={14} />}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1px', background: 'var(--border-subtle)', height: '100%' }}>
        {indicators.map((m, i) => (
          <div key={i} style={{ background: 'var(--bg-surface)', padding: '10px' }}>
            <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px', display: 'flex', alignItems: 'center', gap: '4px' }}>
              {m.label}
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '16px', fontWeight: 600 }}>{m.value}</div>
            {m.sublabel ? (
              <div style={{ fontSize: '9px', color: 'var(--text-muted)', marginTop: '4px', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                {m.sublabel}
              </div>
            ) : null}
            <div style={{ fontSize: '10px', color: m.up ? 'var(--status-low)' : 'var(--status-critical)', marginTop: m.sublabel ? '2px' : '4px' }}>{m.change}</div>
          </div>
        ))}
      </div>
      {data?.updated_at && (
        <div style={{ fontSize: '9px', color: 'var(--text-muted)', padding: '4px 8px', textAlign: 'right', borderTop: '1px solid var(--border-subtle)' }}>
          Updated: {new Date(data.updated_at).toLocaleTimeString()}
        </div>
      )}
    </Widget>
  );
});
