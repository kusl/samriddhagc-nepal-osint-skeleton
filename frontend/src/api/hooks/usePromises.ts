import { useQuery } from '@tanstack/react-query';

import { getPromiseSummary, type PromiseSummary } from '../promises';

export const promiseKeys = {
  all: ['promises'] as const,
  summary: (party: string, electionYear: string) =>
    [...promiseKeys.all, 'summary', party, electionYear] as const,
};

/**
 * Manifesto promise-tracker summary for PromiseTrackerWidget.
 *
 * Restored 2026-09-01 — the widget imported this hook but it was never
 * committed, which broke the whole `api/hooks` barrel import.
 */
export function usePromiseSummary(party: string = 'RSP', electionYear: string = '2082') {
  return useQuery<PromiseSummary>({
    queryKey: promiseKeys.summary(party, electionYear),
    queryFn: () => getPromiseSummary(party, electionYear),
    staleTime: 5 * 60 * 1000,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  });
}
