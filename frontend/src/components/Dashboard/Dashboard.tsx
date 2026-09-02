import { useEffect, useState, createContext, useContext, useRef, useSyncExternalStore, useMemo, lazy, Suspense, type ComponentType, type LazyExoticComponent, type ReactNode, type Ref, type RefObject } from 'react';
import { useNavigate } from 'react-router-dom';
import { getDashboardBootstrap, hydrateDashboardBootstrap, type DashboardBootstrapPreset } from '../../api/dashboard';
import { queryClient } from '../../lib/queryClient';
import { DashboardHeader } from './DashboardHeader';
import { AnalystToolbar } from './AnalystToolbar';
import { FeedbackPanel } from './FeedbackPanel';
import { AlertTicker } from './AlertTicker';
import { useDashboardStore, PRESETS, WIDGET_META } from '../../stores/dashboardStore';
import { useAuthStore, UserRole } from '../../store/slices/authSlice';
import { DesktopOnlyGate, FORCE_DESKTOP_KEY, readForceDesktop } from '../common/DesktopOnlyGate';
import { useUserPreferencesStore } from '../../store/slices/userPreferencesSlice';
import { DashboardTour, WelcomeModal, getDashboardTourSteps } from '../onboarding';
import { CustomizePanel } from './CustomizePanel';
import { CommandPalette } from './CommandPalette';
import '../../styles/dashboard.css';
import '../../styles/professional-dashboard.css';

// Analyst mode context for child components
interface AnalystModeContextType {
  feedbackMode: boolean;
  selectedStories: Set<string>;
  toggleStorySelection: (id: string) => void;
  openFeedbackPanel: (story: any) => void;
}

export const AnalystModeContext = createContext<AnalystModeContextType | null>(null);
export const useAnalystMode = () => useContext(AnalystModeContext);

type WidgetLoader = () => Promise<{ default: ComponentType<any> }>;

