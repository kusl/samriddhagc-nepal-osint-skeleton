import apiClient from './client';

export interface ProcurementContract {
  id: string;
  external_id: string;
  ifb_number: string;
  project_name: string;
  procuring_entity: string;
  entity_bucket: string;
  entity_bucket_label: string;
  procurement_type: string;
  contract_award_date: string | null;
  contract_amount_npr: number | null;
  contractor_name: string;
  district: string | null;
  province: number | null;
  fiscal_year_bs: string | null;
  source_url: string | null;
  fetched_at: string | null;
  created_at: string | null;
}

export interface ProcurementContractListResponse {
  contracts: ProcurementContract[];
  total: number;
  page: number;
  per_page: number;
  has_more: boolean;
}

export interface ProcurementTypeStats {
  type: string;
  count: number;
  total_value: number;
}

export interface ProcurementFiscalYearStats {
  fiscal_year: string | null;
  count: number;
  total_value: number;
}

export interface ProcurementEntityBucketStats {
  bucket: string;
  label: string;
  count?: number;
  contract_count?: number;
  total_value: number;
  entity_count: number;
}

export interface ProcurementStatsResponse {
  total_contracts: number;
  total_value_npr: number;
  by_procurement_type: ProcurementTypeStats[];
  by_fiscal_year: ProcurementFiscalYearStats[];
  by_entity_bucket: ProcurementEntityBucketStats[];
}

export interface ProcurementTopEntity {
  procuring_entity: string;
  entity_bucket: string;
  entity_bucket_label: string;
  contract_count: number;
  total_value: number;
}

export interface ProcurementSummaryCard {
  label: string;
  value: string;
  meta: string;
  compact?: boolean;
}

export interface ProcurementWidgetSummaryResponse {
  generated_at: string;
  total: number;
  cards: ProcurementSummaryCard[];
  stats: ProcurementStatsResponse;
  entity_buckets: ProcurementEntityBucketStats[];
  top_entities: ProcurementTopEntity[];
  contracts: ProcurementContract[];
}

export interface ProcurementListParams {
  entity_bucket?: string;
  procurement_type?: string;
  search?: string;
  page?: number;
  per_page?: number;
}

export async function getProcurementContracts(
  params: ProcurementListParams = {},
): Promise<ProcurementContractListResponse> {
  const { data } = await apiClient.get('/procurement/contracts', { params });
  return data;
}

export async function getProcurementStats(): Promise<ProcurementStatsResponse> {
  const { data } = await apiClient.get('/procurement/stats');
  return data;
}

export async function getProcurementEntityBuckets(): Promise<ProcurementEntityBucketStats[]> {
  const { data } = await apiClient.get('/procurement/entity-buckets');
  return data;
}

export async function getProcurementTopEntities(params: {
  limit?: number;
  entity_bucket?: string;
} = {}): Promise<ProcurementTopEntity[]> {
  const { data } = await apiClient.get('/procurement/top-entities', { params });
  return data;
}

export async function getProcurementWidgetSummary(
  params: ProcurementListParams = {},
): Promise<ProcurementWidgetSummaryResponse> {
  const { data } = await apiClient.get('/procurement/widget-summary', { params });
  return data;
}
