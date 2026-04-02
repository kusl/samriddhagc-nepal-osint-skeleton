import { memo } from 'react';
import { CircleDollarSign } from 'lucide-react';
import { EconomySectionWidget } from './EconomySectionWidget';

export const MonetaryConditionsWidget = memo(function MonetaryConditionsWidget() {
  return <EconomySectionWidget widgetId="monetary-conditions" sectionKey="monetary_conditions" icon={<CircleDollarSign size={14} />} />;
});

