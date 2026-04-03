import { useQuery } from '@tanstack/react-query';
import { getEconomySnapshot, type EconomySnapshot } from '../economy';

export const economyKeys = {
  all: ['economy'] as const,
  snapshot: () => [...economyKeys.all, 'snapshot', 'v1'] as const,
};

export function useEconomySnapshot() {
  return useQuery<EconomySnapshot>({
    queryKey: economyKeys.snapshot(),
    queryFn: getEconomySnapshot,
    staleTime: 30 * 60 * 1000,
    refetchInterval: 60 * 60 * 1000,
    refetchOnWindowFocus: true,
  });
}

