import { create } from 'zustand'
import type { NotificationTab } from '../api/notifications'

interface NotificationState {
  unreadCount: number
  isOpen: boolean
  preferencesOpen: boolean
  activeTab: NotificationTab

  setUnreadCount: (count: number) => void
  setOpen: (open: boolean) => void
  toggleOpen: () => void
  setPreferencesOpen: (open: boolean) => void
  setActiveTab: (tab: NotificationTab) => void
}

export const useNotificationStore = create<NotificationState>((set) => ({
  unreadCount: 0,
  isOpen: false,
  preferencesOpen: false,
  activeTab: 'all',

  setUnreadCount: (count) => set({ unreadCount: count }),
  setOpen: (open) => set({ isOpen: open }),
  toggleOpen: () => set((state) => ({ isOpen: !state.isOpen })),
  setPreferencesOpen: (open) => set({ preferencesOpen: open }),
  setActiveTab: (tab) => set({ activeTab: tab }),
}))
