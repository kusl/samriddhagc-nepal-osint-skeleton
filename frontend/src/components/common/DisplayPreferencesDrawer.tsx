import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import { useSettingsStore, type NprNumberingSystem } from '../../store/slices/settingsSlice'
import { CURRENCY_PREVIEW_VALUE, formatCompactNpr, formatUsdCompact } from '../../utils/currency'

interface DisplayPreferencesDrawerProps {
  open: boolean
  onClose: () => void
}

const NUMBERING_OPTIONS: Array<{
  value: NprNumberingSystem
  label: string
  detail: string
}> = [
  { value: 'vedic', label: 'Vedic', detail: 'Cr / Arba' },
  { value: 'international', label: 'International', detail: 'M / B' },
]

export function DisplayPreferencesDrawer({ open, onClose }: DisplayPreferencesDrawerProps) {
  const {
    nprNumberingSystem,
    showUsdEquivalents,
    setNprNumberingSystem,
    setShowUsdEquivalents,
  } = useSettingsStore()

  const [draftSystem, setDraftSystem] = useState<NprNumberingSystem>('vedic')
  const [draftShowUsd, setDraftShowUsd] = useState(true)

  useEffect(() => {
    if (!open) return
    setDraftSystem(nprNumberingSystem)
    setDraftShowUsd(showUsdEquivalents)
  }, [open, nprNumberingSystem, showUsdEquivalents])

  if (!open) return null

  const preview = formatCompactNpr(CURRENCY_PREVIEW_VALUE, { system: draftSystem })

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 140, display: 'flex', justifyContent: 'flex-end', background: 'rgba(3, 8, 18, 0.72)' }}>
      <button
        aria-label="Close display preferences"
        onClick={onClose}
        style={{ position: 'absolute', inset: 0, background: 'transparent', border: 'none' }}
      />
      <aside style={{
        position: 'relative',
        width: 'min(430px, 100vw)',
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
              Display Preferences
            </div>
            <h3 style={{ margin: '6px 0 0', fontSize: 24, lineHeight: 1.1, color: 'var(--text-primary)' }}>
              Currency display
            </h3>
          </div>
          <button className="navbar-btn" onClick={onClose} title="Close">
            <X size={14} />
          </button>
        </div>

        <div style={{ padding: 18, overflowY: 'auto', display: 'grid', gap: 20 }}>
          <section style={{ display: 'grid', gap: 10 }}>
            <div>
              <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.14em', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                Numbering System
              </div>
              <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                Use Nepal’s familiar crore and arba system by default, or switch to international million and billion notation.
              </div>
            </div>

            <div style={{ display: 'grid', gap: 8 }}>
              {NUMBERING_OPTIONS.map((option) => {
                const active = draftSystem === option.value
                return (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => setDraftSystem(option.value)}
                    style={{
                      border: active ? '1px solid rgba(255,107,0,0.75)' : '1px solid rgba(120, 144, 176, 0.18)',
                      background: active ? 'rgba(255,107,0,0.14)' : 'rgba(255,255,255,0.02)',
                      color: active ? 'var(--text-primary)' : 'var(--text-secondary)',
                      padding: '11px 12px',
                      textAlign: 'left',
                      display: 'grid',
                      gap: 4,
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
                      <span style={{ fontSize: 13, fontWeight: 600 }}>{option.label}</span>
                      <span style={{ fontSize: 11, color: active ? 'var(--bloomberg-orange, #FF6B00)' : 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                        {option.detail}
                      </span>
                    </div>
                    <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                      {formatCompactNpr(CURRENCY_PREVIEW_VALUE, { system: option.value })}
                    </span>
                  </button>
                )
              })}
            </div>
          </section>

          <section style={{ display: 'grid', gap: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, fontSize: 13, color: 'var(--text-secondary)', alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.14em', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginBottom: 4 }}>
                  USD Conversion
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                  Show USD equivalents when the widget already has an exchange rate available.
                </div>
              </div>
              <input type="checkbox" checked={draftShowUsd} onChange={(e) => setDraftShowUsd(e.target.checked)} />
            </div>
          </section>

          <section style={{
            padding: '12px 14px',
            border: '1px solid rgba(120, 144, 176, 0.18)',
            background: 'rgba(255,255,255,0.02)',
            display: 'grid',
            gap: 6,
          }}>
            <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.14em', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
              Preview
            </div>
            <div style={{ fontSize: 18, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontWeight: 700 }}>
              {preview}
              {draftShowUsd ? (
                <span style={{ marginLeft: 8, fontSize: 12, color: 'var(--text-muted)', fontWeight: 500 }}>
                  ({formatUsdCompact(2_250_000_000)})
                </span>
              ) : null}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              Example amount: NPR 300,000,000,000
            </div>
          </section>
        </div>

        <div style={{ marginTop: 'auto', padding: 18, borderTop: '1px solid rgba(120, 144, 176, 0.18)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
            Saved locally on this device
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <button className="navbar-btn" onClick={onClose}>Cancel</button>
            <button
              className="navbar-btn navbar-btn-active"
              onClick={() => {
                setNprNumberingSystem(draftSystem)
                setShowUsdEquivalents(draftShowUsd)
                onClose()
              }}
            >
              Save display
            </button>
          </div>
        </div>
      </aside>
    </div>
  )
}
