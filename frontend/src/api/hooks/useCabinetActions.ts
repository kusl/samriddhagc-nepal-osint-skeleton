import { useQuery } from '@tanstack/react-query';
import {
  getCabinetActionItem,
  getCabinetActionItems,
  getCabinetActionSummary,
  type CabinetActionListParams,
  type CabinetActionPublicItem,
  type CabinetActionSummary,
} from '../cabinetActions';

export const cabinetActionKeys = {
  all: ['cabinet-actions'] as const,
  summary: () => [...cabinetActionKeys.all, 'summary'] as const,
  list: (params: CabinetActionListParams) => [...cabinetActionKeys.all, 'list', params] as const,
  detail: (itemId: string) => [...cabinetActionKeys.all, 'detail', itemId] as const,
};

export function useCabinetActionSummary() {
  return useQuery<CabinetActionSummary>({
    queryKey: cabinetActionKeys.summary(),
    queryFn: getCabinetActionSummary,
    staleTime: 5 * 60 * 1000,
    refetchInterval: 10 * 60 * 1000,
  });
}

export function useCabinetActionItems(params: CabinetActionListParams = {}) {
  return useQuery<{ items: CabinetActionPublicItem[] }>({
    queryKey: cabinetActionKeys.list(params),
    queryFn: () => getCabinetActionItems(params),
    staleTime: 5 * 60 * 1000,
    refetchInterval: 10 * 60 * 1000,
  });
}

export function useCabinetActionDetail(itemId?: string | null) {
  return useQuery<CabinetActionPublicItem | null>({
    queryKey: cabinetActionKeys.detail(itemId || 'none'),
    queryFn: () => getCabinetActionItem(itemId!),
    enabled: Boolean(itemId),
    staleTime: 5 * 60 * 1000,
  });
}