const WIDGET_LOADERS: Record<string, WidgetLoader> = {
  map: () => import('./widgets/MapWidget').then((m) => ({ default: m.MapWidget })),
  elections: () => import('./widgets/ElectionsWidget').then((m) => ({ default: m.ElectionsWidget })),
  'election-map': () => import('./widgets/ElectionMapWidget').then((m) => ({ default: m.ElectionMapWidget })),
  kpi: () => import('./widgets/KPIWidget').then((m) => ({ default: m.KPIWidget })),
  stories: () => import('./widgets/StoriesWidget').then((m) => ({ default: m.StoriesWidget })),
  newsfeed: () => import('./widgets/NewsFeedWidget').then((m) => ({ default: m.NewsFeedWidget })),
  weather: () => import('./widgets/WeatherWidget').then((m) => ({ default: m.WeatherWidget })),
  disasters: () => import('./widgets/DisastersWidget').then((m) => ({ default: m.DisastersWidget })),
  market: () => import('./widgets/MarketWidget').then((m) => ({ default: m.MarketWidget })),
  entities: () => import('./widgets').then((m) => ({ default: m.EntitiesWidget })),
  briefing: () => import('./widgets').then((m) => ({ default: m.BriefingWidget })),
  social: () => import('./widgets').then((m) => ({ default: m.SocialWidget })),
  govt: () => import('./widgets/AnnouncementsWidget').then((m) => ({ default: m.AnnouncementsWidget })),
  threats: () => import('./widgets/ThreatsWidget').then((m) => ({ default: m.ThreatsWidget })),
  seismic: () => import('./widgets').then((m) => ({ default: m.SeismicWidget })),
  'election-status': () => import('./widgets/ElectionStatusWidget').then((m) => ({ default: m.ElectionStatusWidget })),
  'swing-analysis': () => import('./widgets/SwingAnalysisWidget').then((m) => ({ default: m.SwingAnalysisWidget })),
  'close-races': () => import('./widgets/CloseRacesWidget').then((m) => ({ default: m.CloseRacesWidget })),
  incumbency: () => import('./widgets/IncumbencyWidget').then((m) => ({ default: m.IncumbencyWidget })),
  candidates: () => import('./widgets/CandidatesWidget').then((m) => ({ default: m.CandidatesWidget })),
  'party-switch': () => import('./widgets/PartySwitchWidget').then((m) => ({ default: m.PartySwitchWidget })),
  neta: () => import('./widgets/KnowYourNetaWidget').then((m) => ({ default: m.KnowYourNetaWidget })),
  'election-live': () => import('./widgets/ElectionLiveWidget').then((m) => ({ default: m.ElectionLiveWidget })),
  'election-pr': () => import('./widgets/ElectionPRWidget').then((m) => ({ default: m.ElectionPRWidget })),
  'election-seats': () => import('./widgets/ElectionSeatsWidget').then((m) => ({ default: m.ElectionSeatsWidget })),
  'promise-tracker': () => import('./widgets/PromiseTrackerWidget').then((m) => ({ default: m.PromiseTrackerWidget })),
  'parliament-session': () => import('./widgets/ParliamentSessionWidget').then((m) => ({ default: m.ParliamentSessionWidget })),
  'govt-decisions': () => import('./widgets/GovtDecisionsWidget').then((m) => ({ default: m.GovtDecisionsWidget })),
  'cabinet-action-tracker': () => import('./widgets/CabinetActionTrackerWidget').then((m) => ({ default: m.CabinetActionTrackerWidget })),
  'govt-loan-tracker': () => import('./widgets/GovtLoanTrackerWidget').then((m) => ({ default: m.GovtLoanTrackerWidget })),
  'debt-tracker': () => import('./widgets/DebtTrackerWidget').then((m) => ({ default: m.DebtTrackerWidget })),
  'govt-contracts': () => import('./widgets/GovtContractsWidget').then((m) => ({ default: m.GovtContractsWidget })),
  'economic-news': () => import('./widgets/EconomicNewsWidget').then((m) => ({ default: m.EconomicNewsWidget })),
  'price-watch': () => import('./widgets/PriceWatchWidget').then((m) => ({ default: m.PriceWatchWidget })),
  'trade-customs': () => import('./widgets/TradeCustomsWidget').then((m) => ({ default: m.TradeCustomsWidget })),
  'public-spending': () => import('./widgets/PublicSpendingWidget').then((m) => ({ default: m.PublicSpendingWidget })),
  'nrb-macro': () => import('./widgets/NrbMacroWidget').then((m) => ({ default: m.NrbMacroWidget })),
  'nrb-prices': () => import('./widgets/NrbPricesFlowsWidget').then((m) => ({ default: m.NrbPricesFlowsWidget })),
  'nrb-banking': () => import('./widgets/NrbBankingLiquidityWidget').then((m) => ({ default: m.NrbBankingLiquidityWidget })),
  'fiscal-position': () => import('./widgets/FiscalPositionWidget').then((m) => ({ default: m.FiscalPositionWidget })),
  'external-sector': () => import('./widgets/ExternalSectorWidget').then((m) => ({ default: m.ExternalSectorWidget })),
  'monetary-conditions': () => import('./widgets/MonetaryConditionsWidget').then((m) => ({ default: m.MonetaryConditionsWidget })),
  'prices-cost-pressure': () => import('./widgets/PricesCostPressureWidget').then((m) => ({ default: m.PricesCostPressureWidget })),
  rivers: () => import('./widgets/RiverMonitoringWidget').then((m) => ({ default: m.RiverMonitoringWidget })),
  'bill-tracker': () => import('./widgets/BillTrackerWidget').then((m) => ({ default: m.BillTrackerWidget })),
  'parliament-activity': () => import('./widgets/ParliamentaryActivityWidget').then((m) => ({ default: m.ParliamentaryActivityWidget })),
  'cases-active': () => import('./widgets').then((m) => ({ default: m.ActiveCasesWidget })),
  'collab-feed': () => import('./widgets').then((m) => ({ default: m.CollaborationFeedWidget })),
  'verification-queue': () => import('./widgets').then((m) => ({ default: m.VerificationQueueWidget })),
  'entity-watchlist': () => import('./widgets').then((m) => ({ default: m.EntityWatchlistWidget })),
  'analyst-notes': () => import('./widgets').then((m) => ({ default: m.AnalystNotesWidget })),
  'source-reliability': () => import('./widgets').then((m) => ({ default: m.SourceReliabilityWidget })),
  'analyst-leaderboard': () => import('./widgets').then((m) => ({ default: m.AnalystLeaderboardWidget })),
  'intel-brief-hero': () => import('./widgets/IntelBriefHeroWidget').then((m) => ({ default: m.IntelBriefHeroWidget })),
  'developing-stories': () => import('./widgets/DevelopingStoriesWidget').then((m) => ({ default: m.DevelopingStoriesWidget })),
  'political-pulse': () => import('./widgets/PoliticalPulseWidget').then((m) => ({ default: m.PoliticalPulseWidget })),
  'province-monitor': () => import('./widgets/ProvinceMonitorWidget').then((m) => ({ default: m.ProvinceMonitorWidget })),
  'narrative-tracker': () => import('./widgets/NarrativeTrackerWidget').then((m) => ({ default: m.NarrativeTrackerWidget })),
  'fact-check': () => import('./widgets/FactCheckWidget').then((m) => ({ default: m.FactCheckWidget })),
  'flood-situation-command': () => import('./widgets/FloodSituationCommandWidget').then((m) => ({ default: m.FloodSituationCommandWidget })),
  'flood-district-map': () => import('./widgets/FloodDistrictMapWidget').then((m) => ({ default: m.FloodDistrictMapWidget })),
  'flood-operational-picture': () => import('./widgets/FloodOperationalPictureWidget').then((m) => ({ default: m.FloodOperationalPictureWidget })),
  'flood-district-toll': () => import('./widgets/FloodDistrictTollWidget').then((m) => ({ default: m.FloodDistrictTollWidget })),
  'flood-missing-ledger': () => import('./widgets/FloodMissingLedgerWidget').then((m) => ({ default: m.FloodMissingLedgerWidget })),
  'flood-rescue-ops': () => import('./widgets/FloodRescueOpsWidget').then((m) => ({ default: m.FloodRescueOpsWidget })),
  'flood-damage-aid': () => import('./widgets/FloodDamageAidWidget').then((m) => ({ default: m.FloodDamageAidWidget })),
  'flood-tunnel-rescue': () => import('./widgets/FloodTunnelRescueWidget').then((m) => ({ default: m.FloodTunnelRescueWidget })),
  'flood-assistance': () => import('./widgets/FloodAssistanceWidget').then((m) => ({ default: m.FloodAssistanceWidget })),
  'flood-river-gauges': () => import('./widgets/FloodRiverGaugesWidget').then((m) => ({ default: m.FloodRiverGaugesWidget })),
  'flood-satellite-intel': () => import('./widgets/FloodSatelliteIntelWidget').then((m) => ({ default: m.FloodSatelliteIntelWidget })),
  'flood-satellite-map': () => import('./widgets/FloodSatelliteMapWidget').then((m) => ({ default: m.FloodSatelliteMapWidget })),
  'flood-chronology': () => import('./widgets/FloodChronologyWidget').then((m) => ({ default: m.FloodChronologyWidget })),
  'flood-damage-explorer': () => import('./widgets/FloodDamageExplorerWidget').then((m) => ({ default: m.FloodDamageExplorerWidget })),
  'flood-cited-reporting': () => import('./widgets/FloodCitedReportingWidget').then((m) => ({ default: m.FloodCitedReportingWidget })),
  'flood-assessment': () => import('./widgets/FloodAssessmentWidget').then((m) => ({ default: m.FloodAssessmentWidget })),
  'flood-gov-services': () => import('./widgets/FloodGovServicesWidget').then((m) => ({ default: m.FloodGovServicesWidget })),
  'flood-source-matrix': () => import('./widgets/FloodSourceMatrixWidget').then((m) => ({ default: m.FloodSourceMatrixWidget })),
  'flood-sitrep-log': () => import('./widgets/FloodSitrepLogWidget').then((m) => ({ default: m.FloodSitrepLogWidget })),
  'flood-ground-imagery': () => import('./widgets/FloodGroundImageryWidget').then((m) => ({ default: m.FloodGroundImageryWidget })),
};

