import apiClient from './client';

export interface GovtDecisionPublicItem {
  id: string;
  title: string;
  office: string | null;
  implementingMinistry: string | null;
  decisionType: string | null;
  decision: string | null;
  status: string | null;
  evidenceNote: string | null;
  sourceName: string | null;
  sourceUrl: string | null;
  publishedAt: string | null;
}

export async function getLatestGovtDecisions(
  limit: number = 100,
  dedupe: boolean = false,
): Promise<{ items: GovtDecisionPublicItem[] }> {
  const response = await apiClient.get('/govt-decisions/latest', { params: { limit, dedupe } });
  return response.data;
}
