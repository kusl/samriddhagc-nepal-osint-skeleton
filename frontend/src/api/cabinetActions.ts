import apiClient from './client';

export interface CabinetActionPublicItem {
  id: string;
  itemNumber: number;
  sectionKey: string;
  sectionTitle: string | null;
  title: string;
  summary: string;
  leadInstitution: string | null;
  supportingInstitutions: string[];
  actionType: string | null;
  trackabilityClass: string;
  deadlineTextNe: string | null;
  dueDateBs: string | null;
  dueDateAd: string | null;
  status: string;
  evidenceNote: string | null;
  sourcePdfPage: number | null;
  relatedManifestoPromises: string[];
  milestoneCount: number;
  sourceTextNe?: string;
  milestones?: Array<{
    id: string;
    milestoneOrder: number;
    title: string;
    summary: string;
    sourceTextNe: string;
    deadlineTextNe: string | null;
    dueDateBs: string | null;
    dueDateAd: string | null;
    status: string;
    evidenceStrength: string | null;
  }>;
  evidence?: Array<{
    id: string;
    sourceKind: string;
    sourceTitle: string;
    sourceName: string | null;
    sourceUrl: string | null;
    publishedAt: string | null;
    isOfficial: boolean;
    status: string | null;
    note: string | null;
    confidence: number | null;
  }>;
}

export interface CabinetActionSummary {
  total_actions: number;
  total_scored_actions: number;
  completed_on_time: number;
  completed_late: number;
  overdue: number;
  underway: number;
  non_scored: number;
  completion_rate: number;
  on_time_rate: number;
}

export interface CabinetActionListParams {
  limit?: number;
  section_key?: string;
  status?: string;
  lead_institution?: string;
  trackability_class?: string;
  due_bucket?: 'due_soon' | 'overdue';
}

export async function getCabinetActionSummary(): Promise<CabinetActionSummary> {
  const response = await apiClient.get('/cabinet-actions/summary');
  return response.data;
}

export async function getCabinetActionItems(params: CabinetActionListParams = {}): Promise<{ items: CabinetActionPublicItem[] }> {
  const response = await apiClient.get('/cabinet-actions/items', { params });
  return response.data;
}

export async function getCabinetActionItem(itemId: string): Promise<CabinetActionPublicItem | null> {
  const response = await apiClient.get(`/cabinet-actions/items/${itemId}`);
  return response.data;
}
