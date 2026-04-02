import apiClient from './client'

export interface AutomationControl {
  automation_key: string
  label: string
  description: string
  is_enabled: boolean
  reason?: string | null
  last_changed_at?: string | null
  last_rerun_requested_at?: string | null
  last_run_started_at?: string | null
  last_run_completed_at?: string | null
  last_success_at?: string | null
  last_run_status?: string | null
  last_error?: string | null
}

export interface OpenAIStatus {
  status: 'healthy' | 'disabled' | 'misconfigured'
  api_key_configured: boolean
  embedding_enabled: boolean
  clustering_enabled: boolean
  agent_enabled: boolean
  developing_stories_enabled: boolean
  story_tracker_enabled: boolean
  embedding_model_key: string
  embedding_model: string
  clustering_model: string
  agent_fast_model: string
  agent_deep_model: string
  usage_limit_enabled: boolean
  local_embeddings_active: boolean
}

export interface EmbeddingTelemetry {
  total: number
  created_24h: number
  recent_stories_embedded_24h: number
  last_embedding_at?: string | null
  model_counts: Record<string, number>
  estimated_openai_embedding_calls_24h: number
  batch_size: number
}

export interface ClusteringTelemetry {
  total_clusters: number
  updated_clusters_24h: number
  recent_stories_clustered_24h: number
  last_cluster_activity_at?: string | null
}

export interface AutomationControlsResponse {
  items: AutomationControl[]
  openai: OpenAIStatus
  telemetry?: {
    embeddings: EmbeddingTelemetry
    clustering: ClusteringTelemetry
  }
}

export interface PaginationEnvelope<T> {
  items: T[]
  page: number
  per_page: number
  total: number
  total_pages: number
}

export interface EditorialOverviewResponse {
  editorial_backlog: {
    fact_check_pending_review: number
    fact_check_queue: number
    fact_check_reruns: number
    developing_stories_review: number
    story_tracker_review: number
    story_tracker_stale: number
    haiku_relevance_queue: number
    haiku_summary_queue: number
  }
  paused_automations: number
  automation_controls: AutomationControl[]
  alerts: Array<{
    severity: string
    title: string
    detail: string
  }>
  users: {
    total_users: number
    active_last_hour: number
    new_last_24h: number
    new_last_7d: number
    provider_counts: Record<string, number>
    role_counts: Record<string, number>
    guest_to_registered: {
      guest: number
      registered: number
    }
    signups_by_day: Array<{ date: string; count: number }>
  }
  analyst_brief: {
    latest_run_number?: number | null
    latest_status: string
    latest_created_at?: string | null
  }
  recent_actions: Array<{
    id: string
    action: string
    target_type?: string | null
    target_id?: string | null
    details?: Record<string, unknown> | null
    created_at: string
    user_email: string
  }>
}

export interface FactCheckInboxItem {
  story_id: string
  fact_check_result_id: string
  title?: string | null
  source_name?: string | null
  url?: string | null
  request_count: number
  checked_at: string
  raw: {
    verdict: string
    verdict_summary: string
    confidence: number
    key_finding?: string | null
    context?: string | null
    claims_analyzed?: any[] | null
    sources_checked?: any[] | null
  }
  review: {
    workflow_status: string
    final_verdict?: string | null
    final_verdict_summary?: string | null
    final_confidence?: number | null
    final_key_finding?: string | null
    final_context?: string | null
    override_notes?: string | null
    approved_at?: string | null
    rejected_at?: string | null
    rejection_reason?: string | null
    needs_rerun: boolean
    rerun_requested_at?: string | null
  }
  effective: {
    verdict: string
    verdict_summary: string
    confidence: number
    key_finding?: string | null
    context?: string | null
  }
}

export interface DevelopingStoryItem {
  cluster_id: string
  headline: string
  summary?: string | null
  category?: string | null
  severity?: string | null
  system_headline: string
  system_summary?: string | null
  system_category?: string | null
  system_severity?: string | null
  workflow_status: string
  story_count: number
  source_count: number
  first_published?: string | null
  last_updated?: string | null
  bluf?: string | null
  analyst_notes?: string | null
  stories: Array<{
    id: string
    title: string
    summary?: string | null
    source_name?: string | null
    url?: string | null
    published_at?: string | null
  }>
}

export interface StoryTrackerItem {
  narrative_id: string
  label: string
  thesis?: string | null
  category?: string | null
  direction?: string | null
  momentum_score: number
  confidence?: number | null
  workflow_status: string
  review_notes?: string | null
  cluster_count: number
  first_seen_at?: string | null
  last_updated?: string | null
  clusters: Array<{
    cluster_id: string
    headline: string
    category?: string | null
    severity?: string | null
    story_count: number
    source_count: number
    last_updated?: string | null
    similarity_score?: number | null
  }>
}

