import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import {
  dimensionsFromSize,
  dimensionsFromSizes,
  findNearestPreset,
  type WidgetDimensions,
  type WidgetSize,
} from '../components/Dashboard/widgetGrid';

export type { WidgetSize } from '../components/Dashboard/widgetGrid';

export interface WidgetConfig {
  id: string;
  name: string;
  visible: boolean;
  size: WidgetSize;
}

export interface Preset {
  id: string;
  name: string;
  description: string;
  order: string[];
  visibility: Record<string, boolean>;
  sizes: Record<string, WidgetSize>;
}

// All available widgets
// Role hierarchy: consumer < analyst < dev
export type WidgetRole = 'consumer' | 'analyst' | 'dev';

const ARCHIVED_ELECTION_WIDGET_IDS = new Set([
  'elections',
  'election-map',
  'election-pr',
  'election-seats',
  'election-status',
  'swing-analysis',
  'close-races',
  'incumbency',
  'candidates',
  'party-switch',
  'election-live',
]);

const RETIRED_NATIONAL_ASSESSMENT_WIDGET_IDS = new Set([
  'situation-brief',
  'intel-brief-hero',
]);

function moveBottomWidgetsToEnd(order: string[]): string[] {
  const pinnedBottomWidgets = ['disasters', 'govt'];
  const filtered = order.filter((id) => !pinnedBottomWidgets.includes(id));
  for (const widgetId of pinnedBottomWidgets) {
    if (order.includes(widgetId)) {
      filtered.push(widgetId);
    }
  }
  return filtered;
}

export const WIDGET_META: Record<string, {
  name: string;
  category: string;
  minRole?: WidgetRole;  // Minimum role required (default: consumer)
  consumerName?: string; // Friendlier name for consumers
  wip?: boolean;         // Work in progress (hardcoded/placeholder data)
}> = {
  // Core widgets - available to all (REAL DATA)
  map: { name: 'Situation Map', category: 'core', consumerName: 'News Map' },
  'election-map': { name: 'Election Map', category: 'elections', consumerName: 'Election Map' },
  kpi: { name: 'Key Metrics', category: 'core', consumerName: 'Today\'s Stats' },
  stories: { name: 'Stories Feed', category: 'core', consumerName: 'Top Stories' },
  newsfeed: { name: 'Live News Feed', category: 'core', consumerName: 'Live Feed' },
  briefing: { name: 'Briefing', category: 'core', minRole: 'analyst', wip: true },
  entities: { name: 'Key Entities', category: 'core', minRole: 'analyst', consumerName: 'People in News', wip: true },

  // Collaboration widgets - analyst only (WIP - no backend yet)
  'cases-active': { name: 'Active Cases', category: 'collaboration', minRole: 'analyst', wip: true },
  'collab-feed': { name: 'Activity Feed', category: 'collaboration', minRole: 'analyst', wip: true },
  'verification-queue': { name: 'Verification Queue', category: 'collaboration', minRole: 'analyst', wip: true },
  'analyst-leaderboard': { name: 'Leaderboard', category: 'collaboration', minRole: 'analyst', wip: true },

  // Research widgets
  'entity-watchlist': { name: 'Entity Watchlist', category: 'research', minRole: 'analyst', wip: true },
  'analyst-notes': { name: 'Research Notes', category: 'research', minRole: 'analyst', wip: true },
  'source-reliability': { name: 'Source Reliability', category: 'research', consumerName: 'Source Reliability' },

  // Politics & elections - available to all (ECN data)
  elections: { name: 'Election Watchlist', category: 'politics', consumerName: 'Elections' },
  govt: { name: 'Govt Announcements', category: 'politics', consumerName: 'Government Updates' },

  // Economy - available to all (REAL DATA - NEPSE, forex, gold/silver)
  market: { name: 'Market & Exchange', category: 'economy', consumerName: 'Markets' },
  'economic-news': { name: 'Economic News', category: 'economy', consumerName: 'Economic News' },
  'price-watch': { name: 'Price Watch', category: 'economy', consumerName: 'Price Watch' },
  'trade-customs': { name: 'Trade & Customs', category: 'economy', consumerName: 'Trade & Customs' },
  'public-spending': { name: 'Public Spending', category: 'economy', consumerName: 'Public Spending' },
  'nrb-macro': { name: 'NRB Macro Monitor', category: 'economy', consumerName: 'NRB Macro Monitor' },
  'nrb-prices': { name: 'NRB Prices & Flows', category: 'economy', consumerName: 'NRB Prices & Flows' },
  'nrb-banking': { name: 'Banking & Liquidity', category: 'economy', consumerName: 'Banking & Liquidity' },
  'fiscal-position': { name: 'Fiscal Position', category: 'economy', consumerName: 'Fiscal Position' },
  'external-sector': { name: 'External Sector', category: 'economy', consumerName: 'External Sector' },
  'monetary-conditions': { name: 'Monetary Conditions', category: 'economy', consumerName: 'Monetary Conditions' },
  'prices-cost-pressure': { name: 'Prices & Cost Pressure', category: 'economy', consumerName: 'Prices & Cost Pressure' },

  // Security - available to all (REAL DATA)
  threats: { name: 'Risk Matrix', category: 'security', consumerName: 'Risk Matrix' },

  // Media - available to all
  social: { name: 'Social Feed', category: 'media' },  // Uses Twitter API

  // Disasters & environment - REAL DATA from APIs
  disasters: { name: 'Disaster Alerts', category: 'disasters', consumerName: 'Alerts' },
  rivers: { name: 'River Monitoring', category: 'disasters', consumerName: 'River Monitoring' },
  weather: { name: 'Weather & Forecast', category: 'disasters', consumerName: 'Weather' },
  seismic: { name: 'Seismic Activity', category: 'disasters', consumerName: 'Earthquakes' },

  // Election Monitor Widgets - ECN data (result.election.gov.np)
  'election-pr': { name: 'PR Seat Projection', category: 'elections' },
  'election-seats': { name: 'HOR Seat Tracker', category: 'elections' },
  'election-status': { name: 'FPTP Constituency Results', category: 'elections' },
  'swing-analysis': { name: 'Swing Analysis', category: 'elections', minRole: 'analyst' },
  'close-races': { name: 'Close Races', category: 'elections' },
  'incumbency': { name: 'Incumbency', category: 'elections', minRole: 'analyst' },
  'candidates': { name: 'Candidates', category: 'elections' },
  'party-switch': { name: 'Party Switchers', category: 'elections', minRole: 'analyst' },

  // Know Your Parliamentarian — elected winners from 2082
  neta: { name: 'Know Your Parliamentarian', category: 'politics', consumerName: 'Your Parliamentarians' },

  // Election Live Stream
  'election-live': { name: 'Election Live', category: 'elections', consumerName: 'Live Coverage' },

  // Situation Monitor Widgets
  'political-pulse': { name: 'Political Pulse', category: 'media', consumerName: 'Political Activity' },
  'province-monitor': { name: 'Provincial Monitor', category: 'core', consumerName: 'Provincial Monitor' },
  'narrative-tracker': { name: 'Story Tracker', category: 'core', consumerName: 'Story Clusters' },
  'developing-stories': { name: 'Developing Stories', category: 'core', consumerName: 'Breaking News' },
  'fact-check': { name: 'Fact Check', category: 'core', consumerName: 'Fact Checker' },

  // Parliament & Accountability
  'promise-tracker': { name: 'Accountability Tracker', category: 'parliament', consumerName: 'Cabinet & Manifesto Tracker' },
  'parliament-session': { name: 'Parliamentary Summary', category: 'parliament', consumerName: 'Parliament Summary' },
  'govt-decisions': { name: 'Government Decisions', category: 'parliament', consumerName: 'Govt Decisions' },
  'govt-loan-tracker': { name: 'Nepal Debt Clock', category: 'parliament', consumerName: 'Debt Clock' },
  'debt-tracker': { name: 'Debt Tracker', category: 'parliament', consumerName: 'Debt Tracker' },
  'govt-contracts': { name: 'Govt Contracts', category: 'parliament', consumerName: 'Govt Contracts' },
  'bill-tracker': { name: 'Bills Tracker', category: 'parliament', consumerName: 'Parliamentary Bills' },
  'parliament-activity': { name: 'Parliamentary Activity', category: 'parliament', consumerName: 'MP Activity' },
};

