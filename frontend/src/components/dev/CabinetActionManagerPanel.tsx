import { useEffect, useMemo, useState } from 'react'
import { ClipboardList, Search, Save, Loader2, CheckCircle2, AlertTriangle } from 'lucide-react'

import {
  type CabinetActionEditorialItem,
  fetchCabinetActionInbox,
  quickUpdateCabinetAction,
} from '../../api/editorial'

const STATUS_OPTIONS = [
  { value: 'not_started', label: 'Not Started', color: '#71717A' },
  { value: 'announced', label: 'Announced', color: '#60A5FA' },
  { value: 'implementation_started', label: 'Implementation Started', color: '#3B82F6' },
  { value: 'partially_completed', label: 'Partial', color: '#EAB308' },
  { value: 'completed_on_time', label: 'Completed On Time', color: '#22C55E' },
  { value: 'completed_late', label: 'Completed Late', color: '#84CC16' },
  { value: 'overdue', label: 'Overdue', color: '#F87171' },
  { value: 'cannot_verify', label: 'Cannot Verify', color: '#A78BFA' },
  { value: 'declaratory_non_scored', label: 'Declaratory', color: '#94A3B8' },
] as const

const STATUS_COLOR_MAP: Record<string, string> = Object.fromEntries(
  STATUS_OPTIONS.map((option) => [option.value, option.color]),
)

type PendingChange = {
  status: string
}

function getEffectiveStatus(item: CabinetActionEditorialItem): string {
  return item.review.final_status || item.raw.status
}

function getEffectiveTitle(item: CabinetActionEditorialItem): string {
  return item.review.final_title_en || item.raw.title_en
}

function getEffectiveSection(item: CabinetActionEditorialItem): string {
  return item.review.final_section_title_en || item.raw.section_title_en || item.raw.section_key
}

function getEffectiveInstitution(item: CabinetActionEditorialItem): string {
  return item.review.final_lead_institution || item.raw.lead_institution || 'Unassigned'
}

