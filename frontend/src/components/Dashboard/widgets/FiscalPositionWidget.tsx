import { memo } from 'react';
import { Landmark } from 'lucide-react';
import { EconomySectionWidget } from './EconomySectionWidget';

export const FiscalPositionWidget = memo(function FiscalPositionWidget() {
  return <EconomySectionWidget widgetId="fiscal-position" sectionKey="fiscal_position" icon={<Landmark size={14} />} />;
});

