// Manifesto promise-tracker client.
//
// Restored 2026-09-01: PromiseTrackerWidget imports `usePromiseSummary` from
// api/hooks, but neither the hook nor this client module was committed.
// Backend contract: app/api/v1/promises.py::promise_summary.
import apiClient from './client';

export interface ManifestoPromiseItem {
  promise_id: string;
  category: string;
  promise: string;
  detail: string | null;
  source: string | null;
  status: string;
  status_detail: string | null;
  evidence_urls: string[] | null;
  last_checked_at: string | null;
  status_changed_at: string | null;
}

export interface PromiseSummary {
  total: number;
  by_status: Record<string, number>;
  by_category: Record<string, number>;
  promises: ManifestoPromiseItem[];
}

/** Summary stats + promise list for one party's manifesto in an election year. */
export const getPromiseSummary = async (
  party: string = 'RSP',
  electionYear: string = '2082',
): Promise<PromiseSummary> => {
  const response = await apiClient.get('/promises/summary', {
    params: { party, election_year: electionYear },
  });
  return response.data;
};
