import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { getNepalDebtClock, type DebtClockSummary } from '../debtClock';

export const debtClockKeys = {
  all: ['debt-clock'] as const,
  nepal: () => [...debtClockKeys.all, 'nepal', 'v4'] as const,
};

export function useNepalDebtClock() {
  return useQuery<DebtClockSummary>({
    queryKey: debtClockKeys.nepal(),
    queryFn: getNepalDebtClock,
    staleTime: 5 * 60 * 1000,
    gcTime: 30 * 60 * 1000,
    placeholderData: keepPreviousData,
    refetchInterval: 15 * 60 * 1000,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  });
}
