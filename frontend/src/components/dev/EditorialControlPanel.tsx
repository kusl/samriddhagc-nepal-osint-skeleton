import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ExternalLink, FileWarning, Gavel, Sparkles, Target } from 'lucide-react'
import {
  approveCabinetAction,
  approveGovtDecision,
  approveDevelopingStory,
  approveFactCheck,
  approveStoryTracker,
  fetchCabinetActionDetail,
  fetchCabinetActionInbox,
  fetchGovtDecisionDetail,
  fetchGovtDecisionInbox,
  fetchDevelopingStoryDetail,
  fetchDevelopingStoriesInbox,
  fetchFactCheckDetail,
  fetchFactCheckInbox,
  fetchStoryTrackerInbox,
  patchCabinetAction,
  patchGovtDecision,
  patchDevelopingStory,
  patchFactCheck,
  patchStoryTracker,
  rejectCabinetAction,
  rejectGovtDecision,
  rejectDevelopingStory,
  rejectFactCheck,
  rejectStoryTracker,
  rerunCabinetAction,
  rerunGovtDecision,
  rerunDevelopingStory,
  rerunFactCheck,
  rerunStoryTracker,
  supersedeGovtDecision,
} from '../../api/editorial'
import { ActionReasonModal } from './ActionReasonModal'

const PAGE_SIZE = 40

type EditorialSection = 'fact-checks' | 'developing' | 'tracker' | 'govt-decisions' | 'cabinet-actions'

type PendingModalAction =
  | { type: 'factCheckSave' | 'factCheckApprove' | 'factCheckReject' | 'factCheckSuppress' | 'factCheckRerun'; id: string }
  | { type: 'clusterSave' | 'clusterApprove' | 'clusterReject' | 'clusterRerun'; id: string }
  | { type: 'trackerSave' | 'trackerApprove' | 'trackerReject' | 'trackerRerun'; id: string }
  | { type: 'decisionSave' | 'decisionApprove' | 'decisionReject' | 'decisionRerun' | 'decisionSupersede'; id: string }
  | { type: 'cabinetSave' | 'cabinetApprove' | 'cabinetReject' | 'cabinetRerun'; id: string }
  | null

