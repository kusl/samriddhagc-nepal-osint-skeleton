import type { QueryClient } from '@tanstack/react-query';

import apiClient from './client';
import { kpiKeys } from './hooks/useKPI';
import { situationMonitorKeys } from './hooks/useSituationMonitor';
import { marketKeys } from './hooks/useMarket';
import { debtClockKeys } from './hooks/useDebtClock';
import { economyKeys } from './hooks/useEconomy';
import { govtDecisionKeys } from './hooks/useGovtDecisions';
import { cabinetActionKeys } from './hooks/useCabinetActions';
import { parliamentKeys } from './hooks/useParliament';
import { promiseKeys } from './hooks/usePromises';

export type DashboardBootstrapPreset = 'news' | 'economy' | 'parliament' | 'intelligence';

export interface DashboardBootstrapResponse {
  preset: DashboardBootstrapPreset;
  generated_at: string;
  queries: Record<string, unknown>;
}

export async function getDashboardBootstrap(
  preset: DashboardBootstrapPreset,
): Promise<DashboardBootstrapResponse> {
  const response = await apiClient.get<DashboardBootstrapResponse>('/dashboard/bootstrap', {
    params: { preset },
  });
  return response.data;
}

export function hydrateDashboardBootstrap(
  queryClient: QueryClient,
  payload: DashboardBootstrapResponse,
) {
  const queries = payload.queries ?? {};

  if (queries.kpi_snapshot_24h !== undefined) {
    queryClient.setQueryData(kpiKeys.snapshot(24, undefined), queries.kpi_snapshot_24h);
  }

  if (queries.kpi_hourly_trends_24h !== undefined) {
    queryClient.setQueryData(kpiKeys.hourlyTrends(24, undefined), queries.kpi_hourly_trends_24h);
  }

  if (queries.developing_stories !== undefined) {
    queryClient.setQueryData(
      situationMonitorKeys.developingStories({ hours: 72, limit: 15 }),
      queries.developing_stories,
    );
  }

  if (queries.province_anomalies_latest !== undefined) {
    queryClient.setQueryData(
      situationMonitorKeys.provinceAnomalies(),
      queries.province_anomalies_latest,
    );
  }

  if (queries.market_summary !== undefined) {
    queryClient.setQueryData(marketKeys.summary(), queries.market_summary);
  }

  if (queries.debt_clock_nepal !== undefined) {
    queryClient.setQueryData(debtClockKeys.nepal(), queries.debt_clock_nepal);
  }

  if (queries.economy_snapshot !== undefined) {
    queryClient.setQueryData(economyKeys.snapshot(), queries.economy_snapshot);
  }

  if (queries.govt_decisions_latest !== undefined) {
    queryClient.setQueryData(govtDecisionKeys.latest(25, false), queries.govt_decisions_latest);
    queryClient.setQueryData(govtDecisionKeys.archive(25, false), {
      pageParams: [null],
      pages: [queries.govt_decisions_latest],
    });
  }

  if (queries.cabinet_actions_summary !== undefined) {
    queryClient.setQueryData(cabinetActionKeys.summary(), queries.cabinet_actions_summary);
  }

  if (queries.promises_summary_rsp_2082 !== undefined) {
    queryClient.setQueryData(
      promiseKeys.summary('RSP', '2082'),
      queries.promises_summary_rsp_2082,
    );
  }

  if (queries.parliament_bills_page_1 !== undefined) {
    queryClient.setQueryData(
      parliamentKeys.bills({
        page: 1,
        per_page: 50,
        status: null,
        bill_type: null,
        chamber: null,
      }),
      queries.parliament_bills_page_1,
    );
  }

  if (queries.verbatim_summary !== undefined) {
    queryClient.setQueryData(parliamentKeys.verbatimSummary(), queries.verbatim_summary);
  }
}