export const WIDGET_COMPONENTS: Record<string, LazyExoticComponent<ComponentType<any>>> = Object.fromEntries(
  Object.entries(WIDGET_LOADERS).map(([widgetId, loader]) => [widgetId, lazy(loader)]),
) as Record<string, LazyExoticComponent<ComponentType<any>>>;

const BOOTSTRAP_PRESETS = new Set<DashboardBootstrapPreset>(['news', 'economy', 'parliament', 'intelligence']);
const IMMEDIATE_WIDGETS_BY_PRESET: Record<string, string[]> = {
  news: ['kpi', 'developing-stories', 'newsfeed', 'fact-check'],
  economy: ['economic-news', 'market', 'nrb-macro', 'fiscal-position'],
  parliament: ['parliament-session', 'govt-decisions', 'promise-tracker', 'bill-tracker'],
  intelligence: ['kpi', 'developing-stories', 'fact-check', 'province-monitor'],
};

const MOBILE_WIDGETS_BY_PRESET: Record<string, string[]> = {
  news: ['developing-stories', 'fact-check', 'newsfeed', 'market', 'province-monitor'],
  analyst: ['election-map', 'newsfeed', 'election-status', 'fact-check'],
  intelligence: ['map', 'developing-stories', 'fact-check', 'newsfeed', 'province-monitor'],
  elections: ['election-seats', 'election-status', 'election-pr', 'election-live'],
  economy: ['economic-news', 'market', 'trade-customs', 'fiscal-position', 'external-sector', 'monetary-conditions', 'prices-cost-pressure', 'govt-loan-tracker', 'govt-contracts', 'debt-tracker'],
  parliament: ['promise-tracker', 'bill-tracker', 'parliament-activity', 'govt-decisions', 'neta', 'parliament-session'],
  disaster: ['map', 'disasters', 'weather', 'newsfeed', 'govt'],
  flood: ['flood-situation-command', 'flood-assessment', 'flood-gov-services', 'flood-district-map', 'flood-district-toll', 'flood-chronology', 'flood-river-gauges', 'flood-missing-ledger', 'flood-cited-reporting'],
};

