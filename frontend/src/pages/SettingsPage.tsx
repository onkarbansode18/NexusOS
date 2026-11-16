import React, { useState, useEffect } from 'react'
import { PageTopbar } from '../components/PageTopbar'
import { PdfReportModal } from '../components/PdfReportModal'
import { useNexusStore } from '../store'
import { api } from '../api/client'
import {
  Shield,
  Sliders,
  Lock,
  CheckCircle2,
  Server,
  FileText,
  AlertTriangle,
  Edit3,
  Save,
  X,
  Plus,
  Download,
  RefreshCw,
  Check,
  Cpu,
  HardDrive,
  Activity,
  Smartphone,
  Send,
  Bell,
  Mail,
  Phone,
} from 'lucide-react'

type SettingsTab = 'safety' | 'governance' | 'host' | 'alerts' | 'reports' | 'emergency'

export function SettingsPage() {
  const { metrics, processes, policy, fetchPolicy, setPolicy, toggleSimulationMode } = useNexusStore()

  // Active sub-navigation tab
  const [activeTab, setActiveTab] = useState<SettingsTab>('safety')

  // Edit modes for individual cards
  const [editingThresholds, setEditingThresholds] = useState(false)
  const [cpuWarning, setCpuWarning] = useState<number>(policy.cpu_warning_pct || 80)
  const [cpuCritical, setCpuCritical] = useState<number>(policy.cpu_critical_pct || 90)
  const [ramWarning, setRamWarning] = useState<number>(policy.ram_warning_pct || 80)
  const [ramCritical, setRamCritical] = useState<number>(policy.ram_critical_pct || 92)
  const [diskWarning, setDiskWarning] = useState<number>(policy.disk_warning_pct || 85)
  const [diskCritical, setDiskCritical] = useState<number>(policy.disk_critical_pct || 95)
  const [savingThresholds, setSavingThresholds] = useState(false)

  // Whitelist & Blacklist state
  const [whitelist, setWhitelist] = useState<string[]>([])
  const [blacklist, setBlacklist] = useState<string[]>([])
  const [newWhitelistProcess, setNewWhitelistProcess] = useState('')
  const [newBlacklistProcess, setNewBlacklistProcess] = useState('')
  const [showAddWhitelist, setShowAddWhitelist] = useState(false)
  const [showAddBlacklist, setShowAddBlacklist] = useState(false)

  // Emergency Stop status
  const [emergencyStopActive, setEmergencyStopActive] = useState(false)
  const [emergencyReason, setEmergencyReason] = useState('')
  const [togglingEmergency, setTogglingEmergency] = useState(false)

  // Reports
  const [showPdfModal, setShowPdfModal] = useState(false)
  const [exportingReport, setExportingReport] = useState(false)
  const [reportFormat, setReportFormat] = useState<'markdown' | 'json'>('markdown')

  // Critical Email Alerts State
  const [alertEmail, setAlertEmail] = useState('')
  const [emailAlertsEnabled, setEmailAlertsEnabled] = useState(true)
  const [smtpSenderEmail, setSmtpSenderEmail] = useState('')
  const [smtpAppPassword, setSmtpAppPassword] = useState('')
  const [showEmailConfig, setShowEmailConfig] = useState(false)
  const [savingAlerts, setSavingAlerts] = useState(false)
  const [sendingTestAlert, setSendingTestAlert] = useState(false)
  const [alertHistory, setAlertHistory] = useState<any[]>([])
  const [loadingHistory, setLoadingHistory] = useState(false)

  // Notification Toast
  const [toastMessage, setToastMessage] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  // Load backend policy and emergency status on mount
  const loadData = async () => {
    setRefreshing(true)
    try {
      await fetchPolicy()
      const [cooldownRes, alertSettingsRes, historyRes] = await Promise.all([
        api.fetchCooldownStatus().catch(() => null),
        api.fetchAlertSettings().catch(() => null),
        api.fetchAlertHistory(20).catch(() => []),
      ])

      if (cooldownRes) {
        setEmergencyStopActive(!!cooldownRes.emergency_stop_active)
        setEmergencyReason(cooldownRes.emergency_stop_reason || '')
      }

      if (alertSettingsRes) {
        setAlertEmail(alertSettingsRes.email || '')
        setEmailAlertsEnabled(alertSettingsRes.email_enabled ?? true)
        if ((alertSettingsRes as any).smtp_user) setSmtpSenderEmail((alertSettingsRes as any).smtp_user)
      }

      if (Array.isArray(historyRes)) {
        setAlertHistory(historyRes)
      }
    } catch (err) {
      console.warn('Failed to load settings data from backend:', err)
    } finally {
      setRefreshing(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  // Sync policy state to local inputs
  useEffect(() => {
    if (policy) {
      setCpuWarning(policy.cpu_warning_pct ?? 80)
      setCpuCritical(policy.cpu_critical_pct ?? 90)
      setRamWarning(policy.ram_warning_pct ?? 80)
      setRamCritical(policy.ram_critical_pct ?? 92)
      setDiskWarning(policy.disk_warning_pct ?? 85)
      setDiskCritical(policy.disk_critical_pct ?? 95)
      setWhitelist(policy.process_whitelist?.length ? policy.process_whitelist : ['python.exe', 'node.exe', 'chrome.exe'])
      setBlacklist(policy.process_blacklist?.length ? policy.process_blacklist : ['systemd', 'explorer.exe', 'svchost.exe', 'csrss.exe', 'services.exe'])
    }
  }, [policy])

  // Toast auto-clear
  useEffect(() => {
    if (toastMessage) {
      const timer = setTimeout(() => setToastMessage(null), 3500)
      return () => clearTimeout(timer)
    }
  }, [toastMessage])

  // Save Thresholds
  const handleSaveThresholds = async () => {
    setSavingThresholds(true)
    try {
      await api.updatePolicy({
        cpu_warning_pct: Number(cpuWarning),
        cpu_critical_pct: Number(cpuCritical),
        ram_warning_pct: Number(ramWarning),
        ram_critical_pct: Number(ramCritical),
        disk_warning_pct: Number(diskWarning),
        disk_critical_pct: Number(diskCritical),
      })
      setPolicy({
        cpu_warning_pct: Number(cpuWarning),
        cpu_critical_pct: Number(cpuCritical),
        ram_warning_pct: Number(ramWarning),
        ram_critical_pct: Number(ramCritical),
        disk_warning_pct: Number(diskWarning),
        disk_critical_pct: Number(diskCritical),
      })
      setEditingThresholds(false)
      setToastMessage('Threshold policies updated successfully in SQLite.')
    } catch (err) {
      console.error('Failed to update thresholds:', err)
      setToastMessage('Error saving thresholds to backend.')
    } finally {
      setSavingThresholds(false)
    }
  }

  // Whitelist Handlers
  const handleAddWhitelist = async () => {
    const proc = newWhitelistProcess.trim().toLowerCase()
    if (!proc || whitelist.includes(proc)) return
    const updated = [...whitelist, proc]
    setWhitelist(updated)
    setNewWhitelistProcess('')
    setShowAddWhitelist(false)
    try {
      await api.updatePolicy({ process_whitelist: updated })
      setPolicy({ process_whitelist: updated })
      setToastMessage(`Added "${proc}" to permitted whitelist.`)
    } catch {
      setToastMessage('Failed to save whitelist change.')
    }
  }

  const handleRemoveWhitelist = async (name: string) => {
    const updated = whitelist.filter((p) => p !== name)
    setWhitelist(updated)
    try {
      await api.updatePolicy({ process_whitelist: updated })
      setPolicy({ process_whitelist: updated })
      setToastMessage(`Removed "${name}" from whitelist.`)
    } catch {
      setToastMessage('Failed to save whitelist change.')
    }
  }

  // Blacklist Handlers
  const handleAddBlacklist = async () => {
    const proc = newBlacklistProcess.trim().toLowerCase()
    if (!proc || blacklist.includes(proc)) return
    const updated = [...blacklist, proc]
    setBlacklist(updated)
    setNewBlacklistProcess('')
    setShowAddBlacklist(false)
    try {
      await api.updatePolicy({ process_blacklist: updated })
      setPolicy({ process_blacklist: updated })
      setToastMessage(`Added "${proc}" to protected system blacklist.`)
    } catch {
      setToastMessage('Failed to save blacklist change.')
    }
  }

  const handleRemoveBlacklist = async (name: string) => {
    const updated = blacklist.filter((p) => p !== name)
    setBlacklist(updated)
    try {
      await api.updatePolicy({ process_blacklist: updated })
      setPolicy({ process_blacklist: updated })
      setToastMessage(`Removed "${name}" from blacklist.`)
    } catch {
      setToastMessage('Failed to save blacklist change.')
    }
  }

  // Emergency Stop Toggle
  const handleToggleEmergencyStop = async () => {
    setTogglingEmergency(true)
    try {
      if (emergencyStopActive) {
        await api.clearEmergencyStop()
        setEmergencyStopActive(false)
        setEmergencyReason('')
        setToastMessage('Emergency stop cleared. Autonomous operations resumed.')
      } else {
        await api.triggerEmergencyStop('Manual emergency stop triggered via Settings.')
        setEmergencyStopActive(true)
        setEmergencyReason('Manual operator trigger via Settings.')
        setToastMessage('Emergency stop ACTIVE: All autonomous operations halted.')
      }
    } catch (err) {
      console.warn('Emergency stop action failed:', err)
      setToastMessage('Failed to toggle emergency stop on backend.')
    } finally {
      setTogglingEmergency(false)
    }
  }

  // Generate Diagnostic Report
  const handleGenerateReport = async () => {
    setExportingReport(true)
    try {
      const res = await api.generateReport(reportFormat)
      const blob = new Blob([res.report || ''], {
        type: reportFormat === 'json' ? 'application/json' : 'text/markdown',
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `nexus_diagnostic_report_${new Date().toISOString().slice(0, 10)}.${reportFormat === 'json' ? 'json' : 'md'}`
      a.click()
      URL.revokeObjectURL(url)
      setToastMessage(`Exported diagnostic report in ${reportFormat.toUpperCase()} format.`)
    } catch (err) {
      console.error('Failed to generate report:', err)
      setToastMessage('Error generating report from backend.')
    } finally {
      setExportingReport(false)
    }
  }

  // Save Email Alert Settings
  const handleSaveAlerts = async () => {
    setSavingAlerts(true)
    try {
      await api.updateAlertSettings({
        email: alertEmail.trim(),
        email_enabled: emailAlertsEnabled,
        smtp_user: smtpSenderEmail.trim() || undefined,
        smtp_password: smtpAppPassword.trim() || undefined,
      })
      setToastMessage('Email alert settings saved successfully.')
    } catch {
      setToastMessage('Failed to save alert settings on backend.')
    } finally {
      setSavingAlerts(false)
    }
  }

  // Send Test Email Alert
  const handleSendTestAlert = async () => {
    if (!alertEmail.trim()) {
      setToastMessage('Please enter your email address first.')
      return
    }
    setSendingTestAlert(true)
    try {
      // Auto-save any updated credentials first
      await api.updateAlertSettings({
        email: alertEmail.trim(),
        email_enabled: emailAlertsEnabled,
        smtp_user: smtpSenderEmail.trim() || undefined,
        smtp_password: smtpAppPassword.trim() || undefined,
      }).catch(() => null)

      const rec = await api.sendTestAlert('', alertEmail.trim())
      if (rec.status === 'delivered') {
        setToastMessage(`✅ Test email delivered to ${alertEmail}! Check your inbox.`)
      } else {
        setToastMessage(`⚠️ ${rec.provider || 'Email credentials not configured yet.'}`)
      }
      const hist = await api.fetchAlertHistory(20)
      if (Array.isArray(hist)) setAlertHistory(hist)
    } catch (err: any) {
      setToastMessage(err.message || 'Failed to dispatch test email.')
    } finally {
      setSendingTestAlert(false)
    }
  }

  const handleRefreshAlertHistory = async () => {
    setLoadingHistory(true)
    try {
      const hist = await api.fetchAlertHistory(20)
      if (Array.isArray(hist)) setAlertHistory(hist)
      setToastMessage('Alert dispatch history refreshed.')
    } catch {
      setToastMessage('Failed to fetch alert history.')
    } finally {
      setLoadingHistory(false)
    }
  }

  const hostRamGB = metrics?.ram_total_mb ? (metrics.ram_total_mb / 1024).toFixed(1) : '16.0'
  const hostRamUsedGB = metrics?.ram_used_mb ? (metrics.ram_used_mb / 1024).toFixed(1) : '8.2'
  const hostDiskTotalGB = metrics?.disk_total_gb ? metrics.disk_total_gb.toFixed(0) : '512'

  return (
    <div className="dashboard-page" style={{ paddingBottom: 60 }}>
      <PageTopbar
        current="Settings"
        subtitle="Manage autonomous healing policies, guardrails, and environment governance"
        actions={
          <button
            type="button"
            onClick={loadData}
            disabled={refreshing}
            style={{
              height: 32,
              padding: '0 14px',
              background: '#FFFFFF',
              color: '#374151',
              border: '1px solid #E5E7EB',
              borderRadius: 8,
              fontSize: 12,
              fontWeight: 500,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
            }}
          >
            <RefreshCw size={13} className={refreshing ? 'animate-spin' : ''} />
            <span>Reload config</span>
          </button>
        }
      />

      {/* Toast Notification */}
      {toastMessage && (
        <div style={{
          position: 'fixed',
          bottom: 24,
          right: 24,
          background: '#111827',
          color: '#FFFFFF',
          padding: '12px 18px',
          borderRadius: 8,
          fontSize: 13,
          fontWeight: 500,
          boxShadow: '0 10px 25px -5px rgba(0,0,0,0.25)',
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          zIndex: 9999,
          animation: 'slideUp 0.2s ease',
        }}>
          <CheckCircle2 size={16} color="#10B981" />
          <span>{toastMessage}</span>
          <button
            type="button"
            onClick={() => setToastMessage(null)}
            style={{ background: 'none', border: 'none', color: '#9CA3AF', cursor: 'pointer', padding: 2 }}
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* Main Settings Card Container — Clean Two-Column Layout */}
      <div style={{
        background: '#FFFFFF',
        borderRadius: 16,
        border: '1px solid #E5E7EB',
        boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
        padding: '24px 28px',
        marginTop: 6,
      }}>
        {/* Title row */}
        <div style={{ marginBottom: 24, paddingBottom: 16, borderBottom: '1px solid #F3F4F6' }}>
          <h2 style={{ fontSize: 20, fontWeight: 700, color: '#111827', margin: 0 }}>
            Guardian Settings
          </h2>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: '#6B7280' }}>
            System configuration and policy engine parameters for automated remediation.
          </p>
        </div>

        {/* 2-Column Layout: Left Navigation + Right Content */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: '230px 1fr',
          gap: 32,
          alignItems: 'start',
        }}>
          {/* Left Vertical Sub-Navigation */}
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 4,
          }}>
            <button
              type="button"
              onClick={() => setActiveTab('safety')}
              style={{
                width: '100%',
                textAlign: 'left',
                padding: '10px 14px',
                borderRadius: 8,
                fontSize: 13,
                fontWeight: activeTab === 'safety' ? 600 : 500,
                color: activeTab === 'safety' ? '#2563EB' : '#4B5563',
                background: activeTab === 'safety' ? '#EFF6FF' : 'transparent',
                border: 'none',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                transition: 'all 0.15s ease',
              }}
            >
              <Shield size={16} color={activeTab === 'safety' ? '#2563EB' : '#6B7280'} />
              <span>Safety & Policy</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('governance')}
              style={{
                width: '100%',
                textAlign: 'left',
                padding: '10px 14px',
                borderRadius: 8,
                fontSize: 13,
                fontWeight: activeTab === 'governance' ? 600 : 500,
                color: activeTab === 'governance' ? '#2563EB' : '#4B5563',
                background: activeTab === 'governance' ? '#EFF6FF' : 'transparent',
                border: 'none',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                transition: 'all 0.15s ease',
              }}
            >
              <Lock size={16} color={activeTab === 'governance' ? '#2563EB' : '#6B7280'} />
              <span>Process Governance</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('host')}
              style={{
                width: '100%',
                textAlign: 'left',
                padding: '10px 14px',
                borderRadius: 8,
                fontSize: 13,
                fontWeight: activeTab === 'host' ? 600 : 500,
                color: activeTab === 'host' ? '#2563EB' : '#4B5563',
                background: activeTab === 'host' ? '#EFF6FF' : 'transparent',
                border: 'none',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                transition: 'all 0.15s ease',
              }}
            >
              <Server size={16} color={activeTab === 'host' ? '#2563EB' : '#6B7280'} />
              <span>Host Environment</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('alerts')}
              style={{
                width: '100%',
                textAlign: 'left',
                padding: '10px 14px',
                borderRadius: 8,
                fontSize: 13,
                fontWeight: activeTab === 'alerts' ? 600 : 500,
                color: activeTab === 'alerts' ? '#2563EB' : '#4B5563',
                background: activeTab === 'alerts' ? '#EFF6FF' : 'transparent',
                border: 'none',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                transition: 'all 0.15s ease',
              }}
            >
              <Mail size={16} color={activeTab === 'alerts' ? '#2563EB' : '#6B7280'} />
              <span>Critical Email Alerts</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('reports')}
              style={{
                width: '100%',
                textAlign: 'left',
                padding: '10px 14px',
                borderRadius: 8,
                fontSize: 13,
                fontWeight: activeTab === 'reports' ? 600 : 500,
                color: activeTab === 'reports' ? '#2563EB' : '#4B5563',
                background: activeTab === 'reports' ? '#EFF6FF' : 'transparent',
                border: 'none',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                transition: 'all 0.15s ease',
              }}
            >
              <FileText size={16} color={activeTab === 'reports' ? '#2563EB' : '#6B7280'} />
              <span>Audit & Reports</span>
            </button>

            {/* Separator */}
            <div style={{ height: 1, background: '#F3F4F6', margin: '14px 0 8px' }} />

            {/* Emergency Action in Red (like 'Delete Account' in reference) */}
            <button
              type="button"
              onClick={() => setActiveTab('emergency')}
              style={{
                width: '100%',
                textAlign: 'left',
                padding: '10px 14px',
                borderRadius: 8,
                fontSize: 13,
                fontWeight: activeTab === 'emergency' ? 600 : 500,
                color: activeTab === 'emergency' ? '#DC2626' : '#EF4444',
                background: activeTab === 'emergency' ? '#FEF2F2' : 'transparent',
                border: 'none',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                transition: 'all 0.15s ease',
              }}
            >
              <AlertTriangle size={16} color="#DC2626" />
              <span>Emergency Kill Switch</span>
            </button>
          </div>

          {/* Right Main Content Area */}
          <div style={{ minWidth: 0 }}>
            {/* ── TAB 1: SAFETY & POLICY ────────────────────────────────────────── */}
            {activeTab === 'safety' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                {/* Card 1: Autonomous Safety Mode */}
                <div style={{
                  background: '#FFFFFF',
                  border: '1px solid #E5E7EB',
                  borderRadius: 12,
                  padding: '22px 24px',
                  boxShadow: '0 1px 2px rgba(0,0,0,0.02)',
                }}>
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    marginBottom: 16,
                  }}>
                    <div>
                      <div style={{ fontSize: 15, fontWeight: 700, color: '#111827' }}>
                        Autonomous Operation Mode
                      </div>
                      <div style={{ fontSize: 12, color: '#6B7280', marginTop: 2 }}>
                        Controls whether corrective actions are executed on the host OS or evaluated in a safe sandbox.
                      </div>
                    </div>

                    {/* iOS Switch */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <span style={{ fontSize: 12, fontWeight: 600, color: policy.simulation_mode ? '#2563EB' : '#059669' }}>
                        {policy.simulation_mode ? 'Simulation Mode' : 'Live Healing'}
                      </span>
                      <div
                        onClick={toggleSimulationMode}
                        style={{
                          width: 44,
                          height: 24,
                          borderRadius: 12,
                          background: policy.simulation_mode ? '#3B82F6' : '#10B981',
                          position: 'relative',
                          cursor: 'pointer',
                          transition: 'background 0.2s ease',
                        }}
                        title="Click to toggle simulation mode"
                      >
                        <div
                          style={{
                            width: 20,
                            height: 20,
                            borderRadius: '50%',
                            background: '#FFFFFF',
                            position: 'absolute',
                            top: 2,
                            left: policy.simulation_mode ? 22 : 2,
                            transition: 'left 0.2s ease',
                            boxShadow: '0 1px 3px rgba(0,0,0,0.25)',
                          }}
                        />
                      </div>
                    </div>
                  </div>

                  {/* Clean Spec Grid */}
                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                    gap: 16,
                    paddingTop: 16,
                    borderTop: '1px solid #F3F4F6',
                  }}>
                    <div>
                      <div style={{ fontSize: 11, color: '#6B7280', marginBottom: 4 }}>Current State</div>
                      <div style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 6,
                        padding: '3px 9px',
                        borderRadius: 12,
                        fontSize: 12,
                        fontWeight: 600,
                        background: policy.simulation_mode ? '#EFF6FF' : '#ECFDF5',
                        color: policy.simulation_mode ? '#2563EB' : '#059669',
                      }}>
                        ● {policy.simulation_mode ? 'Dry-Run Simulation Active' : 'Live Interventions Permitted'}
                      </div>
                    </div>

                    <div>
                      <div style={{ fontSize: 11, color: '#6B7280', marginBottom: 4 }}>Cooldown Period</div>
                      <div style={{ fontSize: 13, fontWeight: 600, color: '#111827' }}>
                        5 Minutes per target process
                      </div>
                    </div>

                    <div>
                      <div style={{ fontSize: 11, color: '#6B7280', marginBottom: 4 }}>Mitigation Principle</div>
                      <div style={{ fontSize: 13, fontWeight: 600, color: '#111827' }}>
                        Least aggressive action (Renice → Throttle → Restart)
                      </div>
                    </div>
                  </div>
                </div>

                {/* Card 2: Resource Threshold Policy */}
                <div style={{
                  background: '#FFFFFF',
                  border: '1px solid #E5E7EB',
                  borderRadius: 12,
                  padding: '22px 24px',
                  boxShadow: '0 1px 2px rgba(0,0,0,0.02)',
                }}>
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    marginBottom: 16,
                  }}>
                    <div>
                      <div style={{ fontSize: 15, fontWeight: 700, color: '#111827' }}>
                        Resource Alert & Healing Boundaries
                      </div>
                      <div style={{ fontSize: 12, color: '#6B7280', marginTop: 2 }}>
                        Configures warning and critical escalation percentages stored in SQLite and evaluated by the detector.
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={() => {
                        if (editingThresholds) {
                          handleSaveThresholds()
                        } else {
                          setEditingThresholds(true)
                        }
                      }}
                      disabled={savingThresholds}
                      style={{
                        height: 32,
                        padding: '0 14px',
                        background: editingThresholds ? '#111827' : '#FFFFFF',
                        color: editingThresholds ? '#FFFFFF' : '#2563EB',
                        border: editingThresholds ? 'none' : '1px solid #BFDBFE',
                        borderRadius: 8,
                        fontSize: 12,
                        fontWeight: 600,
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                        boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
                      }}
                    >
                      {editingThresholds ? (
                        <>
                          <Save size={13} />
                          <span>{savingThresholds ? 'Saving...' : 'Save Changes'}</span>
                        </>
                      ) : (
                        <>
                          <Edit3 size={13} />
                          <span>Edit</span>
                        </>
                      )}
                    </button>
                  </div>

                  {/* 3 Threshold Sections */}
                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                    gap: 16,
                    paddingTop: 16,
                    borderTop: '1px solid #F3F4F6',
                  }}>
                    {/* CPU */}
                    <div style={{ background: '#F9FAFB', borderRadius: 8, padding: '14px 16px', border: '1px solid #F3F4F6' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, fontWeight: 700, color: '#111827', marginBottom: 12 }}>
                        <Cpu size={15} color="#2563EB" />
                        <span>CPU Thresholds</span>
                      </div>

                      {editingThresholds ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                          <div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#4B5563', marginBottom: 4 }}>
                              <span>Warning</span>
                              <strong>{cpuWarning}%</strong>
                            </div>
                            <input
                              type="range"
                              min={10}
                              max={95}
                              value={cpuWarning}
                              onChange={(e) => setCpuWarning(Number(e.target.value))}
                              style={{ width: '100%', accentColor: '#D97706' }}
                            />
                          </div>
                          <div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#4B5563', marginBottom: 4 }}>
                              <span>Critical</span>
                              <strong>{cpuCritical}%</strong>
                            </div>
                            <input
                              type="range"
                              min={20}
                              max={100}
                              value={cpuCritical}
                              onChange={(e) => setCpuCritical(Number(e.target.value))}
                              style={{ width: '100%', accentColor: '#DC2626' }}
                            />
                          </div>
                        </div>
                      ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                            <span style={{ color: '#6B7280' }}>Warning:</span>
                            <span style={{ fontWeight: 600, color: '#D97706' }}>{cpuWarning}% utilization</span>
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                            <span style={{ color: '#6B7280' }}>Critical:</span>
                            <span style={{ fontWeight: 600, color: '#DC2626' }}>{cpuCritical}% escalation</span>
                          </div>
                        </div>
                      )}
                    </div>

                    {/* RAM */}
                    <div style={{ background: '#F9FAFB', borderRadius: 8, padding: '14px 16px', border: '1px solid #F3F4F6' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, fontWeight: 700, color: '#111827', marginBottom: 12 }}>
                        <Activity size={15} color="#7C3AED" />
                        <span>Memory Thresholds</span>
                      </div>

                      {editingThresholds ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                          <div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#4B5563', marginBottom: 4 }}>
                              <span>Warning</span>
                              <strong>{ramWarning}%</strong>
                            </div>
                            <input
                              type="range"
                              min={30}
                              max={95}
                              value={ramWarning}
                              onChange={(e) => setRamWarning(Number(e.target.value))}
                              style={{ width: '100%', accentColor: '#D97706' }}
                            />
                          </div>
                          <div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#4B5563', marginBottom: 4 }}>
                              <span>Critical</span>
                              <strong>{ramCritical}%</strong>
                            </div>
                            <input
                              type="range"
                              min={50}
                              max={100}
                              value={ramCritical}
                              onChange={(e) => setRamCritical(Number(e.target.value))}
                              style={{ width: '100%', accentColor: '#DC2626' }}
                            />
                          </div>
                        </div>
                      ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                            <span style={{ color: '#6B7280' }}>Warning:</span>
                            <span style={{ fontWeight: 600, color: '#D97706' }}>{ramWarning}% memory</span>
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                            <span style={{ color: '#6B7280' }}>Critical:</span>
                            <span style={{ fontWeight: 600, color: '#DC2626' }}>{ramCritical}% memory</span>
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Disk */}
                    <div style={{ background: '#F9FAFB', borderRadius: 8, padding: '14px 16px', border: '1px solid #F3F4F6' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, fontWeight: 700, color: '#111827', marginBottom: 12 }}>
                        <HardDrive size={15} color="#059669" />
                        <span>Storage Thresholds</span>
                      </div>

                      {editingThresholds ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                          <div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#4B5563', marginBottom: 4 }}>
                              <span>Warning</span>
                              <strong>{diskWarning}%</strong>
                            </div>
                            <input
                              type="range"
                              min={40}
                              max={95}
                              value={diskWarning}
                              onChange={(e) => setDiskWarning(Number(e.target.value))}
                              style={{ width: '100%', accentColor: '#D97706' }}
                            />
                          </div>
                          <div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#4B5563', marginBottom: 4 }}>
                              <span>Critical</span>
                              <strong>{diskCritical}%</strong>
                            </div>
                            <input
                              type="range"
                              min={60}
                              max={100}
                              value={diskCritical}
                              onChange={(e) => setDiskCritical(Number(e.target.value))}
                              style={{ width: '100%', accentColor: '#DC2626' }}
                            />
                          </div>
                        </div>
                      ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                            <span style={{ color: '#6B7280' }}>Warning:</span>
                            <span style={{ fontWeight: 600, color: '#D97706' }}>{diskWarning}% capacity</span>
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                            <span style={{ color: '#6B7280' }}>Critical:</span>
                            <span style={{ fontWeight: 600, color: '#DC2626' }}>{diskCritical}% capacity</span>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* ── TAB 2: PROCESS GOVERNANCE ─────────────────────────────────────── */}
            {activeTab === 'governance' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                {/* Permitted Whitelist Card */}
                <div style={{
                  background: '#FFFFFF',
                  border: '1px solid #E5E7EB',
                  borderRadius: 12,
                  padding: '22px 24px',
                  boxShadow: '0 1px 2px rgba(0,0,0,0.02)',
                }}>
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    marginBottom: 16,
                  }}>
                    <div>
                      <div style={{ fontSize: 15, fontWeight: 700, color: '#111827' }}>
                        Permitted Intervention Whitelist
                      </div>
                      <div style={{ fontSize: 12, color: '#6B7280', marginTop: 2 }}>
                        Processes listed here are explicitly authorized for autonomous throttle, renice, and restart.
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={() => setShowAddWhitelist(!showAddWhitelist)}
                      style={{
                        height: 32,
                        padding: '0 14px',
                        background: '#FFFFFF',
                        color: '#2563EB',
                        border: '1px solid #BFDBFE',
                        borderRadius: 8,
                        fontSize: 12,
                        fontWeight: 600,
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                      }}
                    >
                      {showAddWhitelist ? <X size={13} /> : <Plus size={13} />}
                      <span>{showAddWhitelist ? 'Cancel' : 'Edit / Add'}</span>
                    </button>
                  </div>

                  {showAddWhitelist && (
                    <div style={{ display: 'flex', gap: 8, marginBottom: 16, padding: '12px 14px', background: '#F9FAFB', borderRadius: 8 }}>
                      <input
                        type="text"
                        placeholder="e.g. uvicorn.exe"
                        value={newWhitelistProcess}
                        onChange={(e) => setNewWhitelistProcess(e.target.value)}
                        style={{
                          height: 32,
                          padding: '0 10px',
                          borderRadius: 6,
                          border: '1px solid #D1D5DB',
                          fontSize: 12,
                          flex: 1,
                          outline: 'none',
                        }}
                        onKeyDown={(e) => e.key === 'Enter' && handleAddWhitelist()}
                      />
                      <button
                        type="button"
                        onClick={handleAddWhitelist}
                        style={{
                          height: 32,
                          padding: '0 16px',
                          background: '#111827',
                          color: '#FFFFFF',
                          border: 'none',
                          borderRadius: 6,
                          fontSize: 12,
                          fontWeight: 600,
                          cursor: 'pointer',
                        }}
                      >
                        Add Process
                      </button>
                    </div>
                  )}

                  <div style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    gap: 8,
                    paddingTop: 16,
                    borderTop: '1px solid #F3F4F6',
                  }}>
                    {whitelist.map((p) => (
                      <span
                        key={p}
                        style={{
                          padding: '4px 12px',
                          background: '#ECFDF5',
                          border: '1px solid #A7F3D0',
                          borderRadius: 16,
                          fontSize: 12,
                          fontWeight: 500,
                          color: '#065F46',
                          fontFamily: 'monospace',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 6,
                        }}
                      >
                        <span>{p}</span>
                        <button
                          type="button"
                          onClick={() => handleRemoveWhitelist(p)}
                          style={{
                            border: 'none',
                            background: 'none',
                            cursor: 'pointer',
                            padding: 0,
                            color: '#059669',
                            display: 'flex',
                            alignItems: 'center',
                          }}
                          title={`Remove ${p}`}
                        >
                          <X size={12} />
                        </button>
                      </span>
                    ))}
                  </div>
                </div>

                {/* Protected Blacklist Card */}
                <div style={{
                  background: '#FFFFFF',
                  border: '1px solid #E5E7EB',
                  borderRadius: 12,
                  padding: '22px 24px',
                  boxShadow: '0 1px 2px rgba(0,0,0,0.02)',
                }}>
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    marginBottom: 16,
                  }}>
                    <div>
                      <div style={{ fontSize: 15, fontWeight: 700, color: '#111827' }}>
                        Protected System Blacklist
                      </div>
                      <div style={{ fontSize: 12, color: '#6B7280', marginTop: 2 }}>
                        Critical host operating system processes that Nexus is strictly prohibited from terminating or altering.
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={() => setShowAddBlacklist(!showAddBlacklist)}
                      style={{
                        height: 32,
                        padding: '0 14px',
                        background: '#FFFFFF',
                        color: '#2563EB',
                        border: '1px solid #BFDBFE',
                        borderRadius: 8,
                        fontSize: 12,
                        fontWeight: 600,
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                      }}
                    >
                      {showAddBlacklist ? <X size={13} /> : <Plus size={13} />}
                      <span>{showAddBlacklist ? 'Cancel' : 'Edit / Protect'}</span>
                    </button>
                  </div>

                  {showAddBlacklist && (
                    <div style={{ display: 'flex', gap: 8, marginBottom: 16, padding: '12px 14px', background: '#F9FAFB', borderRadius: 8 }}>
                      <input
                        type="text"
                        placeholder="e.g. services.exe"
                        value={newBlacklistProcess}
                        onChange={(e) => setNewBlacklistProcess(e.target.value)}
                        style={{
                          height: 32,
                          padding: '0 10px',
                          borderRadius: 6,
                          border: '1px solid #D1D5DB',
                          fontSize: 12,
                          flex: 1,
                          outline: 'none',
                        }}
                        onKeyDown={(e) => e.key === 'Enter' && handleAddBlacklist()}
                      />
                      <button
                        type="button"
                        onClick={handleAddBlacklist}
                        style={{
                          height: 32,
                          padding: '0 16px',
                          background: '#111827',
                          color: '#FFFFFF',
                          border: 'none',
                          borderRadius: 6,
                          fontSize: 11,
                          fontWeight: 600,
                          cursor: 'pointer',
                        }}
                      >
                        Protect
                      </button>
                    </div>
                  )}

                  <div style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    gap: 8,
                    paddingTop: 16,
                    borderTop: '1px solid #F3F4F6',
                  }}>
                    {blacklist.map((p) => (
                      <span
                        key={p}
                        style={{
                          padding: '4px 12px',
                          background: '#FEF2F2',
                          border: '1px solid #FECACA',
                          borderRadius: 16,
                          fontSize: 12,
                          fontWeight: 500,
                          color: '#991B1B',
                          fontFamily: 'monospace',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 6,
                        }}
                      >
                        <span>{p}</span>
                        <button
                          type="button"
                          onClick={() => handleRemoveBlacklist(p)}
                          style={{
                            border: 'none',
                            background: 'none',
                            cursor: 'pointer',
                            padding: 0,
                            color: '#DC2626',
                            display: 'flex',
                            alignItems: 'center',
                          }}
                          title={`Remove ${p}`}
                        >
                          <X size={12} />
                        </button>
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* ── TAB 3: HOST ENVIRONMENT ──────────────────────────────────────── */}
            {activeTab === 'host' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                <div style={{
                  background: '#FFFFFF',
                  border: '1px solid #E5E7EB',
                  borderRadius: 12,
                  padding: '22px 24px',
                  boxShadow: '0 1px 2px rgba(0,0,0,0.02)',
                }}>
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    marginBottom: 16,
                  }}>
                    <div>
                      <div style={{ fontSize: 15, fontWeight: 700, color: '#111827' }}>
                        Host Specifications & Telemetry
                      </div>
                      <div style={{ fontSize: 12, color: '#6B7280', marginTop: 2 }}>
                        Live hardware and runtime state streamed from the local machine.
                      </div>
                    </div>

                    <div style={{
                      fontSize: 11,
                      fontWeight: 600,
                      padding: '3px 9px',
                      borderRadius: 12,
                      background: '#ECFDF5',
                      color: '#059669',
                    }}>
                      ● Live Connected
                    </div>
                  </div>

                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                    gap: 16,
                    paddingTop: 16,
                    borderTop: '1px solid #F3F4F6',
                  }}>
                    <div>
                      <div style={{ fontSize: 11, color: '#6B7280', marginBottom: 4 }}>Host Operating System</div>
                      <div style={{ fontSize: 13, fontWeight: 600, color: '#111827' }}>Windows (64-bit Architecture)</div>
                    </div>

                    <div>
                      <div style={{ fontSize: 11, color: '#6B7280', marginBottom: 4 }}>Installed RAM</div>
                      <div style={{ fontSize: 13, fontWeight: 600, color: '#111827' }}>{hostRamUsedGB} GB in use / {hostRamGB} GB total</div>
                    </div>

                    <div>
                      <div style={{ fontSize: 11, color: '#6B7280', marginBottom: 4 }}>Drive Volume</div>
                      <div style={{ fontSize: 13, fontWeight: 600, color: '#111827' }}>{hostDiskTotalGB} GB storage volume</div>
                    </div>

                    <div>
                      <div style={{ fontSize: 11, color: '#6B7280', marginBottom: 4 }}>Active Processes</div>
                      <div style={{ fontSize: 13, fontWeight: 600, color: '#2563EB', fontFamily: 'monospace' }}>
                        {processes.length > 0 ? `${processes.length} tasks monitored` : 'Active'}
                      </div>
                    </div>

                    <div>
                      <div style={{ fontSize: 11, color: '#6B7280', marginBottom: 4 }}>Backend API Gateway</div>
                      <div style={{ fontSize: 13, fontWeight: 600, color: '#111827' }}>FastAPI + SQLite (Port 8000)</div>
                    </div>

                    <div>
                      <div style={{ fontSize: 11, color: '#6B7280', marginBottom: 4 }}>ML Anomaly Engine</div>
                      <div style={{ fontSize: 13, fontWeight: 600, color: '#111827' }}>IsolationForest + Sliding Baseline</div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* ── TAB: CRITICAL ALERTS & SMS NOTIFICATIONS ───────────────────── */}
            {activeTab === 'alerts' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                {/* Card 1: Email Alert Configuration */}
                <div style={{
                  background: '#FFFFFF',
                  border: '1px solid #E5E7EB',
                  borderRadius: 12,
                  padding: '24px 26px',
                  boxShadow: '0 1px 2px rgba(0,0,0,0.02)',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
                    <div style={{ background: '#EFF6FF', padding: '10px 11px', borderRadius: 10, display: 'flex', alignItems: 'center' }}>
                      <Mail size={22} color="#2563EB" />
                    </div>
                    <div>
                      <div style={{ fontSize: 16, fontWeight: 700, color: '#111827' }}>
                        Critical Email Alerts
                      </div>
                      <div style={{ fontSize: 13, color: '#6B7280', marginTop: 2 }}>
                        Receive instant email notifications when critical CPU/RAM anomalies or runaway processes are detected.
                      </div>
                    </div>
                  </div>

                  {/* Alert Email Input */}
                  <div style={{ marginBottom: 20 }}>
                    <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#374151', marginBottom: 6 }}>
                      Alert Email Address
                    </label>
                    <div style={{ position: 'relative' }}>
                      <Mail size={15} color="#9CA3AF" style={{ position: 'absolute', left: 12, top: 11 }} />
                      <input
                        type="email"
                        placeholder="e.g. your@gmail.com"
                        value={alertEmail}
                        onChange={(e) => setAlertEmail(e.target.value)}
                        style={{
                          width: '100%',
                          height: 38,
                          padding: '0 12px 0 36px',
                          background: '#FFFFFF',
                          border: '1px solid #D1D5DB',
                          borderRadius: 8,
                          fontSize: 13,
                          color: '#111827',
                          outline: 'none',
                        }}
                      />
                    </div>
                    <div style={{ fontSize: 11, color: '#6B7280', marginTop: 4 }}>
                      You will receive full diagnostic reports with root-cause analysis at this address.
                    </div>
                  </div>

                  {/* Email Alerts Toggle */}
                  <div style={{
                    background: '#F9FAFB',
                    border: '1px solid #E5E7EB',
                    borderRadius: 8,
                    padding: '14px 18px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    marginBottom: 20,
                  }}>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 600, color: '#111827' }}>
                        Enable Email Incident Reports
                      </div>
                      <div style={{ fontSize: 12, color: '#6B7280', marginTop: 1 }}>
                        Sends full root-cause diagnostic reports to your inbox on critical events.
                      </div>
                    </div>
                    <div
                      onClick={() => setEmailAlertsEnabled(!emailAlertsEnabled)}
                      style={{
                        width: 44, height: 24, borderRadius: 12,
                        background: emailAlertsEnabled ? '#2563EB' : '#D1D5DB',
                        position: 'relative', cursor: 'pointer', transition: 'background 0.2s ease',
                      }}
                    >
                      <div style={{
                        width: 20, height: 20, borderRadius: '50%', background: '#FFFFFF',
                        position: 'absolute', top: 2,
                        left: emailAlertsEnabled ? 22 : 2,
                        transition: 'left 0.2s ease', boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
                      }} />
                    </div>
                  </div>

                  {/* Action Buttons */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                    <button
                      type="button"
                      onClick={handleSaveAlerts}
                      disabled={savingAlerts}
                      style={{
                        height: 38, padding: '0 18px', background: '#2563EB', color: '#FFFFFF',
                        border: 'none', borderRadius: 8, fontSize: 13, fontWeight: 600,
                        cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8,
                        boxShadow: '0 1px 2px rgba(37,99,235,0.2)',
                      }}
                    >
                      <Save size={15} />
                      <span>{savingAlerts ? 'Saving...' : 'Save Alert Configuration'}</span>
                    </button>

                    <button
                      type="button"
                      onClick={handleSendTestAlert}
                      disabled={sendingTestAlert}
                      style={{
                        height: 38, padding: '0 16px', background: '#FFFFFF', color: '#374151',
                        border: '1px solid #D1D5DB', borderRadius: 8, fontSize: 13, fontWeight: 500,
                        cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8,
                        boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
                      }}
                    >
                      <Send size={14} />
                      <span>{sendingTestAlert ? 'Sending...' : 'Send Test Email'}</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => setShowEmailConfig(!showEmailConfig)}
                      style={{
                        height: 38, padding: '0 14px',
                        background: showEmailConfig ? '#EFF6FF' : '#F9FAFB',
                        color: showEmailConfig ? '#2563EB' : '#4B5563',
                        border: `1px solid ${showEmailConfig ? '#BFDBFE' : '#E5E7EB'}`,
                        borderRadius: 8, fontSize: 12, fontWeight: 600, cursor: 'pointer', marginLeft: 'auto',
                      }}
                    >
                      {showEmailConfig ? 'Hide Setup ✕' : 'Configure Gmail Credentials ⚙️'}
                    </button>
                  </div>

                  {/* Gmail Credentials Panel */}
                  {showEmailConfig && (
                    <div style={{
                      marginTop: 20, padding: '18px 20px', background: '#F8FAFC',
                      border: '1px solid #E2E8F0', borderRadius: 10,
                      display: 'flex', flexDirection: 'column', gap: 14,
                    }}>
                      <div style={{ fontSize: 13, fontWeight: 700, color: '#1E293B', display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span>Gmail SMTP Credentials</span>
                        <span style={{ fontSize: 11, background: '#EFF6FF', color: '#2563EB', padding: '2px 8px', borderRadius: 12, fontWeight: 600 }}>
                          Required for Real Email
                        </span>
                      </div>

                      <div style={{ fontSize: 12, color: '#475569', lineHeight: 1.6, background: '#FFFFFF', padding: '10px 14px', borderRadius: 8, border: '1px solid #E2E8F0' }}>
                        💡 Go to <a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noreferrer" style={{ color: '#2563EB', fontWeight: 600 }}>myaccount.google.com/apppasswords</a>, create a 16-character App Password named <strong>"Nexus"</strong>, and enter it below. Use your Gmail address as the sender.
                      </div>

                      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                        <div>
                          <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: '#374151', marginBottom: 4 }}>
                            Sender Gmail Address
                          </label>
                          <input
                            type="email"
                            placeholder="your_email@gmail.com"
                            value={smtpSenderEmail}
                            onChange={(e) => setSmtpSenderEmail(e.target.value)}
                            style={{
                              width: '100%', height: 34, padding: '0 10px',
                              borderRadius: 6, border: '1px solid #CBD5E1',
                              fontSize: 12, outline: 'none',
                            }}
                          />
                        </div>
                        <div>
                          <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: '#374151', marginBottom: 4 }}>
                            Gmail App Password (16 characters)
                          </label>
                          <input
                            type="password"
                            placeholder="e.g. abcd efgh ijkl mnop"
                            value={smtpAppPassword}
                            onChange={(e) => setSmtpAppPassword(e.target.value)}
                            style={{
                              width: '100%', height: 34, padding: '0 10px',
                              borderRadius: 6, border: '1px solid #CBD5E1',
                              fontSize: 12, outline: 'none', fontFamily: 'monospace',
                            }}
                          />
                        </div>
                      </div>

                      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                        <button
                          type="button"
                          onClick={handleSaveAlerts}
                          disabled={savingAlerts}
                          style={{
                            height: 32, padding: '0 16px', background: '#059669',
                            color: '#FFFFFF', border: 'none', borderRadius: 6,
                            fontSize: 12, fontWeight: 600, cursor: 'pointer',
                          }}
                        >
                          {savingAlerts ? 'Saving...' : 'Save Gmail Credentials'}
                        </button>
                      </div>
                    </div>
                  )}
                </div>

                {/* Card 2: Email Dispatch History */}
                <div style={{
                  background: '#FFFFFF', border: '1px solid #E5E7EB',
                  borderRadius: 12, padding: '22px 24px',
                  boxShadow: '0 1px 2px rgba(0,0,0,0.02)',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                    <div>
                      <div style={{ fontSize: 15, fontWeight: 700, color: '#111827' }}>
                        Email Alert History
                      </div>
                      <div style={{ fontSize: 12, color: '#6B7280', marginTop: 2 }}>
                        Log of all email alerts dispatched for critical incidents.
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={handleRefreshAlertHistory}
                      disabled={loadingHistory}
                      style={{
                        height: 30, padding: '0 12px', background: '#F9FAFB',
                        border: '1px solid #E5E7EB', borderRadius: 6, fontSize: 12,
                        color: '#374151', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6,
                      }}
                    >
                      <RefreshCw size={12} className={loadingHistory ? 'animate-spin' : ''} />
                      <span>Refresh</span>
                    </button>
                  </div>

                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                      <thead>
                        <tr style={{ background: '#F9FAFB', borderBottom: '1px solid #E5E7EB', color: '#6B7280', textAlign: 'left' }}>
                          <th style={{ padding: '10px 14px' }}>TIME</th>
                          <th style={{ padding: '10px 14px' }}>TO EMAIL</th>
                          <th style={{ padding: '10px 14px' }}>PROCESS / TRIGGER</th>
                          <th style={{ padding: '10px 14px' }}>SEVERITY</th>
                          <th style={{ padding: '10px 14px' }}>STATUS</th>
                        </tr>
                      </thead>
                      <tbody>
                        {alertHistory.length === 0 ? (
                          <tr>
                            <td colSpan={5} style={{ padding: '28px', textAlign: 'center', color: '#9CA3AF' }}>
                              No alerts dispatched yet. Click "Send Test Email" to verify your configuration.
                            </td>
                          </tr>
                        ) : (
                          alertHistory.map((a) => {
                            const isDelivered = a.status === 'delivered'
                            const isCrit = a.severity === 'critical'
                            const dateStr = a.timestamp ? new Date(a.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '--'
                            return (
                              <tr key={a.id} style={{ borderBottom: '1px solid #F3F4F6' }}>
                                <td style={{ padding: '10px 14px', fontFamily: 'monospace', color: '#4B5563', whiteSpace: 'nowrap' }}>
                                  {dateStr}
                                </td>
                                <td style={{ padding: '10px 14px', color: '#111827', fontWeight: 500 }}>
                                  {a.target_email || '—'}
                                </td>
                                <td style={{ padding: '10px 14px', color: '#374151', fontWeight: 600 }}>
                                  {a.process_name}
                                </td>
                                <td style={{ padding: '10px 14px' }}>
                                  <span style={{
                                    fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 10,
                                    background: isCrit ? '#FEE2E2' : a.severity === 'test' ? '#ECFDF5' : '#FEF3C7',
                                    color: isCrit ? '#DC2626' : a.severity === 'test' ? '#059669' : '#D97706',
                                  }}>
                                    {a.severity?.toUpperCase()}
                                  </span>
                                </td>
                                <td style={{ padding: '10px 14px' }}>
                                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                    {isDelivered ? (
                                      <>
                                        <CheckCircle2 size={14} color="#059669" />
                                        <span style={{ color: '#059669', fontWeight: 600 }}>Email Delivered</span>
                                        <span style={{ color: '#6B7280', fontSize: 11 }}>({a.provider})</span>
                                      </>
                                    ) : (
                                      <>
                                        <AlertTriangle size={14} color="#D97706" />
                                        <span style={{ color: '#D97706', fontWeight: 600 }}>Not Configured</span>
                                        <span style={{ color: '#9CA3AF', fontSize: 11 }}>({a.provider})</span>
                                      </>
                                    )}
                                  </div>
                                </td>
                              </tr>
                            )
                          })
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}
            {/* ── TAB 4: AUDIT & REPORTS ───────────────────────────────────────── */}
            {activeTab === 'reports' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                {/* Diagnostic Report Export Card */}
                <div style={{
                  background: '#FFFFFF',
                  border: '1px solid #E5E7EB',
                  borderRadius: 12,
                  padding: '22px 24px',
                  boxShadow: '0 1px 2px rgba(0,0,0,0.02)',
                }}>
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    marginBottom: 16,
                  }}>
                    <div>
                      <div style={{ fontSize: 15, fontWeight: 700, color: '#111827' }}>
                        Diagnostic Audit Log Export
                      </div>
                      <div style={{ fontSize: 12, color: '#6B7280', marginTop: 2 }}>
                        Generate comprehensive diagnostic documents containing evaluated anomalies and action history.
                      </div>
                    </div>

                    <div style={{ display: 'flex', background: '#F3F4F6', borderRadius: 6, padding: 2 }}>
                      {(['markdown', 'json'] as const).map((fmt) => (
                        <button
                          key={fmt}
                          type="button"
                          onClick={() => setReportFormat(fmt)}
                          style={{
                            border: 'none',
                            background: reportFormat === fmt ? '#FFFFFF' : 'transparent',
                            color: reportFormat === fmt ? '#111827' : '#6B7280',
                            fontSize: 11,
                            fontWeight: reportFormat === fmt ? 600 : 400,
                            padding: '3px 10px',
                            borderRadius: 4,
                            cursor: 'pointer',
                          }}
                        >
                          {fmt.toUpperCase()}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div style={{
                    paddingTop: 16,
                    borderTop: '1px solid #F3F4F6',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    flexWrap: 'wrap',
                    gap: 12,
                  }}>
                    <p style={{ margin: 0, fontSize: 12, color: '#6B7280', maxWidth: 450 }}>
                      Exports a full JSON or Markdown report querying live database incidents, safety policies, and telemetry.
                    </p>

                    <button
                      type="button"
                      onClick={handleGenerateReport}
                      disabled={exportingReport}
                      style={{
                        height: 34,
                        padding: '0 16px',
                        background: '#111827',
                        color: '#FFFFFF',
                        border: 'none',
                        borderRadius: 8,
                        fontSize: 12,
                        fontWeight: 600,
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                      }}
                    >
                      <Download size={13} />
                      <span>{exportingReport ? 'Generating...' : `Export ${reportFormat.toUpperCase()}`}</span>
                    </button>
                  </div>
                </div>

                {/* SOC2 Compliance PDF */}
                <div style={{
                  background: '#FFFFFF',
                  border: '1px solid #E5E7EB',
                  borderRadius: 12,
                  padding: '22px 24px',
                  boxShadow: '0 1px 2px rgba(0,0,0,0.02)',
                }}>
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    marginBottom: 16,
                  }}>
                    <div>
                      <div style={{ fontSize: 15, fontWeight: 700, color: '#111827' }}>
                        Executive SOC2 Compliance Report
                      </div>
                      <div style={{ fontSize: 12, color: '#6B7280', marginTop: 2 }}>
                        Formatted audit document with SHA-256 cryptographic verification for compliance reviews.
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={() => setShowPdfModal(true)}
                      style={{
                        height: 34,
                        padding: '0 16px',
                        background: '#FFFFFF',
                        color: '#2563EB',
                        border: '1px solid #BFDBFE',
                        borderRadius: 8,
                        fontSize: 12,
                        fontWeight: 600,
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                      }}
                    >
                      <FileText size={13} />
                      <span>Preview & Export PDF</span>
                    </button>
                  </div>

                  <p style={{ margin: 0, fontSize: 12, color: '#6B7280', paddingTop: 16, borderTop: '1px solid #F3F4F6' }}>
                    Compiles operator logs, detected anomalies, verification deltas, and maintenance window audit trail into a print-ready PDF.
                  </p>
                </div>
              </div>
            )}

            {/* ── TAB 5: EMERGENCY KILL SWITCH ──────────────────────────────────── */}
            {activeTab === 'emergency' && (
              <div style={{
                background: emergencyStopActive ? '#FEF2F2' : '#FFFFFF',
                border: emergencyStopActive ? '1px solid #FCA5A5' : '1px solid #FEE2E2',
                borderRadius: 12,
                padding: '24px 26px',
                boxShadow: '0 1px 2px rgba(0,0,0,0.02)',
              }}>
                <div style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  justifyContent: 'space-between',
                  gap: 16,
                  marginBottom: 16,
                }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
                    <AlertTriangle size={24} color="#DC2626" style={{ flexShrink: 0, marginTop: 2 }} />
                    <div>
                      <div style={{ fontSize: 16, fontWeight: 700, color: '#991B1B' }}>
                        Guardian Emergency Kill Switch
                      </div>
                      <p style={{ margin: '4px 0 0', fontSize: 12, color: '#7F1D1D', lineHeight: 1.5 }}>
                        Instantly freezes all autonomous mitigation and healing operations system-wide.
                        Use this if an intervention loop causes unexpected application behavior.
                      </p>
                    </div>
                  </div>

                  <span style={{
                    fontSize: 11,
                    fontWeight: 700,
                    padding: '3px 10px',
                    borderRadius: 12,
                    background: emergencyStopActive ? '#DC2626' : '#F3F4F6',
                    color: emergencyStopActive ? '#FFFFFF' : '#4B5563',
                  }}>
                    {emergencyStopActive ? '● STOP ENGAGED' : '● System Ready'}
                  </span>
                </div>

                <div style={{
                  paddingTop: 16,
                  borderTop: '1px solid #FECACA',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  flexWrap: 'wrap',
                  gap: 12,
                }}>
                  <div style={{ fontSize: 12, color: '#991B1B' }}>
                    {emergencyStopActive
                      ? `Reason: ${emergencyReason || 'Triggered by operator via Settings'}`
                      : 'Emergency stop is currently clear. Interventions follow normal simulation/live rules.'}
                  </div>

                  <button
                    type="button"
                    onClick={handleToggleEmergencyStop}
                    disabled={togglingEmergency}
                    style={{
                      height: 34,
                      padding: '0 18px',
                      background: emergencyStopActive ? '#10B981' : '#DC2626',
                      color: '#FFFFFF',
                      border: 'none',
                      borderRadius: 8,
                      fontSize: 12,
                      fontWeight: 600,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
                    }}
                  >
                    {emergencyStopActive ? 'Resume Automated Healing' : 'Trigger Emergency Stop Now'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* PDF Modal */}
      {showPdfModal && <PdfReportModal isOpen={showPdfModal} onClose={() => setShowPdfModal(false)} />}
    </div>
  )
}
