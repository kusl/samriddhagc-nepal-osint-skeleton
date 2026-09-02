// Dashboard bootstrap client.
//
// Reconstructed 2026-09-01: this module is imported by components/Dashboard/
// Dashboard.tsx but was never committed to the repo (the sanitized VPS sync
// dropped it), so the dev server could not resolve the import and the whole
// app failed to mount. Backend contract: app/api/v1/dashboard.py.
//
// The endpoint returns the above-the-fold dataset for a preset in one round
// trip; hydrating it into the react-query cache lets the dashboard widgets
// render immediately instead of each firing its own request on mount.
import type { QueryClient } from '@tanstack/react-query';

import apiClient from './client';
import { kpiKeys } from './hooks/useKPI';
import { situationMonitorKeys } from './hooks/useSituationMonitor';
import { marketKeys } from './hooks/useMarket';
import { debtClockKeys } from './hooks/useDebtClock';
import { economyKeys } from './hooks/useEconomy';
import { govtDecisionKeys } from './hooks/useGovtDecisions';
import { cabinetActionKeys } from './hooks/useCabinetActions';

export type DashboardBootstrapPreset = 'news' | 'economy' | 'parliament' | 'intelligence';

export interface DashboardBootstrapResponse {
  preset: DashboardBootstrapPreset;
  generated_at: string;
  queries: Record<string, unknown>;
}

/** Fetch the one-shot above-the-fold payload for a dashboard preset. */
export const getDashboardBootstrap = async (
  preset: DashboardBootstrapPreset = 'news',
): Promise<DashboardBootstrapResponse> => {
  const response = await apiClient.get('/dashboard/bootstrap', { params: { preset } });
  return response.data;
};

// Maps each key the backend puts in `queries` to the react-query key the
// corresponding hook reads. The arguments here must match the hook call sites
// exactly, since a react-query key is compared structurally — a mismatch is
// harmless (the widget just fetches normally) but wins nothing.
const BOOTSTRAP_KEY_MAP: Record<string, readonly unknown[]> = {
  // dashboard.py: get_kpi_snapshot(hours=24, districts=None)
  kpi_snapshot_24h: kpiKeys.snapshot(24, undefined),
  // dashboard.py: get_hourly_trends(hours=24, districts=None)
  kpi_hourly_trends_24h: kpiKeys.hourlyTrends(24, undefined),
  // dashboard.py: get_developing_stories(hours=72, limit=15, category=None)
  developing_stories: situationMonitorKeys.developingStories({ hours: 72, limit: 15 }),
  province_anomalies_latest: situationMonitorKeys.provinceAnomalies(),
  market_summary: marketKeys.summary(),
  debt_clock_nepal: debtClockKeys.nepal(),
  economy_snapshot: economyKeys.snapshot(),
  // dashboard.py: get_latest_govt_decisions(limit=25, dedupe=False)
  govt_decisions_latest: govtDecisionKeys.latest(25, false),
  cabinet_actions_summary: cabinetActionKeys.summary(),
  // promises_summary_rsp_2082, parliament_bills_page_1 and verbatim_summary are
  // returned by the endpoint but intentionally left unmapped: their hooks are
  // not exported with a stable key factory, so those widgets fetch as usual.
};

/**
 * Seed the react-query cache from a bootstrap payload.
 *
 * Purely an optimisation — anything not mapped, or absent from the payload, is
 * fetched by its own hook on mount as before.
 */
export const hydrateDashboardBootstrap = (
  queryClient: QueryClient,
  payload: DashboardBootstrapResponse | null | undefined,
): void => {
  if (!payload?.queries) return;

  for (const [name, data] of Object.entries(payload.queries)) {
    if (data === null || data === undefined) continue;
    const queryKey = BOOTSTRAP_KEY_MAP[name];
    if (!queryKey) continue;
    queryClient.setQueryData(queryKey, data);
  }
};

export default getDashboardBootstrap;
