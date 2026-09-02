import { useEffect, useRef, lazy, Suspense } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { Dashboard as NewDashboard } from './components/Dashboard'
// MobileBottomNav removed — election season, single-page mobile experience
import { useAuthStore, User } from './store/slices/authSlice'
import { useUserPreferencesStore } from './store/slices/userPreferencesSlice'
import { ProtectedRoute } from './components/ProtectedRoute'
import { usePermissions } from './hooks/usePermissions'
import { publicLogin } from './api/auth'
import { fetchNotificationPreferences, updateNotificationPreferences } from './api/notifications'
import { useNotificationStore } from './stores/notificationStore'
import { getProvinceForDistrict } from './data/districts'
import { IS_PUBLIC_ONLY } from './config/deployment'

const CandidateDeepDive = lazy(() => import('./components/elections/CandidateDeepDive').then((m) => ({ default: m.CandidateDeepDive })))
const MainLayout = lazy(() => import('./components/layout/MainLayout').then((m) => ({ default: m.MainLayout })))
const Analysis = lazy(() => import('./pages/Analysis'))
const Indices = lazy(() => import('./pages/Indices'))
const ActivityLogs = lazy(() => import('./pages/ActivityLogs'))
const ReviewQueue = lazy(() => import('./pages/ReviewQueue'))
const ReviewDesk = lazy(() => import('./pages/ReviewDesk'))
const DisasterAlerts = lazy(() => import('./pages/DisasterAlerts'))
const Login = lazy(() => import('./pages/Login'))
const ChooseUsername = lazy(() => import('./pages/ChooseUsername'))
const DevWorkstation = lazy(() => import('./pages/DevWorkstation'))
const UITestDashboard = lazy(() => import('./components/Dashboard/UITestDashboard').then((m) => ({ default: m.UITestDashboard })))

const BUILD_MARKER = 'aviation-v59'

function toStoreUser(apiUser: {
  id: string; email: string; full_name: string | null; username: string | null;
  role: string; auth_provider: string; avatar_url: string | null;
}): User {
  return {
    id: apiUser.id, email: apiUser.email, fullName: apiUser.full_name,
    username: apiUser.username, role: apiUser.role as User['role'],
    authProvider: apiUser.auth_provider as User['authProvider'],
    avatarUrl: apiUser.avatar_url,
  }
}

const pageTransition = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
  transition: { duration: 0.15 },
}

