import { memo } from 'react';
import { Ship } from 'lucide-react';
import { EconomySectionWidget } from './EconomySectionWidget';

export const ExternalSectorWidget = memo(function ExternalSectorWidget() {
  return <EconomySectionWidget widgetId="external-sector" sectionKey="external_sector" icon={<Ship size={14} />} />;
});

