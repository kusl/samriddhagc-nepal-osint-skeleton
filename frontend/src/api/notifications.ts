import { apiClient } from './client'

export type NotificationSeverity = 'low' | 'medium' | 'high' | 'critical'
export type NotificationReasonCode =
  | 'major_nepal'
  | 'followed_topic'
  | 'followed_district'
  | 'followed_province'
  | 'home_district'
export type NotificationTab = 'all' | 'for_you' | 'major'

export interface Notification {
  id: string
  type: string
  category: string
  severity: NotificationSeverity | null
  title: string
  message: string | null
  data: Record<string, any> | null
  reason_code: NotificationReasonCode | null
  reason_label: string | null
  topic_id: string | null
  province_name: string | null
  district_name: string | null
  source_kind: string | null
  source_id: string | null
  deeplink_url: string | null
  is_read: boolean
  created_at: string
}

export interface NotificationListResponse {
  items: Notification[]
  unread_count: number
}

export interface NotificationFeedResponse extends NotificationListResponse {
  next_cursor: string | null
  tab: NotificationTab
}

export interface NotificationPreferences {
  notifications_enabled: boolean
  include_major_alerts: boolean
  min_severity: NotificationSeverity
  home_district: string | null
  followed_districts: string[]
  followed_provinces: string[]
  followed_topics: string[]
  muted_districts: string[]
  muted_provinces: string[]
  muted_topics: string[]
  quiet_hours_start: string | null
  quiet_hours_end: string | null
  has_saved_preferences: boolean
}

export interface NotificationPreferencesUpdate {
  notifications_enabled?: boolean
  include_major_alerts?: boolean
  min_severity?: NotificationSeverity
  home_district?: string | null
  followed_districts?: string[]
  followed_provinces?: string[]
  followed_topics?: string[]
}

export async function fetchNotifications(): Promise<NotificationListResponse> {
  const { data } = await apiClient.get('/notifications/')
  return data
}

export async function fetchNotificationFeed(params: {
  tab?: NotificationTab
  unreadOnly?: boolean
  limit?: number
  cursor?: string | null
}): Promise<NotificationFeedResponse> {
  const { data } = await apiClient.get('/notifications/feed', {
    params: {
      tab: params.tab ?? 'all',
      unread_only: params.unreadOnly ?? false,
      limit: params.limit ?? 25,
      cursor: params.cursor ?? undefined,
    },
  })
  return data
}

export async function fetchNotificationPreferences(): Promise<NotificationPreferences> {
  const { data } = await apiClient.get('/notifications/preferences')
  return data
}

export async function updateNotificationPreferences(
  payload: NotificationPreferencesUpdate,
): Promise<NotificationPreferences> {
  const { data } = await apiClient.put('/notifications/preferences', payload)
  return data
}

export async function markNotificationRead(notificationId: string): Promise<{ success: boolean }> {
  const { data } = await apiClient.post(`/notifications/${notificationId}/read`)
  return data
}

export async function markAllNotificationsRead(): Promise<{ success: boolean; marked_read: number }> {
  const { data } = await apiClient.post('/notifications/read-all')
  return data
}

export async function muteNotification(notificationId: string): Promise<{ success: boolean; preferences: NotificationPreferences }> {
  const { data } = await apiClient.post(`/notifications/${notificationId}/mute`)
  return data
}

export async function followSimilarNotification(notificationId: string): Promise<{ success: boolean; preferences: NotificationPreferences }> {
  const { data } = await apiClient.post(`/notifications/${notificationId}/follow-similar`)
  return data
}
