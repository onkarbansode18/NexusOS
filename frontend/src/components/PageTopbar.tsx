import React, { useState, useRef, useEffect } from 'react'
import { Bell, Check, ExternalLink, Shield, Settings, User } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useNexusStore } from '../store'

interface PageTopbarProps {
  current: string
  subtitle?: string
  actions?: React.ReactNode
}

export function PageTopbar({
  current,
  subtitle,
  actions,
}: PageTopbarProps) {
  const navigate = useNavigate()
  const { policy, toggleSimulationMode, incidents, openIncidentCount, resolveIncident } = useNexusStore()
  const isSimulated = policy?.simulation_mode ?? true

  const [showNotifs, setShowNotifs] = useState(false)
  const [showOperator, setShowOperator] = useState(false)

  const notifRef = useRef<HTMLDivElement>(null)
  const operatorRef = useRef<HTMLDivElement>(null)

  // Close popovers on click outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (notifRef.current && !notifRef.current.contains(event.target as Node)) {
        setShowNotifs(false)
      }
      if (operatorRef.current && !operatorRef.current.contains(event.target as Node)) {
        setShowOperator(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const activeIncidents = incidents.filter(i => i.status !== 'resolved' && i.status !== 'dismissed')

  return (
    <div className="dash-header">
      <div>
        <h1 className="dash-title">{current}</h1>
        {subtitle && <p className="dash-subtitle">{subtitle}</p>}
      </div>

      <div className="dash-header-actions">
        {actions}

        {/* Mode pill — toggleable on click */}
        <button
          type="button"
          onClick={() => toggleSimulationMode()}
          className={`mode-chip ${isSimulated ? 'mode-sim' : 'mode-live'}`}
          style={{ border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}
          title={`Click to switch to ${isSimulated ? 'Live' : 'Simulation'} mode`}
        >
          <span style={{
            width: 6,
            height: 6,
            borderRadius: '50%',
            background: isSimulated ? '#D97706' : '#DC2626',
            marginRight: 6,
            display: 'inline-block'
          }} />
          {isSimulated ? 'Simulation mode' : 'Live mode'}
        </button>

        {/* Bell notification button + Dropdown */}
        <div style={{ position: 'relative' }} ref={notifRef}>
          <button
            type="button"
            onClick={() => {
              setShowNotifs(!showNotifs)
              setShowOperator(false)
            }}
            style={{
              width: 32,
              height: 32,
              borderRadius: '50%',
              background: showNotifs ? '#F3F4F6' : '#FFFFFF',
              border: '1px solid #E5E7EB',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#374151',
              cursor: 'pointer',
              position: 'relative',
              transition: 'background 0.12s ease',
            }}
            aria-label="Notifications"
            title="System notifications"
          >
            <Bell size={14} strokeWidth={1.8} />
            {openIncidentCount > 0 && (
              <span style={{
                position: 'absolute',
                top: 5,
                right: 6,
                width: 6,
                height: 6,
                borderRadius: '50%',
                background: '#DC2626',
              }} />
            )}
          </button>

          {/* Notifications Popover */}
          {showNotifs && (
            <div
              style={{
                position: 'absolute',
                top: 40,
                right: 0,
                width: 340,
                background: '#FFFFFF',
                borderRadius: 10,
                border: '1px solid #E5E7EB',
                boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.05)',
                zIndex: 60,
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  padding: '12px 16px',
                  borderBottom: '1px solid #F3F4F6',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <div style={{ fontSize: 13, fontWeight: 700, color: '#111827' }}>
                  Notifications ({openIncidentCount})
                </div>
                {activeIncidents.length > 0 && (
                  <button
                    type="button"
                    onClick={() => {
                      activeIncidents.forEach(inc => resolveIncident(inc.id))
                    }}
                    style={{
                      background: 'none',
                      border: 'none',
                      fontSize: 11,
                      color: '#4B5563',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 4,
                      padding: 0,
                      fontWeight: 500,
                    }}
                  >
                    <Check size={12} />
                    Mark all resolved
                  </button>
                )}
              </div>

              <div style={{ maxHeight: 280, overflowY: 'auto' }}>
                {activeIncidents.length === 0 ? (
                  <div style={{ padding: '24px 16px', textAlign: 'center', fontSize: 12, color: '#6B7280' }}>
                    <div style={{ marginBottom: 4, fontWeight: 600, color: '#111827' }}>All clear</div>
                    No active resource incidents detected.
                  </div>
                ) : (
                  activeIncidents.slice(0, 5).map(inc => (
                    <div
                      key={inc.id}
                      onClick={() => {
                        setShowNotifs(false)
                        navigate('/incidents')
                      }}
                      style={{
                        padding: '10px 16px',
                        borderBottom: '1px solid #F3F4F6',
                        cursor: 'pointer',
                        transition: 'background 0.12s ease',
                      }}
                      onMouseEnter={e => e.currentTarget.style.background = '#F9FAFB'}
                      onMouseLeave={e => e.currentTarget.style.background = '#FFFFFF'}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 2 }}>
                        <span style={{ fontSize: 12, fontWeight: 600, color: '#111827' }}>
                          {inc.process_name}
                        </span>
                        <span style={{
                          fontSize: 10,
                          fontWeight: 600,
                          padding: '1px 6px',
                          borderRadius: 4,
                          background: inc.severity === 'critical' ? '#FEE2E2' : '#FEF3C7',
                          color: inc.severity === 'critical' ? '#991B1B' : '#92400E',
                          textTransform: 'uppercase',
                        }}>
                          {inc.severity}
                        </span>
                      </div>
                      <div style={{ fontSize: 11, color: '#4B5563', lineHeight: 1.4, marginBottom: 4 }}>
                        {inc.title}
                      </div>
                      <div style={{ fontSize: 10, color: '#9CA3AF' }}>
                        {inc.detected_at ? new Date(inc.detected_at).toLocaleTimeString() : 'Just now'}
                      </div>
                    </div>
                  ))
                )}
              </div>

              <div
                style={{
                  padding: '8px 16px',
                  background: '#F9FAFB',
                  borderTop: '1px solid #F3F4F6',
                  textAlign: 'center',
                }}
              >
                <button
                  type="button"
                  onClick={() => {
                    setShowNotifs(false)
                    navigate('/incidents')
                  }}
                  style={{
                    background: 'none',
                    border: 'none',
                    fontSize: 12,
                    fontWeight: 600,
                    color: '#2563EB',
                    cursor: 'pointer',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 4,
                  }}
                >
                  <span>View all in Incidents</span>
                  <ExternalLink size={11} />
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Operator avatar + Dropdown */}
        <div style={{ position: 'relative' }} ref={operatorRef}>
          <div
            onClick={() => {
              setShowOperator(!showOperator)
              setShowNotifs(false)
            }}
            style={{
              width: 32,
              height: 32,
              borderRadius: '50%',
              background: showOperator ? '#111827' : '#374151',
              color: '#FFFFFF',
              fontSize: 11,
              fontWeight: 700,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              letterSpacing: '0.02em',
              userSelect: 'none',
              cursor: 'pointer',
              transition: 'background 0.12s ease',
            }}
            title="Operator account"
          >
            OP
          </div>

          {showOperator && (
            <div
              style={{
                position: 'absolute',
                top: 40,
                right: 0,
                width: 220,
                background: '#FFFFFF',
                borderRadius: 10,
                border: '1px solid #E5E7EB',
                boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.05)',
                zIndex: 60,
                overflow: 'hidden',
                padding: '6px 0',
              }}
            >
              <div style={{ padding: '8px 14px 10px', borderBottom: '1px solid #F3F4F6' }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: '#111827' }}>Operator (Admin)</div>
                <div style={{ fontSize: 11, color: '#6B7280', fontFamily: 'monospace', marginTop: 1 }}>nexus-host-01</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 6 }}>
                  <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#10B981', display: 'inline-block' }} />
                  <span style={{ fontSize: 11, color: '#059669', fontWeight: 600 }}>Daemon Connected</span>
                </div>
              </div>

              <div style={{ padding: '4px 0' }}>
                <button
                  type="button"
                  onClick={() => {
                    setShowOperator(false)
                    navigate('/settings')
                  }}
                  style={{
                    width: '100%',
                    padding: '8px 14px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    background: 'none',
                    border: 'none',
                    fontSize: 12,
                    color: '#374151',
                    cursor: 'pointer',
                    textAlign: 'left',
                  }}
                  onMouseEnter={e => e.currentTarget.style.background = '#F9FAFB'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                >
                  <Settings size={14} color="#6B7280" />
                  <span>Host settings</span>
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setShowOperator(false)
                    navigate('/policy')
                  }}
                  style={{
                    width: '100%',
                    padding: '8px 14px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    background: 'none',
                    border: 'none',
                    fontSize: 12,
                    color: '#374151',
                    cursor: 'pointer',
                    textAlign: 'left',
                  }}
                  onMouseEnter={e => e.currentTarget.style.background = '#F9FAFB'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                >
                  <Shield size={14} color="#6B7280" />
                  <span>Safety policy</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
