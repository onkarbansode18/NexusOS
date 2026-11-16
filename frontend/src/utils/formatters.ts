/**
 * Formats timestamps into compact relative times:
 * - < 45s: "just now"
 * - < 60m: "X min ago"
 * - < 24h: "X h ago"
 * - >= 24h: localized short date (e.g. "Oct 25")
 */
export function formatRelativeTime(dateStr?: string | null): string {
  if (!dateStr) return 'just now'
  const date = new Date(dateStr)
  if (isNaN(date.getTime())) return dateStr
  const diffMs = Date.now() - date.getTime()
  if (diffMs < 0 || diffMs < 45000) return 'just now'
  const mins = Math.floor(diffMs / 60000)
  if (mins < 60) return `${mins} min ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours} h ago`
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

/**
 * Returns absolute ISO-like local display string for title tooltips
 */
export function formatAbsoluteTime(dateStr?: string | null): string {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  if (isNaN(date.getTime())) return dateStr
  return date.toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}
