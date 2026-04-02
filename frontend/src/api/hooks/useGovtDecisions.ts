import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { getLatestGovtDecisions, type GovtDecisionPublicPage } from '../govtDecisions';

export const govtDecisionKeys = {
  all: ['govt-decisions'] as const,
  latest: (limit: number, dedupe: boolean) => [...govtDecisionKeys.all, 'latest', limit, dedupe] as const,
  archive: (limit: number, dedupe: boolean) => [...govtDecisionKeys.all, 'archive', limit, dedupe] as const,
};

export function useLatestGovtDecisions(limit: number = 100, dedupe: boolean = false) {
  return useQuery<GovtDecisionPublicPage>({
    queryKey: govtDecisionKeys.latest(limit, dedupe),
    queryFn: () => getLatestGovtDecisions({ limit, dedupe }),
    staleTime: 5 * 60 * 1000,
    refetchInterval: 10 * 60 * 1000,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  });
}

export function useGovtDecisionArchive(limit: number = 25, dedupe: boolean = false) {
  return useInfiniteQuery<GovtDecisionPublicPage>({
    queryKey: govtDecisionKeys.archive(limit, dedupe),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => getLatestGovtDecisions({ limit, dedupe, cursor: pageParam as string | null }),
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    staleTime: 5 * 60 * 1000,
    refetchInterval: 10 * 60 * 1000,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  });
}
