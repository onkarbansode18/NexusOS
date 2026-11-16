import React, { useState } from 'react'
import { useNexusStore } from '../store'
import { api } from '../api/client'
import { Plus, Trash2, Check, Lock, AlertTriangle, ShieldCheck, Sliders, Shield } from 'lucide-react'
import { PageTopbar } from '../components/PageTopbar'

export function PolicyPage() {
  const { policy, setPolicy, toggleSimulationMode } = useNexusStore()
  const [saving, setSaving] = useState(false)
  const [saveSuccess, setSaveSuccess] = useState(false)
  const [showLiveConfirm, setShowLiveConfirm] = useState(false)
  const [newWhitelistProcess, setNewWhitelistProcess] = useState('')
  const [newBlacklistProcess, setNewBlacklistProcess] = useState('')

  // Local editable state for thresholds
  const [cpuWarning, setCpuWarning]   = useState(policy?.cpu_warning_pct ?? 80)
  const [cpuCritical, setCpuCritical] = useState(policy?.cpu_critical_pct ?? 95)
  const [ramWarning, setRamWarning]   = useState(policy?.ram_warning_pct ?? 70)
  const [ramCritical, setRamCritical] = useState(policy?.ram_critical_pct ?? 90)
  const [diskWarning, setDiskWarning] = useState(policy?.disk_warning_pct ?? 80)
  const [diskCritical, setDiskCritical] = useState(policy?.disk_critical_pct ?? 90)

  const isSimulated = policy?.simulation_mode ?? true

  const handleSave = async () => {
    setSaving(true)
    try {
      const patch = {
        cpu_warning_pct: cpuWarning,
        cpu_critical_pct: cpuCritical,
        ram_warning_pct: ramWarning,
        ram_critical_pct: ramCritical,
        disk_warning_pct: diskWarning,
        disk_critical_pct: diskCritical,
        process_whitelist: policy.process_whitelist,
        process_blacklist: policy.process_blacklist,
      }
      const updated = await api.updatePolicy(patch as Record<string, unknown>)
      setPolicy(updated as Partial<import('../types').Policy>)
      setSaveSuccess(true)
      setTimeout(() => setSaveSuccess(false), 2500)
    } catch (err) {
      console.error('Failed to save policy:', err)
    } finally {
      setSaving(false)
    }
  }

  const handleModeToggle = () => {
    if (isSimulated) {
      setShowLiveConfirm(true)
    } else {
      toggleSimulationMode()
    }
  }

  const confirmSwitchToLive = () => {
    toggleSimulationMode()
    setShowLiveConfirm(false)
  }

  const addWhitelisted = () => {
    if (!newWhitelistProcess.trim() || !policy) return
    const name = newWhitelistProcess.trim().toLowerCase()
    if (!policy.process_whitelist.includes(name)) {
      const updated = [...policy.process_whitelist, name]
      setPolicy({ process_whitelist: updated })
      api.updatePolicy({ process_whitelist: updated }).catch(console.warn)
    }
    setNewWhitelistProcess('')
  }

  const removeWhitelisted = (name: string) => {
    if (!policy) return
    const updated = policy.process_whitelist.filter((i) => i !== name)
    setPolicy({ process_whitelist: updated })
    api.updatePolicy({ process_whitelist: updated }).catch(console.warn)
  }

  const addProtected = () => {
    if (!newBlacklistProcess.trim() || !policy) return
    const name = newBlacklistProcess.trim().toLowerCase()
    if (!policy.process_blacklist.includes(name)) {
      const updated = [...policy.process_blacklist, name]
      setPolicy({ process_blacklist: updated })
      api.updatePolicy({ process_blacklist: updated }).catch(console.warn)
    }
    setNewBlacklistProcess('')
  }

  const removeProtected = (name: string) => {
    if (!policy) return
    const updated = policy.process_blacklist.filter((i) => i !== name)
    setPolicy({ process_blacklist: updated })
    api.updatePolicy({ process_blacklist: updated }).catch(console.warn)
  }

  return (
    <div className="dashboard-page">
      <PageTopbar
        current="Safety & Policy Controls"
        subtitle="Resource saturation thresholds, execution limits, and process protection rules"
        actions={
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            style={{
              height: 30,
              padding: '0 14px',
              background: '#111827',
              color: '#FFFFFF',
              border: 'none',
              borderRadius: 8,
              fontSize: 12,
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              cursor: 'pointer',
            }}
          >
            {saveSuccess ? (
              <>
                <Check size={13} strokeWidth={2.5} />
                <span>Policies saved</span>
              </>
            ) : (
              <span>{saving ? 'Saving…' : 'Save policies'}</span>
            )}
          </button>
        }
      />

      <div style={{ maxWidth: 840, display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* Section 1: Execution Mode */}
        <div className="dash-card" style={{ padding: '20px 24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, paddingBottom: 14, borderBottom: '1px solid var(--border)' }}>
            <div className="stat-icon-ring" style={{ width: 28, height: 28 }}>
              <Shield size={14} strokeWidth={1.75} />
            </div>
            <div>
              <div className="dash-card-title" style={{ fontSize: 14 }}>1. Execution mode</div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Define whether actions are simulated or executed on the host</div>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: 16 }}>
            <div style={{ maxWidth: 520 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: '#111827' }}>
                  {isSimulated ? 'Simulation mode active' : 'Live execution mode active'}
                </span>
                <span className={isSimulated ? 'pill-watching' : 'pill-resolved'}>
                  {isSimulated ? 'Simulation' : 'Live'}
                </span>
              </div>
              <p style={{ fontSize: 12, color: 'var(--text-muted)', margin: '3px 0 0', lineHeight: 1.5 }}>
                {isSimulated
                  ? 'All healing interventions are modeled and logged without modifying operating system processes. Disabling switches to Live mode.'
                  : 'Corrective actions (renice, suspend, restart, kill) execute directly on host processes.'}
              </p>
            </div>

            <button
              type="button"
              onClick={handleModeToggle}
              style={{
                height: 30,
                padding: '0 12px',
                background: isSimulated ? '#111827' : 'var(--surface-3)',
                color: isSimulated ? '#FFFFFF' : '#111827',
                border: '1px solid var(--border)',
                borderRadius: 8,
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              {isSimulated ? 'Switch to live mode' : 'Switch to simulation'}
            </button>
          </div>
        </div>

        {/* Section 2: Anomaly Thresholds */}
        <div className="dash-card" style={{ padding: '20px 24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, paddingBottom: 14, borderBottom: '1px solid var(--border)' }}>
            <div className="stat-icon-ring" style={{ width: 28, height: 28 }}>
              <Sliders size={14} strokeWidth={1.75} />
            </div>
            <div>
              <div className="dash-card-title" style={{ fontSize: 14 }}>2. Anomaly thresholds</div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Sustained telemetry boundaries before autonomous intervention evaluates</div>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 16, paddingTop: 16 }}>
            {/* CPU */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <span style={{ fontSize: 13, fontWeight: 600, color: '#111827' }}>CPU core load boundary</span>
                <p style={{ fontSize: 12, color: 'var(--text-muted)', margin: '2px 0 0' }}>Triggers priority throttling (renice +19)</p>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--text-muted)' }}>
                  <span>Warn</span>
                  <input
                    type="number"
                    min={1}
                    max={99}
                    value={cpuWarning}
                    onChange={(e) => setCpuWarning(Number(e.target.value))}
                    className="dash-search-input"
                    style={{ width: 60, height: 30, borderRadius: 6, textAlign: 'center', padding: '0 4px', fontWeight: 600 }}
                  />
                  <span>%</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--text-muted)' }}>
                  <span>Crit</span>
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={cpuCritical}
                    onChange={(e) => setCpuCritical(Number(e.target.value))}
                    className="dash-search-input"
                    style={{ width: 60, height: 30, borderRadius: 6, textAlign: 'center', padding: '0 4px', fontWeight: 600 }}
                  />
                  <span>%</span>
                </div>
              </div>
            </div>

            {/* RAM */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderTop: '1px solid var(--border)', paddingTop: 16 }}>
              <div>
                <span style={{ fontSize: 13, fontWeight: 600, color: '#111827' }}>RAM physical memory capacity</span>
                <p style={{ fontSize: 12, color: 'var(--text-muted)', margin: '2px 0 0' }}>Dispatches working-set cache reclamation signal</p>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--text-muted)' }}>
                  <span>Warn</span>
                  <input
                    type="number"
                    min={1}
                    max={99}
                    value={ramWarning}
                    onChange={(e) => setRamWarning(Number(e.target.value))}
                    className="dash-search-input"
                    style={{ width: 60, height: 30, borderRadius: 6, textAlign: 'center', padding: '0 4px', fontWeight: 600 }}
                  />
                  <span>%</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--text-muted)' }}>
                  <span>Crit</span>
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={ramCritical}
                    onChange={(e) => setRamCritical(Number(e.target.value))}
                    className="dash-search-input"
                    style={{ width: 60, height: 30, borderRadius: 6, textAlign: 'center', padding: '0 4px', fontWeight: 600 }}
                  />
                  <span>%</span>
                </div>
              </div>
            </div>

            {/* Disk */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderTop: '1px solid var(--border)', paddingTop: 16 }}>
              <div>
                <span style={{ fontSize: 13, fontWeight: 600, color: '#111827' }}>Disk volume storage threshold</span>
                <p style={{ fontSize: 12, color: 'var(--text-muted)', margin: '2px 0 0' }}>Triggers automated purge of verified temp files and rotatable logs</p>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--text-muted)' }}>
                  <span>Warn</span>
                  <input
                    type="number"
                    min={1}
                    max={99}
                    value={diskWarning}
                    onChange={(e) => setDiskWarning(Number(e.target.value))}
                    className="dash-search-input"
                    style={{ width: 60, height: 30, borderRadius: 6, textAlign: 'center', padding: '0 4px', fontWeight: 600 }}
                  />
                  <span>%</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--text-muted)' }}>
                  <span>Crit</span>
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={diskCritical}
                    onChange={(e) => setDiskCritical(Number(e.target.value))}
                    className="dash-search-input"
                    style={{ width: 60, height: 30, borderRadius: 6, textAlign: 'center', padding: '0 4px', fontWeight: 600 }}
                  />
                  <span>%</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Section 3: Protected Processes (Blacklist) */}
        <div className="dash-card" style={{ padding: '20px 24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, paddingBottom: 14, borderBottom: '1px solid var(--border)' }}>
            <div className="stat-icon-ring" style={{ width: 28, height: 28 }}>
              <ShieldCheck size={14} strokeWidth={1.75} />
            </div>
            <div>
              <div className="dash-card-title" style={{ fontSize: 14 }}>3. Protected processes (blacklist)</div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Immune to autonomous intervention or termination</div>
            </div>
          </div>

          <div style={{ display: 'flex', gap: 8, paddingTop: 16 }}>
            <input
              type="text"
              placeholder="Process name (e.g. postgres.exe, svchost.exe)"
              value={newBlacklistProcess}
              onChange={(e) => setNewBlacklistProcess(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && addProtected()}
              className="dash-search-input"
              style={{ flex: 1, borderRadius: 8, height: 32 }}
            />
            <button
              type="button"
              onClick={addProtected}
              style={{
                height: 32,
                padding: '0 12px',
                background: '#111827',
                color: '#FFFFFF',
                border: 'none',
                borderRadius: 8,
                fontSize: 12,
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: 5,
                cursor: 'pointer',
              }}
            >
              <Plus size={13} strokeWidth={2} />
              <span>Protect</span>
            </button>
          </div>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 14 }}>
            {(policy?.process_blacklist ?? []).map((name) => (
              <span
                key={name}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '4px 10px',
                  background: 'var(--surface-3)',
                  border: '1px solid var(--border)',
                  borderRadius: 20,
                  fontSize: 12,
                  fontFamily: 'monospace',
                  color: '#111827',
                }}
              >
                <Lock size={11} className="text-text-muted" />
                <span>{name}</span>
                <button
                  type="button"
                  onClick={() => removeProtected(name)}
                  style={{
                    border: 'none',
                    background: 'transparent',
                    cursor: 'pointer',
                    color: 'var(--text-faint)',
                    padding: 0,
                    display: 'flex',
                    alignItems: 'center',
                  }}
                  title="Remove from protection"
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Confirmation Modal for Live Mode */}
      {showLiveConfirm && (
        <div style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0,0,0,0.4)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 100,
        }}>
          <div style={{
            background: 'var(--surface)',
            borderRadius: 14,
            padding: 24,
            width: 440,
            boxShadow: '0 20px 40px rgba(0,0,0,0.2)',
            display: 'flex',
            flexDirection: 'column',
            gap: 16,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div className="stat-icon-ring" style={{ background: '#FEE2E2', color: '#DC2626' }}>
                <AlertTriangle size={16} strokeWidth={2} />
              </div>
              <h3 style={{ fontSize: 16, fontWeight: 700, margin: 0, color: '#111827' }}>Switch to Live Mode?</h3>
            </div>
            <p style={{ fontSize: 13, color: 'var(--text-muted)', margin: 0, lineHeight: 1.5 }}>
              In Live mode, the Nexus guardian agent has kernel authorization to terminate processes, renice priorities, and trim working sets on the host operating system.
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 8 }}>
              <button
                type="button"
                onClick={() => setShowLiveConfirm(false)}
                style={{
                  border: '1px solid var(--border)',
                  background: 'transparent',
                  padding: '6px 14px',
                  borderRadius: 8,
                  fontSize: 12,
                  fontWeight: 500,
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmSwitchToLive}
                style={{
                  border: 'none',
                  background: '#DC2626',
                  color: '#FFFFFF',
                  padding: '6px 14px',
                  borderRadius: 8,
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Confirm Live Mode
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
