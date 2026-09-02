import { useState, useEffect, useRef, memo, useSyncExternalStore } from 'react';
import { useNavigate } from 'react-router-dom';
import { BookOpen, Grid3X3, User, LogOut, Terminal, Search, Github } from 'lucide-react';
import { useDashboardStore } from '../../stores/dashboardStore';
import { useAuthStore } from '../../store/slices/authSlice';
import { usePermissions } from '../../hooks/usePermissions';
import { useUserPreferencesStore } from '../../store/slices/userPreferencesSlice';
import { useNotificationStore } from '../../stores/notificationStore';
import { subscribeViewerCount, getViewerCountSnapshot, getViewerCountServerSnapshot } from '../../api/websocket';
import { NotificationBell } from '../common/NotificationBell';
import { DisplayPreferencesDrawer } from '../common/DisplayPreferencesDrawer';
import { IS_PUBLIC_ONLY, isPresetEnabled } from '../../config/deployment';

// Accountability is archived: PRESETS.parliament and every widget it names are still
// registered, so re-adding { id: 'parliament', label: 'Accountability' } here restores it.
const ALL_PRESET_TABS = [
  { id: 'news', label: 'News' },
  { id: 'flood', label: 'Flood' },
  { id: 'economy', label: 'Economy' },
] as const;

// A deployment can drop tabs whose backing data it does not have
// (VITE_DISABLED_PRESETS) — see src/config/deployment.ts.
const PRESET_TABS = ALL_PRESET_TABS.filter(tab => isPresetEnabled(tab.id));

const subscribeOnlineStatus = (cb: () => void) => {
  window.addEventListener('online', cb);
  window.addEventListener('offline', cb);
  return () => {
    window.removeEventListener('online', cb);
    window.removeEventListener('offline', cb);
  };
};

const getOnlineStatusSnapshot = () => navigator.onLine;
const getOnlineStatusServerSnapshot = () => true;

const ViewerBadge = memo(function ViewerBadge() {
  const viewers = useSyncExternalStore(subscribeViewerCount, getViewerCountSnapshot, getViewerCountServerSnapshot);
  if (viewers <= 0) return null;
  return (
    <span style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', marginLeft: 4 }}>
      {viewers}
    </span>
  );
});

const Clock = memo(function Clock() {
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const hh = time.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
  const date = time.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }).toUpperCase();

  return (
    <div className="hidden sm:flex items-center gap-2" style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontVariantNumeric: 'tabular-nums' }}>
      <span style={{ color: 'var(--text-muted)' }}>{date}</span>
      <span style={{ color: 'var(--text-secondary)', fontWeight: 600 }}>{hh}</span>
    </div>
  );
});

