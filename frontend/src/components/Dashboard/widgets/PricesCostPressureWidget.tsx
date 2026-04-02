import { memo } from 'react';
import { CandlestickChart } from 'lucide-react';
import { EconomySectionWidget } from './EconomySectionWidget';

export const PricesCostPressureWidget = memo(function PricesCostPressureWidget() {
  return <EconomySectionWidget widgetId="prices-cost-pressure" sectionKey="prices_cost_pressure" icon={<CandlestickChart size={14} />} />;
});