function formatRelative(value?: string | null) {
  if (!value) return 'never'
  const date = new Date(value)
  const diffMs = Date.now() - date.getTime()
  const mins = Math.floor(diffMs / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

function QueueItem({
  title,
  meta,
  active,
  status,
  onClick,
}: {
  title: string
  meta: string
  active: boolean
  status: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full rounded-xl border px-4 py-3 text-left transition-colors ${
        active
          ? 'border-blue-400/30 bg-blue-500/10'
          : 'border-white/8 bg-black/20 hover:border-white/20'
      }`}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="line-clamp-2 text-sm font-medium text-white">{title}</div>
        <span className="rounded-full border border-white/10 px-2 py-0.5 text-[10px] uppercase tracking-[0.18em] text-white/45">
          {status}
        </span>
      </div>
      <div className="mt-2 text-xs text-white/40">{meta}</div>
    </button>
  )
}

function QueuePagination({
  page,
  totalPages,
  total,
  onPageChange,
}: {
  page: number
  totalPages: number
  total: number
  onPageChange: (page: number) => void
}) {
  return (
    <div className="flex items-center justify-between border-t border-white/8 pt-3 text-xs text-white/40">
      <span>{total} total</span>
      <div className="flex items-center gap-2">
        <span>Page {page} / {Math.max(totalPages, 1)}</span>
        <button
          type="button"
          onClick={() => onPageChange(Math.max(1, page - 1))}
          disabled={page <= 1}
          className="rounded-lg border border-white/10 px-2.5 py-1 text-white/60 transition-colors hover:border-white/20 hover:text-white disabled:cursor-not-allowed disabled:opacity-35"
        >
          Prev
        </button>
        <button
          type="button"
          onClick={() => onPageChange(Math.min(totalPages || 1, page + 1))}
          disabled={page >= totalPages}
          className="rounded-lg border border-white/10 px-2.5 py-1 text-white/60 transition-colors hover:border-white/20 hover:text-white disabled:cursor-not-allowed disabled:opacity-35"
        >
          Next
        </button>
      </div>
    </div>
  )
}

function QueueColumn({
  items,
  pagination,
}: {
  items: ReactNode
  pagination: ReactNode
}) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex-1 overflow-y-auto pr-1">{items}</div>
      <div className="mt-3">{pagination}</div>
    </div>
  )
}

function DetailColumn({ children }: { children: ReactNode }) {
  return <div className="h-full overflow-y-auto pr-1">{children}</div>
}

function SectionShell({
  icon,
  title,
  description,
  queue,
  detail,
}: {
  icon: ReactNode
  title: string
  description: string
  queue: ReactNode
  detail: ReactNode
}) {
  return (
    <section className="overflow-hidden rounded-[28px] border border-white/10 bg-[#0e1220]">
      <div className="border-b border-white/8 px-5 py-4">
        <div className="flex items-center gap-2 text-white">
          <span className="text-blue-400">{icon}</span>
          <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
        </div>
        <p className="mt-1 text-sm text-white/45">{description}</p>
      </div>
      <div className="grid min-h-[calc(100vh-360px)] grid-cols-1 xl:grid-cols-[360px_minmax(0,1fr)]">
        <div className="min-h-0 overflow-hidden border-r border-white/8 p-4">{queue}</div>
        <div className="min-h-0 overflow-hidden p-5">{detail}</div>
      </div>
    </section>
  )
}

export function EditorialControlPanel() {
  const queryClient = useQueryClient()
  const [activeSection, setActiveSection] = useState<EditorialSection>('fact-checks')
  const [factCheckId, setFactCheckId] = useState<string | null>(null)
  const [clusterId, setClusterId] = useState<string | null>(null)
  const [trackerId, setTrackerId] = useState<string | null>(null)
  const [decisionId, setDecisionId] = useState<string | null>(null)
  const [cabinetActionId, setCabinetActionId] = useState<string | null>(null)
  const [factCheckPage, setFactCheckPage] = useState(1)
  const [clusterPage, setClusterPage] = useState(1)
  const [trackerPage, setTrackerPage] = useState(1)
  const [decisionPage, setDecisionPage] = useState(1)
  const [cabinetActionPage, setCabinetActionPage] = useState(1)
  const [pendingAction, setPendingAction] = useState<PendingModalAction>(null)

  const factCheckInbox = useQuery({
    queryKey: ['editorial-fact-check-inbox', factCheckPage],
    queryFn: () => fetchFactCheckInbox({ page: factCheckPage, per_page: PAGE_SIZE }),
    refetchInterval: 60000,
  })
  const clusterInbox = useQuery({
    queryKey: ['editorial-developing-inbox', clusterPage],
    queryFn: () => fetchDevelopingStoriesInbox({ page: clusterPage, per_page: PAGE_SIZE }),
    refetchInterval: 60000,
  })
  const trackerInbox = useQuery({
    queryKey: ['editorial-story-tracker-inbox', trackerPage],
    queryFn: () => fetchStoryTrackerInbox({ page: trackerPage, per_page: PAGE_SIZE }),
    refetchInterval: 60000,
  })
  const decisionInbox = useQuery({
    queryKey: ['editorial-govt-decision-inbox', decisionPage],
    queryFn: () => fetchGovtDecisionInbox({ workflowStatus: 'draft,needs_correction', page: decisionPage, per_page: PAGE_SIZE }),
    refetchInterval: 60000,
  })
  const cabinetActionInbox = useQuery({
    queryKey: ['editorial-cabinet-action-inbox', cabinetActionPage],
    queryFn: () => fetchCabinetActionInbox({ workflowStatus: 'draft,needs_correction', page: cabinetActionPage, per_page: PAGE_SIZE }),
    refetchInterval: 60000,
  })

  useEffect(() => {
    const firstId = factCheckInbox.data?.items[0]?.story_id
    const exists = factCheckInbox.data?.items.some((item) => item.story_id === factCheckId)
    if (firstId && (!factCheckId || !exists)) setFactCheckId(firstId)
  }, [factCheckInbox.data, factCheckId])

  useEffect(() => {
    const firstId = clusterInbox.data?.items[0]?.cluster_id
    const exists = clusterInbox.data?.items.some((item) => item.cluster_id === clusterId)
    if (firstId && (!clusterId || !exists)) setClusterId(firstId)
  }, [clusterInbox.data, clusterId])

  useEffect(() => {
    const firstId = trackerInbox.data?.items[0]?.narrative_id
    const exists = trackerInbox.data?.items.some((item) => item.narrative_id === trackerId)
    if (firstId && (!trackerId || !exists)) setTrackerId(firstId)
  }, [trackerInbox.data, trackerId])

  useEffect(() => {
    const firstId = decisionInbox.data?.items[0]?.item_id
    const exists = decisionInbox.data?.items.some((item) => item.item_id === decisionId)
    if (firstId && (!decisionId || !exists)) setDecisionId(firstId)
  }, [decisionInbox.data, decisionId])
  useEffect(() => {
    const firstId = cabinetActionInbox.data?.items[0]?.item_id
    const exists = cabinetActionInbox.data?.items.some((item) => item.item_id === cabinetActionId)
    if (firstId && (!cabinetActionId || !exists)) setCabinetActionId(firstId)
  }, [cabinetActionInbox.data, cabinetActionId])

  const factCheckDetail = useQuery({
    queryKey: ['editorial-fact-check-detail', factCheckId],
    queryFn: () => fetchFactCheckDetail(factCheckId!),
    enabled: Boolean(factCheckId),
  })

  const clusterDetail = useQuery({
    queryKey: ['editorial-developing-detail', clusterId],
    queryFn: () => fetchDevelopingStoryDetail(clusterId!),
    enabled: Boolean(clusterId),
  })
  const decisionDetail = useQuery({
    queryKey: ['editorial-govt-decision-detail', decisionId],
    queryFn: () => fetchGovtDecisionDetail(decisionId!),
    enabled: Boolean(decisionId),
  })
  const cabinetActionDetail = useQuery({
    queryKey: ['editorial-cabinet-action-detail', cabinetActionId],
    queryFn: () => fetchCabinetActionDetail(cabinetActionId!),
    enabled: Boolean(cabinetActionId),
  })

  const [factCheckDraft, setFactCheckDraft] = useState({
    final_verdict: '',
    final_verdict_summary: '',
    final_confidence: '',
    final_key_finding: '',
    final_context: '',
    override_notes: '',
  })
  const [clusterDraft, setClusterDraft] = useState({
    analyst_headline: '',
    analyst_summary: '',
    analyst_category: '',
    analyst_severity: '',
    analyst_notes: '',
  })
  const [trackerDraft, setTrackerDraft] = useState({
    label: '',
    thesis: '',
    review_notes: '',
  })
  const [decisionDraft, setDecisionDraft] = useState({
    final_office: '',
    final_implementing_ministry: '',
    final_decision_type: '',
    final_decision_title: '',
    final_decision_summary: '',
    final_status: '',
    final_source_url: '',
    final_evidence_note: '',
    final_confidence: '',
    reviewer_note: '',
  })
  const [cabinetActionDraft, setCabinetActionDraft] = useState({
    final_section_key: '',
    final_section_title_en: '',
    final_title_en: '',
    final_summary_en: '',
    final_lead_institution: '',
    final_supporting_institutions: '',
    final_action_type: '',
    final_trackability_class: '',
    final_status: '',
    final_evidence_note: '',
    final_confidence: '',
    final_manifesto_promise_ids: '',
    reviewer_note: '',
  })

  useEffect(() => {
    const item = factCheckDetail.data
    if (!item) return
    setFactCheckDraft({
      final_verdict: item.review.final_verdict || item.effective.verdict || '',
      final_verdict_summary: item.review.final_verdict_summary || item.effective.verdict_summary || '',
      final_confidence: item.review.final_confidence != null ? String(item.review.final_confidence) : String(item.effective.confidence),
      final_key_finding: item.review.final_key_finding || item.effective.key_finding || '',
      final_context: item.review.final_context || item.effective.context || '',
      override_notes: item.review.override_notes || '',
    })
  }, [factCheckDetail.data])

  useEffect(() => {
    const item = clusterDetail.data
    if (!item) return
    setClusterDraft({
      analyst_headline: item.headline || '',
      analyst_summary: item.summary || '',
      analyst_category: item.category || '',
      analyst_severity: item.severity || '',
      analyst_notes: item.analyst_notes || '',
    })
  }, [clusterDetail.data])

  useEffect(() => {
    const item = trackerInbox.data?.items.find((entry) => entry.narrative_id === trackerId)
    if (!item) return
    setTrackerDraft({
      label: item.label || '',
      thesis: item.thesis || '',
      review_notes: item.review_notes || '',
    })
  }, [trackerInbox.data, trackerId])

  useEffect(() => {
    const item = decisionDetail.data
    if (!item) return
    setDecisionDraft({
      final_office: item.review.final_office || item.effective.office || '',
      final_implementing_ministry: item.review.final_implementing_ministry || item.effective.implementing_ministry || '',
      final_decision_type: item.review.final_decision_type || item.effective.decision_type || '',
      final_decision_title: item.review.final_decision_title || item.effective.decision_title || '',
      final_decision_summary: item.review.final_decision_summary || item.effective.decision_summary || '',
      final_status: item.review.final_status || item.effective.status || '',
      final_source_url: item.review.final_source_url || item.effective.source_url || '',
      final_evidence_note: item.review.final_evidence_note || item.effective.evidence_note || '',
      final_confidence: item.review.final_confidence != null
        ? String(item.review.final_confidence)
        : String(item.effective.confidence ?? ''),
      reviewer_note: item.review.reviewer_note || '',
    })
  }, [decisionDetail.data])

  useEffect(() => {
    const item = cabinetActionDetail.data
    if (!item) return
    setCabinetActionDraft({
      final_section_key: item.review.final_section_key || item.effective.section_key || item.raw.section_key || '',
      final_section_title_en: item.review.final_section_title_en || item.effective.section_title_en || item.raw.section_title_en || '',
      final_title_en: item.review.final_title_en || item.effective.title_en || item.raw.title_en || '',
      final_summary_en: item.review.final_summary_en || item.effective.summary_en || item.raw.summary_en || '',
      final_lead_institution: item.review.final_lead_institution || item.effective.lead_institution || item.raw.lead_institution || '',
      final_supporting_institutions: (item.review.final_supporting_institutions || item.effective.supporting_institutions || item.raw.supporting_institutions || []).join(', '),
      final_action_type: item.review.final_action_type || item.effective.action_type || item.raw.action_type || '',
      final_trackability_class: item.review.final_trackability_class || item.effective.trackability_class || item.raw.trackability_class || '',
      final_status: item.review.final_status || item.effective.status || item.raw.status || '',
      final_evidence_note: item.review.final_evidence_note || item.effective.evidence_note || '',
      final_confidence: item.review.final_confidence != null ? String(item.review.final_confidence) : String(item.effective.confidence ?? ''),
      final_manifesto_promise_ids: (item.review.final_manifesto_promise_ids || item.manifesto_links.map((link) => link.promise_id)).join(', '),
      reviewer_note: item.review.reviewer_note || '',
    })
  }, [cabinetActionDetail.data])

  const selectedTracker = useMemo(
    () => trackerInbox.data?.items.find((entry) => entry.narrative_id === trackerId) || null,
    [trackerInbox.data, trackerId],
  )

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ['editorial-overview'] })
    queryClient.invalidateQueries({ queryKey: ['editorial-fact-check-inbox'] })
    queryClient.invalidateQueries({ queryKey: ['editorial-fact-check-detail'] })
    queryClient.invalidateQueries({ queryKey: ['editorial-developing-inbox'] })
    queryClient.invalidateQueries({ queryKey: ['editorial-developing-detail'] })
    queryClient.invalidateQueries({ queryKey: ['editorial-story-tracker-inbox'] })
    queryClient.invalidateQueries({ queryKey: ['editorial-govt-decision-inbox'] })
    queryClient.invalidateQueries({ queryKey: ['editorial-govt-decision-detail'] })
    queryClient.invalidateQueries({ queryKey: ['editorial-cabinet-action-inbox'] })
    queryClient.invalidateQueries({ queryKey: ['editorial-cabinet-action-detail'] })
    queryClient.invalidateQueries({ queryKey: ['govt-decisions'] })
    queryClient.invalidateQueries({ queryKey: ['cabinet-actions'] })
  }

  const actionMutation = useMutation({
    mutationFn: async ({ action, reason }: { action: PendingModalAction; reason: string }) => {
      if (!action) return null

      if (action.type === 'factCheckSave' && factCheckId) {
        return patchFactCheck(factCheckId, {
          ...factCheckDraft,
          final_confidence: Number(factCheckDraft.final_confidence),
          reason,
        })
      }
      if (action.type === 'factCheckApprove' && factCheckId) return approveFactCheck(factCheckId, reason)
      if (action.type === 'factCheckReject' && factCheckId) return rejectFactCheck(factCheckId, reason, 'rejected')
      if (action.type === 'factCheckSuppress' && factCheckId) return rejectFactCheck(factCheckId, reason, 'suppressed')
      if (action.type === 'factCheckRerun' && factCheckId) return rerunFactCheck(factCheckId, reason)

      if (action.type === 'clusterSave' && clusterId) return patchDevelopingStory(clusterId, { ...clusterDraft, reason })
      if (action.type === 'clusterApprove' && clusterId) return approveDevelopingStory(clusterId, reason)
      if (action.type === 'clusterReject' && clusterId) return rejectDevelopingStory(clusterId, reason)
      if (action.type === 'clusterRerun' && clusterId) return rerunDevelopingStory(clusterId, reason)

      if (action.type === 'trackerSave' && trackerId) return patchStoryTracker(trackerId, { ...trackerDraft, reason })
      if (action.type === 'trackerApprove' && trackerId) return approveStoryTracker(trackerId, reason)
      if (action.type === 'trackerReject' && trackerId) return rejectStoryTracker(trackerId, reason)
      if (action.type === 'trackerRerun' && trackerId) return rerunStoryTracker(trackerId, reason)

      if (action.type === 'decisionSave' && decisionId) {
        return patchGovtDecision(decisionId, {
          ...decisionDraft,
          final_confidence: decisionDraft.final_confidence === '' ? null : Number(decisionDraft.final_confidence),
          reason,
        })
      }
      if (action.type === 'decisionApprove' && decisionId) return approveGovtDecision(decisionId, reason)
      if (action.type === 'decisionReject' && decisionId) return rejectGovtDecision(decisionId, reason)
      if (action.type === 'decisionRerun' && decisionId) return rerunGovtDecision(decisionId, reason)
      if (action.type === 'decisionSupersede' && decisionId) return supersedeGovtDecision(decisionId, reason)

      if (action.type === 'cabinetSave' && cabinetActionId) {
        return patchCabinetAction(cabinetActionId, {
          ...cabinetActionDraft,
          final_supporting_institutions: cabinetActionDraft.final_supporting_institutions
            .split(',')
            .map((part) => part.trim())
            .filter(Boolean),
          final_manifesto_promise_ids: cabinetActionDraft.final_manifesto_promise_ids
            .split(',')
            .map((part) => part.trim())
            .filter(Boolean),
          final_confidence: cabinetActionDraft.final_confidence === '' ? null : Number(cabinetActionDraft.final_confidence),
          reason,
        })
      }
      if (action.type === 'cabinetApprove' && cabinetActionId) return approveCabinetAction(cabinetActionId, reason)
      if (action.type === 'cabinetReject' && cabinetActionId) return rejectCabinetAction(cabinetActionId, reason)
      if (action.type === 'cabinetRerun' && cabinetActionId) return rerunCabinetAction(cabinetActionId, reason)

      return null
    },
    onSuccess: () => {
      invalidateAll()
      setPendingAction(null)
    },
  })

  const modalCopy = useMemo(() => {
    if (!pendingAction) return null
    const map: Record<Exclude<PendingModalAction, null>['type'], { title: string; description: string; confirmLabel: string }> = {
      factCheckSave: {
        title: 'Save fact-check override',
        description: 'This updates the internal override draft and returns the item to pending review.',
        confirmLabel: 'Save override',
      },
      factCheckApprove: {
        title: 'Approve fact-check',
        description: 'The approved version becomes the public fact-check result.',
        confirmLabel: 'Approve fact-check',
      },
      factCheckReject: {
        title: 'Reject fact-check',
        description: 'This removes the system output from public use but preserves the raw result internally.',
        confirmLabel: 'Reject fact-check',
      },
      factCheckSuppress: {
        title: 'Suppress fact-check',
        description: 'Suppress hides the result from public use without deleting the raw system output.',
        confirmLabel: 'Suppress result',
      },
      factCheckRerun: {
        title: 'Request fact-check rerun',
        description: 'This flags the story for regeneration by the fact-check worker.',
        confirmLabel: 'Request rerun',
      },
      clusterSave: {
        title: 'Save developing-story draft',
        description: 'This stores developer overrides for the developing story.',
        confirmLabel: 'Save draft',
      },
      clusterApprove: {
        title: 'Approve developing story',
        description: 'This marks the story cluster as verified.',
        confirmLabel: 'Approve story',
      },
      clusterReject: {
        title: 'Reject developing story',
        description: 'This marks the story cluster as rejected for editorial feeds.',
        confirmLabel: 'Reject story',
      },
      clusterRerun: {
        title: 'Rerun BLUF generation',
        description: 'This regenerates the developing-story BLUF for the selected cluster.',
        confirmLabel: 'Rerun BLUF',
      },
      trackerSave: {
        title: 'Save story-tracker draft',
        description: 'This updates the narrative label, thesis, or review notes.',
        confirmLabel: 'Save draft',
      },
      trackerApprove: {
        title: 'Approve story-tracker narrative',
        description: 'This marks the narrative as approved for ongoing tracker use.',
        confirmLabel: 'Approve narrative',
      },
      trackerReject: {
        title: 'Reject story-tracker narrative',
        description: 'This removes the narrative from approved tracker use.',
        confirmLabel: 'Reject narrative',
      },
      trackerRerun: {
        title: 'Queue story-tracker rerun',
        description: 'This queues a tracker refresh while keeping the current record for context.',
        confirmLabel: 'Queue rerun',
      },
      decisionSave: {
        title: 'Save government-decision draft',
        description: 'This stores the edited government-decision fields and returns the item to draft review.',
        confirmLabel: 'Save draft',
      },
      decisionApprove: {
        title: 'Approve government decision',
        description: 'This publishes the reviewed government decision to the public widget feed.',
        confirmLabel: 'Approve decision',
      },
      decisionReject: {
        title: 'Reject government decision',
        description: 'This removes the extracted item from public consideration while preserving the raw result.',
        confirmLabel: 'Reject decision',
      },
      decisionRerun: {
        title: 'Request government-decision rerun',
        description: 'This flags the item for re-extraction during the next automation cycle.',
        confirmLabel: 'Request rerun',
      },
      decisionSupersede: {
        title: 'Supersede government decision',
        description: 'This marks the current item as superseded by a newer record.',
        confirmLabel: 'Supersede item',
      },
      cabinetSave: {
        title: 'Save cabinet-action draft',
        description: 'This stores the reviewed cabinet action fields and leaves the item in draft for approval.',
        confirmLabel: 'Save draft',
      },
      cabinetApprove: {
        title: 'Approve cabinet action',
        description: 'This publishes the reviewed cabinet action record and any manifesto cross-links.',
        confirmLabel: 'Approve action',
      },
      cabinetReject: {
        title: 'Reject cabinet action',
        description: 'This hides the cabinet action item from public output while preserving the source record internally.',
        confirmLabel: 'Reject action',
      },
      cabinetRerun: {
        title: 'Request cabinet-action rerun',
        description: 'This flags the item for re-evaluation during the next cabinet action tracking cycle.',
        confirmLabel: 'Request rerun',
      },
    }
    return map[pendingAction.type]
  }, [pendingAction])

  const sectionTabs = [
    { key: 'fact-checks' as const, label: 'Fact Checks', count: factCheckInbox.data?.total || 0 },
    { key: 'developing' as const, label: 'Developing Stories', count: clusterInbox.data?.total || 0 },
    { key: 'tracker' as const, label: 'Story Tracker', count: trackerInbox.data?.total || 0 },
    { key: 'govt-decisions' as const, label: 'Government Decisions', count: decisionInbox.data?.total || 0 },
    { key: 'cabinet-actions' as const, label: 'Cabinet Actions', count: cabinetActionInbox.data?.total || 0 },
  ]

  const factCheckSection = (
    <SectionShell
      icon={<FileWarning size={16} />}
      title="Fact-Check Moderation"
      description="Raw system verdicts, internal overrides, and developer approval flow for public fact checks."
      queue={
        <QueueColumn
          items={
            <div className="space-y-3">
              {(factCheckInbox.data?.items || []).map((item) => (
                <QueueItem
                  key={item.story_id}
                  title={item.title || item.raw.verdict_summary}
                  meta={`${item.source_name || 'Unknown source'} · ${item.request_count} requests · ${formatRelative(item.checked_at)}`}
                  active={factCheckId === item.story_id}
                  status={item.review.workflow_status}
                  onClick={() => setFactCheckId(item.story_id)}
                />
              ))}
            </div>
          }
          pagination={
            <QueuePagination
              page={factCheckInbox.data?.page || factCheckPage}
              totalPages={factCheckInbox.data?.total_pages || 1}
              total={factCheckInbox.data?.total || 0}
              onPageChange={setFactCheckPage}
            />
          }
        />
      }
      detail={
        !factCheckDetail.data ? (
          <div className="text-sm text-white/35">Select a fact-check from the queue.</div>
        ) : (
          <DetailColumn>
            <div className="space-y-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h3 className="text-xl font-semibold text-white">{factCheckDetail.data.title}</h3>
                  <p className="mt-1 text-sm text-white/45">
                    {factCheckDetail.data.source_name || 'Unknown source'} · {formatRelative(factCheckDetail.data.checked_at)}
                  </p>
                </div>
                {factCheckDetail.data.url && (
                  <a href={factCheckDetail.data.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 rounded-xl border border-white/10 px-3 py-2 text-sm text-white/55 hover:border-white/20 hover:text-white transition-colors">
                    <ExternalLink size={14} />
                    Source
                  </a>
                )}
              </div>

              <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                <div className="text-xs uppercase tracking-[0.22em] text-white/35">Raw System Output</div>
                <div className="mt-3 grid grid-cols-1 gap-4 lg:grid-cols-2">
                  <div>
                    <div className="text-sm text-white">Verdict</div>
                    <div className="mt-1 text-sm text-white/65">{factCheckDetail.data.raw.verdict}</div>
                  </div>
                  <div>
                    <div className="text-sm text-white">Confidence</div>
                    <div className="mt-1 text-sm text-white/65">{Math.round(factCheckDetail.data.raw.confidence * 100)}%</div>
                  </div>
                  <div className="text-sm text-white/60 lg:col-span-2">{factCheckDetail.data.raw.verdict_summary}</div>
                </div>
              </div>

              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <div>
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Final Verdict</label>
                  <input value={factCheckDraft.final_verdict} onChange={(event) => setFactCheckDraft((prev) => ({ ...prev, final_verdict: event.target.value }))} className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
                <div>
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Final Confidence</label>
                  <input value={factCheckDraft.final_confidence} onChange={(event) => setFactCheckDraft((prev) => ({ ...prev, final_confidence: event.target.value }))} className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
                <div className="lg:col-span-2">
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Final Verdict Summary</label>
                  <textarea value={factCheckDraft.final_verdict_summary} onChange={(event) => setFactCheckDraft((prev) => ({ ...prev, final_verdict_summary: event.target.value }))} className="min-h-28 w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-3 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
                <div>
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Key Finding</label>
                  <textarea value={factCheckDraft.final_key_finding} onChange={(event) => setFactCheckDraft((prev) => ({ ...prev, final_key_finding: event.target.value }))} className="min-h-24 w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-3 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
                <div>
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Context</label>
                  <textarea value={factCheckDraft.final_context} onChange={(event) => setFactCheckDraft((prev) => ({ ...prev, final_context: event.target.value }))} className="min-h-24 w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-3 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
                <div className="lg:col-span-2">
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Override Notes</label>
                  <textarea value={factCheckDraft.override_notes} onChange={(event) => setFactCheckDraft((prev) => ({ ...prev, override_notes: event.target.value }))} className="min-h-24 w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-3 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={() => setPendingAction({ type: 'factCheckSave', id: factCheckDetail.data.story_id })} className="rounded-xl border border-blue-400/20 bg-blue-500/10 px-3 py-2 text-sm text-blue-200 hover:bg-blue-500/20 transition-colors">Save Draft</button>
                <button type="button" onClick={() => setPendingAction({ type: 'factCheckApprove', id: factCheckDetail.data.story_id })} className="rounded-xl border border-emerald-400/20 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-200 hover:bg-emerald-500/20 transition-colors">Approve</button>
                <button type="button" onClick={() => setPendingAction({ type: 'factCheckReject', id: factCheckDetail.data.story_id })} className="rounded-xl border border-red-400/20 bg-red-500/10 px-3 py-2 text-sm text-red-200 hover:bg-red-500/20 transition-colors">Reject</button>
                <button type="button" onClick={() => setPendingAction({ type: 'factCheckSuppress', id: factCheckDetail.data.story_id })} className="rounded-xl border border-amber-400/20 bg-amber-500/10 px-3 py-2 text-sm text-amber-200 hover:bg-amber-500/20 transition-colors">Suppress</button>
                <button type="button" onClick={() => setPendingAction({ type: 'factCheckRerun', id: factCheckDetail.data.story_id })} className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white/60 hover:border-white/20 hover:text-white transition-colors">Request Rerun</button>
              </div>
            </div>
          </DetailColumn>
        )
      }
    />
  )

  const developingSection = (
    <SectionShell
      icon={<Sparkles size={16} />}
      title="Developing Stories"
      description="Developer overrides, verification, and BLUF reruns for fast-moving event clusters."
      queue={
        <QueueColumn
          items={
            <div className="space-y-3">
              {(clusterInbox.data?.items || []).map((item) => (
                <QueueItem
                  key={item.cluster_id}
                  title={item.headline}
                  meta={`${item.source_count} sources · ${item.story_count} stories · ${formatRelative(item.last_updated)}`}
                  active={clusterId === item.cluster_id}
                  status={item.workflow_status}
                  onClick={() => setClusterId(item.cluster_id)}
                />
              ))}
            </div>
          }
          pagination={
            <QueuePagination
              page={clusterInbox.data?.page || clusterPage}
              totalPages={clusterInbox.data?.total_pages || 1}
              total={clusterInbox.data?.total || 0}
              onPageChange={setClusterPage}
            />
          }
        />
      }
      detail={
        !clusterDetail.data ? (
          <div className="text-sm text-white/35">Select a developing story from the queue.</div>
        ) : (
          <DetailColumn>
            <div className="space-y-5">
              <div>
                <h3 className="text-xl font-semibold text-white">{clusterDetail.data.headline}</h3>
                <p className="mt-1 text-sm text-white/45">
                  {clusterDetail.data.story_count} stories · {clusterDetail.data.source_count} sources · {formatRelative(clusterDetail.data.last_updated)}
                </p>
              </div>

              <div className="rounded-2xl border border-white/10 bg-black/20 p-4 text-sm text-white/60">
                <div className="text-xs uppercase tracking-[0.22em] text-white/35">System Draft</div>
                <div className="mt-3 space-y-2">
                  <div><span className="text-white/35">Headline:</span> {clusterDetail.data.system_headline}</div>
                  <div><span className="text-white/35">Summary:</span> {clusterDetail.data.system_summary || 'No summary'}</div>
                </div>
              </div>

              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <div className="lg:col-span-2">
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Headline Override</label>
                  <input value={clusterDraft.analyst_headline} onChange={(event) => setClusterDraft((prev) => ({ ...prev, analyst_headline: event.target.value }))} className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
                <div>
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Category</label>
                  <input value={clusterDraft.analyst_category} onChange={(event) => setClusterDraft((prev) => ({ ...prev, analyst_category: event.target.value }))} className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
                <div>
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Severity</label>
                  <input value={clusterDraft.analyst_severity} onChange={(event) => setClusterDraft((prev) => ({ ...prev, analyst_severity: event.target.value }))} className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
                <div className="lg:col-span-2">
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Summary Override</label>
                  <textarea value={clusterDraft.analyst_summary} onChange={(event) => setClusterDraft((prev) => ({ ...prev, analyst_summary: event.target.value }))} className="min-h-28 w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-3 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
                <div className="lg:col-span-2">
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Internal Notes</label>
                  <textarea value={clusterDraft.analyst_notes} onChange={(event) => setClusterDraft((prev) => ({ ...prev, analyst_notes: event.target.value }))} className="min-h-24 w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-3 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
              </div>

              <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                <div className="text-xs uppercase tracking-[0.22em] text-white/35">Evidence Stories</div>
                <div className="mt-3 space-y-3">
                  {clusterDetail.data.stories.map((story) => (
                    <div key={story.id} className="rounded-xl border border-white/8 bg-white/[0.02] p-3">
                      <div className="text-sm text-white">{story.title}</div>
                      <div className="mt-1 text-xs text-white/40">{story.source_name || 'Unknown source'} · {formatRelative(story.published_at)}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={() => setPendingAction({ type: 'clusterSave', id: clusterDetail.data.cluster_id })} className="rounded-xl border border-blue-400/20 bg-blue-500/10 px-3 py-2 text-sm text-blue-200 hover:bg-blue-500/20 transition-colors">Save Draft</button>
                <button type="button" onClick={() => setPendingAction({ type: 'clusterApprove', id: clusterDetail.data.cluster_id })} className="rounded-xl border border-emerald-400/20 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-200 hover:bg-emerald-500/20 transition-colors">Approve</button>
                <button type="button" onClick={() => setPendingAction({ type: 'clusterReject', id: clusterDetail.data.cluster_id })} className="rounded-xl border border-red-400/20 bg-red-500/10 px-3 py-2 text-sm text-red-200 hover:bg-red-500/20 transition-colors">Reject</button>
                <button type="button" onClick={() => setPendingAction({ type: 'clusterRerun', id: clusterDetail.data.cluster_id })} className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white/60 hover:border-white/20 hover:text-white transition-colors">Rerun BLUF</button>
              </div>
            </div>
          </DetailColumn>
        )
      }
    />
  )

  const trackerSection = (
    <SectionShell
      icon={<Target size={16} />}
      title="Story Tracker"
      description="Narrative-level tracker controls for strategic labels, theses, approval state, and refresh requests."
      queue={
        <QueueColumn
          items={
            <div className="space-y-3">
              {(trackerInbox.data?.items || []).map((item) => (
                <QueueItem
                  key={item.narrative_id}
                  title={item.label}
                  meta={`${item.cluster_count} clusters · ${item.category || 'uncategorized'} · ${formatRelative(item.last_updated)}`}
                  active={trackerId === item.narrative_id}
                  status={item.workflow_status}
                  onClick={() => setTrackerId(item.narrative_id)}
                />
              ))}
            </div>
          }
          pagination={
            <QueuePagination
              page={trackerInbox.data?.page || trackerPage}
              totalPages={trackerInbox.data?.total_pages || 1}
              total={trackerInbox.data?.total || 0}
              onPageChange={setTrackerPage}
            />
          }
        />
      }
      detail={
        !selectedTracker ? (
          <div className="text-sm text-white/35">Select a narrative from the tracker queue.</div>
        ) : (
          <DetailColumn>
            <div className="space-y-5">
              <div>
                <h3 className="text-xl font-semibold text-white">{selectedTracker.label}</h3>
                <p className="mt-1 text-sm text-white/45">
                  {selectedTracker.cluster_count} clusters · {selectedTracker.direction || 'stable'} · {formatRelative(selectedTracker.last_updated)}
                </p>
              </div>

              <div className="grid grid-cols-1 gap-4">
                <div>
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Narrative Label</label>
                  <input value={trackerDraft.label} onChange={(event) => setTrackerDraft((prev) => ({ ...prev, label: event.target.value }))} className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
                <div>
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Thesis</label>
                  <textarea value={trackerDraft.thesis} onChange={(event) => setTrackerDraft((prev) => ({ ...prev, thesis: event.target.value }))} className="min-h-28 w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-3 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
                <div>
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Review Notes</label>
                  <textarea value={trackerDraft.review_notes} onChange={(event) => setTrackerDraft((prev) => ({ ...prev, review_notes: event.target.value }))} className="min-h-24 w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-3 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
              </div>

              <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                <div className="text-xs uppercase tracking-[0.22em] text-white/35">Linked Clusters</div>
                <div className="mt-3 space-y-3">
                  {selectedTracker.clusters.map((cluster) => (
                    <div key={cluster.cluster_id} className="rounded-xl border border-white/8 bg-white/[0.02] p-3">
                      <div className="text-sm text-white">{cluster.headline}</div>
                      <div className="mt-1 text-xs text-white/40">
                        {cluster.source_count} sources · {cluster.story_count} stories · {formatRelative(cluster.last_updated)}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={() => setPendingAction({ type: 'trackerSave', id: selectedTracker.narrative_id })} className="rounded-xl border border-blue-400/20 bg-blue-500/10 px-3 py-2 text-sm text-blue-200 hover:bg-blue-500/20 transition-colors">Save Draft</button>
                <button type="button" onClick={() => setPendingAction({ type: 'trackerApprove', id: selectedTracker.narrative_id })} className="rounded-xl border border-emerald-400/20 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-200 hover:bg-emerald-500/20 transition-colors">Approve</button>
                <button type="button" onClick={() => setPendingAction({ type: 'trackerReject', id: selectedTracker.narrative_id })} className="rounded-xl border border-red-400/20 bg-red-500/10 px-3 py-2 text-sm text-red-200 hover:bg-red-500/20 transition-colors">Reject</button>
                <button type="button" onClick={() => setPendingAction({ type: 'trackerRerun', id: selectedTracker.narrative_id })} className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white/60 hover:border-white/20 hover:text-white transition-colors">Queue Refresh</button>
              </div>
            </div>
          </DetailColumn>
        )
      }
    />
  )

  const govtDecisionSection = (
    <SectionShell
      icon={<Gavel size={16} />}
      title="Government Decisions"
      description="OpenAI-extracted government decisions from trusted news and official sites, with dev review before or after publication."
      queue={
        <QueueColumn
          items={
            <div className="space-y-3">
              {(decisionInbox.data?.items || []).map((item) => (
                <QueueItem
                  key={item.item_id}
                  title={item.effective.decision_title || item.raw.decision_title || item.representative_title || 'Untitled decision'}
                  meta={`${item.source_count} sources · ${item.effective.decision_type || item.raw.decision_type || 'unknown type'} · ${formatRelative(item.published_at)}`}
                  active={decisionId === item.item_id}
                  status={item.review.workflow_status}
                  onClick={() => setDecisionId(item.item_id)}
                />
              ))}
            </div>
          }
          pagination={
            <QueuePagination
              page={decisionInbox.data?.page || decisionPage}
              totalPages={decisionInbox.data?.total_pages || 1}
              total={decisionInbox.data?.total || 0}
              onPageChange={setDecisionPage}
            />
          }
        />
      }
      detail={
        !decisionDetail.data ? (
          <div className="text-sm text-white/35">Select a government decision from the queue.</div>
        ) : (
          <DetailColumn>
            <div className="space-y-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h3 className="text-xl font-semibold text-white">
                    {decisionDetail.data.effective.decision_title || decisionDetail.data.raw.decision_title || decisionDetail.data.representative_title}
                  </h3>
                  <p className="mt-1 text-sm text-white/45">
                    {decisionDetail.data.source_count} sources · {decisionDetail.data.review.workflow_status} · {formatRelative(decisionDetail.data.published_at)}
                  </p>
                </div>
                {(decisionDetail.data.effective.source_url || decisionDetail.data.representative_url) && (
                  <a
                    href={decisionDetail.data.effective.source_url || decisionDetail.data.representative_url || '#'}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-2 rounded-xl border border-white/10 px-3 py-2 text-sm text-white/55 hover:border-white/20 hover:text-white transition-colors"
                  >
                    <ExternalLink size={14} />
                    Source
                  </a>
                )}
              </div>

              <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                <div className="text-xs uppercase tracking-[0.22em] text-white/35">Raw System Output</div>
                <div className="mt-3 grid grid-cols-1 gap-4 lg:grid-cols-2">
                  <div>
                    <div className="text-sm text-white">Office</div>
                    <div className="mt-1 text-sm text-white/65">{decisionDetail.data.raw.office || 'Not set'}</div>
                  </div>
                  <div>
                    <div className="text-sm text-white">Confidence</div>
                    <div className="mt-1 text-sm text-white/65">
                      {decisionDetail.data.raw.confidence != null ? `${Math.round(decisionDetail.data.raw.confidence * 100)}%` : 'Not set'}
                    </div>
                  </div>
                  <div>
                    <div className="text-sm text-white">Decision Type</div>
                    <div className="mt-1 text-sm text-white/65">{decisionDetail.data.raw.decision_type || 'Not set'}</div>
                  </div>
                  <div>
                    <div className="text-sm text-white">Status</div>
                    <div className="mt-1 text-sm text-white/65">{decisionDetail.data.raw.status || 'Not set'}</div>
                  </div>
                  <div className="text-sm text-white/60 lg:col-span-2">{decisionDetail.data.raw.decision_summary || 'No system summary'}</div>
                </div>
              </div>

              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <div>
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Office</label>
                  <input value={decisionDraft.final_office} onChange={(event) => setDecisionDraft((prev) => ({ ...prev, final_office: event.target.value }))} className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
                <div>
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Implementing Ministry</label>
                  <input value={decisionDraft.final_implementing_ministry} onChange={(event) => setDecisionDraft((prev) => ({ ...prev, final_implementing_ministry: event.target.value }))} className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
                <div>
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Decision Type</label>
                  <input value={decisionDraft.final_decision_type} onChange={(event) => setDecisionDraft((prev) => ({ ...prev, final_decision_type: event.target.value }))} className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
                <div>
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Status</label>
                  <input value={decisionDraft.final_status} onChange={(event) => setDecisionDraft((prev) => ({ ...prev, final_status: event.target.value }))} className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
                <div className="lg:col-span-2">
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Decision Title</label>
                  <input value={decisionDraft.final_decision_title} onChange={(event) => setDecisionDraft((prev) => ({ ...prev, final_decision_title: event.target.value }))} className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
                <div className="lg:col-span-2">
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Decision Summary</label>
                  <textarea value={decisionDraft.final_decision_summary} onChange={(event) => setDecisionDraft((prev) => ({ ...prev, final_decision_summary: event.target.value }))} className="min-h-28 w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-3 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
                <div>
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Source Link</label>
                  <input value={decisionDraft.final_source_url} onChange={(event) => setDecisionDraft((prev) => ({ ...prev, final_source_url: event.target.value }))} className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
                <div>
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Confidence</label>
                  <input value={decisionDraft.final_confidence} onChange={(event) => setDecisionDraft((prev) => ({ ...prev, final_confidence: event.target.value }))} className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
                <div className="lg:col-span-2">
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Evidence Note</label>
                  <textarea value={decisionDraft.final_evidence_note} onChange={(event) => setDecisionDraft((prev) => ({ ...prev, final_evidence_note: event.target.value }))} className="min-h-24 w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-3 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
                <div className="lg:col-span-2">
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Reviewer Note</label>
                  <textarea value={decisionDraft.reviewer_note} onChange={(event) => setDecisionDraft((prev) => ({ ...prev, reviewer_note: event.target.value }))} className="min-h-24 w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-3 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
              </div>

              <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                <div className="text-xs uppercase tracking-[0.22em] text-white/35">Supporting Sources</div>
                <div className="mt-3 space-y-3">
                  {(decisionDetail.data.raw.supporting_sources || []).map((source) => (
                    <div key={`${source.kind}-${source.id}`} className="rounded-xl border border-white/8 bg-white/[0.02] p-3">
                      <div className="text-sm text-white">{source.title}</div>
                      <div className="mt-1 text-xs text-white/40">
                        {source.source_name} · {source.kind} · {formatRelative(source.published_at)}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={() => setPendingAction({ type: 'decisionSave', id: decisionDetail.data.item_id })} className="rounded-xl border border-blue-400/20 bg-blue-500/10 px-3 py-2 text-sm text-blue-200 hover:bg-blue-500/20 transition-colors">Save Draft</button>
                <button type="button" onClick={() => setPendingAction({ type: 'decisionApprove', id: decisionDetail.data.item_id })} className="rounded-xl border border-emerald-400/20 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-200 hover:bg-emerald-500/20 transition-colors">Approve</button>
                <button type="button" onClick={() => setPendingAction({ type: 'decisionReject', id: decisionDetail.data.item_id })} className="rounded-xl border border-red-400/20 bg-red-500/10 px-3 py-2 text-sm text-red-200 hover:bg-red-500/20 transition-colors">Reject</button>
                <button type="button" onClick={() => setPendingAction({ type: 'decisionRerun', id: decisionDetail.data.item_id })} className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white/60 hover:border-white/20 hover:text-white transition-colors">Request Rerun</button>
                <button type="button" onClick={() => setPendingAction({ type: 'decisionSupersede', id: decisionDetail.data.item_id })} className="rounded-xl border border-amber-400/20 bg-amber-500/10 px-3 py-2 text-sm text-amber-200 hover:bg-amber-500/20 transition-colors">Supersede</button>
              </div>
            </div>
          </DetailColumn>
        )
      }
    />
  )

  const cabinetActionSection = (
    <SectionShell
      icon={<Sparkles size={16} />}
      title="Cabinet Actions"
      description="Source-controlled tracker for the Balen government 100-day cabinet programme, with deadline, milestone, and evidence review."
      queue={
        <QueueColumn
          items={
            <div className="space-y-3">
              {(cabinetActionInbox.data?.items || []).map((item) => (
                <QueueItem
                  key={item.item_id}
                  title={`Item ${item.item_number}: ${item.effective.title_en || item.raw.title_en}`}
                  meta={`${item.effective.status || item.raw.status} · due ${item.raw.due_date_ad || item.raw.due_date_bs || 'unset'} · page ${item.source_pdf_page || 'n/a'}`}
                  active={cabinetActionId === item.item_id}
                  status={item.review.workflow_status}
                  onClick={() => setCabinetActionId(item.item_id)}
                />
              ))}
            </div>
          }
          pagination={
            <QueuePagination
              page={cabinetActionInbox.data?.page || cabinetActionPage}
              totalPages={cabinetActionInbox.data?.total_pages || 1}
              total={cabinetActionInbox.data?.total || 0}
              onPageChange={setCabinetActionPage}
            />
          }
        />
      }
      detail={
        !cabinetActionDetail.data ? (
          <div className="text-sm text-white/35">Select a cabinet action item from the queue.</div>
        ) : (
          <DetailColumn>
            <div className="space-y-5">
              <div>
                <h3 className="text-xl font-semibold text-white">
                  Item {cabinetActionDetail.data.item_number}: {cabinetActionDetail.data.effective.title_en || cabinetActionDetail.data.raw.title_en}
                </h3>
                <p className="mt-1 text-sm text-white/45">
                  {cabinetActionDetail.data.review.workflow_status} · due {cabinetActionDetail.data.raw.due_date_ad || cabinetActionDetail.data.raw.due_date_bs || 'unset'} · page {cabinetActionDetail.data.source_pdf_page || 'n/a'}
                </p>
              </div>

              <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                <div className="text-xs uppercase tracking-[0.22em] text-white/35">Source Record</div>
                <div className="mt-3 grid grid-cols-1 gap-4 lg:grid-cols-2">
                  <div>
                    <div className="text-sm text-white">Section</div>
                    <div className="mt-1 text-sm text-white/65">{cabinetActionDetail.data.raw.section_title_en || cabinetActionDetail.data.raw.section_key}</div>
                  </div>
                  <div>
                    <div className="text-sm text-white">Lead Institution</div>
                    <div className="mt-1 text-sm text-white/65">{cabinetActionDetail.data.raw.lead_institution || 'Not set'}</div>
                  </div>
                  <div>
                    <div className="text-sm text-white">Trackability</div>
                    <div className="mt-1 text-sm text-white/65">{cabinetActionDetail.data.raw.trackability_class}</div>
                  </div>
                  <div>
                    <div className="text-sm text-white">Status</div>
                    <div className="mt-1 text-sm text-white/65">{cabinetActionDetail.data.raw.status}</div>
                  </div>
                  <div className="text-sm text-white/60 lg:col-span-2">{cabinetActionDetail.data.raw.summary_en}</div>
                  <div className="rounded-xl border border-white/8 bg-white/[0.02] p-3 text-sm text-white/55 lg:col-span-2">
                    {cabinetActionDetail.data.raw.source_text_ne}
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <div>
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Section Key</label>
                  <input value={cabinetActionDraft.final_section_key} onChange={(event) => setCabinetActionDraft((prev) => ({ ...prev, final_section_key: event.target.value }))} className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
                <div>
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Section Title</label>
                  <input value={cabinetActionDraft.final_section_title_en} onChange={(event) => setCabinetActionDraft((prev) => ({ ...prev, final_section_title_en: event.target.value }))} className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
                <div className="lg:col-span-2">
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">English Title</label>
                  <input value={cabinetActionDraft.final_title_en} onChange={(event) => setCabinetActionDraft((prev) => ({ ...prev, final_title_en: event.target.value }))} className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
                <div className="lg:col-span-2">
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">English Summary</label>
                  <textarea value={cabinetActionDraft.final_summary_en} onChange={(event) => setCabinetActionDraft((prev) => ({ ...prev, final_summary_en: event.target.value }))} className="min-h-28 w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-3 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
                <div>
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Lead Institution</label>
                  <input value={cabinetActionDraft.final_lead_institution} onChange={(event) => setCabinetActionDraft((prev) => ({ ...prev, final_lead_institution: event.target.value }))} className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
                <div>
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Action Type</label>
                  <input value={cabinetActionDraft.final_action_type} onChange={(event) => setCabinetActionDraft((prev) => ({ ...prev, final_action_type: event.target.value }))} className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
                <div>
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Trackability</label>
                  <input value={cabinetActionDraft.final_trackability_class} onChange={(event) => setCabinetActionDraft((prev) => ({ ...prev, final_trackability_class: event.target.value }))} className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
                <div>
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Status</label>
                  <input value={cabinetActionDraft.final_status} onChange={(event) => setCabinetActionDraft((prev) => ({ ...prev, final_status: event.target.value }))} className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
                <div className="lg:col-span-2">
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Supporting Institutions (comma separated)</label>
                  <input value={cabinetActionDraft.final_supporting_institutions} onChange={(event) => setCabinetActionDraft((prev) => ({ ...prev, final_supporting_institutions: event.target.value }))} className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
                <div>
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Confidence</label>
                  <input value={cabinetActionDraft.final_confidence} onChange={(event) => setCabinetActionDraft((prev) => ({ ...prev, final_confidence: event.target.value }))} className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
                <div>
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Manifesto Links (comma separated)</label>
                  <input value={cabinetActionDraft.final_manifesto_promise_ids} onChange={(event) => setCabinetActionDraft((prev) => ({ ...prev, final_manifesto_promise_ids: event.target.value }))} className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
                <div className="lg:col-span-2">
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Evidence Note</label>
                  <textarea value={cabinetActionDraft.final_evidence_note} onChange={(event) => setCabinetActionDraft((prev) => ({ ...prev, final_evidence_note: event.target.value }))} className="min-h-24 w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-3 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
                <div className="lg:col-span-2">
                  <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-white/35">Reviewer Note</label>
                  <textarea value={cabinetActionDraft.reviewer_note} onChange={(event) => setCabinetActionDraft((prev) => ({ ...prev, reviewer_note: event.target.value }))} className="min-h-24 w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-3 text-sm text-white focus:border-blue-500/50 focus:outline-none" />
                </div>
              </div>

              <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                <div className="text-xs uppercase tracking-[0.22em] text-white/35">Milestones</div>
                <div className="mt-3 space-y-3">
                  {cabinetActionDetail.data.milestones.map((milestone) => (
                    <div key={milestone.id} className="rounded-xl border border-white/8 bg-white/[0.02] p-3">
                      <div className="text-sm text-white">#{milestone.milestone_order} {milestone.title_en}</div>
                      <div className="mt-1 text-xs text-white/45">{milestone.status} · due {milestone.due_date_ad || milestone.due_date_bs || 'unset'}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={() => setPendingAction({ type: 'cabinetSave', id: cabinetActionDetail.data.item_id })} className="rounded-xl border border-blue-400/20 bg-blue-500/10 px-3 py-2 text-sm text-blue-200 hover:bg-blue-500/20 transition-colors">Save Draft</button>
                <button type="button" onClick={() => setPendingAction({ type: 'cabinetApprove', id: cabinetActionDetail.data.item_id })} className="rounded-xl border border-emerald-400/20 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-200 hover:bg-emerald-500/20 transition-colors">Approve</button>
                <button type="button" onClick={() => setPendingAction({ type: 'cabinetReject', id: cabinetActionDetail.data.item_id })} className="rounded-xl border border-red-400/20 bg-red-500/10 px-3 py-2 text-sm text-red-200 hover:bg-red-500/20 transition-colors">Reject</button>
                <button type="button" onClick={() => setPendingAction({ type: 'cabinetRerun', id: cabinetActionDetail.data.item_id })} className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white/60 hover:border-white/20 hover:text-white transition-colors">Request Rerun</button>
              </div>
            </div>
          </DetailColumn>
        )
      }
    />
  )

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap gap-2">
        {sectionTabs.map((section) => (
          <button
            key={section.key}
            type="button"
            onClick={() => setActiveSection(section.key)}
            className={`rounded-xl border px-3 py-2 text-sm transition-colors ${
              activeSection === section.key
                ? 'border-blue-400/30 bg-blue-500/10 text-blue-200'
                : 'border-white/10 bg-white/[0.03] text-white/55 hover:border-white/20 hover:text-white'
            }`}
          >
            {section.label}
            <span className="ml-2 text-white/35">{section.count}</span>
          </button>
        ))}
      </div>

      {activeSection === 'fact-checks' && factCheckSection}
      {activeSection === 'developing' && developingSection}
      {activeSection === 'tracker' && trackerSection}
      {activeSection === 'govt-decisions' && govtDecisionSection}
      {activeSection === 'cabinet-actions' && cabinetActionSection}

      {pendingAction && modalCopy && (
        <ActionReasonModal
          isOpen
          title={modalCopy.title}
          description={modalCopy.description}
          confirmLabel={modalCopy.confirmLabel}
          isLoading={actionMutation.isPending}
          onClose={() => setPendingAction(null)}
          onConfirm={(reason) => actionMutation.mutate({ action: pendingAction, reason })}
        />
      )}
    </section>
  )
}
