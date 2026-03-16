import { AlertTriangle, Bell, MapPin, ShieldCheck } from 'lucide-react'
import type { Notification } from '../../api/notifications'

interface NotificationItemProps {
  notification: Notification
  onMarkRead: () => void
  onMute: () => void
  onFollowSimilar: () => void
  onOpen: () => void
}

const ICON_MAP = {
  major_alert: AlertTriangle,
  place_alert: MapPin,
  topic_alert: Bell,
  correction_approved: ShieldCheck,
  correction_rejected: AlertTriangle,
  correction_rolled_back: AlertTriangle,
  bulk_upload_complete: Bell,
} as const

const SEVERITY_COLOR: Record<string, string> = {
  low: '#6b7280',
  medium: '#eab308',
  high: '#f97316',
  critical: '#ef4444',
}

function formatRelative(dateStr: string): string {
  const d = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const mins = Math.floor(diffMs / 60000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

export function NotificationItem({
  notification,
  onMarkRead,
  onMute,
  onFollowSimilar,
  onOpen,
}: NotificationItemProps) {
  const Icon = ICON_MAP[notification.type as keyof typeof ICON_MAP] || Bell
  const severityColor = notification.severity ? SEVERITY_COLOR[notification.severity] ?? '#3b82f6' : '#3b82f6'

  return (
    <div
      style={{
        borderBottom: '1px solid rgba(255,255,255,0.05)',
        background: notification.is_read ? 'transparent' : 'rgba(59, 130, 246, 0.04)',
        display: 'grid',
        gridTemplateColumns: '3px 1fr',
      }}
    >
      <div style={{ background: severityColor }} />
      <div style={{ padding: '12px 14px 12px 12px' }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
          <div style={{
            width: 28, height: 28,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            border: '1px solid rgba(120, 144, 176, 0.18)',
            color: 'var(--text-secondary)',
            background: 'rgba(255,255,255,0.03)',
            flexShrink: 0,
          }}>
            <Icon size={13} />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '0.12em' }}>
                {notification.type.replace('_', ' ')}
              </span>
              {notification.reason_label && (
                <span style={{
                  fontSize: 10,
                  color: 'var(--text-secondary)',
                  border: '1px solid rgba(120, 144, 176, 0.16)',
                  padding: '2px 6px',
                  fontFamily: 'var(--font-mono)',
                }}>
                  {notification.reason_label}
                </span>
              )}
              {notification.severity && (
                <span style={{
                  fontSize: 10,
                  color: severityColor,
                  border: `1px solid ${severityColor}44`,
                  padding: '2px 6px',
                  fontFamily: 'var(--font-mono)',
                  textTransform: 'uppercase',
                }}>
                  {notification.severity}
                </span>
              )}
            </div>
            <button
              onClick={() => {
                if (!notification.is_read) onMarkRead()
                onOpen()
              }}
              style={{
                display: 'block',
                background: 'transparent',
                border: 'none',
                padding: 0,
                margin: 0,
                textAlign: 'left',
                width: '100%',
                cursor: 'pointer',
              }}
            >
              <div style={{ fontSize: 13, color: 'var(--text-primary)', fontWeight: 600, lineHeight: 1.35 }}>
                {notification.title}
              </div>
              {notification.message && (
                <p style={{ margin: '5px 0 0', fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                  {notification.message}
                </p>
              )}
            </button>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginTop: 10 }}>
              <span style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                {formatRelative(notification.created_at)}
              </span>
              <div style={{ display: 'flex', gap: 10 }}>
                <button className="navbar-btn" onClick={onFollowSimilar} style={{ fontSize: 10 }}>
                  Follow more
                </button>
                <button className="navbar-btn" onClick={onMute} style={{ fontSize: 10 }}>
                  Mute
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
