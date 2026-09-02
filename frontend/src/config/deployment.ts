/**
 * Deployment-shape switches for the public nepalosint.com build.
 *
 * The app is normally a full analyst workstation with accounts, dev routes and
 * every preset tab. The public deployment ships only the read-only consumer
 * surface, so these two flags let one codebase produce both without forking:
 *
 *   VITE_PUBLIC_ONLY=true         hide every account/login affordance and send
 *                                 /login and /dev back to the dashboard. The
 *                                 backend guest bootstrap (POST /auth/public)
 *                                 still runs — it is invisible plumbing that
 *                                 mints the token the read APIs require, not a
 *                                 user-facing sign-in.
 *
 *   VITE_DISABLED_PRESETS=a,b     drop these preset tabs from the header. Used
 *                                 to hide tabs whose backing tables are empty
 *                                 in a given deployment (see the Economy tab:
 *                                 its NRB macro tables did not survive the
 *                                 Lightsail loss, so it would render as a wall
 *                                 of blank widgets).
 */

export const IS_PUBLIC_ONLY = import.meta.env.VITE_PUBLIC_ONLY === 'true'

export const DISABLED_PRESETS: ReadonlySet<string> = new Set(
  (import.meta.env.VITE_DISABLED_PRESETS ?? '')
    .split(',')
    .map((id: string) => id.trim())
    .filter(Boolean),
)

export const isPresetEnabled = (id: string) => !DISABLED_PRESETS.has(id)
