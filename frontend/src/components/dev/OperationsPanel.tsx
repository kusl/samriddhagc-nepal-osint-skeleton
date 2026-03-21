import { useState, useEffect } from 'react'
import { Play, Loader2, CheckCircle2, XCircle, Newspaper, CloudSun, Landmark, Radio, Brain, Shield } from 'lucide-react'
import {
  triggerRssIngestion,
  triggerWebScraping,
  triggerNitterAccounts,
  triggerNitterHashtags,
  triggerBipadIngestion,
  triggerGeeChangeDetection,
  triggerParliamentSync,
  triggerRecalculateScores,
  triggerAnalystAgent,
  fetchNitterStatus,
} from '../../api/operations'
import {
  clearSourceOverride,
  getSources,
  rateSource,
  recomputeSources,
  type SourceReliability,
} from '../../api/collaboration'

type TriggerStatus = 'idle' | 'loading' | 'success' | 'error'

interface TriggerButton {
  id: string
  label: string
  description: string
  action: () => Promise<any>
}

interface TriggerGroup {
  title: string
  icon: React.ReactNode
  triggers: TriggerButton[]
}

const GROUPS: TriggerGroup[] = [
  {
    title: 'News & Social',
    icon: <Newspaper size={16} />,
    triggers: [
      { id: 'rss-priority', label: 'RSS Ingestion (Priority)', description: 'Ingest priority RSS sources only', action: () => triggerRssIngestion(true) },
      { id: 'rss-all', label: 'RSS Ingestion (All)', description: 'Ingest all configured RSS feeds', action: () => triggerRssIngestion(false) },
      { id: 'scrape-all', label: 'Web Scraping (All)', description: 'Scrape Ratopati, Ekantipur, etc.', action: triggerWebScraping },
      { id: 'nitter-accounts', label: 'Nitter Accounts', description: 'Scrape Twitter account timelines', action: triggerNitterAccounts },
      { id: 'nitter-hashtags', label: 'Nitter Hashtags', description: 'Scrape Twitter hashtag search', action: triggerNitterHashtags },
    ],
  },
  {
    title: 'Disasters & Environment',
    icon: <CloudSun size={16} />,
    triggers: [
      { id: 'bipad', label: 'BIPAD Disasters', description: 'Ingest incidents, flood warnings, rainfall, forest fires, pollution', action: triggerBipadIngestion },
      { id: 'gee', label: 'GEE Change Detection', description: 'Run satellite change analysis', action: triggerGeeChangeDetection },
    ],
  },
  {
    title: 'Elections & Parliament',
    icon: <Landmark size={16} />,
    triggers: [
      { id: 'parliament-sync', label: 'Parliament Full Sync', description: 'Sync MPs, bills, committees', action: triggerParliamentSync },
      { id: 'recalc-scores', label: 'Recalculate Scores', description: 'Recalculate MP performance scores', action: triggerRecalculateScores },
    ],
  },
  {
    title: 'Intelligence',
    icon: <Brain size={16} />,
    triggers: [
      { id: 'analyst-3h', label: 'Analyst Agent (3h)', description: 'Run situation brief for last 3 hours', action: () => triggerAnalystAgent(3) },
      { id: 'analyst-6h', label: 'Analyst Agent (6h)', description: 'Run situation brief for last 6 hours', action: () => triggerAnalystAgent(6) },
      { id: 'analyst-12h', label: 'Analyst Agent (12h)', description: 'Run situation brief for last 12 hours', action: () => triggerAnalystAgent(12) },
    ],
  },
]