export function CabinetActionManagerPanel() {
  const [items, setItems] = useState<CabinetActionEditorialItem[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [sectionFilter, setSectionFilter] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<string | null>(null)
  const [pendingChanges, setPendingChanges] = useState<Record<string, PendingChange>>({})
  const [saving, setSaving] = useState<Record<string, 'saving' | 'saved' | 'error'>>({})

  useEffect(() => {
    void fetchItems()
  }, [])

  async function fetchItems() {
    setLoading(true)
    try {
      const response = await fetchCabinetActionInbox({ page: 1, per_page: 200 })
      setItems(response.items)
    } finally {
      setLoading(false)
    }
  }

  const sections = useMemo(() => {
    const values = new Set(items.map((item) => getEffectiveSection(item)))
    return Array.from(values).sort((a, b) => a.localeCompare(b))
  }, [items])

  const stats = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const item of items) {
      const effective = pendingChanges[item.item_id]?.status ?? getEffectiveStatus(item)
      counts[effective] = (counts[effective] || 0) + 1
    }
    return counts
  }, [items, pendingChanges])

  const filtered = useMemo(() => {
    let list = items

    if (sectionFilter) {
      list = list.filter((item) => getEffectiveSection(item) === sectionFilter)
    }
    if (statusFilter) {
      list = list.filter((item) => (pendingChanges[item.item_id]?.status ?? getEffectiveStatus(item)) === statusFilter)
    }
    if (search.trim()) {
      const query = search.toLowerCase()
      list = list.filter((item) => {
        const institution = getEffectiveInstitution(item).toLowerCase()
        const section = getEffectiveSection(item).toLowerCase()
        const title = getEffectiveTitle(item).toLowerCase()
        return (
          title.includes(query) ||
          institution.includes(query) ||
          section.includes(query) ||
          String(item.item_number).includes(query)
        )
      })
    }

    return list
  }, [items, pendingChanges, search, sectionFilter, statusFilter])

  function handleStatusChange(itemId: string, status: string) {
    setPendingChanges((previous) => ({
      ...previous,
      [itemId]: { status },
    }))
  }

  async function saveChange(itemId: string) {
    const change = pendingChanges[itemId]
    if (!change) return

    setSaving((previous) => ({ ...previous, [itemId]: 'saving' }))
    try {
      const updated = await quickUpdateCabinetAction(itemId, { status: change.status })
      setItems((previous) => previous.map((item) => (item.item_id === itemId ? updated : item)))
      setPendingChanges((previous) => {
        const next = { ...previous }
        delete next[itemId]
        return next
      })
      setSaving((previous) => ({ ...previous, [itemId]: 'saved' }))
      window.setTimeout(() => {
        setSaving((previous) => {
          const next = { ...previous }
          delete next[itemId]
          return next
        })
      }, 1800)
    } catch {
      setSaving((previous) => ({ ...previous, [itemId]: 'error' }))
    }
  }

  async function saveAll() {
    for (const itemId of Object.keys(pendingChanges)) {
      await saveChange(itemId)
    }
  }

  const pendingCount = Object.keys(pendingChanges).length

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 size={20} className="animate-spin text-white/30" />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <ClipboardList size={18} className="text-blue-400" />
          <div>
            <h2 className="text-sm font-semibold text-white">Cabinet Action Tracker</h2>
            <p className="text-xs text-white/40">{items.length} actions · Toggle statuses manually</p>
          </div>
        </div>
        {pendingCount > 0 && (
          <button
            onClick={saveAll}
            className="flex items-center gap-2 rounded-md border border-blue-500/30 bg-blue-500/20 px-3 py-1.5 text-xs font-medium text-blue-400 transition-all hover:bg-blue-500/30"
          >
            <Save size={13} />
            Save All ({pendingCount})
          </button>
        )}
      </div>

      <div className="flex flex-wrap gap-4 rounded-md border border-white/[0.06] bg-white/[0.03] px-3 py-2.5">
        {STATUS_OPTIONS.map((status) => (
          <div key={status.value} className="flex items-center gap-2 text-xs">
            <div className="h-2 w-2 rounded-full" style={{ background: status.color }} />
            <span className="text-white/50">{status.label}</span>
            <span className="font-mono font-bold text-white/80">{stats[status.value] || 0}</span>
          </div>
        ))}
      </div>

      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-white/30" />
          <input
            type="text"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search cabinet actions..."
            className="w-full rounded-md border border-white/[0.08] bg-white/[0.04] py-1.5 pl-8 pr-3 text-xs text-white placeholder:text-white/25 focus:border-blue-500/40 focus:outline-none"
          />
        </div>
        <select
          value={sectionFilter || ''}
          onChange={(event) => setSectionFilter(event.target.value || null)}
          className="rounded-md border border-white/[0.08] bg-white/[0.04] px-2 py-1.5 text-xs text-white/70 focus:border-blue-500/40 focus:outline-none"
        >
          <option value="">All Sections</option>
          {sections.map((section) => (
            <option key={section} value={section}>
              {section}
            </option>
          ))}
        </select>
        <select
          value={statusFilter || ''}
          onChange={(event) => setStatusFilter(event.target.value || null)}
          className="rounded-md border border-white/[0.08] bg-white/[0.04] px-2 py-1.5 text-xs text-white/70 focus:border-blue-500/40 focus:outline-none"
        >
          <option value="">All Statuses</option>
          {STATUS_OPTIONS.map((status) => (
            <option key={status.value} value={status.value}>
              {status.label}
            </option>
          ))}
        </select>
      </div>

      <div className="overflow-hidden rounded-md border border-white/[0.06]">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-white/[0.03] text-left text-white/40">
              <th className="w-16 px-3 py-2 font-medium">Item</th>
              <th className="px-3 py-2 font-medium">Action</th>
              <th className="w-44 px-3 py-2 font-medium">Section</th>
              <th className="w-40 px-3 py-2 font-medium">Institution</th>
              <th className="w-40 px-3 py-2 font-medium">Status</th>
              <th className="w-20 px-3 py-2 font-medium">Action</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((item) => {
              const effectiveStatus = pendingChanges[item.item_id]?.status ?? getEffectiveStatus(item)
              const hasChange = Boolean(pendingChanges[item.item_id])
              const saveState = saving[item.item_id]
              const statusColor = STATUS_COLOR_MAP[effectiveStatus] || '#94A3B8'

              return (
                <tr
                  key={item.item_id}
                  className={`border-t border-white/[0.04] transition-colors ${hasChange ? 'bg-blue-500/[0.04]' : 'hover:bg-white/[0.02]'}`}
                >
                  <td className="px-3 py-2 font-mono text-white/50">#{item.item_number}</td>
                  <td className="px-3 py-2">
                    <div className="leading-snug text-white/85">{getEffectiveTitle(item)}</div>
                    <div className="mt-0.5 text-[10px] text-white/35">
                      {item.raw.due_date_ad ? `Due ${item.raw.due_date_ad}` : 'No explicit due date'}
                    </div>
                  </td>
                  <td className="px-3 py-2 text-[10px] text-white/45">{getEffectiveSection(item)}</td>
                  <td className="px-3 py-2 text-[10px] text-white/45">{getEffectiveInstitution(item)}</td>
                  <td className="px-3 py-2">
                    <select
                      value={effectiveStatus}
                      onChange={(event) => handleStatusChange(item.item_id, event.target.value)}
                      className="w-full rounded border px-2 py-1 text-[11px] font-medium focus:outline-none"
                      style={{
                        background: `${statusColor}15`,
                        borderColor: `${statusColor}40`,
                        color: statusColor,
                      }}
                    >
                      {STATUS_OPTIONS.map((status) => (
                        <option key={status.value} value={status.value} style={{ background: '#1C2127', color: '#F6F7F9' }}>
                          {status.label}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-3 py-2">
                    {hasChange && !saveState && (
                      <button
                        onClick={() => saveChange(item.item_id)}
                        className="flex items-center gap-1 rounded bg-blue-500/20 px-2 py-1 text-[10px] font-medium text-blue-400 transition-all hover:bg-blue-500/30"
                      >
                        <Save size={10} />
                        Save
                      </button>
                    )}
                    {saveState === 'saving' && <Loader2 size={13} className="animate-spin text-blue-400" />}
                    {saveState === 'saved' && <CheckCircle2 size={13} className="text-emerald-400" />}
                    {saveState === 'error' && <AlertTriangle size={13} className="text-red-400" />}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {filtered.length === 0 && (
        <div className="py-8 text-center text-xs text-white/30">No cabinet actions found</div>
      )}
    </div>
  )
}
