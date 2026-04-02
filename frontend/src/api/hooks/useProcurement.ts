import { keepPreviousData, useQuery } from '@tanstack/react-query';
import {
  getProcurementContracts,
  getProcurementEntityBuckets,
  getProcurementStats,
  getProcurementTopEntities,
  getProcurementWidgetSummary,
  type ProcurementContractListResponse,
  type ProcurementEntityBucketStats,
  type ProcurementListParams,
  type ProcurementStatsResponse,
  type ProcurementTopEntity,
  type ProcurementWidgetSummaryResponse,
} from '../procurement';

export const procurementKeys = {
  all: ['procurement'] as const,
  contracts: (params: ProcurementListParams) => [...procurementKeys.all, 'contracts', params] as const,
  stats: () => [...procurementKeys.all, 'stats'] as const,
  buckets: () => [...procurementKeys.all, 'buckets'] as const,
  topEntities: (entityBucket?: string) => [...procurementKeys.all, 'top-entities', entityBucket || 'all'] as const,
  widgetSummary: (params: ProcurementListParams) => [...procurementKeys.all, 'widget-summary', params] as const,
};

export function useProcurementContracts(params: ProcurementListParams) {
  return useQuery<ProcurementContractListResponse>({
    queryKey: procurementKeys.contracts(params),
    queryFn: () => getProcurementContracts(params),
    staleTime: 10 * 60 * 1000,
    gcTime: 30 * 60 * 1000,
    placeholderData: keepPreviousData,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  });
}

export function useProcurementStats() {
  return useQuery<ProcurementStatsResponse>({
    queryKey: procurementKeys.stats(),
    queryFn: getProcurementStats,
    staleTime: 15 * 60 * 1000,
    gcTime: 30 * 60 * 1000,
    placeholderData: keepPreviousData,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  });
}

export function useProcurementEntityBuckets() {
  return useQuery<ProcurementEntityBucketStats[]>({
    queryKey: procurementKeys.buckets(),
    queryFn: getProcurementEntityBuckets,
    staleTime: 15 * 60 * 1000,
    gcTime: 30 * 60 * 1000,
    placeholderData: keepPreviousData,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  });
}

export function useProcurementTopEntities(entityBucket?: string) {
  return useQuery<ProcurementTopEntity[]>({
    queryKey: procurementKeys.topEntities(entityBucket),
    queryFn: () =>
      getProcurementTopEntities({
        limit: 5,
        ...(entityBucket && entityBucket !== 'all' ? { entity_bucket: entityBucket } : {}),
      }),
    staleTime: 15 * 60 * 1000,
    gcTime: 30 * 60 * 1000,
    placeholderData: keepPreviousData,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  });
}

export function useProcurementWidgetSummary(params: ProcurementListParams) {
  return useQuery<ProcurementWidgetSummaryResponse>({
    queryKey: procurementKeys.widgetSummary(params),
    queryFn: () => getProcurementWidgetSummary(params),
    staleTime: 15 * 60 * 1000,
    gcTime: 30 * 60 * 1000,
    placeholderData: keepPreviousData,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  });
}
