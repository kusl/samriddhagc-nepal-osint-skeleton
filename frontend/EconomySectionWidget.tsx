import { memo, type ReactNode } from 'react';
import { RefreshCw } from 'lucide-react';
import { Widget } from '../Widget';
import { useEconomySnapshot } from '../../../api/hooks';
import { useSettingsStore } from '../../../store/slices/settingsSlice';
import { buildNprDisplay, formatUsdCompact, formatUsdFull } from '../../../utils/currency';
import { WidgetEmpty, WidgetError, WidgetSkeleton } from './shared';

function getMetricDisplay(
  unit: string,
  rawValue: number | null,
  displayValue: string,
  system: 'vedic' | 'international',
): { text: string; title?: string } {
  if (rawValue == null || Number.isNaN(rawValue)) {
    return { text: displayValue };
  }

  if (unit === 'npr_million' || unit === 'npr_million_signed') {
    const nprValue = rawValue * 1_000_000;
    const display = buildNprDisplay(nprValue, { system });
    return { text: display.text, title: display.title };
  }

  if (unit === 'usd_million') {
    const usdValue = rawValue * 1_000_000;
    return {
      text: formatUsdCompact(usdValue),
      title: formatUsdFull(usdValue, 0),
    };
  }

  return { text: displayValue };
}

function EconomySectionWidgetImpl({
  widgetId,
  sectionKey,
  icon,
}: {
  widgetId: string;
  sectionKey: string;
  icon: ReactNode;
}) {
  const { data, isLoading, isError, refetch } = useEconomySnapshot();
  const { nprNumberingSystem } = useSettingsStore();
  const section = data?.sections?.[sectionKey];

  return (
    <Widget
      id={widgetId}
      icon={icon}
      badge={section?.badge || 'NRB'}
      actions={
        <button className="widget-action" title="Refresh economy snapshot" onClick={() => refetch()}>
          <RefreshCw size={12} />
        </button>
      }
    >
      {isLoading ? (
        <WidgetSkeleton />
      ) : isError ? (
        <WidgetError message="Failed to load economy snapshot" onRetry={() => refetch()} />
      ) : !section ? (
        <WidgetEmpty message="No economy data available" />
      ) : (
        <div
          style={{
            height: '100%',
            background: 'var(--bg-surface)',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
              gridAutoRows: '1fr',
              gap: 1,
              background: 'var(--border-subtle)',
            }}
          >
            {section.metrics.map((metric) => {
              const valueDisplay = getMetricDisplay(
                metric.unit,
                metric.raw_value,
                metric.display_value,
                nprNumberingSystem,
              );

              return (
                <div
                  key={metric.key}
                  style={{
                    background: 'var(--bg-surface)',
                    padding: '12px',
                    minHeight: 90,
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                  }}
                >
                  <div>
                    <div
                      style={{
                        fontSize: 9,
                        color: 'var(--text-muted)',
                        textTransform: 'uppercase',
                        letterSpacing: '0.08em',
                        marginBottom: 8,
                      }}
                    >
                      {metric.label}
                    </div>
                    <div
                      title={valueDisplay.title}
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: 18,
                        lineHeight: 1.12,
                        color: 'var(--text-primary)',
                        marginBottom: 8,
                        wordBreak: 'break-word',
                      }}
                    >
                      {valueDisplay.text}
                    </div>
                  </div>
                  <div
                    style={{
                      fontSize: 9,
                      color: 'var(--text-disabled)',
                      lineHeight: 1.35,
                      display: '-webkit-box',
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: 'vertical',
                      overflow: 'hidden',
                    }}
                  >
                    {metric.meta}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </Widget>
  );
}

export const EconomySectionWidget = memo(EconomySectionWidgetImpl);
