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

/**
 * One page of public government decisions.
 *
 * Restored 2026-09-01: `useGovtDecisions.ts` imports this type and calls the
 * fetcher with a single options object including `cursor`, but this module
 * exported neither — it took positional args and had no page type, so the
 * infinite-scroll archive would have passed an object where a number was
 * expected. Backend: app/api/v1/govt_decisions.py.
 */
export interface GovtDecisionPublicPage {
  items: GovtDecisionPublicItem[];
  next_cursor?: string | null;
}

export async function getLatestGovtDecisions(
  { limit = 100, dedupe = false, cursor = null }: {
    limit?: number;
    dedupe?: boolean;
    cursor?: string | null;
  } = {},
): Promise<GovtDecisionPublicPage> {
  const params: Record<string, unknown> = { limit, dedupe };
  if (cursor) params.cursor = cursor;
  const response = await apiClient.get('/govt-decisions/latest', { params });
  return response.data;
}