function TriggerCard({ trigger }: { trigger: TriggerButton }) {
  const [status, setStatus] = useState<TriggerStatus>('idle')
  const [errorMsg, setErrorMsg] = useState('')

  const handleRun = async () => {
    setStatus('loading')
    setErrorMsg('')
    try {
      await trigger.action()
      setStatus('success')
      setTimeout(() => setStatus('idle'), 3000)
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || err?.message || 'Failed')
      setStatus('error')
      setTimeout(() => setStatus('idle'), 5000)
    }
  }

  return (
    <div className="flex items-center justify-between gap-4 px-4 py-3 bg-white/[0.02] border border-white/[0.06] rounded-lg hover:border-white/[0.12] transition-colors">
      <div className="min-w-0">
        <p className="text-sm font-medium text-white">{trigger.label}</p>
        <p className="text-xs text-white/40 mt-0.5">{trigger.description}</p>
        {status === 'error' && errorMsg && (
          <p className="text-xs text-red-400 mt-1">{errorMsg}</p>
        )}
      </div>
      <button
        onClick={handleRun}
        disabled={status === 'loading'}
        className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-all shrink-0
          ${status === 'success'
            ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
            : status === 'error'
              ? 'bg-red-500/20 text-red-400 border border-red-500/30'
              : 'bg-blue-500/10 text-blue-400 border border-blue-500/20 hover:bg-blue-500/20 hover:border-blue-500/30 disabled:opacity-50'
          }`}
      >
        {status === 'loading' && <Loader2 size={13} className="animate-spin" />}
        {status === 'success' && <CheckCircle2 size={13} />}
        {status === 'error' && <XCircle size={13} />}
        {status === 'idle' && <Play size={13} />}
        {status === 'loading' ? 'Running…' : status === 'success' ? 'Done' : status === 'error' ? 'Failed' : 'Run'}
      </button>
    </div>
  )
}

function NitterStatusCard() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchNitterStatus()
      .then((res) => setData(res.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="bg-white/[0.02] border border-white/[0.06] rounded-lg p-4">
      <div className="flex items-center gap-2.5 mb-3">
        <Radio size={16} className="text-white/40" />
        <h3 className="text-sm font-medium text-white">Nitter Status</h3>
      </div>
      {loading ? (
        <div className="flex items-center gap-2 text-xs text-white/40">
          <Loader2 size={12} className="animate-spin" /> Loading…
        </div>
      ) : data ? (
        <div className="space-y-1.5 text-xs">
          {data.instances && (
            <div className="flex justify-between">
              <span className="text-white/40">Instances</span>
              <span className="text-white font-mono">{Array.isArray(data.instances) ? data.instances.length : '—'}</span>
            </div>
          )}
          {data.last_scrape && (
            <div className="flex justify-between">
              <span className="text-white/40">Last scrape</span>
              <span className="text-white font-mono">{new Date(data.last_scrape).toLocaleString()}</span>
            </div>
          )}
          {data.status && (
            <div className="flex justify-between">
              <span className="text-white/40">Status</span>
              <span className={`font-mono ${data.status === 'healthy' ? 'text-emerald-400' : 'text-amber-400'}`}>{data.status}</span>
            </div>
          )}
          {typeof data === 'object' && !data.instances && !data.last_scrape && !data.status && (
            <pre className="text-white/60 font-mono whitespace-pre-wrap break-all">{JSON.stringify(data, null, 2)}</pre>
          )}
        </div>
      ) : (
        <p className="text-xs text-white/30">Unable to fetch status</p>
      )}
    </div>
  )
}

function SourceReliabilityControls() {
  const [sources, setSources] = useState<SourceReliability[]>([])
  const [selectedSourceId, setSelectedSourceId] = useState('')
  const [rating, setRating] = useState('B')
  const [credibility, setCredibility] = useState(2)
  const [notes, setNotes] = useState('')
  const [loadingSources, setLoadingSources] = useState(true)
  const [running, setRunning] = useState<'idle' | 'recompute-all' | 'recompute-one' | 'override' | 'clear'>('idle')
  const [message, setMessage] = useState<string>('')
  const [error, setError] = useState<string>('')

  const loadSources = async () => {
    setLoadingSources(true)
    try {
      const data = await getSources({ sort_by: 'confidence', limit: 20 })
      setSources(data)
      if (!selectedSourceId && data.length > 0) {
        setSelectedSourceId(data[0].source_id)
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to load sources')
    } finally {
      setLoadingSources(false)
    }
  }

  useEffect(() => {
    loadSources()
  }, [])

  const runAction = async (mode: 'recompute-all' | 'recompute-one' | 'override' | 'clear', fn: () => Promise<void>) => {
    setRunning(mode)
    setMessage('')
    setError('')
    try {
      await fn()
      await loadSources()
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Operation failed')
    } finally {
      setRunning('idle')
    }
  }

  return (
    <div className="bg-white/[0.02] border border-white/[0.06] rounded-lg p-4 space-y-3">
      <div className="flex items-center gap-2.5">
        <Shield size={16} className="text-white/40" />
        <h3 className="text-sm font-medium text-white">Source Reliability</h3>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[1fr_auto_auto] gap-2">
        <select
          value={selectedSourceId}
          onChange={(e) => setSelectedSourceId(e.target.value)}
          className="bg-black/20 border border-white/[0.08] rounded-md px-3 py-2 text-sm text-white"
          disabled={loadingSources}
        >
          {sources.map((source) => (
            <option key={source.source_id} value={source.source_id}>
              {source.source_name} ({source.admiralty_code})
            </option>
          ))}
        </select>
        <button
          onClick={() => runAction('recompute-all', async () => {
            const result = await recomputeSources({ limit: 20, lookback_days: 90 })
            setMessage(`Recomputed ${result.updated}/${result.processed} active sources`)
          })}
          disabled={running !== 'idle'}
          className="px-3 py-2 text-xs font-medium rounded-md bg-blue-500/10 text-blue-400 border border-blue-500/20 hover:bg-blue-500/20 disabled:opacity-50"
        >
          {running === 'recompute-all' ? 'Running…' : 'Recompute Active'}
        </button>
        <button
          onClick={() => runAction('recompute-one', async () => {
            const result = await recomputeSources({ source_id: selectedSourceId, limit: 1, lookback_days: 90 })
            setMessage(`Recomputed ${result.updated}/${result.processed} selected source`)
          })}
          disabled={running !== 'idle' || !selectedSourceId}
          className="px-3 py-2 text-xs font-medium rounded-md bg-white/[0.04] text-white border border-white/[0.08] hover:border-white/[0.16] disabled:opacity-50"
        >
          {running === 'recompute-one' ? 'Running…' : 'Recompute One'}
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[1fr_100px_1fr_auto_auto] gap-2">
        <select
          value={rating}
          onChange={(e) => setRating(e.target.value)}
          className="bg-black/20 border border-white/[0.08] rounded-md px-3 py-2 text-sm text-white"
        >
          {['A', 'B', 'C', 'D', 'E'].map((grade) => (
            <option key={grade} value={grade}>{grade}</option>
          ))}
        </select>
        <select
          value={credibility}
          onChange={(e) => setCredibility(Number(e.target.value))}
          className="bg-black/20 border border-white/[0.08] rounded-md px-3 py-2 text-sm text-white"
        >
          {[1, 2, 3, 4].map((value) => (
            <option key={value} value={value}>{value}</option>
          ))}
        </select>
        <input
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Override notes..."
          className="bg-black/20 border border-white/[0.08] rounded-md px-3 py-2 text-sm text-white placeholder:text-white/30"
        />
        <button
          onClick={() => runAction('override', async () => {
            const source = await rateSource(selectedSourceId, { reliability_rating: rating, credibility_rating: credibility, notes })
            setMessage(`Pinned ${source.source_name} to ${source.admiralty_code}`)
          })}
          disabled={running !== 'idle' || !selectedSourceId}
          className="px-3 py-2 text-xs font-medium rounded-md bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20 disabled:opacity-50"
        >
          {running === 'override' ? 'Saving…' : 'Set Override'}
        </button>
        <button
          onClick={() => runAction('clear', async () => {
            const source = await clearSourceOverride(selectedSourceId)
            setMessage(`Restored automated rating for ${source.source_name}`)
          })}
          disabled={running !== 'idle' || !selectedSourceId}
          className="px-3 py-2 text-xs font-medium rounded-md bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 disabled:opacity-50"
        >
          {running === 'clear' ? 'Clearing…' : 'Clear Override'}
        </button>
      </div>

      {loadingSources && <p className="text-xs text-white/40">Loading active sources…</p>}
      {!!message && <p className="text-xs text-emerald-400">{message}</p>}
      {!!error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  )
}

export function OperationsPanel() {
  return (
    <div className="space-y-8">
      {GROUPS.map((group) => (
        <section key={group.title}>
          <div className="flex items-center gap-2.5 mb-3">
            <div className="text-white/40">{group.icon}</div>
            <h2 className="text-sm font-semibold text-white tracking-tight">{group.title}</h2>
          </div>
          <div className="space-y-2">
            {group.triggers.map((trigger) => (
              <TriggerCard key={trigger.id} trigger={trigger} />
            ))}
          </div>
        </section>
      ))}

      {/* Status readout */}
      <section>
        <h2 className="text-sm font-semibold text-white tracking-tight mb-3">Status Readout</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <NitterStatusCard />
          <SourceReliabilityControls />
        </div>
      </section>
    </div>
  )
}
