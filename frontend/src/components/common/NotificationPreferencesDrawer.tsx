import { useEffect, useMemo, useState } from 'react'
import { X } from 'lucide-react'
import type { NotificationPreferences, NotificationSeverity } from '../../api/notifications'
import { DISTRICTS, getProvinceForDistrict } from '../../data/districts'
import { TOPICS, type TopicId, useUserPreferencesStore } from '../../store/slices/userPreferencesSlice'

interface NotificationPreferencesDrawerProps {
  open: boolean
  preferences: NotificationPreferences | undefined
  isSaving: boolean
  onClose: () => void
  onSave: (payload: {
    notifications_enabled: boolean
    include_major_alerts: boolean
    min_severity: NotificationSeverity
    home_district: string | null
    followed_districts: string[]
    followed_provinces: string[]
    followed_topics: string[]
  }) => void
}

export function NotificationPreferencesDrawer({
  open,
  preferences,
  isSaving,
  onClose,
  onSave,
}: NotificationPreferencesDrawerProps) {
  const { selectedDistricts, selectedTopics, homeDistrict } = useUserPreferencesStore()
  const [notificationsEnabled, setNotificationsEnabled] = useState(true)
  const [includeMajorAlerts, setIncludeMajorAlerts] = useState(true)
  const [minSeverity, setMinSeverity] = useState<NotificationSeverity>('high')
  const [draftHomeDistrict, setDraftHomeDistrict] = useState<string | null>(null)
  const [draftDistricts, setDraftDistricts] = useState<string[]>([])
  const [draftTopics, setDraftTopics] = useState<string[]>([])

  useEffect(() => {
    if (!open) return
    setNotificationsEnabled(preferences?.notifications_enabled ?? true)
    setIncludeMajorAlerts(preferences?.include_major_alerts ?? true)
    setMinSeverity(preferences?.min_severity ?? 'high')
    setDraftHomeDistrict(preferences?.home_district ?? homeDistrict ?? null)
    setDraftDistricts(preferences?.followed_districts ?? selectedDistricts ?? [])
    setDraftTopics(preferences?.followed_topics ?? selectedTopics ?? ['disasters', 'elections'])
  }, [open, preferences, selectedDistricts, selectedTopics, homeDistrict])

  const provinces = useMemo(() => {
    return Array.from(new Set(draftDistricts.map((district) => getProvinceForDistrict(district)).filter(Boolean))) as string[]
  }, [draftDistricts])

  if (!open) return null

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 140, display: 'flex', justifyContent: 'flex-end', background: 'rgba(3, 8, 18, 0.72)' }}>
      <button
        aria-label="Close notification preferences"
        onClick={onClose}
        style={{ position: 'absolute', inset: 0, background: 'transparent', border: 'none' }}
      />
      <aside style={{
        position: 'relative',
        width: 'min(460px, 100vw)',
        height: '100%',
        background: 'linear-gradient(180deg, rgba(7,12,24,0.98) 0%, rgba(6,10,18,0.98) 100%)',
        borderLeft: '1px solid rgba(120, 144, 176, 0.22)',
        boxShadow: '-16px 0 48px rgba(0,0,0,0.45)',
        display: 'flex',
        flexDirection: 'column',
      }}>
        <div style={{ padding: '18px 18px 14px', borderBottom: '1px solid rgba(120, 144, 176, 0.18)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.16em', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
              Notification Preferences
            </div>
            <h3 style={{ margin: '6px 0 0', fontSize: 24, lineHeight: 1.1, color: 'var(--text-primary)' }}>
              Personal alerts
            </h3>
          </div>
          <button className="navbar-btn" onClick={onClose} title="Close">
            <X size={14} />
          </button>
        </div>

        <div style={{ padding: 18, overflowY: 'auto', display: 'grid', gap: 18 }}>
          <section style={{ display: 'grid', gap: 12 }}>
            <label style={{ display: 'flex', justifyContent: 'space-between', gap: 16, fontSize: 13, color: 'var(--text-secondary)' }}>
              <span>Pause notifications</span>
              <input type="checkbox" checked={!notificationsEnabled} onChange={(e) => setNotificationsEnabled(!e.target.checked)} />
            </label>
            <label style={{ display: 'flex', justifyContent: 'space-between', gap: 16, fontSize: 13, color: 'var(--text-secondary)' }}>
              <span>Include major Nepal alerts</span>
              <input type="checkbox" checked={includeMajorAlerts} onChange={(e) => setIncludeMajorAlerts(e.target.checked)} />
            </label>
            <label style={{ display: 'grid', gap: 6 }}>
              <span style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.14em', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                Severity threshold
              </span>
              <select
                value={minSeverity}
                onChange={(e) => setMinSeverity(e.target.value as NotificationSeverity)}
                style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(120, 144, 176, 0.2)', color: 'var(--text-primary)', padding: '10px 12px' }}
              >
                <option value="low">All alerts</option>
                <option value="medium">Medium and above</option>
                <option value="high">Important only</option>
                <option value="critical">Critical only</option>
              </select>
            </label>
          </section>

          <section style={{ display: 'grid', gap: 10 }}>
            <label style={{ display: 'grid', gap: 6 }}>
              <span style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.14em', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                Home district
              </span>
              <select
                value={draftHomeDistrict ?? ''}
                onChange={(e) => setDraftHomeDistrict(e.target.value || null)}
                style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(120, 144, 176, 0.2)', color: 'var(--text-primary)', padding: '10px 12px' }}
              >
                <option value="">None</option>
                {DISTRICTS.map((district) => (
                  <option key={district.name} value={district.name}>
                    {district.name}
                  </option>
                ))}
              </select>
            </label>
            <div style={{ display: 'grid', gap: 8 }}>
              <span style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.14em', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                Followed districts
              </span>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, maxHeight: 180, overflowY: 'auto', paddingRight: 4 }}>
                {DISTRICTS.map((district) => {
                  const selected = draftDistricts.includes(district.name)
                  return (
                    <button
                      key={district.name}
                      type="button"
                      onClick={() => {
                        setDraftDistricts((current) =>
                          current.includes(district.name)
                            ? current.filter((item) => item !== district.name)
                            : [...current, district.name],
                        )
                      }}
                      style={{
                        border: selected ? '1px solid rgba(59,130,246,0.8)' : '1px solid rgba(120, 144, 176, 0.18)',
                        background: selected ? 'rgba(30, 64, 175, 0.28)' : 'rgba(255,255,255,0.02)',
                        color: selected ? 'var(--text-primary)' : 'var(--text-secondary)',
                        padding: '7px 10px',
                        fontSize: 12,
                        fontFamily: 'var(--font-mono)',
                      }}
                    >
                      {district.name}
                    </button>
                  )
                })}
              </div>
            </div>
          </section>

          <section style={{ display: 'grid', gap: 8 }}>
            <span style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.14em', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
              Followed topics
            </span>
            <div style={{ display: 'grid', gap: 8 }}>
              {TOPICS.map((topic) => {
                const selected = draftTopics.includes(topic.id)
                return (
                  <label key={topic.id} style={{
                    display: 'grid',
                    gridTemplateColumns: '18px 1fr',
                    gap: 10,
                    alignItems: 'start',
                    padding: '10px 12px',
                    border: '1px solid rgba(120, 144, 176, 0.18)',
                    background: selected ? 'rgba(16, 76, 157, 0.16)' : 'rgba(255,255,255,0.02)',
                  }}>
                    <input
                      type="checkbox"
                      checked={selected}
                      onChange={(e) => {
                        const next = e.target.checked
                        setDraftTopics((current) => {
                          if (next) return Array.from(new Set([...current, topic.id]))
                          if (current.length <= 1) return current
                          return current.filter((item) => item !== topic.id)
                        })
                      }}
                    />
                    <div>
                      <div style={{ fontSize: 13, color: 'var(--text-primary)' }}>{topic.label}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{topic.description}</div>
                    </div>
                  </label>
                )
              })}
            </div>
          </section>
        </div>

        <div style={{ marginTop: 'auto', padding: 18, borderTop: '1px solid rgba(120, 144, 176, 0.18)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
            {provinces.length > 0 ? `${provinces.length} provinces covered` : 'No places selected yet'}
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <button className="navbar-btn" onClick={onClose}>Cancel</button>
            <button
              className="navbar-btn navbar-btn-active"
              onClick={() => onSave({
                notifications_enabled: notificationsEnabled,
                include_major_alerts: includeMajorAlerts,
                min_severity: minSeverity,
                home_district: draftHomeDistrict,
                followed_districts: draftDistricts,
                followed_provinces: provinces,
                followed_topics: draftTopics.filter((topic): topic is TopicId => TOPICS.some((item) => item.id === topic)),
              })}
              disabled={isSaving}
              style={{ opacity: isSaving ? 0.6 : 1 }}
            >
              {isSaving ? 'Saving...' : 'Save alerts'}
            </button>
          </div>
        </div>
      </aside>
    </div>
  )
}
