import { useQuery } from '@tanstack/react-query';
import { getNepalDebtClock, type DebtClockSummary } from '../debtClock';

export const debtClockKeys = {
  all: ['debt-clock'] as const,
  nepal: () => [...debtClockKeys.all, 'nepal'] as const,
};

export function useNepalDebtClock() {
  return useQuery<DebtClockSummary>({
    queryKey: debtClockKeys.nepal(),
    queryFn: getNepalDebtClock,
    staleTime: 15 * 60 * 1000,
    refetchInterval: 30 * 60 * 1000,
  });
}