function AnimatedRoutes({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  return (
    <AnimatePresence mode="wait">
      <motion.div key={location.pathname} {...pageTransition} style={{ display: 'contents' }}>
        {children}
      </motion.div>
    </AnimatePresence>
  )
}

function withRouteSuspense(element: React.ReactNode) {
  return <Suspense fallback={null}>{element}</Suspense>
}

function App() {
  const location = useLocation()
  const { isAuthenticated, needsUsername, isGuest, login, user } = useAuthStore()
  const {
    hasCompletedOnboarding,
    selectedDistricts,
    homeDistrict,
    selectedTopics,
    alertSeverityThreshold,
    includeMajorAlerts,
    pushNotificationsEnabled,
    hydrateNotificationPreferences,
  } = useUserPreferencesStore()
  const { setPreferencesOpen } = useNotificationStore()
  const { isConsumer } = usePermissions()
  const attemptedRef = useRef(false)
  const wasAuthenticatedRef = useRef(isAuthenticated)
  const notificationPrefsSyncRef = useRef<string | null>(null)
  const shouldRenderPublicConsumerView = !isAuthenticated
    && (IS_PUBLIC_ONLY || (
      location.pathname !== '/login'
      && location.pathname !== '/choose-username'
      && !location.pathname.startsWith('/dev')
    ))
  const shouldAttemptGuestBootstrap = shouldRenderPublicConsumerView

  useEffect(() => {
    document.documentElement.setAttribute('data-build-marker', BUILD_MARKER)
  }, [])

  useEffect(() => {
    if (wasAuthenticatedRef.current && !isAuthenticated) {
      attemptedRef.current = false
      notificationPrefsSyncRef.current = null
    }
    wasAuthenticatedRef.current = isAuthenticated
  }, [isAuthenticated])

  useEffect(() => {
    if (!isAuthenticated || isGuest || !user?.id || location.pathname === '/login') return
    if (notificationPrefsSyncRef.current === user.id) return
    notificationPrefsSyncRef.current = user.id
    let cancelled = false

    const syncNotificationPreferences = async () => {
      try {
        const serverPrefs = await fetchNotificationPreferences()
        if (cancelled) return
        if (serverPrefs.has_saved_preferences) {
          hydrateNotificationPreferences(serverPrefs)
          return
        }

        const saved = await updateNotificationPreferences({
          notifications_enabled: pushNotificationsEnabled,
          include_major_alerts: includeMajorAlerts,
          min_severity: alertSeverityThreshold === 'critical' ? 'critical' : alertSeverityThreshold === 'high' ? 'high' : 'low',
          home_district: homeDistrict,
          followed_districts: selectedDistricts,
          followed_provinces: Array.from(
            new Set(selectedDistricts.map((district) => getProvinceForDistrict(district)).filter(Boolean)),
          ) as string[],
          followed_topics: selectedTopics,
        })
        if (cancelled) return
        hydrateNotificationPreferences(saved)
        setPreferencesOpen(true)
      } catch (error) {
        console.warn('Notification preference sync failed', error)
        notificationPrefsSyncRef.current = null
      }
    }

    void syncNotificationPreferences()
    return () => {
      cancelled = true
    }
  }, [
    alertSeverityThreshold,
    homeDistrict,
    hydrateNotificationPreferences,
    includeMajorAlerts,
    isAuthenticated,
    isGuest,
    location.pathname,
    pushNotificationsEnabled,
    selectedDistricts,
    selectedTopics,
    setPreferencesOpen,
    user?.id,
  ])

  // Auto-login as guest when not authenticated
  useEffect(() => {
    if (!shouldAttemptGuestBootstrap || isAuthenticated || attemptedRef.current) return
    let cancelled = false

    const runBootstrap = () => {
      if (cancelled || attemptedRef.current) return
      attemptedRef.current = true
      publicLogin()
        .then((result) => {
          if (cancelled) return
          login(result.access_token, result.refresh_token, toStoreUser(result.user))
        })
        .catch(() => {
          if (cancelled) return
          attemptedRef.current = false
        })
    }

    const timeoutId = window.setTimeout(runBootstrap, 1200)
    const idleId = 'requestIdleCallback' in window
      ? window.requestIdleCallback(() => {
          window.clearTimeout(timeoutId)
          runBootstrap()
        }, { timeout: 3500 })
      : null

    return () => {
      cancelled = true
      window.clearTimeout(timeoutId)
      if (idleId !== null && 'cancelIdleCallback' in window) {
        window.cancelIdleCallback(idleId)
      }
    }
  }, [isAuthenticated, login, shouldAttemptGuestBootstrap])

  if (!isAuthenticated && !shouldRenderPublicConsumerView) {
    return (
      <Routes>
        <Route path="/login" element={withRouteSuspense(<Login />)} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    )
  }

  // Redirect to choose-username if needed (not for guests — they get auto-generated usernames)
  if (needsUsername && !isGuest) {
    return (
      <Routes>
        <Route path="/choose-username" element={withRouteSuspense(<ChooseUsername />)} />
        <Route path="*" element={<Navigate to="/choose-username" replace />} />
      </Routes>
    )
  }

  // Show onboarding if not completed (skip for consumer role and during elections)
  // Disabled during election season — everyone goes straight to election monitor
  // if (!hasCompletedOnboarding && !isConsumer) {
  //   return <Onboarding />
  // }

  // ============================================
  // UI TEST ROUTE
  // ============================================

  if (!IS_PUBLIC_ONLY && (location.pathname === '/uitest' || location.pathname === '/uitest/')) {
    return (
      <>
        <Suspense fallback={null}>
          <CandidateDeepDive />
        </Suspense>
        <AnimatedRoutes>
          <Routes>
            <Route path="/uitest" element={withRouteSuspense(<UITestDashboard />)} />
            <Route path="/uitest/" element={withRouteSuspense(<UITestDashboard />)} />
            <Route path="*" element={<Navigate to="/uitest" replace />} />
          </Routes>
        </AnimatedRoutes>
      </>
    )
  }

  // Consumer role: analyst dashboard is default landing page
  if (isConsumer || shouldRenderPublicConsumerView) {
    return (
      <>
        <Suspense fallback={null}>
          <CandidateDeepDive />
        </Suspense>
        <AnimatedRoutes>
          <Routes>
            <Route path="/" element={<NewDashboard />} />
            <Route
              path="/login"
              element={IS_PUBLIC_ONLY ? <Navigate to="/" replace /> : withRouteSuspense(<Login />)}
            />
            <Route path="/disasters" element={withRouteSuspense(<DisasterAlerts />)} />
            {/* Owner-only verification desk for the extractor's facts; gated by the review key, not by login. */}
            <Route path="/review" element={withRouteSuspense(<ReviewDesk />)} />
            {/* Flood is a dashboard preset now; keep circulated /flood links working. */}
            <Route path="/flood" element={<Navigate to="/" replace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AnimatedRoutes>
        {/* MobileBottomNav removed for election season */}
      </>
    )
  }

  // ============================================
  // DEV ROUTES (no analyst in consumer deployment)
  // ============================================

  // Dev Workstation (full-screen, no MainLayout)
  if (location.pathname.startsWith('/dev')) {
    return (
      <>
        <Suspense fallback={null}>
          <CandidateDeepDive />
        </Suspense>
        <AnimatedRoutes>
          <Routes>
            <Route path="/dev" element={<Navigate to="/dev/overview" replace />} />
            <Route path="/dev/*" element={withRouteSuspense(<ProtectedRoute requiredRole="dev"><DevWorkstation /></ProtectedRoute>)} />
            <Route path="/login" element={withRouteSuspense(<Login />)} />
            <Route path="*" element={<Navigate to="/dev/overview" replace />} />
          </Routes>
        </AnimatedRoutes>
        {/* MobileBottomNav removed for election season */}
      </>
    )
  }

  // All other routes — analyst dashboard is landing page
  return (
    <>
    <Suspense fallback={null}>
      <CandidateDeepDive />
    </Suspense>
    <Suspense fallback={null}>
      <MainLayout>
        <AnimatedRoutes>
          <Routes>
            <Route path="/" element={<NewDashboard />} />
            <Route path="/disasters" element={withRouteSuspense(<DisasterAlerts />)} />
            {/* Flood is a dashboard preset now; keep circulated /flood links working. */}
            <Route path="/flood" element={<Navigate to="/" replace />} />

            {/* Dev-only routes */}
            <Route path="/analysis" element={withRouteSuspense(<ProtectedRoute requiredRole="dev"><Analysis /></ProtectedRoute>)} />
            <Route path="/indices" element={withRouteSuspense(<ProtectedRoute requiredRole="dev"><Indices /></ProtectedRoute>)} />
            <Route path="/activity" element={withRouteSuspense(<ProtectedRoute requiredRole="dev"><ActivityLogs /></ProtectedRoute>)} />
            <Route path="/review-queue" element={withRouteSuspense(<ProtectedRoute requiredRole="dev"><ReviewQueue /></ProtectedRoute>)} />

            <Route path="/login" element={withRouteSuspense(<Login />)} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AnimatedRoutes>
      </MainLayout>
    </Suspense>
    {/* MobileBottomNav removed for election season */}
    </>
  )
}

export default App