// Mobile detection hook
const MOBILE_QUERY = '(max-width: 768px)';
const mobileSubscribe = (cb: () => void) => {
  const mql = window.matchMedia(MOBILE_QUERY);
  mql.addEventListener('change', cb);
  return () => mql.removeEventListener('change', cb);
};
const getMobileSnapshot = () => window.matchMedia(MOBILE_QUERY).matches;
const getMobileServerSnapshot = () => false;

function useIsMobile() {
  return useSyncExternalStore(mobileSubscribe, getMobileSnapshot, getMobileServerSnapshot);
}

// Get appropriate preset based on user role
function getPresetForRole(role?: UserRole): string {
  switch (role) {
    case 'dev':
    case 'analyst':
      return 'intelligence';
    case 'consumer':
    default:
      return 'news';
  }
}

function getMobileWidgetOrder(presetId: string, visibleWidgets: string[]): string[] {
  const presetWidgets = MOBILE_WIDGETS_BY_PRESET[presetId];
  if (presetWidgets) {
    const visibleSet = new Set(visibleWidgets);
    const ordered = presetWidgets.filter((id) => visibleSet.has(id) && WIDGET_COMPONENTS[id]);
    if (ordered.length > 0) return ordered;
  }

  return visibleWidgets.filter((id) => WIDGET_COMPONENTS[id]).slice(0, 5);
}

function getImmediateWidgetIds(presetId: string, visibleWidgets: string[]): string[] {
  const preferred = IMMEDIATE_WIDGETS_BY_PRESET[presetId];
  if (!preferred) {
    return visibleWidgets.filter((id) => WIDGET_COMPONENTS[id]).slice(0, 4);
  }

  const visibleSet = new Set(visibleWidgets);
  const ordered = preferred.filter((id) => visibleSet.has(id) && WIDGET_COMPONENTS[id]);
  return ordered.length > 0 ? ordered : visibleWidgets.filter((id) => WIDGET_COMPONENTS[id]).slice(0, 4);
}

