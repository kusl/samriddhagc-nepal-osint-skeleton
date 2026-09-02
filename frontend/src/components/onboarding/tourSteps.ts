import { IS_PUBLIC_ONLY, isPresetEnabled } from '../../config/deployment'

export type TourPlacement = 'top' | 'right' | 'bottom' | 'left' | 'center'

export interface DashboardTourStep {
  id: string
  title: string
  description: string
  targetId?: string
  placement: TourPlacement
  mobileEnabled: boolean
  guestCta?: 'create-account'
  requiresScroll?: boolean
  presetId?: 'news' | 'economy' | 'parliament' | 'elections'
}

const DESKTOP_STEPS: DashboardTourStep[] = [
  {
    id: 'presets',
    title: 'Switch dashboard views',
    description: 'These tabs swap the dashboard composition. Use them to move between the news, flood, and economy views.',
    targetId: 'preset-tabs',
    placement: 'bottom',
    mobileEnabled: false,
  },
  {
    id: 'news-tab',
    title: 'Start in the News workspace',
    description: 'Begin in News when you want the live operational picture first. This is the default workspace for breaking developments, verified updates, and fast situational awareness.',
    targetId: 'news-tab',
    placement: 'bottom',
    mobileEnabled: false,
    presetId: 'news',
  },
  {
    id: 'news-map',
    title: 'Use the map for fast geographic context',
    description: 'The News map shows where activity, incidents, and pressure are concentrating. Use it first when you want to understand location, spread, and intensity before opening individual stories.',
    targetId: 'news-map',
    placement: 'bottom',
    mobileEnabled: true,
    requiresScroll: true,
    presetId: 'news',
  },
  {
    id: 'stories-feed',
    title: 'Watch the live intake',
    description: 'Live Feed shows raw story intake as it lands. This is where you monitor what is new before it matures into broader narrative patterns.',
    targetId: 'stories-feed',
    placement: 'top',
    mobileEnabled: true,
    requiresScroll: true,
  },
  {
    id: 'fact-check',
    title: 'Open the fact checks',
    description: 'Fact Check highlights claims that have already been reviewed, disputed, or confirmed so you can separate noise from stronger reporting.',
    targetId: 'fact-check',
    placement: 'top',
    mobileEnabled: true,
    requiresScroll: true,
    presetId: 'news',
  },
  {
    id: 'provincial-monitor',
    title: 'Scan province-by-province',
    description: 'Provincial Monitor rolls activity up by province so you can see where pressure, risk, or stability is concentrated.',
    targetId: 'provincial-monitor',
    placement: 'top',
    mobileEnabled: false,
    requiresScroll: true,
    presetId: 'news',
  },
  {
    id: 'economy-tab',
    title: 'Use Economy for the financial picture',
    description: 'Open Economy when you want the business and macro side of the country. This workspace brings together economic news, markets, NRB indicators, trade and customs, debt, contracts, and other financial signals in one place.',
    targetId: 'economy-tab',
    placement: 'bottom',
    mobileEnabled: false,
    presetId: 'economy',
  },
  {
    id: 'account-menu',
    title: 'Guest versus account',
    description: 'Guest sessions are temporary and read-only. Create an account when you want a persistent identity and future personalized features.',
    targetId: 'account-menu',
    placement: 'bottom',
    mobileEnabled: true,
    guestCta: 'create-account',
  },
  {
    id: 'help-tour',
    title: 'Replay this anytime',
    description: 'Use Guide whenever you want to replay the tour later. You do not need to remember everything on the first pass.',
    targetId: 'help-tour',
    placement: 'bottom',
    mobileEnabled: true,
    guestCta: 'create-account',
  },
]

const MOBILE_STEPS: DashboardTourStep[] = [
  {
    id: 'news-map',
    title: 'Start with the map',
    description: 'The map gives you the fastest geographic read on where activity is clustering before you drill into individual stories.',
    targetId: 'news-map',
    placement: 'bottom',
    mobileEnabled: true,
    requiresScroll: true,
    presetId: 'news',
  },
  {
    id: 'fact-check',
    title: 'Use live feed and fact check together',
    description: 'Watch new reporting in the live feed, then cross-check reviewed claims here when you need more confidence.',
    targetId: 'fact-check',
    placement: 'top',
    mobileEnabled: true,
    requiresScroll: true,
  },
  {
    id: 'economy-tab',
    title: 'Use Economy for markets and macro',
    description: 'After the live news view, open Economy when you want NRB indicators, markets, trade, debt, and broader business signals in one workspace.',
    targetId: 'economy-tab',
    placement: 'bottom',
    mobileEnabled: true,
    presetId: 'economy',
  },
  {
    id: 'help-tour',
    title: 'Return here anytime',
    description: 'Open Guide to replay this walkthrough later. If you are still in a guest session, create an account when you want a persistent identity.',
    targetId: 'help-tour',
    placement: 'bottom',
    mobileEnabled: true,
    guestCta: 'create-account',
  },
]

export function getDashboardTourSteps(isMobile: boolean): DashboardTourStep[] {
  const steps = isMobile ? MOBILE_STEPS : DESKTOP_STEPS

  // Never walk someone to a tab this deployment does not render, and on the
  // public build drop the account steps — there is no sign-up to send them to.
  return steps.filter((step) => {
    if (step.presetId && !isPresetEnabled(step.presetId)) return false
    if (IS_PUBLIC_ONLY && step.guestCta === 'create-account') return false
    if (IS_PUBLIC_ONLY && step.id === 'account-menu') return false
    return true
  })
}
