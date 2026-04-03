import type { NprNumberingSystem } from '../store/slices/settingsSlice'

const NPR_PREFIX = 'Nrs'
const VEDIC_LOCALE = 'en-IN'
const INTERNATIONAL_LOCALE = 'en-US'

type CompactUnit = {
  threshold: number
  suffix: string
}

const VEDIC_UNITS: CompactUnit[] = [
  { threshold: 1_000_000_000, suffix: 'Arba' },
  { threshold: 10_000_000, suffix: 'Cr' },
  { threshold: 100_000, suffix: 'Lakh' },
]

const INTERNATIONAL_UNITS: CompactUnit[] = [
  { threshold: 1_000_000_000_000, suffix: 'T' },
  { threshold: 1_000_000_000, suffix: 'B' },
  { threshold: 1_000_000, suffix: 'M' },
  { threshold: 1_000, suffix: 'K' },
]

function getLocale(system: NprNumberingSystem): string {
  return system === 'vedic' ? VEDIC_LOCALE : INTERNATIONAL_LOCALE
}

function trimTrailingZeros(value: string): string {
  return value.replace(/\.0+$|(\.\d*?)0+$/, '$1')
}

function formatScaledValue(value: number, threshold: number, locale: string, maximumFractionDigits: number): string {
  return trimTrailingZeros(
    (value / threshold).toLocaleString(locale, {
      minimumFractionDigits: 0,
      maximumFractionDigits,
    }),
  )
}

export function formatGroupedNumber(
  value: number,
  system: NprNumberingSystem,
  maximumFractionDigits = 0,
): string {
  return new Intl.NumberFormat(getLocale(system), {
    maximumFractionDigits,
  }).format(value)
}

export function formatNprFull(
  value: number | null | undefined,
  options: {
    system?: NprNumberingSystem
    prefix?: string
    maximumFractionDigits?: number
    fallback?: string
  } = {},
): string {
  if (value == null || Number.isNaN(value)) {
    return options.fallback ?? 'N/A'
  }

  const {
    system = 'vedic',
    prefix = NPR_PREFIX,
    maximumFractionDigits = 0,
  } = options

  return `${prefix} ${formatGroupedNumber(value, system, maximumFractionDigits)}`
}

export function formatCompactNpr(
  value: number | null | undefined,
  options: {
    system?: NprNumberingSystem
    prefix?: string
    maximumFractionDigits?: number
    fallback?: string
  } = {},
): string {
  if (value == null || Number.isNaN(value)) {
    return options.fallback ?? 'N/A'
  }

  const {
    system = 'vedic',
    prefix = NPR_PREFIX,
    maximumFractionDigits = 2,
  } = options

  const absValue = Math.abs(value)
  const locale = getLocale(system)
  const units = system === 'vedic' ? VEDIC_UNITS : INTERNATIONAL_UNITS

  for (const unit of units) {
    if (absValue >= unit.threshold) {
      return `${prefix} ${formatScaledValue(value, unit.threshold, locale, maximumFractionDigits)} ${unit.suffix}`
    }
  }

  return `${prefix} ${formatGroupedNumber(value, system, 0)}`
}

export function formatUsdCompact(
  value: number | null | undefined,
  maximumFractionDigits = 2,
): string {
  if (value == null || Number.isNaN(value)) {
    return 'N/A'
  }

  const absValue = Math.abs(value)
  for (const unit of INTERNATIONAL_UNITS) {
    if (absValue >= unit.threshold) {
      return `$${formatScaledValue(value, unit.threshold, INTERNATIONAL_LOCALE, maximumFractionDigits)}${unit.suffix}`
    }
  }

  return `$${value.toLocaleString(INTERNATIONAL_LOCALE, { maximumFractionDigits: 0 })}`
}

export function formatUsdFull(value: number | null | undefined, maximumFractionDigits = 0): string {
  if (value == null || Number.isNaN(value)) {
    return 'N/A'
  }
  return `$${value.toLocaleString(INTERNATIONAL_LOCALE, { maximumFractionDigits })}`
}

export function buildNprDisplay(
  value: number | null | undefined,
  options: {
    system?: NprNumberingSystem
    usdPerNpr?: number | null
    showUsdEquivalent?: boolean
    compact?: boolean
    prefix?: string
    maximumFractionDigits?: number
    fallback?: string
  } = {},
): {
  text: string
  fullText: string
  title: string
  usdText: string | null
} {
  if (value == null || Number.isNaN(value)) {
    const fallback = options.fallback ?? 'N/A'
    return {
      text: fallback,
      fullText: fallback,
      title: fallback,
      usdText: null,
    }
  }

  const {
    system = 'vedic',
    usdPerNpr = null,
    showUsdEquivalent = false,
    compact = true,
    prefix = NPR_PREFIX,
    maximumFractionDigits = 2,
  } = options

  const text = compact
    ? formatCompactNpr(value, { system, prefix, maximumFractionDigits })
    : formatNprFull(value, { system, prefix })
  const fullText = formatNprFull(value, { system, prefix })
  const usdText = showUsdEquivalent && usdPerNpr
    ? `≈ ${formatUsdCompact(value * usdPerNpr)}`
    : null

  return {
    text,
    fullText,
    title: usdText ? `${fullText} • ${usdText}` : fullText,
    usdText,
  }
}

export const CURRENCY_PREVIEW_VALUE = 300_000_000_000
