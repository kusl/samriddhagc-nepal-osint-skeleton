import { useEffect, useMemo, useRef } from 'react'
import { Bell, Settings } from 'lucide-react'
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  fetchNotificationFeed,
  fetchNotificationPreferences,
  followSimilarNotification,
  markAllNotificationsRead,
  markNotificationRead,
  muteNotification,
  updateNotificationPreferences,
} from '../../api/notifications'
import { NotificationItem } from './NotificationItem'
import { NotificationPreferencesDrawer } from './NotificationPreferencesDrawer'
import { useNotificationStore } from '../../stores/notificationStore'
import { useAuthStore } from '../../store/slices/authSlice'

const TABS: Array<{ id: 'all' | 'for_you' | 'major'; label: string }> = [
  { id: 'all', label: 'All' },
  { id: 'for_you', label: 'For You' },
  { id: 'major', label: 'Major' },
]

export function NotificationBell() {
  const navigate = useNavigate()
  const ref = useRef<HTMLDivElement>(null)
  const queryClient = useQueryClient()
  const { isGuest, isAuthenticated } = useAuthStore()
  // Anonymous visitors have no notifications, and while the guest bootstrap is
  // still in flight there is no token at all — gating on !isGuest alone let
  // these queries fire unauthenticated on first paint and 401.
  const canLoadNotifications = isAuthenticated && !isGuest
  const {
    unreadCount,
    isOpen,
    preferencesOpen,
    activeTab,
    setUnreadCount,
    setOpen,
    toggleOpen,
    setPreferencesOpen,
    setActiveTab,
  } = useNotificationStore()

  const unreadQuery = useQuery({
    queryKey: ['notifications', 'badge'],
    queryFn: () => fetchNotificationFeed({ tab: 'all', limit: 1 }),
    enabled: canLoadNotifications,
    refetchInterval: 30000,
  })

  const feedQuery = useInfiniteQuery({
    queryKey: ['notifications', 'feed', activeTab],
    queryFn: ({ pageParam }) => fetchNotificationFeed({ tab: activeTab, limit: 20, cursor: pageParam as string | null }),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: canLoadNotifications,
    refetchInterval: isOpen ? 30000 : false,
  })

  const preferencesQuery = useQuery({
    queryKey: ['notifications', 'preferences'],
    queryFn: fetchNotificationPreferences,
    enabled: canLoadNotifications && (isOpen || preferencesOpen),
    staleTime: 60000,
  })

  useEffect(() => {
    setUnreadCount(unreadQuery.data?.unread_count || 0)
  }, [unreadQuery.data?.unread_count, setUnreadCount])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [setOpen])

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ['notifications'] })
  }

  const markReadMut = useMutation({
    mutationFn: (id: string) => markNotificationRead(id),
    onSuccess: invalidateAll,
  })

  const markAllMut = useMutation({
    mutationFn: () => markAllNotificationsRead(),
    onSuccess: invalidateAll,
  })

  const muteMut = useMutation({
    mutationFn: (id: string) => muteNotification(id),
    onSuccess: () => {
      invalidateAll()
      queryClient.invalidateQueries({ queryKey: ['notifications', 'preferences'] })
    },
  })

  const followMut = useMutation({
    mutationFn: (id: string) => followSimilarNotification(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['notifications', 'preferences'] }),
  })

  const savePreferencesMut = useMutation({
    mutationFn: updateNotificationPreferences,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications', 'preferences'] })
      invalidateAll()
      setPreferencesOpen(false)
    },
  })

  const items = useMemo(
    () => feedQuery.data?.pages.flatMap((page) => page.items) ?? [],
    [feedQuery.data],
  )

  if (isGuest) {
    return null
  }

  return (
    <>
      <div ref={ref} className="relative">
        <button
          onClick={() => toggleOpen()}
          className="navbar-btn"
          title="Notifications"
          style={{ position: 'relative' }}
        >
          <Bell size={14} />
          {unreadCount > 0 && (
            <span style={{
              position: 'absolute',
              top: 5,
              right: 4,
              minWidth: 15,
              height: 15,
              borderRadius: 999,
              padding: '0 4px',
              background: '#ef4444',
              color: 'white',
              fontSize: 9,
              lineHeight: '15px',
              fontFamily: 'var(--font-mono)',
            }}>
              {unreadCount > 9 ? '9+' : unreadCount}
            </span>
          )}
        </button>

        {isOpen && (
          <div style={{
            position: 'absolute',
            right: 0,
            top: '100%',
            marginTop: 6,
            width: 420,
            maxWidth: 'calc(100vw - 24px)',
            background: 'linear-gradient(180deg, rgba(10,14,24,0.98) 0%, rgba(7,10,18,0.98) 100%)',
            border: '1px solid rgba(120, 144, 176, 0.18)',
            boxShadow: '0 18px 60px rgba(0,0,0,0.5)',
            zIndex: 90,
            overflow: 'hidden',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 14px', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
              <div>
                <div style={{ fontSize: 11, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                  Notification Inbox
                </div>
                <div style={{ fontSize: 15, color: 'var(--text-primary)', marginTop: 3 }}>
                  Important alerts for your account
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="navbar-btn" title="Alert preferences" onClick={() => setPreferencesOpen(true)}>
                  <Settings size={14} />
                </button>
                {unreadCount > 0 && (
                  <button className="navbar-btn" onClick={() => markAllMut.mutate()}>
                    Mark all read
                  </button>
                )}
              </div>
            </div>

            <div style={{ display: 'flex', gap: 8, padding: '10px 14px', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
              {TABS.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  style={{
                    border: activeTab === tab.id ? '1px solid rgba(59,130,246,0.7)' : '1px solid rgba(120, 144, 176, 0.18)',
                    background: activeTab === tab.id ? 'rgba(30, 64, 175, 0.18)' : 'rgba(255,255,255,0.02)',
                    color: activeTab === tab.id ? 'var(--text-primary)' : 'var(--text-secondary)',
                    padding: '7px 10px',
                    fontSize: 11,
                    fontFamily: 'var(--font-mono)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.08em',
                  }}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            <div style={{ maxHeight: 520, overflowY: 'auto' }}>
              {!feedQuery.isLoading && items.length === 0 && (
                <div style={{ padding: 18, display: 'grid', gap: 10 }}>
                  <div style={{ fontSize: 14, color: 'var(--text-primary)' }}>
                    No important alerts right now
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                    Follow districts and topics so NepalOSINT can surface the events that matter to you.
                  </div>
                  <div>
                    <button className="navbar-btn navbar-btn-active" onClick={() => setPreferencesOpen(true)}>
                      Set up alerts
                    </button>
                  </div>
                </div>
              )}

              {items.map((notification) => (
                <NotificationItem
                  key={notification.id}
                  notification={notification}
                  onMarkRead={() => markReadMut.mutate(notification.id)}
                  onMute={() => muteMut.mutate(notification.id)}
                  onFollowSimilar={() => followMut.mutate(notification.id)}
                  onOpen={() => {
                    setOpen(false)
                    navigate(notification.deeplink_url || '/')
                  }}
                />
              ))}

              {feedQuery.hasNextPage && (
                <div style={{ padding: 14 }}>
                  <button className="navbar-btn" onClick={() => feedQuery.fetchNextPage()}>
                    Load more
                  </button>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      <NotificationPreferencesDrawer
        open={preferencesOpen}
        preferences={preferencesQuery.data}
        isSaving={savePreferencesMut.isPending}
        onClose={() => setPreferencesOpen(false)}
        onSave={(payload) => savePreferencesMut.mutate(payload)}
      />
    </>
  )
}
