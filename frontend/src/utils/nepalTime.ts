export const NEPAL_TIME_ZONE = 'Asia/Kathmandu'
export const NEPAL_TIME_LABEL = 'NPT'

const nepalTimeFormatter = new Intl.DateTimeFormat('en-GB', {
  timeZone: NEPAL_TIME_ZONE,
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
})

const nepalShortDateFormatter = new Intl.DateTimeFormat('en-GB', {
  timeZone: NEPAL_TIME_ZONE,
  day: '2-digit',
  month: 'short',
})

const nepalLongDateFormatter = new Intl.DateTimeFormat('en-GB', {
  timeZone: NEPAL_TIME_ZONE,
  day: '2-digit',
  month: 'short',
  year: 'numeric',
})

export function formatNepalTime(date: Date): string {
  return nepalTimeFormatter.format(date)
}

export function formatNepalShortDate(date: Date): string {
  return nepalShortDateFormatter.format(date).toUpperCase()
}

export function formatNepalLongDate(date: Date): string {
  return nepalLongDateFormatter.format(date).toUpperCase()
}