export const DashboardHeader = memo(function DashboardHeader() {
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);
  const [displayPreferencesOpen, setDisplayPreferencesOpen] = useState(false);
  const { setCustomizePanelOpen, customizePanelOpen, applyPreset, activePreset } = useDashboardStore();
  const { user, logout, isGuest } = useAuthStore();
  const { isDev } = usePermissions();
  const { requestTourReplay } = useUserPreferencesStore();
  const { setPreferencesOpen } = useNotificationStore();
  const navigate = useNavigate();
  const menuRef = useRef<HTMLDivElement>(null);
  const isConnected = useSyncExternalStore(subscribeOnlineStatus, getOnlineStatusSnapshot, getOnlineStatusServerSnapshot);
  const isPublicViewer = !user;
  const isGuestLike = isGuest || isPublicViewer;

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setAccountMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleLogout = () => {
    setAccountMenuOpen(false);
    logout();
  };

  const handleGoToLogin = () => {
    setAccountMenuOpen(false);
    navigate('/login');
  };

  const getRoleBadgeClass = () => {
    switch (user?.role) {
      case 'dev': return 'bg-emerald-500/20 text-emerald-400';
      case 'analyst': return 'bg-amber-500/20 text-amber-400';
      default: return 'bg-blue-500/20 text-blue-400';
    }
  };

  return (
    <header className="unified-navbar">
      <div style={{ display: 'flex', alignItems: 'center', height: '100%', gap: 0 }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '0 14px', height: '100%',
          borderRight: '1px solid var(--border-subtle)',
        }}>
          <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: '0.03em', color: 'var(--text-primary)' }}>
            NepalOSINT
          </span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <span style={{
              fontSize: 9, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em',
              color: isConnected ? 'var(--status-low)' : 'var(--status-critical)',
            }}>
              {isConnected ? 'Live' : 'Offline'}
            </span>
            <ViewerBadge />
          </div>
        </div>

        <nav style={{ display: 'flex', alignItems: 'center', height: '100%' }} data-tour-id="preset-tabs">
          {PRESET_TABS.map(tab => {
            const isActive = activePreset === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => applyPreset(tab.id)}
                data-tour-id={
                  tab.id === 'news'
                    ? 'news-tab'
                    : tab.id === 'economy'
                      ? 'economy-tab'
                      : undefined
                }
                style={{
                  position: 'relative',
                  height: '100%',
                  padding: '0 16px',
                  background: 'transparent',
                  border: 'none',
                  fontSize: 12,
                  fontWeight: 500,
                  fontFamily: 'var(--font-sans)',
                  color: isActive ? 'var(--text-primary)' : 'var(--text-muted)',
                  cursor: 'pointer',
                  transition: 'color 0.15s',
                }}
                onMouseEnter={e => { if (!isActive) (e.target as HTMLElement).style.color = 'var(--text-secondary)'; }}
                onMouseLeave={e => { if (!isActive) (e.target as HTMLElement).style.color = 'var(--text-muted)'; }}
              >
                {tab.label}
                {isActive && (
                  <span style={{
                    position: 'absolute', bottom: 0, left: 8, right: 8, height: 2,
                    background: 'var(--accent-primary)', borderRadius: 1,
                  }} />
                )}
              </button>
            );
          })}
        </nav>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 2, height: '100%' }}>
        <Clock />

        <div className="hidden sm:block" style={{ width: 1, height: 16, background: 'var(--border-subtle)', margin: '0 6px' }} />

        <button
          className="navbar-btn hidden sm:inline-flex"
          title="Search (K)"
          onClick={() => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k' }))}
        >
          <Search size={14} />
          <kbd style={{
            fontSize: 9, color: 'var(--text-disabled)',
            background: 'var(--bg-elevated)', padding: '1px 4px',
            border: '1px solid var(--border-subtle)',
            fontFamily: 'var(--font-mono)', lineHeight: 1,
          }}>K</kbd>
        </button>

        <NotificationBell />

        {user?.role === 'consumer' && (
          <button
            className="navbar-btn"
            title="Guide"
            data-tour-id="help-tour"
            onClick={() => requestTourReplay()}
          >
            <BookOpen size={14} />
            <span className="hidden sm:inline" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
              Guide
            </span>
          </button>
        )}

        <button
          className={`navbar-btn ${customizePanelOpen ? 'navbar-btn-active' : ''}`}
          title="Customize"
          onClick={() => setCustomizePanelOpen(!customizePanelOpen)}
        >
          <Grid3X3 size={14} />
        </button>

        {isDev && (
          <button
            className="navbar-btn"
            title="Developer Console"
            onClick={() => navigate('/dev')}
          >
            <Terminal size={14} />
          </button>
        )}

        <div className="hidden sm:block" style={{ width: 1, height: 16, background: 'var(--border-subtle)', margin: '0 4px' }} />

        <a
          className="navbar-btn"
          title="GitHub Repository"
          href="https://github.com/nlethetech/nepal-osint-skeleton"
          target="_blank"
          rel="noreferrer"
          aria-label="GitHub Repository"
        >
          <Github size={14} />
        </a>

        <div className="relative" style={{ height: '100%', display: 'flex', alignItems: 'center' }} ref={menuRef}>
          <button
            className={`navbar-btn ${accountMenuOpen ? 'navbar-btn-active' : ''}`}
            onClick={() => setAccountMenuOpen(!accountMenuOpen)}
            title="Account"
            data-tour-id="account-menu"
          >
            <User size={14} />
            <span className="hidden sm:inline" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
              {isGuestLike ? 'Guest' : (user?.username || user?.role || 'User')}
            </span>
          </button>

          {accountMenuOpen && (
            <div style={{
              position: 'absolute', right: 0, top: '100%', marginTop: 4,
              width: 240, background: 'var(--bg-elevated)',
              border: '1px solid var(--border-subtle)',
              boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
              zIndex: 50, overflow: 'hidden',
            }}>
              <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--border-subtle)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={{
                    width: 28, height: 28, background: 'var(--bg-active)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    <User size={12} style={{ color: 'var(--text-muted)' }} />
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-primary)', margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {isGuestLike ? 'Guest Session' : (user?.username || user?.fullName || 'User')}
                    </p>
                    {!isGuestLike && user?.email && (
                      <p style={{ fontSize: 11, color: 'var(--text-muted)', margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {user.email}
                      </p>
                    )}
                  </div>
                </div>
                <div style={{ marginTop: 8 }}>
                  <span className={`inline-flex px-2 py-0.5 text-[10px] font-medium uppercase ${getRoleBadgeClass()}`}>
                    {isGuestLike ? 'guest' : (user?.role || 'consumer')}
                  </span>
                </div>
              </div>

              <div style={{ padding: '4px 0' }}>
                {isGuestLike ? (
                  <>
                    <button
                      onClick={() => {
                        setAccountMenuOpen(false)
                        setDisplayPreferencesOpen(true)
                      }}
                      style={{
                        width: '100%', display: 'flex', alignItems: 'center', gap: 10,
                        padding: '8px 14px', background: 'transparent', border: 'none',
                        fontSize: 12, color: 'var(--text-secondary)', cursor: 'pointer',
                        textAlign: 'left', fontFamily: 'var(--font-sans)',
                      }}
                      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'var(--bg-hover)'; }}
                      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent'; }}
                    >
                      Display preferences
                    </button>
                    {!IS_PUBLIC_ONLY && (
                    <button
                      onClick={handleGoToLogin}
                      style={{
                        width: '100%', display: 'flex', alignItems: 'center', gap: 10,
                        padding: '8px 14px', background: 'transparent', border: 'none',
                        fontSize: 12, color: 'var(--text-secondary)', cursor: 'pointer',
                        textAlign: 'left', fontFamily: 'var(--font-sans)',
                      }}
                      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'var(--bg-hover)'; }}
                      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent'; }}
                    >
                      Sign In / Create Account
                    </button>
                    )}
                  </>
                ) : (
                  <>
                    <button
                      onClick={() => {
                        setAccountMenuOpen(false)
                        setDisplayPreferencesOpen(true)
                      }}
                      style={{
                        width: '100%', display: 'flex', alignItems: 'center', gap: 10,
                        padding: '8px 14px', background: 'transparent', border: 'none',
                        fontSize: 12, color: 'var(--text-secondary)', cursor: 'pointer',
                        textAlign: 'left', fontFamily: 'var(--font-sans)',
                      }}
                      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'var(--bg-hover)'; }}
                      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent'; }}
                    >
                      Display preferences
                    </button>
                    <button
                      onClick={() => {
                        setAccountMenuOpen(false)
                        setPreferencesOpen(true)
                      }}
                      style={{
                        width: '100%', display: 'flex', alignItems: 'center', gap: 10,
                        padding: '8px 14px', background: 'transparent', border: 'none',
                        fontSize: 12, color: 'var(--text-secondary)', cursor: 'pointer',
                        textAlign: 'left', fontFamily: 'var(--font-sans)',
                      }}
                      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'var(--bg-hover)'; }}
                      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent'; }}
                    >
                      Alert preferences
                    </button>
                    <button
                      onClick={handleLogout}
                      style={{
                        width: '100%', display: 'flex', alignItems: 'center', gap: 10,
                        padding: '8px 14px', background: 'transparent', border: 'none',
                        fontSize: 12, color: 'var(--text-secondary)', cursor: 'pointer',
                        textAlign: 'left', fontFamily: 'var(--font-sans)',
                      }}
                      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'var(--bg-hover)'; }}
                      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent'; }}
                    >
                      <LogOut size={12} />
                      Sign out
                    </button>
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      <DisplayPreferencesDrawer
        open={displayPreferencesOpen}
        onClose={() => setDisplayPreferencesOpen(false)}
      />
    </header>
  );
});