// Check if widget is WIP
export function isWidgetWIP(widgetId: string): boolean {
  return WIDGET_META[widgetId]?.wip || false;
}

// Helper to check if user can access widget
export function canAccessWidget(widgetId: string, userRole: WidgetRole | undefined): boolean {
  const meta = WIDGET_META[widgetId];
  if (!meta) return false;

  const minRole = meta.minRole || 'consumer';
  const roleHierarchy: WidgetRole[] = ['consumer', 'analyst', 'dev'];
  const userLevel = roleHierarchy.indexOf(userRole || 'consumer');
  const requiredLevel = roleHierarchy.indexOf(minRole);

  return userLevel >= requiredLevel;
}

// Get display name based on role
export function getWidgetDisplayName(widgetId: string, userRole: WidgetRole | undefined): string {
  const meta = WIDGET_META[widgetId];
  if (!meta) return widgetId;

  // Use consumer-friendly name for consumers
  if (userRole === 'consumer' && meta.consumerName) {
    return meta.consumerName;
  }
  return meta.name;
}

// Preset configurations - All sizes designed to fill 12-column grid without gaps
export const PRESETS: Record<string, Preset> = {
  // ============================================
  // CONSUMER PRESETS (Simplified, read-only)
  // ============================================
  news: {
    id: 'news',
    name: 'News Dashboard',
    description: 'News Map with stats, provincial monitor, live feed, fact-check, clusters, markets, alerts and govt updates',
    order: [
      'map', 'kpi', 'newsfeed', 'developing-stories',
      'fact-check', 'stories', 'social', 'narrative-tracker', 'province-monitor', 'market',
      'weather', 'source-reliability', 'disasters', 'govt'
    ],
    visibility: {
      map: true, 'election-live': false, kpi: true, newsfeed: true,
      'developing-stories': true, 'fact-check': true, stories: true, social: true,
      'narrative-tracker': true, 'province-monitor': true, market: true,
      disasters: true, govt: true, weather: true, 'source-reliability': true,
      // Hidden
      'election-map': false, 'election-status': false,
      'political-pulse': false, briefing: false, entities: false,
      seismic: false, elections: false,
      threats: false, neta: false,
    },
    sizes: {
      map: 'situation',               // Row 1: 12 cols, double height (news map)
      'election-live': 'hero',        // Row 2: 12 cols (2x2 live streams)
      kpi: 'full',                    // Row 3: 12 cols
      newsfeed: 'large',              // Row 4: 8 cols (live feed)
      'developing-stories': 'small',  // Row 4: 4 cols (8+4=12)
      'fact-check': 'medium',         // Row 5: 6 cols
      stories: 'medium',              // Row 5: 6 cols (6+6=12)
      social: 'medium',               // Row 6: 6 cols
      'narrative-tracker': 'medium',  // Row 6: 6 cols (6+6=12)
      'province-monitor': 'large',    // Row 7: 8 cols
      market: 'small',                // Row 7: 4 cols (8+4=12)
      weather: 'medium',              // Row 8: 6 cols
      'source-reliability': 'medium', // Row 8: 6 cols (6+6=12)
      disasters: 'medium',            // Row 9: 6 cols
      govt: 'medium',                 // Row 9: 6 cols (6+6=12)
    }
  },

  // ============================================
  // ANALYST PRESETS (Comprehensive)
  // ============================================
  analyst: {
    id: 'analyst',
    name: 'Analyst Election Monitor',
    description: 'Election coverage with live feeds, verification surfaces and social signals',
    order: [
      'election-map', 'kpi', 'newsfeed', 'developing-stories',
      'stories', 'fact-check', 'social', 'election-status'
    ],
    visibility: {
      'election-map': true, kpi: true, newsfeed: true,
      'developing-stories': true, stories: true, social: true, 'election-status': true,
      'fact-check': true,
      // Hidden
      map: false, market: false, weather: false, govt: false, threats: false,
      disasters: false, elections: false, seismic: false, 'province-monitor': false,
      briefing: false, entities: false
    },
    sizes: {
      'election-map': 'situation',
      kpi: 'full',
      newsfeed: 'large',
      'developing-stories': 'small',
      stories: 'medium',
      social: 'medium',
      'election-status': 'medium',
      'fact-check': 'medium',
    }
  },

  intelligence: {
    id: 'intelligence',
    name: 'Intelligence Monitor',
    description: 'Tactical situation map, provincial monitor, developing stories, fact-checks & narrative tracking',
    // Layout: situation(12) -> full(12) -> full(12) -> medium+medium(6+6) x2
    order: [
      'map', 'kpi', 'developing-stories', 'fact-check', 'province-monitor',
      'newsfeed', 'narrative-tracker', 'social'
    ],
    visibility: {
      map: true, kpi: true, 'province-monitor': true, 'developing-stories': true, 'fact-check': true,
      newsfeed: true, 'narrative-tracker': true, social: true,
      // Hidden
      stories: false, weather: false, disasters: false, elections: false,
      market: false, govt: false, threats: false, briefing: false, entities: false,
      seismic: false,
      'election-map': false, 'election-status': false, 'swing-analysis': false,
      'close-races': false, 'incumbency': false, 'candidates': false, 'party-switch': false,
      neta: false, 'political-pulse': false,
    },
    sizes: {
      map: 'situation',                // Row 1: 12 cols, double height (tactical map)
      kpi: 'full',                    // Row 2: 12 cols
      'developing-stories': 'medium', // Row 3: 6 cols
      'fact-check': 'medium',         // Row 3: 6 cols (6+6=12)
      'province-monitor': 'full',     // Row 4: 12 cols
      newsfeed: 'medium',             // Row 5: 6 cols
      'narrative-tracker': 'medium',  // Row 5: 6 cols (6+6=12)
      social: 'full',                 // Row 6: 12 cols
    }
  },

  elections: {
    id: 'elections',
    name: 'Election Monitor',
    description: 'Nepal\'s Election Monitor — live stream, map, results',
    order: [
      'election-map', 'election-seats', 'election-live', 'election-pr', 'election-status'
    ],
    visibility: {
      'election-map': true, 'election-seats': true, 'election-live': true, 'election-pr': true, 'election-status': true,
      'candidates': false, 'close-races': false,
      newsfeed: false, social: false,
      // Hidden during live counting
      'swing-analysis': false, 'incumbency': false, 'party-switch': false,
      map: false, govt: false, elections: false, entities: false, stories: false,
      kpi: false, disasters: false, market: false,
      weather: false, seismic: false,
      threats: false, briefing: false
    },
    sizes: {
      'election-map': 'situation',   // Row 1: 12 cols, double height
      'election-seats': 'hero',       // Row 2: 12 cols (combined seat tracker)
      'election-live': 'hero',       // Row 3: 12 cols (YouTube live streams)
      'election-pr': 'hero',         // Row 4: 12 cols (PR seat projection)
      'election-status': 'hero',     // Row 4: 12 cols, tall (national scoreboard)
      'candidates': 'full',          // Row 4: 12 cols
      'close-races': 'full',         // Row 5: 12 cols
      newsfeed: 'medium',            // Row 6: 6 cols
      social: 'medium',              // Row 6: 6 cols (6+6=12)
    }
  },

  parliament: {
    id: 'parliament',
    name: 'Accountability',
    description: 'Track government promises, bills, parliamentary speeches & elected leaders',
    order: [
      'promise-tracker',
      'bill-tracker', 'parliament-activity',
      'govt-decisions', 'neta',
      'parliament-session',
    ],
    visibility: {
      'promise-tracker': true, 'bill-tracker': true, 'parliament-activity': true,
      'govt-decisions': true, 'parliament-session': true, neta: true,
      // Hidden
      'political-pulse': false,
      'election-seats': false, newsfeed: false, social: false, 'fact-check': false,
      map: false, kpi: false, 'situation-brief': false, stories: false,
      'election-map': false, 'election-status': false, 'election-live': false, 'election-pr': false,
      weather: false, disasters: false, elections: false, market: false, govt: false,
      'economic-news': false, 'price-watch': false, 'trade-customs': false, 'public-spending': false, 'nrb-macro': false,
      'govt-loan-tracker': false, 'debt-tracker': false, 'govt-contracts': false,
      threats: false, briefing: false, entities: false, seismic: false,
      'swing-analysis': false, 'close-races': false, 'incumbency': false,
      'candidates': false, 'party-switch': false,
      'developing-stories': false, 'narrative-tracker': false, 'province-monitor': false,
      'intel-brief-hero': false,
    },
    sizes: {
      'promise-tracker': 'hero',              // Row 1: 12 cols, ~6-7 rows tall (manifesto tracker)
      'bill-tracker': 'half',                 // Row 2: 6 cols (bills pipeline)
      'parliament-activity': 'half',          // Row 2: 6 cols (verbatim speech activity)
      'govt-decisions': 'half',               // Row 3: 6 cols
      neta: 'half',                           // Row 3: 6 cols
      'parliament-session': 'full',           // Row 4: 12 cols
    }
  },

  economy: {
    id: 'economy',
    name: 'Economy',
    description: 'Economic news, markets, customs flow, central bank data and public contracts',
    order: [
      'economic-news',
      'market',
      'trade-customs',
      'fiscal-position', 'external-sector',
      'monetary-conditions', 'prices-cost-pressure',
      'govt-loan-tracker', 'govt-contracts',
      'debt-tracker',
    ],
    visibility: {
      'economic-news': true,
      market: true,
      'price-watch': false,
      'trade-customs': true,
      'nrb-macro': false,
      'nrb-prices': false,
      'nrb-banking': false,
      'fiscal-position': true,
      'external-sector': true,
      'monetary-conditions': true,
      'prices-cost-pressure': true,
      'govt-loan-tracker': true,
      'public-spending': false,
      'govt-contracts': true,
      'debt-tracker': true,
      // Hidden
      map: false, 'election-map': false, kpi: false, stories: false, newsfeed: false,
      weather: false, disasters: false, elections: false, entities: false,
      briefing: false, social: false, govt: false, threats: false, seismic: false,
      'election-pr': false, 'election-seats': false, 'election-status': false,
      'swing-analysis': false, 'close-races': false, 'incumbency': false, 'candidates': false,
      'party-switch': false, neta: false, 'election-live': false,
      'intel-brief-hero': false, 'political-pulse': false, 'province-monitor': false,
      'narrative-tracker': false, 'developing-stories': false, 'fact-check': false,
      'promise-tracker': false, 'parliament-session': false, 'govt-decisions': false,
      'bill-tracker': false, 'parliament-activity': false,
      'situation-brief': false, 'source-reliability': false,
      'cases-active': false, 'collab-feed': false, 'verification-queue': false,
      'entity-watchlist': false, 'analyst-notes': false, 'analyst-leaderboard': false,
      rivers: false,
    },
    sizes: {
      'economic-news': 'hero',
      market: 'half',
      'trade-customs': 'half',
      'fiscal-position': 'half',
      'external-sector': 'half',
      'monetary-conditions': 'half',
      'prices-cost-pressure': 'half',
      'govt-loan-tracker': 'half',
      'govt-contracts': 'half',
      'debt-tracker': 'hero',
    },
  },

  disaster: {
    id: 'disaster',
    name: 'Disaster Response',
    description: 'Emergency monitoring & alerts',
    // Layout: situation(12) -> medium+medium(6+6) -> full(12) -> medium+medium(6+6)
    order: [
      'map', 'weather', 'newsfeed',
      'rivers', 'disasters', 'govt'
    ],
    visibility: {
      map: true, weather: true, rivers: true, disasters: true, seismic: false,
      stories: false, briefing: false, newsfeed: true, govt: true,
      kpi: false, elections: false, market: false, social: false, entities: false,
      threats: false
    },
    sizes: {
      map: 'situation',    // Row 1: 12 cols, double height
      weather: 'medium',   // Row 2: 6 cols
      newsfeed: 'medium',  // Row 2: 6 cols (6+6=12)
      rivers: 'medium',    // Row 3: 6 cols
      disasters: 'medium', // Row 3: 6 cols (6+6=12)
      govt: 'full',        // Row 4: 12 cols
    }
  },

  compact: {
    id: 'compact',
    name: 'Compact View',
    description: 'Essential widgets only',
    // Layout: hero(12) -> full(12) -> medium+medium(6+6=12) -> large+small(8+4=12)
    order: ['map', 'kpi', 'newsfeed', 'market', 'disasters', 'weather'],
    visibility: {
      map: true, kpi: true, weather: true, disasters: true, newsfeed: true, market: true,
      stories: false, briefing: false, social: false, govt: false, entities: false,
      elections: false, seismic: false, threats: false
    },
    sizes: {
      map: 'situation',    // Row 1: 12 cols, double height
      kpi: 'full',         // Row 2: 12 cols
      newsfeed: 'medium',  // Row 3: 6 cols
      market: 'medium',    // Row 3: 6 cols (6+6=12)
      disasters: 'large',  // Row 4: 8 cols
      weather: 'small'     // Row 4: 4 cols (8+4=12)
    }
  },

  // ============================================
  // POLITICAL ANALYST PRESET (Primary Analyst Workflow)
  // ============================================

  'political-analyst': {
    id: 'political-analyst',
    name: 'Political Analyst',
    description: 'Political intelligence & governance monitoring',
    // Optimized layout for political analysis workflow
    // Row 1: Map (12) - Situation Monitor (double height)
    // Row 2: Election Status (6) + Govt Announcements (6) = 12
    // Row 3: Active Cases (6) + Stories Feed (6) = 12
    // Row 4: Swing Analysis (6) + Entity Watchlist (6) = 12
    // Row 5: Social Feed (4) + Activity Feed (4) + Verification Queue (4) = 12
    // Row 6: Analyst Notes (4) + Leaderboard (4)
    order: [
      'map', 'election-status', 'govt', 'stories', 'swing-analysis',
      'social'
    ],
    visibility: {
      map: true, 'election-status': true, govt: true, 'cases-active': false, stories: true,
      'entity-watchlist': false, 'swing-analysis': true, social: true, 'collab-feed': false,
      'verification-queue': false, 'analyst-notes': false, 'analyst-leaderboard': false,
      market: false, kpi: false, threats: false, newsfeed: false, briefing: false,
      weather: false, seismic: false, disasters: false, entities: false,
      'source-reliability': false, elections: false,
      'close-races': false, 'incumbency': false, 'candidates': false, 'party-switch': false
    },
    sizes: {
      map: 'situation',              // Row 1: 12 cols, double height
      'election-status': 'medium',   // Row 2: 6 cols
      govt: 'medium',                // Row 2: 6 cols (6+6=12)
      stories: 'medium',             // Row 3: 6 cols
      'swing-analysis': 'medium',    // Row 3: 6 cols (6+6=12)
      social: 'medium'               // Row 4: 6 cols
    }
  },

  // ============================================
  // COLLABORATION HUB (Team Workspace)
  // ============================================

  'collab-hub': {
    id: 'collab-hub',
    name: 'Collaboration Hub',
    description: 'Team workspace & community verification',
    // Layout: large+small(8+4=12) -> medium+medium(6+6=12) x2 -> small+small+small(4+4+4=12) x2
    order: [
      'map', 'stories'
    ],
    visibility: {
      'cases-active': false, 'verification-queue': false, 'collab-feed': false,
      'analyst-leaderboard': false, map: true, stories: true, 'entity-watchlist': false,
      'source-reliability': false, 'analyst-notes': false,
      market: false, kpi: false, threats: false, newsfeed: false, briefing: false,
      weather: false, seismic: false, disasters: false, entities: false,
      social: false, govt: false, elections: false,
      'election-status': false, 'swing-analysis': false, 'close-races': false,
      'incumbency': false, 'candidates': false, 'party-switch': false
    },
    sizes: {
      map: 'hero',                   // Row 1: 12 cols (full width, half height)
      stories: 'full'                // Row 2: 12 cols
    }
  },

  // ============================================
  // ANALYST OPS PRESET (Bloomberg-Dense Console)
  // ============================================
  'analyst-ops': {
    id: 'analyst-ops',
    name: 'Analyst Console',
    description: 'Dense 6-widget ops workstation - no scrolling',
    // Layout: full(12) -> large+small(8+4=12) -> small+small+small(4+4+4=12)
    order: ['kpi', 'stories', 'newsfeed', 'threats', 'elections'],
    visibility: {
      kpi: true, stories: true, 'verification-queue': false,
      newsfeed: true, threats: true, elections: true,
      // Everything else hidden for focus
      map: false, disasters: false, weather: false,      seismic: false, market: false, social: false, govt: false,
      briefing: false, entities: false,
      'cases-active': false, 'collab-feed': false, 'analyst-leaderboard': false,
      'analyst-notes': false, 'entity-watchlist': false, 'source-reliability': false,
      'election-status': false, 'swing-analysis': false, 'close-races': false,
      'incumbency': false, 'candidates': false, 'party-switch': false
    },
    sizes: {
      kpi: 'full',                    // Row 1: 12 cols
      stories: 'large',               // Row 2: 8 cols
      newsfeed: 'small',              // Row 2: 4 cols (8+4=12)
      threats: 'small',               // Row 3: 4 cols
      elections: 'small'              // Row 3: 4 cols
    }
  },

  // ============================================
  // SITUATION MONITOR (Intelligence Platform)
  // ============================================
  'situation-monitor': {
    id: 'situation-monitor',
    name: 'Situation Monitor',
    description: 'At-a-glance intelligence platform — geographic, provincial, political and narrative monitoring',
    // Layout: situation(12) -> full(12) -> hero(12) -> full(12) -> full(12)
    order: [
      'map', 'developing-stories', 'political-pulse', 'province-monitor',
      'narrative-tracker', 'social'
    ],
    visibility: {
      map: true,
      'developing-stories': true,
      'political-pulse': true,
      'province-monitor': true,
      'narrative-tracker': true,
      social: true,
      // Hide everything else
      kpi: false, 'situation-brief': false, stories: false, newsfeed: false,
      weather: false, disasters: false, elections: false, market: false,
      entities: false, briefing: false, govt: false, threats: false,
      seismic: false,
      'election-map': false, 'election-status': false, 'swing-analysis': false,
      'close-races': false, 'incumbency': false, 'candidates': false, 'party-switch': false,
      neta: false, 'cases-active': false, 'collab-feed': false,
      'verification-queue': false, 'entity-watchlist': false,
      'analyst-notes': false, 'source-reliability': false, 'analyst-leaderboard': false,
    },
    sizes: {
      map: 'situation',                 // Row 1: 12 cols
      'developing-stories': 'full',     // Row 2: 12 cols
      'political-pulse': 'hero',        // Row 3: 12 cols (tall)
      'province-monitor': 'full',       // Row 4: 12 cols
      'narrative-tracker': 'full',      // Row 5: 12 cols
      social: 'full',                   // Row 6: 12 cols
    }
  }
};