export interface GovtDecisionEditorialItem {
  item_id: string
  external_key: string
  event_key: string
  representative_title?: string | null
  representative_url?: string | null
  source_name?: string | null
  published_at?: string | null
  source_story_ids: string[]
  source_announcement_ids: string[]
  source_count: number
  raw: {
    office?: string | null
    implementing_ministry?: string | null
    decision_type?: string | null
    decision_title?: string | null
    decision_summary?: string | null
    status?: string | null
    evidence_summary?: string | null
    confidence?: number | null
    is_actual_decision: boolean
    supporting_sources?: Array<{
      kind: string
      id: string
      title: string
      summary?: string | null
      source_name: string
      source_token: string
      url: string
      published_at: string
      cluster_id?: string | null
      is_official: boolean
    }>
    model_payload?: Record<string, unknown> | null
  }
  review: {
    workflow_status: string
    final_office?: string | null
    final_implementing_ministry?: string | null
    final_decision_type?: string | null
    final_decision_title?: string | null
    final_decision_summary?: string | null
    final_status?: string | null
    final_source_url?: string | null
    final_evidence_note?: string | null
    final_confidence?: number | null
    reviewer_note?: string | null
    approved_at?: string | null
    rejected_at?: string | null
    rejection_reason?: string | null
    needs_rerun: boolean
    rerun_requested_at?: string | null
  }
  effective: {
    office?: string | null
    implementing_ministry?: string | null
    decision_type?: string | null
    decision_title?: string | null
    decision_summary?: string | null
    status?: string | null
    source_url?: string | null
    evidence_note?: string | null
    confidence?: number | null
  }
}

export interface CabinetActionEditorialItem {
  item_id: string
  program_id: string
  item_number: number
  source_pdf_page?: number | null
  raw: {
    section_key: string
    section_title_ne?: string | null
    section_title_en?: string | null
    source_text_ne: string
    title_en: string
    summary_en: string
    lead_institution?: string | null
    supporting_institutions: string[]
    action_type?: string | null
    trackability_class: string
    deadline_text_ne?: string | null
    deadline_kind?: string | null
    deadline_value?: number | null
    due_date_bs?: string | null
    due_date_ad?: string | null
    status: string
    evidence_strength?: string | null
    is_public: boolean
    last_checked_at?: string | null
    raw_seed_payload?: Record<string, unknown> | null
  }
  review: {
    workflow_status: string
    final_section_key?: string | null
    final_section_title_en?: string | null
    final_title_en?: string | null
    final_summary_en?: string | null
    final_lead_institution?: string | null
    final_supporting_institutions?: string[] | null
    final_action_type?: string | null
    final_trackability_class?: string | null
    final_status?: string | null
    final_evidence_note?: string | null
    final_confidence?: number | null
    final_is_public?: boolean | null
    final_manifesto_promise_ids?: string[] | null
    milestone_overrides?: Array<Record<string, unknown>> | null
    reviewer_note?: string | null
    approved_at?: string | null
    rejected_at?: string | null
    rejection_reason?: string | null
    needs_rerun: boolean
    rerun_requested_at?: string | null
  }
  effective: {
    section_key?: string | null
    section_title_en?: string | null
    title_en?: string | null
    summary_en?: string | null
    lead_institution?: string | null
    supporting_institutions?: string[] | null
    action_type?: string | null
    trackability_class?: string | null
    status?: string | null
    evidence_note?: string | null
    confidence?: number | null
    is_public?: boolean | null
    manifesto_promise_ids?: string[] | null
  }
  milestones: Array<{
    id: string
    milestone_order: number
    source_text_ne: string
    title_en: string
    summary_en: string
    deadline_text_ne?: string | null
    due_date_bs?: string | null
    due_date_ad?: string | null
    status: string
    evidence_strength?: string | null
  }>
  evidence: Array<{
    id: string
    source_kind: string
    source_title: string
    source_name?: string | null
    source_url?: string | null
    published_at?: string | null
    is_official: boolean
    extracted_status?: string | null
    evidence_note_en?: string | null
    confidence?: number | null
    is_public: boolean
    is_applied: boolean
  }>
  manifesto_links: Array<{
    id: string
    promise_id: string
    category: string
    title: string
  }>
}

export interface ReasonBody {
  reason: string
}

export async function fetchEditorialOverview(): Promise<EditorialOverviewResponse> {
  const { data } = await apiClient.get('/admin/editorial/overview')
  return data
}