function DashboardWidgetPlaceholder({
  widgetId,
  size,
  containerRef,
}: {
  widgetId: string;
  size?: string;
  containerRef?: Ref<HTMLDivElement>;
}) {
  const sizeClass = `widget-${size || 'medium'}`;
  const widgetLabel = WIDGET_META[widgetId]?.consumerName || WIDGET_META[widgetId]?.name || widgetId;
  return (
    <div ref={containerRef} className={`widget ${sizeClass} dashboard-shell-widget`} aria-hidden="true">
      <div className="widget-header">
        <span className="widget-drag-handle" />
        <span className="widget-title">
          <span className="widget-title-text">{widgetLabel}</span>
        </span>
      </div>
      <div className="widget-body">
        <div className="widget-skeleton">
          <div className="widget-skeleton-topline">
            <div className="widget-skeleton-chip" />
          </div>
          <div className="widget-skeleton-grid">
            <div className="widget-skeleton-card">
              <div className="widget-skeleton-label" />
              <div className="widget-skeleton-value" />
              <div className="widget-skeleton-meta" />
            </div>
            <div className="widget-skeleton-card">
              <div className="widget-skeleton-label" />
              <div className="widget-skeleton-value short" />
              <div className="widget-skeleton-meta" />
            </div>
            <div className="widget-skeleton-card">
              <div className="widget-skeleton-label" />
              <div className="widget-skeleton-value short" />
              <div className="widget-skeleton-meta short" />
            </div>
          </div>
          <div className="widget-skeleton-list">
            <div className="widget-skeleton-row">
              <div className="widget-skeleton-line headline" />
              <div className="widget-skeleton-line" />
            </div>
            <div className="widget-skeleton-row">
              <div className="widget-skeleton-line headline medium" />
              <div className="widget-skeleton-line medium" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function DeferredDashboardWidget({
  widgetId,
  size,
  canMount,
  eager,
  resetKey,
  rootRef,
  children,
}: {
  widgetId: string;
  size?: string;
  canMount: boolean;
  eager: boolean;
  resetKey: string;
  rootRef: RefObject<HTMLDivElement | null>;
  children: ReactNode;
}) {
  const placeholderRef = useRef<HTMLDivElement | null>(null);
  const [ready, setReady] = useState(canMount && eager);

  useEffect(() => {
    if (!canMount) {
      setReady(false);
      return;
    }
    setReady(eager);
  }, [canMount, eager, resetKey]);

  useEffect(() => {
    if (!canMount || eager || ready) return;
    const node = placeholderRef.current;
    if (!node) return;

    if (typeof IntersectionObserver === 'undefined') {
      const timeoutId = window.setTimeout(() => setReady(true), 1500);
      return () => window.clearTimeout(timeoutId);
    }

    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting || entry.intersectionRatio > 0)) {
        setReady(true);
        observer.disconnect();
      }
    }, {
      root: rootRef.current,
      rootMargin: '360px 0px',
    });

    observer.observe(node);
    return () => observer.disconnect();
  }, [canMount, eager, ready, rootRef, resetKey]);

  if (ready) {
    return <>{children}</>;
  }

  return <DashboardWidgetPlaceholder widgetId={widgetId} size={size} containerRef={placeholderRef} />;
}