// Theme types
export type ThemeMode = 'default' | 'bloomberg';

interface DashboardState {
  // Current layout state
  widgetOrder: string[];
  widgetVisibility: Record<string, boolean>;
  widgetSizes: Record<string, WidgetSize>;
  widgetDimensions: Record<string, WidgetDimensions>;
  activePreset: string;

  // UI state
  customizePanelOpen: boolean;
  theme: ThemeMode;

  // Actions
  setWidgetOrder: (order: string[]) => void;
  toggleWidgetVisibility: (widgetId: string) => void;
  setWidgetSize: (widgetId: string, size: WidgetSize) => void;
  setWidgetDimensions: (widgetId: string, dimensions: WidgetDimensions) => void;
  applyPreset: (presetId: string) => void;
  setCustomizePanelOpen: (open: boolean) => void;
  moveWidget: (fromIndex: number, toIndex: number) => void;
  setTheme: (theme: ThemeMode) => void;
  toggleTheme: () => void;
}

const defaultPreset = PRESETS.news;

export const useDashboardStore = create<DashboardState>()(
  persist(
    (set, get) => ({
      // Initial state from default preset
      widgetOrder: [...defaultPreset.order],
      widgetVisibility: { ...defaultPreset.visibility },
      widgetSizes: { ...defaultPreset.sizes } as Record<string, WidgetSize>,
      widgetDimensions: dimensionsFromSizes(defaultPreset.sizes as Record<string, WidgetSize>),
      activePreset: 'news',
      customizePanelOpen: false,
      theme: 'bloomberg' as ThemeMode,  // Default to Bloomberg theme

      setWidgetOrder: (order) => set({ widgetOrder: order, activePreset: 'custom' }),

      toggleWidgetVisibility: (widgetId) =>
        set((state) => {
          const newVisibility = !state.widgetVisibility[widgetId];
          // If turning on and not in order, add to end of order
          let newOrder = state.widgetOrder;
          if (newVisibility && !state.widgetOrder.includes(widgetId)) {
            newOrder = [...state.widgetOrder, widgetId];
          }
          return {
            widgetOrder: newOrder,
            widgetVisibility: {
              ...state.widgetVisibility,
              [widgetId]: newVisibility,
            },
            activePreset: 'custom',  // Mark as custom when user modifies
          };
        }),

      setWidgetSize: (widgetId, size) =>
        set((state) => ({
          widgetSizes: {
            ...state.widgetSizes,
            [widgetId]: size,
          },
          widgetDimensions: {
            ...state.widgetDimensions,
            [widgetId]: dimensionsFromSize(size),
          },
          activePreset: 'custom',  // Mark as custom when user modifies
        })),

      setWidgetDimensions: (widgetId, dimensions) =>
        set((state) => ({
          widgetDimensions: {
            ...state.widgetDimensions,
            [widgetId]: dimensions,
          },
          widgetSizes: {
            ...state.widgetSizes,
            [widgetId]: findNearestPreset(dimensions.cols, dimensions.rows),
          },
          activePreset: 'custom',  // Mark as custom when user modifies
        })),

      applyPreset: (presetId) => {
        const preset = PRESETS[presetId];
        if (!preset) return;
        set({
          widgetOrder: [...preset.order],
          widgetVisibility: { ...preset.visibility },
          widgetSizes: { ...preset.sizes } as Record<string, WidgetSize>,
          widgetDimensions: dimensionsFromSizes(preset.sizes as Record<string, WidgetSize>),
          activePreset: presetId,
        });
      },

      setCustomizePanelOpen: (open) => set({ customizePanelOpen: open }),

      moveWidget: (fromIndex, toIndex) =>
        set((state) => {
          const newOrder = [...state.widgetOrder];
          const [removed] = newOrder.splice(fromIndex, 1);
          newOrder.splice(toIndex, 0, removed);
          return { widgetOrder: newOrder };
        }),

      setTheme: (theme) => set({ theme }),

      toggleTheme: () =>
        set((state) => ({
          theme: state.theme === 'bloomberg' ? 'default' : 'bloomberg',
        })),
    }),
    {
      name: 'rta-dashboard-v14',  // v61: restore province monitor to its original placement and size
      version: 61,
      migrate: (persistedState: unknown, version: number) => {
        if (!persistedState || typeof persistedState !== 'object') {
          return persistedState as DashboardState;
        }

        const state = persistedState as DashboardState;

        if (version < 61) {
          if (state.activePreset === 'news' || state.activePreset === 'analyst' || state.activePreset === 'intelligence') {
            const preset = PRESETS[state.activePreset];
            return {
              ...state,
              activePreset: state.activePreset,
              widgetOrder: [...preset.order],
              widgetVisibility: { ...preset.visibility },
              widgetSizes: { ...preset.sizes } as Record<string, WidgetSize>,
              widgetDimensions: dimensionsFromSizes(preset.sizes as Record<string, WidgetSize>),
            };
          }
        }

        if (version < 60) {
          const sanitizedOrder = Array.isArray(state.widgetOrder)
            ? state.widgetOrder.filter((id) => !RETIRED_NATIONAL_ASSESSMENT_WIDGET_IDS.has(id))
            : [];
          const sanitizedVisibility = Object.fromEntries(
            Object.entries(state.widgetVisibility || {}).map(([id, visible]) => [
              id,
              RETIRED_NATIONAL_ASSESSMENT_WIDGET_IDS.has(id) ? false : visible,
            ]),
          ) as Record<string, boolean>;
          const sanitizedSizes = Object.fromEntries(
            Object.entries(state.widgetSizes || {}).filter(([id]) => !RETIRED_NATIONAL_ASSESSMENT_WIDGET_IDS.has(id)),
          ) as Record<string, WidgetSize>;

          if (state.activePreset === 'news' || state.activePreset === 'analyst' || state.activePreset === 'intelligence' || state.activePreset === 'situation-monitor') {
            const preset = PRESETS[state.activePreset];
            return {
              ...state,
              activePreset: state.activePreset,
              widgetOrder: [...preset.order],
              widgetVisibility: { ...preset.visibility },
              widgetSizes: { ...preset.sizes } as Record<string, WidgetSize>,
              widgetDimensions: dimensionsFromSizes(preset.sizes as Record<string, WidgetSize>),
            };
          }

          return {
            ...state,
            widgetOrder: sanitizedOrder,
            widgetVisibility: sanitizedVisibility,
            widgetSizes: sanitizedSizes,
            widgetDimensions: dimensionsFromSizes(sanitizedSizes),
          };
        }

        if (version < 59 && state.activePreset === 'economy') {
          const preset = PRESETS.economy;
          return {
            ...state,
            activePreset: 'economy',
            widgetOrder: [...preset.order],
            widgetVisibility: { ...preset.visibility },
            widgetSizes: { ...preset.sizes } as Record<string, WidgetSize>,
            widgetDimensions: dimensionsFromSizes(preset.sizes as Record<string, WidgetSize>),
          };
        }

        if (version < 57 && state.activePreset === 'economy') {
          const preset = PRESETS.economy;
          return {
            ...state,
            activePreset: 'economy',
            widgetOrder: [...preset.order],
            widgetVisibility: { ...preset.visibility },
            widgetSizes: { ...preset.sizes } as Record<string, WidgetSize>,
            widgetDimensions: dimensionsFromSizes(preset.sizes as Record<string, WidgetSize>),
          };
        }

        if (version < 56 && state.activePreset === 'economy') {
          const preset = PRESETS.economy;
          return {
            ...state,
            activePreset: 'economy',
            widgetOrder: [...preset.order],
            widgetVisibility: { ...preset.visibility },
            widgetSizes: { ...preset.sizes } as Record<string, WidgetSize>,
            widgetDimensions: dimensionsFromSizes(preset.sizes as Record<string, WidgetSize>),
          };
        }

        if (version < 55 && state.activePreset === 'parliament') {
          const preset = PRESETS.parliament;
          return {
            ...state,
            activePreset: 'parliament',
            widgetOrder: [...preset.order],
            widgetVisibility: { ...preset.visibility },
            widgetSizes: { ...preset.sizes } as Record<string, WidgetSize>,
            widgetDimensions: dimensionsFromSizes(preset.sizes as Record<string, WidgetSize>),
          };
        }

        if (version < 54 && state.activePreset === 'parliament') {
          const preset = PRESETS.parliament;
          return {
            ...state,
            activePreset: 'parliament',
            widgetOrder: [...preset.order],
            widgetVisibility: { ...preset.visibility },
            widgetSizes: { ...preset.sizes } as Record<string, WidgetSize>,
            widgetDimensions: dimensionsFromSizes(preset.sizes as Record<string, WidgetSize>),
          };
        }

        if (version < 53 && state.activePreset === 'parliament') {
          const preset = PRESETS.parliament;
          return {
            ...state,
            activePreset: 'parliament',
            widgetOrder: [...preset.order],
            widgetVisibility: { ...preset.visibility },
            widgetSizes: { ...preset.sizes } as Record<string, WidgetSize>,
            widgetDimensions: dimensionsFromSizes(preset.sizes as Record<string, WidgetSize>),
          };
        }

        if (version < 52 && state.activePreset === 'parliament') {
          const preset = PRESETS.parliament;
          return {
            ...state,
            activePreset: 'parliament',
            widgetOrder: [...preset.order],
            widgetVisibility: { ...preset.visibility },
            widgetSizes: { ...preset.sizes } as Record<string, WidgetSize>,
            widgetDimensions: dimensionsFromSizes(preset.sizes as Record<string, WidgetSize>),
          };
        }

        if (version < 51 && state.activePreset === 'parliament') {
          const preset = PRESETS.parliament;
          return {
            ...state,
            activePreset: 'parliament',
            widgetOrder: [...preset.order],
            widgetVisibility: { ...preset.visibility },
            widgetSizes: { ...preset.sizes } as Record<string, WidgetSize>,
            widgetDimensions: dimensionsFromSizes(preset.sizes as Record<string, WidgetSize>),
          };
        }

        if (version < 50 && state.activePreset === 'parliament') {
          const preset = PRESETS.parliament;
          return {
            ...state,
            activePreset: 'parliament',
            widgetOrder: [...preset.order],
            widgetVisibility: { ...preset.visibility },
            widgetSizes: { ...preset.sizes } as Record<string, WidgetSize>,
            widgetDimensions: dimensionsFromSizes(preset.sizes as Record<string, WidgetSize>),
          };
        }

        if (version < 49 && state.activePreset === 'parliament') {
          const preset = PRESETS.parliament;
          return {
            ...state,
            activePreset: 'parliament',
            widgetOrder: [...preset.order],
            widgetVisibility: { ...preset.visibility },
            widgetSizes: { ...preset.sizes } as Record<string, WidgetSize>,
            widgetDimensions: dimensionsFromSizes(preset.sizes as Record<string, WidgetSize>),
          };
        }

        if (version < 48 && state.activePreset === 'news') {
          const preset = PRESETS.news;
          return {
            ...state,
            activePreset: 'news',
            widgetOrder: [...preset.order],
            widgetVisibility: { ...preset.visibility },
            widgetSizes: { ...preset.sizes } as Record<string, WidgetSize>,
            widgetDimensions: dimensionsFromSizes(preset.sizes as Record<string, WidgetSize>),
          };
        }

        if (version < 47 && state.activePreset === 'news') {
          const preset = PRESETS.news;
          return {
            ...state,
            activePreset: 'news',
            widgetOrder: [...preset.order],
            widgetVisibility: { ...preset.visibility },
            widgetSizes: { ...preset.sizes } as Record<string, WidgetSize>,
            widgetDimensions: dimensionsFromSizes(preset.sizes as Record<string, WidgetSize>),
          };
        }

        if (version < 46) {
          const nextOrder = Array.isArray(state.widgetOrder)
            ? moveBottomWidgetsToEnd(state.widgetOrder)
            : state.widgetOrder;
          const nextSizes = {
            ...(state.widgetSizes || {}),
            ...(nextOrder.includes('disasters') ? { disasters: 'medium' as WidgetSize } : {}),
            ...(nextOrder.includes('govt') ? { govt: 'medium' as WidgetSize } : {}),
          };

          if (state.activePreset === 'disaster') {
            const preset = PRESETS.disaster;
            return {
              ...state,
              activePreset: 'disaster',
              widgetOrder: [...preset.order],
              widgetVisibility: { ...preset.visibility },
              widgetSizes: { ...preset.sizes } as Record<string, WidgetSize>,
              widgetDimensions: dimensionsFromSizes(preset.sizes as Record<string, WidgetSize>),
            };
          }

          return {
            ...state,
            widgetOrder: nextOrder,
            widgetSizes: nextSizes,
            widgetDimensions: dimensionsFromSizes(nextSizes as Record<string, WidgetSize>),
          };
        }

        // v45: Archive elections from main shell and add loan tracker to accountability
        if (version < 45) {
          const sanitizedOrder = Array.isArray(state.widgetOrder)
            ? state.widgetOrder.filter((id) => !ARCHIVED_ELECTION_WIDGET_IDS.has(id))
            : state.widgetOrder;
          const sanitizedVisibility = Object.fromEntries(
            Object.entries(state.widgetVisibility || {}).map(([id, visible]) => [
              id,
              ARCHIVED_ELECTION_WIDGET_IDS.has(id) ? false : visible,
            ]),
          ) as Record<string, boolean>;

          if (state.activePreset === 'elections') {
            const preset = PRESETS.news;
            return {
              ...state,
              activePreset: 'news',
              widgetOrder: [...preset.order],
              widgetVisibility: { ...preset.visibility },
              widgetSizes: { ...preset.sizes } as Record<string, WidgetSize>,
              widgetDimensions: dimensionsFromSizes(preset.sizes as Record<string, WidgetSize>),
            };
          }

          if (state.activePreset === 'analyst') {
            const preset = PRESETS.intelligence;
            return {
              ...state,
              activePreset: 'intelligence',
              widgetOrder: [...preset.order],
              widgetVisibility: { ...preset.visibility },
              widgetSizes: { ...preset.sizes } as Record<string, WidgetSize>,
              widgetDimensions: dimensionsFromSizes(preset.sizes as Record<string, WidgetSize>),
            };
          }

          if (state.activePreset === 'parliament') {
            const preset = PRESETS.parliament;
            return {
              ...state,
              widgetOrder: [...preset.order],
              widgetVisibility: { ...preset.visibility },
              widgetSizes: { ...preset.sizes } as Record<string, WidgetSize>,
              widgetDimensions: dimensionsFromSizes(preset.sizes as Record<string, WidgetSize>),
              activePreset: 'parliament',
            };
          }

          return {
            ...state,
            widgetOrder: sanitizedOrder,
            widgetVisibility: sanitizedVisibility,
          };
        }

        // v44: Update News preset to include market widget by default
        if (version < 44 && state.activePreset === 'news') {
          const preset = PRESETS.news;
          return {
            ...state,
            widgetOrder: [...preset.order],
            widgetVisibility: { ...preset.visibility },
            widgetSizes: { ...preset.sizes } as Record<string, WidgetSize>,
            widgetDimensions: dimensionsFromSizes(preset.sizes as Record<string, WidgetSize>),
            activePreset: 'news',
          };
        }

        // v42: Normalize national assessment to hero footprint
        if (version < 42) {
          const nextSizes = {
            ...state.widgetSizes,
            'situation-brief': 'hero' as WidgetSize,
          };

          return {
            ...state,
            widgetSizes: nextSizes,
            widgetDimensions: dimensionsFromSizes(nextSizes),
          };
        }

        // v41: Remove temporary Home preset and reset landing to News
        if (version < 41 && (state.activePreset === 'home' || state.activePreset === 'consumer')) {
          const preset = PRESETS.news;
          return {
            ...state,
            activePreset: 'news',
            widgetOrder: [...preset.order],
            widgetVisibility: { ...preset.visibility },
            widgetSizes: { ...preset.sizes } as Record<string, WidgetSize>,
            widgetDimensions: dimensionsFromSizes(preset.sizes as Record<string, WidgetSize>),
          };
        }

        // v39: Post-election — switch everyone from elections to news preset
        if (version < 39 && state.activePreset === 'elections') {
          const preset = PRESETS.news;
          return {
            ...state,
            activePreset: 'news',
            widgetOrder: [...preset.order],
            widgetVisibility: { ...preset.visibility },
            widgetSizes: { ...preset.sizes } as Record<string, WidgetSize>,
            widgetDimensions: dimensionsFromSizes(preset.sizes as Record<string, WidgetSize>),
          };
        }
        if (version < 13 && state.activePreset === 'consumer') {
          return {
            ...state,
            widgetOrder: Array.isArray(state.widgetOrder)
              ? state.widgetOrder.filter((id) => id !== 'neta')
              : PRESETS.consumer.order,
            widgetVisibility: {
              ...state.widgetVisibility,
              neta: false,
            },
            widgetSizes: {
              ...state.widgetSizes,
              neta: state.widgetSizes?.neta || 'small',
            },
            widgetDimensions: dimensionsFromSizes({
              ...(state.widgetSizes || {}),
              neta: state.widgetSizes?.neta || 'small',
            } as Record<string, WidgetSize>),
          };
        }

        // v15: Add situation-brief widget
        if (version < 15) {
          const order = Array.isArray(state.widgetOrder) ? [...state.widgetOrder] : [];
          // Insert after kpi if present, otherwise add to end
          if (!order.includes('situation-brief')) {
            const kpiIdx = order.indexOf('kpi');
            if (kpiIdx !== -1) {
              order.splice(kpiIdx + 1, 0, 'situation-brief');
            } else {
              order.push('situation-brief');
            }
          }
          return {
            ...state,
            widgetOrder: order,
            widgetVisibility: {
              ...state.widgetVisibility,
              'situation-brief': true,
            },
            widgetSizes: {
              ...state.widgetSizes,
              'situation-brief': 'hero',
            },
            widgetDimensions: dimensionsFromSizes({
              ...(state.widgetSizes || {}),
              'situation-brief': 'hero',
            } as Record<string, WidgetSize>),
          };
        }


        // v23: Remove live-cams from News Dashboard starting view
        if (version < 23) {
          if (state.activePreset === 'consumer') {
            const order = Array.isArray(state.widgetOrder) ? [...state.widgetOrder] : [];
            // Move live-cams to end if present
            const lcIdx = order.indexOf('live-cams');
            if (lcIdx !== -1) {
              order.splice(lcIdx, 1);
              order.push('live-cams');
            }
            return {
              ...state,
              widgetOrder: order,
              widgetVisibility: {
                ...state.widgetVisibility,
                'live-cams': false,
              },
            };
          }
        }

        // v34: Election dashboard was default — now superseded by v39 news migration
        if (version < 38) {
          const preset = PRESETS.news;
          return {
            ...state,
            activePreset: 'news',
            widgetOrder: [...preset.order],
            widgetVisibility: { ...preset.visibility },
            widgetSizes: { ...preset.sizes } as Record<string, WidgetSize>,
            widgetDimensions: dimensionsFromSizes(preset.sizes as Record<string, WidgetSize>),
          };
        }

        // v25: Reset consumer users to cleaner preset layout
        if (version < 25) {
          if (state.activePreset === 'consumer') {
            const preset = PRESETS.consumer;
            return {
              ...state,
              widgetOrder: [...preset.order],
              widgetVisibility: { ...preset.visibility },
              widgetSizes: { ...preset.sizes } as Record<string, WidgetSize>,
              widgetDimensions: dimensionsFromSizes(preset.sizes as Record<string, WidgetSize>),
            };
          }
        }

        // v24: Add developing-stories widget for all users
        if (version < 24) {
          const order = Array.isArray(state.widgetOrder) ? [...state.widgetOrder] : [];
          if (!order.includes('developing-stories')) {
            // Insert after situation-brief if present, otherwise after kpi
            const briefIdx = order.indexOf('situation-brief');
            const kpiIdx = order.indexOf('kpi');
            const insertIdx = briefIdx !== -1 ? briefIdx + 1 : kpiIdx !== -1 ? kpiIdx + 1 : 0;
            order.splice(insertIdx, 0, 'developing-stories');
          }
          return {
            ...state,
            widgetOrder: order,
            widgetVisibility: {
              ...state.widgetVisibility,
              'developing-stories': true,
            },
            widgetSizes: {
              ...state.widgetSizes,
              'developing-stories': 'full',
            },
            widgetDimensions: dimensionsFromSizes({
              ...(state.widgetSizes || {}),
              'developing-stories': 'full',
            } as Record<string, WidgetSize>),
          };
        }


        // v20: Reset consumer users to latest preset (includes live-cams + political-pulse)
        if (version < 20) {
          if (state.activePreset === 'consumer') {
            const preset = PRESETS.consumer;
            return {
              ...state,
              widgetOrder: [...preset.order],
              widgetVisibility: { ...preset.visibility },
              widgetSizes: { ...preset.sizes } as Record<string, WidgetSize>,
              widgetDimensions: dimensionsFromSizes(preset.sizes as Record<string, WidgetSize>),
            };
          }
          // Non-consumer users: register new widgets without auto-enabling
          const order = Array.isArray(state.widgetOrder) ? [...state.widgetOrder] : [];
          if (!order.includes('live-cams')) order.push('live-cams');
          if (!order.includes('political-pulse')) order.push('political-pulse');
          return {
            ...state,
            widgetOrder: order,
            widgetVisibility: {
              ...state.widgetVisibility,
              'live-cams': state.widgetVisibility?.['live-cams'] ?? false,
              'political-pulse': state.widgetVisibility?.['political-pulse'] ?? false,
            },
            widgetSizes: {
              ...state.widgetSizes,
              'live-cams': state.widgetSizes?.['live-cams'] || 'medium',
              'political-pulse': state.widgetSizes?.['political-pulse'] || 'medium',
            },
            widgetDimensions: dimensionsFromSizes({
              ...(state.widgetSizes || {}),
              'live-cams': state.widgetSizes?.['live-cams'] || 'medium',
              'political-pulse': state.widgetSizes?.['political-pulse'] || 'medium',
            } as Record<string, WidgetSize>),
          };
        }

        // v17: Register situation monitor widgets (no auto-enable, just make them available)
        if (version < 17) {
          return {
            ...state,
            widgetVisibility: {
              ...state.widgetVisibility,
              'intel-brief-hero': state.widgetVisibility?.['intel-brief-hero'] ?? false,
              'political-pulse': state.widgetVisibility?.['political-pulse'] ?? false,
              'province-monitor': state.widgetVisibility?.['province-monitor'] ?? false,
              'narrative-tracker': state.widgetVisibility?.['narrative-tracker'] ?? false,
            },
            widgetSizes: {
              ...state.widgetSizes,
              'intel-brief-hero': 'full',
              'political-pulse': 'hero',
              'province-monitor': 'brief',
              'narrative-tracker': 'full',
            },
            widgetDimensions: dimensionsFromSizes({
              ...(state.widgetSizes || {}),
              'intel-brief-hero': 'full',
              'political-pulse': 'hero',
              'province-monitor': 'brief',
              'narrative-tracker': 'full',
            } as Record<string, WidgetSize>),
          };
        }

        // v16: Normalize situation-brief size to dedicated hero footprint
        if (version < 16) {
          return {
            ...state,
            widgetSizes: {
              ...state.widgetSizes,
              'situation-brief': 'hero',
            },
            widgetDimensions: dimensionsFromSizes({
              ...(state.widgetSizes || {}),
              'situation-brief': 'hero',
            } as Record<string, WidgetSize>),
          };
        }

        // v14: Enable market & power widgets by default
        if (version < 14) {
          const order = Array.isArray(state.widgetOrder) ? [...state.widgetOrder] : [];
          if (!order.includes('market')) order.push('market');
          if (!order.includes('power')) order.push('power');
          return {
            ...state,
            widgetOrder: order,
            widgetVisibility: {
              ...state.widgetVisibility,
              market: true,
              power: true,
            },
            widgetSizes: {
              ...state.widgetSizes,
              market: state.widgetSizes?.market || 'medium',
              power: state.widgetSizes?.power || 'medium',
            },
            widgetDimensions: dimensionsFromSizes({
              ...(state.widgetSizes || {}),
              market: state.widgetSizes?.market || 'medium',
              power: state.widgetSizes?.power || 'medium',
            } as Record<string, WidgetSize>),
          };
        }

        return {
          ...state,
          widgetDimensions: state.widgetDimensions || dimensionsFromSizes((state.widgetSizes || defaultPreset.sizes) as Record<string, WidgetSize>),
        };
      },
    }
  )
);