export async function fetchAutomationControls(): Promise<AutomationControlsResponse> {
  const { data } = await apiClient.get('/admin/editorial/automation-controls')
  return data
}

export async function pauseAutomation(automationKey: string, reason: string): Promise<AutomationControl> {
  const { data } = await apiClient.post(`/admin/editorial/automation-controls/${automationKey}/pause`, { reason })
  return data
}

export async function resumeAutomation(automationKey: string, reason: string): Promise<AutomationControl> {
  const { data } = await apiClient.post(`/admin/editorial/automation-controls/${automationKey}/resume`, { reason })
  return data
}

export async function rerunAutomation(automationKey: string, reason: string): Promise<AutomationControl> {
  const { data } = await apiClient.post(`/admin/editorial/automation-controls/${automationKey}/rerun`, { reason })
  return data
}

export async function fetchFactCheckInbox(params: {
  workflowStatus?: string
  page?: number
  per_page?: number
} = {}): Promise<PaginationEnvelope<FactCheckInboxItem>> {
  const { data } = await apiClient.get('/admin/editorial/fact-check/inbox', {
    params: {
      workflow_status: params.workflowStatus,
      page: params.page,
      per_page: params.per_page,
    },
  })
  return data
}

export async function fetchFactCheckDetail(storyId: string): Promise<FactCheckInboxItem> {
  const { data } = await apiClient.get(`/admin/editorial/fact-check/${storyId}`)
  return data
}

export async function patchFactCheck(storyId: string, payload: Record<string, unknown>): Promise<FactCheckInboxItem> {
  const { data } = await apiClient.patch(`/admin/editorial/fact-check/${storyId}`, payload)
  return data
}

export async function approveFactCheck(storyId: string, reason: string): Promise<FactCheckInboxItem> {
  const { data } = await apiClient.post(`/admin/editorial/fact-check/${storyId}/approve`, { reason })
  return data
}

export async function rejectFactCheck(storyId: string, reason: string, workflowStatus: 'rejected' | 'suppressed' = 'rejected'): Promise<FactCheckInboxItem> {
  const { data } = await apiClient.post(`/admin/editorial/fact-check/${storyId}/reject`, {
    reason,
    workflow_status: workflowStatus,
  })
  return data
}

export async function rerunFactCheck(storyId: string, reason: string): Promise<FactCheckInboxItem> {
  const { data } = await apiClient.post(`/admin/editorial/fact-check/${storyId}/rerun`, { reason })
  return data
}

export async function fetchDevelopingStoriesInbox(params: {
  hours?: number
  page?: number
  per_page?: number
} = {}): Promise<PaginationEnvelope<DevelopingStoryItem>> {
  const { data } = await apiClient.get('/admin/editorial/developing-stories/inbox', { params })
  return data
}

export async function fetchDevelopingStoryDetail(clusterId: string): Promise<DevelopingStoryItem> {
  const { data } = await apiClient.get(`/admin/editorial/developing-stories/${clusterId}`)
  return data
}

export async function patchDevelopingStory(clusterId: string, payload: Record<string, unknown>): Promise<DevelopingStoryItem> {
  const { data } = await apiClient.patch(`/admin/editorial/developing-stories/${clusterId}`, payload)
  return data
}

export async function approveDevelopingStory(clusterId: string, reason: string): Promise<DevelopingStoryItem> {
  const { data } = await apiClient.post(`/admin/editorial/developing-stories/${clusterId}/approve`, { reason })
  return data
}

export async function rejectDevelopingStory(clusterId: string, reason: string): Promise<DevelopingStoryItem> {
  const { data } = await apiClient.post(`/admin/editorial/developing-stories/${clusterId}/reject`, { reason })
  return data
}

export async function rerunDevelopingStory(clusterId: string, reason: string): Promise<DevelopingStoryItem> {
  const { data } = await apiClient.post(`/admin/editorial/developing-stories/${clusterId}/rerun`, { reason })
  return data
}

export async function fetchStoryTrackerInbox(params: {
  hours?: number
  page?: number
  per_page?: number
} = {}): Promise<PaginationEnvelope<StoryTrackerItem>> {
  const { data } = await apiClient.get('/admin/editorial/story-tracker/inbox', { params })
  return data
}

export async function patchStoryTracker(narrativeId: string, payload: Record<string, unknown>): Promise<StoryTrackerItem> {
  const { data } = await apiClient.patch(`/admin/editorial/story-tracker/${narrativeId}`, payload)
  return data
}

export async function approveStoryTracker(narrativeId: string, reason: string): Promise<StoryTrackerItem> {
  const { data } = await apiClient.post(`/admin/editorial/story-tracker/${narrativeId}/approve`, { reason })
  return data
}