export function Dashboard() {
  const { widgetOrder, widgetVisibility, widgetSizes, applyPreset, activePreset, theme } = useDashboardStore();
  const { user, isGuest } = useAuthStore();
  const {
    clearTourReplay,
    completeDashboardTour,
    shouldShowDashboardOnboarding,
    skipDashboardTour,
    startDashboardTour,
    tourReplayRequested,
  } = useUserPreferencesStore();
  const initializedForRole = useRef<UserRole | null>(null);
  const isMobileViewport = useIsMobile();
  // Phones get the desktop-only page unless this device has asked for the
  // full desk (remembered per device). A forced desk is laid out as desktop.
  const [forceDesktop, setForceDesktop] = useState<boolean>(() => readForceDesktop());
  const isMobile = isMobileViewport && !forceDesktop;
  const navigate = useNavigate();

  // Analyst mode state
  const [feedbackMode, setFeedbackMode] = useState(false);
  const [selectedStories, setSelectedStories] = useState<Set<string>>(new Set());
  const [feedbackPanelStory, setFeedbackPanelStory] = useState<any>(null);
  const [showWelcome, setShowWelcome] = useState(false);
  const [tourOpen, setTourOpen] = useState(false);
  const [bootstrapStatus, setBootstrapStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const widgetGridRef = useRef<HTMLDivElement | null>(null);

  const isAnalystOrDev = user?.role === 'analyst' || user?.role === 'dev';
  const onboardingUserKey = useMemo(() => {
    if (!user) return null;
    return isGuest ? `guest:${user.id}` : `${user.authProvider}:${user.id}`;
  }, [isGuest, user]);
  const onboardingSteps = useMemo(() => getDashboardTourSteps(isMobile), [isMobile]);

  // Initialize dashboard preset based on user role (only once per role change)
  useEffect(() => {
    if (!user?.role) return;
    if (initializedForRole.current === user.role) return;

    const targetPreset = isMobile && (user.role === 'analyst' || user.role === 'dev')
      ? 'news'
      : getPresetForRole(user.role);

    // Only auto-apply if user hasn't customized (check if current matches a known preset)
    const isDefaultState = (activePreset === 'intelligence' || activePreset === 'news') && initializedForRole.current === null;

    if (isDefaultState && PRESETS[targetPreset]) {
      applyPreset(targetPreset);
    }

    initializedForRole.current = user.role;
  }, [user?.role, applyPreset, activePreset, isMobile]);

  // Keyboard shortcuts: N → News, E → Economy, I → Intelligence.
  // A → Accountability went with the tab; the preset is archived, not deleted.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || (e.target as HTMLElement)?.isContentEditable) return;
      const key = e.key.toLowerCase();
      if (key === 'n') {
        e.preventDefault();
        applyPreset('news');
      } else if (key === 'e') {
        e.preventDefault();
        applyPreset('economy');
      } else if (key === 'i' && (user?.role === 'analyst' || user?.role === 'dev')) {
        e.preventDefault();
        applyPreset('intelligence');
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [applyPreset, user?.role]);

  // Toggle story selection for bulk actions
  const toggleStorySelection = (id: string) => {
    setSelectedStories(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  // Open feedback panel for a story
  const openFeedbackPanel = (story: any) => {
    setFeedbackPanelStory(story);
  };

  // Handle bulk actions
  const handleBulkAction = (action: string) => {
    // TODO: Implement bulk feedback submission
    // TODO: Implement bulk feedback submission
    setSelectedStories(new Set());
  };

  // Handle feedback submission
  const handleFeedbackSubmit = (feedback: any) => {
    // TODO: Submit feedback to backend
    // TODO: Submit to backend
  };

  // Filter and order widgets
  const allVisible = widgetOrder.filter(id => widgetVisibility[id]);
  const visibleWidgets = isMobile
    ? getMobileWidgetOrder(activePreset, allVisible)
    : allVisible;
  const immediateWidgetIds = useMemo(
    () => new Set(getImmediateWidgetIds(activePreset, visibleWidgets)),
    [activePreset, visibleWidgets],
  );
  const widgetMountResetKey = `${activePreset}:${visibleWidgets.join(',')}`;
  const bootstrapPreset = BOOTSTRAP_PRESETS.has(activePreset as DashboardBootstrapPreset)
    ? activePreset as DashboardBootstrapPreset
    : null;
  const bootstrapReady = !bootstrapPreset || bootstrapStatus !== 'loading';
  // Analyst mode context value — memoized to prevent unnecessary consumer re-renders
  const analystModeValue = useMemo<AnalystModeContextType>(() => ({
    feedbackMode,
    selectedStories,
    toggleStorySelection,
    openFeedbackPanel,
  }), [feedbackMode, selectedStories]);

  const themeClass = theme === 'bloomberg' ? 'bloomberg-theme' : '';

  useEffect(() => {
    if (!bootstrapPreset) {
      setBootstrapStatus('ready');
      return;
    }

    let cancelled = false;
    setBootstrapStatus('loading');

    getDashboardBootstrap(bootstrapPreset)
      .then((payload) => {
        if (cancelled) return;
        hydrateDashboardBootstrap(queryClient, payload);
        setBootstrapStatus('ready');
      })
      .catch(() => {
        if (cancelled) return;
        setBootstrapStatus('error');
      });

    return () => {
      cancelled = true;
    };
  }, [bootstrapPreset]);

  useEffect(() => {
    if (!onboardingUserKey || user?.role !== 'consumer') return;
    if (showWelcome || tourOpen) return;

    const timer = window.setTimeout(() => {
      if (shouldShowDashboardOnboarding(onboardingUserKey, isGuest)) {
        setShowWelcome(true);
      }
    }, tourReplayRequested ? 0 : 500);

    return () => window.clearTimeout(timer);
  }, [
    isGuest,
    onboardingUserKey,
    shouldShowDashboardOnboarding,
    showWelcome,
    tourOpen,
    tourReplayRequested,
    user?.role,
  ]);

  const handleStartTour = () => {
    startDashboardTour();
    clearTourReplay();
    setShowWelcome(false);
    setTourOpen(true);
  };

  const handleSkipOnboarding = () => {
    if (onboardingUserKey) {
      skipDashboardTour(onboardingUserKey);
    } else {
      clearTourReplay();
    }
    setShowWelcome(false);
    setTourOpen(false);
  };

  const handleCompleteTour = () => {
    if (onboardingUserKey) {
      completeDashboardTour(onboardingUserKey);
    } else {
      clearTourReplay();
    }
    setShowWelcome(false);
    setTourOpen(false);
  };

  const handleCreateAccount = () => {
    if (onboardingUserKey) {
      skipDashboardTour(onboardingUserKey);
    } else {
      clearTourReplay();
    }
    setShowWelcome(false);
    setTourOpen(false);
    navigate('/login', { state: { mode: 'signup' } });
  };

  const handleTourStepChange = (step: { presetId?: 'news' | 'economy' | 'parliament' | 'elections' }) => {
    if (step.presetId && activePreset !== step.presetId) {
      applyPreset(step.presetId)
    }
  }

  if (isMobileViewport && !forceDesktop) {
    return (
      <DesktopOnlyGate
        onForceDesktop={() => {
          try {
            localStorage.setItem(FORCE_DESKTOP_KEY, '1');
          } catch {
            /* private mode: the choice lasts for this page only */
          }
          const meta = document.querySelector('meta[name="viewport"]');
          if (meta) meta.setAttribute('content', 'width=1280');
          setForceDesktop(true);
        }}
      />
    );
  }

  return (
    <AnalystModeContext.Provider value={analystModeValue}>
      <div
        className={`dashboard-app ${themeClass} ${feedbackMode ? 'feedback-mode' : ''} ${isMobile ? 'mobile-layout' : ''}`}
        data-active-preset={activePreset}
      >
        <DashboardHeader />

        {/* Alert Ticker - always visible */}
        <AlertTicker />

        {/* Analyst Toolbar - only for analyst/dev roles */}
        {isAnalystOrDev && (
          <AnalystToolbar
            feedbackMode={feedbackMode}
            setFeedbackMode={setFeedbackMode}
            selectedCount={selectedStories.size}
            onBulkAction={handleBulkAction}
          />
        )}

        <main className="dashboard-main">
          <div className="widget-grid" ref={widgetGridRef}>
            {visibleWidgets.map(widgetId => {
              const WidgetComponent = WIDGET_COMPONENTS[widgetId];
              if (!WidgetComponent) return null;
              const isImmediate = immediateWidgetIds.has(widgetId);

              return (
                <DeferredDashboardWidget
                  key={widgetId}
                  widgetId={widgetId}
                  size={widgetSizes[widgetId]}
                  canMount={bootstrapReady}
                  eager={isImmediate}
                  resetKey={widgetMountResetKey}
                  rootRef={widgetGridRef}
                >
                  <Suspense
                    fallback={<DashboardWidgetPlaceholder widgetId={widgetId} size={widgetSizes[widgetId]} />}
                  >
                    <WidgetComponent />
                  </Suspense>
                </DeferredDashboardWidget>
              );
            })}
          </div>
        </main>

        <CustomizePanel />
        <CommandPalette />

        {/* Feedback Panel */}
        {feedbackPanelStory && (
          <FeedbackPanel
            story={feedbackPanelStory}
            onClose={() => setFeedbackPanelStory(null)}
            onSubmit={handleFeedbackSubmit}
          />
        )}

        {user?.role === 'consumer' && (
          <>
            <WelcomeModal
              isOpen={showWelcome}
              isGuest={isGuest}
              onStartTour={handleStartTour}
              onSkip={handleSkipOnboarding}
              onCreateAccount={handleCreateAccount}
            />
            <DashboardTour
              isOpen={tourOpen}
              isGuest={isGuest}
              steps={onboardingSteps}
              onComplete={handleCompleteTour}
              onSkip={handleSkipOnboarding}
              onCreateAccount={handleCreateAccount}
              onStepChange={handleTourStepChange}
            />
          </>
        )}

      </div>
    </AnalystModeContext.Provider>
  );
}
