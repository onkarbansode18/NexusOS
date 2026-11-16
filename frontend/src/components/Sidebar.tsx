import React from 'react'
import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  Activity,
  Layers,
  ListFilter,
  Sparkles,
  AlertTriangle,
  Wrench,
  Settings,
  BrainCircuit,
} from 'lucide-react'
import { useNexusStore } from '../store'

// ── Flat nav items matching the reference design ─────────────────────────────
const NAV_ITEMS = [
  { to: '/',             label: 'Dashboard',       icon: LayoutDashboard, end: true  },
  { to: '/monitoring',   label: 'Monitoring',       icon: Activity,        end: false },
  { to: '/applications', label: 'App Manager',      icon: Layers,          end: false },
  { to: '/processes',    label: 'Processes',        icon: ListFilter,      end: false },
  { to: '/predictions',  label: 'AI Insights',      icon: Sparkles,        end: false },
  { to: '/incidents',    label: 'Incidents',        icon: AlertTriangle,   end: false, badge: true },
  { to: '/maintenance',  label: 'Healing Activity', icon: Wrench,          end: false },
  { to: '/hibernator',   label: 'Smart Hibernator', icon: BrainCircuit,    end: false },
]

/** Shield outline icon matching Nexus brand in reference image */
function NexusBrandLogo() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 26, height: 26 }}>
      <svg
        width={22}
        height={22}
        viewBox="0 0 24 24"
        fill="none"
        stroke="#111827"
        strokeWidth={1.8}
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
        <path d="m9 12 2 2 4-4" />
      </svg>
    </div>
  )
}

export function Sidebar() {
  const { openIncidentCount } = useNexusStore()

  return (
    <aside className="app-sidebar" aria-label="Main navigation">
      {/* Logo */}
      <div className="sidebar-logo-block">
        <NexusBrandLogo />
        <span className="sidebar-logo-text" style={{ fontSize: 16, fontWeight: 700, letterSpacing: '-0.02em', color: '#111827' }}>
          Nexus
        </span>
      </div>

      {/* Flat nav items */}
      <nav className="sidebar-nav" aria-label="Primary" style={{ gap: 4, paddingTop: 14, paddingBottom: 0 }}>
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon
          const count = item.badge && openIncidentCount > 0 ? openIncidentCount : null

          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}
            >
              <div className="sidebar-link-main">
                <Icon size={16} strokeWidth={1.75} className="sidebar-link-icon" aria-hidden="true" />
                <span>{item.label}</span>
              </div>
              {count !== null && (
                <span className="sidebar-badge" aria-label={`${count} open incidents`}>
                  {count > 99 ? '99+' : count}
                </span>
              )}
            </NavLink>
          )
        })}
      </nav>

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* Settings link at bottom of sidebar */}
      <div className="sidebar-settings-section" style={{ padding: '0 10px 16px' }}>
        <NavLink
          to="/settings"
          className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}
        >
          <div className="sidebar-link-main">
            <Settings size={16} strokeWidth={1.75} className="sidebar-link-icon" aria-hidden="true" />
            <span>Settings</span>
          </div>
        </NavLink>
      </div>
    </aside>
  )
}