export async function rejectStoryTracker(narrativeId: string, reason: string): Promise<StoryTrackerItem> {
  const { data } = await apiClient.post(`/admin/editorial/story-tracker/${narrativeId}/reject`, { reason })
  return data
}

export async function rerunStoryTracker(narrativeId: string, reason: string): Promise<{ status: string; narrative_id: string }> {
  const { data } = await apiClient.post(`/admin/editorial/story-tracker/${narrativeId}/rerun`, { reason })
  return data
}

export async function fetchGovtDecisionInbox(params: {
  workflowStatus?: string
  page?: number
  per_page?: number
} = {}): Promise<PaginationEnvelope<GovtDecisionEditorialItem>> {
  const { data } = await apiClient.get('/admin/editorial/govt-decisions/inbox', {
    params: {
      workflow_status: params.workflowStatus,
      page: params.page,
      per_page: params.per_page,
    },
  })
  return data
}

export async function fetchGovtDecisionDetail(itemId: string): Promise<GovtDecisionEditorialItem> {
  const { data } = await apiClient.get(`/admin/editorial/govt-decisions/${itemId}`)
  return data
}

export async function patchGovtDecision(itemId: string, payload: Record<string, unknown>): Promise<GovtDecisionEditorialItem> {
  const { data } = await apiClient.patch(`/admin/editorial/govt-decisions/${itemId}`, payload)
  return data
}

export async function approveGovtDecision(itemId: string, reason: string): Promise<GovtDecisionEditorialItem> {
  const { data } = await apiClient.post(`/admin/editorial/govt-decisions/${itemId}/approve`, { reason })
  return data
}

export async function rejectGovtDecision(itemId: string, reason: string): Promise<GovtDecisionEditorialItem> {
  const { data } = await apiClient.post(`/admin/editorial/govt-decisions/${itemId}/reject`, { reason })
  return data
}

export async function rerunGovtDecision(itemId: string, reason: string): Promise<GovtDecisionEditorialItem> {
  const { data } = await apiClient.post(`/admin/editorial/govt-decisions/${itemId}/rerun`, { reason })
  return data
}

export async function supersedeGovtDecision(itemId: string, reason: string): Promise<GovtDecisionEditorialItem> {
  const { data } = await apiClient.post(`/admin/editorial/govt-decisions/${itemId}/supersede`, { reason })
  return data
}

export async function seedCabinetActions(payload: {
  pdf_path: string
  program_key?: string
  auto_approve?: boolean
}) {
  const { data } = await apiClient.post('/admin/editorial/cabinet-actions/seed', payload)
  return data
}

export async function fetchCabinetActionInbox(params: {
  workflowStatus?: string
  page?: number
  per_page?: number
} = {}): Promise<PaginationEnvelope<CabinetActionEditorialItem>> {
  const { data } = await apiClient.get('/admin/editorial/cabinet-actions/inbox', {
    params: {
      workflow_status: params.workflowStatus,
      page: params.page,
      per_page: params.per_page,
    },
  })
  return data
}

export async function fetchCabinetActionDetail(itemId: string): Promise<CabinetActionEditorialItem> {
  const { data } = await apiClient.get(`/admin/editorial/cabinet-actions/${itemId}`)
  return data
}

export async function quickUpdateCabinetAction(
  itemId: string,
  payload: {
    status: string
    evidence_note?: string
    reviewer_note?: string
    is_public?: boolean
  },
): Promise<CabinetActionEditorialItem> {
  const { data } = await apiClient.put(`/admin/editorial/cabinet-actions/${itemId}/quick-update`, payload)
  return data
}

export async function patchCabinetAction(itemId: string, payload: Record<string, unknown>): Promise<CabinetActionEditorialItem> {
  const { data } = await apiClient.patch(`/admin/editorial/cabinet-actions/${itemId}`, payload)
  return data
}

export async function approveCabinetAction(itemId: string, reason: string): Promise<CabinetActionEditorialItem> {
  const { data } = await apiClient.post(`/admin/editorial/cabinet-actions/${itemId}/approve`, { reason })
  return data
}

export async function rejectCabinetAction(itemId: string, reason: string): Promise<CabinetActionEditorialItem> {
  const { data } = await apiClient.post(`/admin/editorial/cabinet-actions/${itemId}/reject`, { reason })
  return data
}

export async function rerunCabinetAction(itemId: string, reason: string): Promise<CabinetActionEditorialItem> {
  const { data } = await apiClient.post(`/admin/editorial/cabinet-actions/${itemId}/rerun`, { reason })
  return data
}
