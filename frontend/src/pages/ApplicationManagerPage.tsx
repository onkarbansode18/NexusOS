import React, { useState, useEffect } from 'react'
import {
  Layers,
  Gamepad2,
  BookOpen,
  Video,
  BatteryCharging,
  Shield,
  ShieldAlert,
  ShieldCheck,
  RefreshCw,
  Play,
  CheckCircle2,
  AlertTriangle,
  Sliders,
  Cpu,
  Search,
  Check,
  X,
  ExternalLink,
  ChevronRight,
  Sparkles,
  Info,
} from 'lucide-react'
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Cell,
  PieChart,
  Pie,
} from 'recharts'
import { api } from '../api/client'
import { useNexusStore } from '../store'
import {
  ApplicationItem,
  ApplicationProfile,
  OperatingModeInfo,
  OperatingModeCardItem,
  OptimizationRecommendation,
  OptimizationHistoryItem,
  OptimizerStatus,
} from '../types'

function buildApplicationsFromProcesses(processes: import('../types').ProcessSnapshot[]): ApplicationItem[] {
  const grouped: Record<string, ApplicationItem> = {}
  for (const p of processes) {
    const rawName = p.name.replace(/\.exe$/i, '')
    const appName = rawName.charAt(0).toUpperCase() + rawName.slice(1)
    const appId = `app_${rawName.toLowerCase().replace(/[^a-z0-9]/g, '_')}`
    if (!grouped[appId]) {
      const isSys = ['svchost', 'system', 'csrss', 'dwm', 'lsass', 'services', 'explorer'].includes(rawName.toLowerCase())
      const isBrowser = ['chrome', 'msedge', 'firefox', 'brave', 'opera'].includes(rawName.toLowerCase())
      const isDev = ['code', 'node', 'python', 'git', 'vite', 'uvicorn', 'cmd', 'powershell'].includes(rawName.toLowerCase())
      const isMedia = ['spotify', 'vlc', 'discord', 'telegram'].includes(rawName.toLowerCase())
      const cat = isSys ? 'System' : (isBrowser ? 'Browsing' : (isDev ? 'Development' : (isMedia ? 'Media' : 'Background Utilities')))

      grouped[appId] = {
        app_id: appId,
        name: appName,
        category: cat,
        executable_path: p.cmdline || p.name,
        root_pid: p.pid,
        pids: [p.pid],
        process_count: 1,
        processes: [{
          pid: p.pid,
          ppid: null,
          name: p.name,
          exe: p.cmdline || null,
          cmdline: p.cmdline ? [p.cmdline] : null,
          cpu_percent: p.cpu_percent,
          memory_mb: p.memory_mb,
          memory_percent: p.memory_percent,
          num_threads: p.threads || 1,
          status: p.status,
          created_at: p.created_at,
          priority: 'NORMAL',
          read_bytes: null,
          write_bytes: null,
        }],
        total_cpu_percent: p.cpu_percent,
        total_memory_mb: p.memory_mb,
        total_memory_percent: p.memory_percent,
        total_threads: p.threads || 1,
        is_system: isSys,
        is_protected: isSys,
        importance: isSys ? 'Critical' : 'Normal',
        status: 'active',
        started_at: p.created_at || '',
        user_classified: false,
      }
    } else {
      const cur = grouped[appId]
      cur.pids.push(p.pid)
      cur.process_count += 1
      cur.total_cpu_percent = +(cur.total_cpu_percent + p.cpu_percent).toFixed(1)
      cur.total_memory_mb = +(cur.total_memory_mb + p.memory_mb).toFixed(1)
      cur.total_memory_percent = +(cur.total_memory_percent + p.memory_percent).toFixed(1)
      cur.total_threads += (p.threads || 1)
    }
  }
  return Object.values(grouped).sort((a, b) => b.total_cpu_percent - a.total_cpu_percent)
}

export function ApplicationManagerPage() {
  const [activeTab, setActiveTab] = useState<'applications' | 'modes' | 'optimizer' | 'history'>('applications')
  const [loading, setLoading] = useState<boolean>(true)
  const [analyzing, setAnalyzing] = useState<boolean>(false)
  const [notification, setNotification] = useState<string | null>(null)

  // Immediate initial state: if store already has live processes, populate instantly on frame 0!
  const [applications, setApplications] = useState<ApplicationItem[]>(() => {
    const procs = useNexusStore.getState().processes
    if (procs && procs.length > 0) {
      return buildApplicationsFromProcesses(procs)
    }
    return []
  })
  const [profiles, setProfiles] = useState<ApplicationProfile[]>([])
  const [activeMode, setActiveMode] = useState<OperatingModeInfo | null>(null)
  const [availableModes, setAvailableModes] = useState<OperatingModeCardItem[]>([])
  const [optimizerStatus, setOptimizerStatus] = useState<OptimizerStatus | null>(null)
  const [recommendations, setRecommendations] = useState<OptimizationRecommendation[]>([])
  const [history, setHistory] = useState<OptimizationHistoryItem[]>([])

  // Search and Category filters
  const [searchTerm, setSearchTerm] = useState<string>('')
  const [categoryFilter, setCategoryFilter] = useState<string>('All')

  // Selected application for detail drawer
  const [selectedApp, setSelectedApp] = useState<ApplicationItem | null>(null)
  const [drawerOpen, setDrawerOpen] = useState<boolean>(false)

  // Profile edit state inside drawer
  const [editImportance, setEditImportance] = useState<string>('Normal')
  const [editProtected, setEditProtected] = useState<boolean>(false)
  const [savingProfile, setSavingProfile] = useState<boolean>(false)

  const { processes, loadProcesses } = useNexusStore()

  // Real-time synchronization: if applications is empty, immediately populate from live processes
  useEffect(() => {
    if (applications.length === 0 && processes && processes.length > 0) {
      setApplications(buildApplicationsFromProcesses(processes))
    }
  }, [processes, applications.length])

  useEffect(() => {
    // On mount, also trigger a fresh process load so we have the most current list
    loadProcesses().then(() => {
      const liveProcs = useNexusStore.getState().processes
      if (liveProcs && liveProcs.length > 0) {
        setApplications(buildApplicationsFromProcesses(liveProcs))
      }
    }).catch(() => {})

    fetchAllData(false)

    // Automatically fetch and update live applications every 3 seconds
    const timer = setInterval(() => {
      fetchAllData(true)
    }, 3000)

    // Auto-run initial optimization analysis in the background if recommendations not yet populated
    const autoAnalyzeTimer = setTimeout(() => {
      api.analyzeAndOptimize()
        .then((res) => {
          if (res?.recommendations) setRecommendations(res.recommendations)
        })
        .catch(() => {})
    }, 1000)

    return () => {
      clearInterval(timer)
      clearTimeout(autoAnalyzeTimer)
    }
  }, [])

  const fetchAllData = async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const [appsRes, modesRes, optStatus, recs, hist, profs] = await Promise.all([
        api.fetchApplications().catch(() => ({ applications: [] as ApplicationItem[] })),
        api.fetchOperatingModes().catch(() => ({ active_mode: null as any, available_modes: [] })),
        api.fetchOptimizerStatus().catch(() => null),
        api.fetchOptimizerRecommendations().catch(() => []),
        api.fetchOptimizerHistory(50).catch(() => []),
        api.fetchApplicationProfiles().catch(() => []),
      ])

      if (appsRes?.applications && appsRes.applications.length > 0) {
        setApplications(appsRes.applications)
      } else {
        // Fallback: build from live processes in the store
        const liveProcs = useNexusStore.getState().processes
        if (liveProcs && liveProcs.length > 0) {
          setApplications(buildApplicationsFromProcesses(liveProcs))
        }
      }

      if (modesRes?.active_mode) setActiveMode(modesRes.active_mode)
      if (modesRes?.available_modes) setAvailableModes(modesRes.available_modes)
      if (optStatus) setOptimizerStatus(optStatus)
      if (recs && recs.length > 0) setRecommendations(recs)
      if (hist) setHistory(hist)
      if (profs) setProfiles(profs)
    } catch (err: any) {
      console.error(err)
      // Even on error, ensure we show something from live processes
      const liveProcs = useNexusStore.getState().processes
      if (liveProcs && liveProcs.length > 0) {
        setApplications(buildApplicationsFromProcesses(liveProcs))
      }
    } finally {
      if (!silent) setLoading(false)
    }
  }

  const showNotice = (msg: string) => {
    setNotification(msg)
    setTimeout(() => setNotification(null), 4000)
  }

  // ── Mode Actions ───────────────────────────────────────────────────────────

  const handleActivateMode = async (modeId: string) => {
    try {
      const res = await api.activateOperatingMode(modeId)
      setActiveMode(res.active_mode)
      showNotice(`Activated ${res.active_mode.name}`)
      fetchAllData()
    } catch (err: any) {
      showNotice(`Error activating mode: ${err.message}`)
    }
  }

  const handleDeactivateMode = async () => {
    try {
      const res = await api.deactivateOperatingMode()
      setActiveMode(res.active_mode)
      showNotice('Deactivated operating mode. Restored priorities.')
      fetchAllData()
    } catch (err: any) {
      showNotice(`Error: ${err.message}`)
    }
  }

  // ── Optimizer Actions ──────────────────────────────────────────────────────

  const handleAnalyzeNow = async () => {
    if (analyzing) return
    setAnalyzing(true)
    try {
      const res = await api.analyzeAndOptimize()
      if (res?.recommendations) setRecommendations(res.recommendations)
      showNotice(`Analysis complete: ${res.total_items ?? 0} candidates evaluated.`)
      fetchAllData(true)
    } catch (err: any) {
      showNotice(`Analysis error: ${err.message}`)
    } finally {
      setAnalyzing(false)
    }
  }

  const handleEmergencyStop = async () => {
    try {
      const res = await api.emergencyStopOptimizer()
      showNotice(res.message)
      fetchAllData()
    } catch (err: any) {
      showNotice(`Emergency stop error: ${err.message}`)
    }
  }

  const handleApproveRecommendation = async (planItemId: string) => {
    try {
      await api.approveOptimizerRecommendation(planItemId)
      showNotice('Optimization action approved and dispatched.')
      fetchAllData()
    } catch (err: any) {
      showNotice(`Approval error: ${err.message}`)
    }
  }

  const handleRejectRecommendation = async (planItemId: string) => {
    try {
      await api.rejectOptimizerRecommendation(planItemId)
      showNotice('Recommendation dismissed.')
      fetchAllData()
    } catch (err: any) {
      showNotice(`Rejection error: ${err.message}`)
    }
  }

  const handleStrategyChange = async (strategy: string) => {
    try {
      await api.setOptimizerStrategy(strategy)
      showNotice(`Optimizer policy set to: ${strategy}`)
      fetchAllData()
    } catch (err: any) {
      showNotice(`Error: ${err.message}`)
    }
  }

  // ── Profile / Detail Drawer Actions ────────────────────────────────────────

  const openAppDrawer = (app: ApplicationItem) => {
    setSelectedApp(app)
    setEditImportance(app.importance || 'Normal')
    setEditProtected(app.is_protected || false)
    setDrawerOpen(true)
  }

  const handleSaveProfile = async () => {
    if (!selectedApp) return
    setSavingProfile(true)
    try {
      await api.saveApplicationProfile({
        app_id: selectedApp.app_id,
        name: selectedApp.name,
        executable_path: selectedApp.executable_path || undefined,
        category: selectedApp.category,
        importance: editImportance,
        is_protected: editProtected,
        preferred_priority: 'NORMAL',
      })
      showNotice(`Profile for ${selectedApp.name} saved successfully.`)
      fetchAllData()
      setDrawerOpen(false)
    } catch (err: any) {
      showNotice(`Save error: ${err.message}`)
    } finally {
      setSavingProfile(false)
    }
  }

  const handleToggleProtection = async (app: ApplicationItem) => {
    const newProt = !app.is_protected
    try {
      await api.saveApplicationProfile({
        app_id: app.app_id,
        name: app.name,
        executable_path: app.executable_path || undefined,
        category: app.category,
        importance: app.importance || 'Normal',
        is_protected: newProt,
      })
      showNotice(`${app.name} is now ${newProt ? 'Protected' : 'Unprotected'}`)
      fetchAllData()
    } catch (err: any) {
      showNotice(`Error: ${err.message}`)
    }
  }

  const handleCategoryChange = async (appId: string, category: string) => {
    try {
      await api.updateApplicationCategory(appId, category)
      showNotice('Category updated successfully.')
      fetchAllData()
    } catch (err: any) {
      showNotice(`Error updating category: ${err.message}`)
    }
  }

  // ── Filtered Applications ──────────────────────────────────────────────────

  const filteredApps = applications.filter((app) => {
    const matchesSearch =
      app.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (app.executable_path && app.executable_path.toLowerCase().includes(searchTerm.toLowerCase()))
    const matchesCat = categoryFilter === 'All' || app.category === categoryFilter
    return matchesSearch && matchesCat
  })

  const categories = [
    'All',
    'Gaming',
    'Development',
    'Browsing',
    'Communication',
    'Education',
    'Media',
    'System',
    'Background Utilities',
  ]

  // Chart data: Distribution of CPU by Category
  const catUsageMap: Record<string, { cpu: number; ram: number }> = {}
  applications.forEach((a) => {
    if (!catUsageMap[a.category]) catUsageMap[a.category] = { cpu: 0, ram: 0 }
    catUsageMap[a.category].cpu += a.total_cpu_percent
    catUsageMap[a.category].ram += a.total_memory_mb
  })
  const categoryChartData = Object.entries(catUsageMap).map(([cat, val]) => ({
    name: cat,
    cpu: Math.round(val.cpu * 10) / 10,
    ram: Math.round(val.ram),
  }))

  const getImportanceBadge = (imp?: string) => {
    switch (imp) {
      case 'Critical': return { bg: '#FEE2E2', text: '#991B1B' }
      case 'High': return { bg: '#FEF3C7', text: '#92400E' }
      case 'Normal': return { bg: '#DEF7EC', text: '#03543F' }
      case 'Low': return { bg: '#EFF6FF', text: '#1E40AF' }
      case 'Background': return { bg: '#F3F4F6', text: '#4B5563' }
      default: return { bg: '#DEF7EC', text: '#03543F' }
    }
  }

  const getActionBadgeColor = (action: string) => {
    switch (action.toLowerCase()) {
      case 'renice': return { bg: '#DEF7EC', text: '#03543F' }
      case 'throttle': return { bg: '#FEF3C7', text: '#92400E' }
      case 'restore_priority': return { bg: '#EFF6FF', text: '#1E40AF' }
      default: return { bg: '#F3F4F6', text: '#374151' }
    }
  }

  return (
    <div style={{ padding: '24px 32px', maxWidth: 1280, margin: '0 auto', color: '#111827' }}>
      {/* ── Page Header ──────────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ background: '#2B5FC7', padding: '8px 9px', borderRadius: 8, display: 'flex', alignItems: 'center' }}>
            <Layers size={22} color="#FFFFFF" />
          </div>
          <div>
            <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, letterSpacing: '-0.02em' }}>
              Application Manager
            </h1>
            <p style={{ margin: 0, fontSize: 13, color: '#6B7280' }}>
              Application-Aware Resource Optimization & Operating Mode Guardian
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button
            onClick={handleEmergencyStop}
            style={{
              background: '#B42318',
              color: '#FFFFFF',
              border: 'none',
              borderRadius: 6,
              padding: '7px 14px',
              fontSize: 13,
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <ShieldAlert size={15} />
            Emergency Stop
          </button>

          <button
            onClick={handleAnalyzeNow}
            disabled={analyzing}
            style={{
              background: '#2B5FC7',
              color: '#FFFFFF',
              border: 'none',
              borderRadius: 6,
              padding: '7px 14px',
              fontSize: 13,
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <Sparkles size={15} />
            {analyzing ? 'Analyzing...' : 'Analyze Now'}
          </button>

          <button
            onClick={() => fetchAllData(false)}
            style={{
              background: '#FFFFFF',
              color: '#374151',
              border: '1px solid #D1D5DB',
              borderRadius: 6,
              padding: '7px 12px',
              fontSize: 13,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {/* Notification toast */}
      {notification && (
        <div
          style={{
            background: '#1E7F4F',
            color: '#FFFFFF',
            padding: '10px 16px',
            borderRadius: 8,
            marginBottom: 16,
            fontSize: 13,
            fontWeight: 500,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          <CheckCircle2 size={16} />
          {notification}
        </div>
      )}

      {/* ── KPI Summary Cards ─────────────────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 20 }}>
        <div style={{ background: '#FFFFFF', border: '1px solid #E5E7EB', borderRadius: 10, padding: 18 }}>
          <div style={{ fontSize: 12, fontWeight: 500, color: '#6B7280', marginBottom: 4 }}>Total Applications</div>
          <div style={{ fontSize: 26, fontWeight: 700, color: '#111827' }}>{applications.length}</div>
          <div style={{ fontSize: 12, color: '#1E7F4F', marginTop: 4 }}>
            {applications.reduce((acc, a) => acc + a.process_count, 0)} total child processes
          </div>
        </div>

        <div style={{ background: '#FFFFFF', border: '1px solid #E5E7EB', borderRadius: 10, padding: 18 }}>
          <div style={{ fontSize: 12, fontWeight: 500, color: '#6B7280', marginBottom: 4 }}>Protected Applications</div>
          <div style={{ fontSize: 26, fontWeight: 700, color: '#111827' }}>
            {applications.filter((a) => a.is_protected || a.is_system).length}
          </div>
          <div style={{ fontSize: 12, color: '#6B7280', marginTop: 4 }}>
            {applications.filter((a) => a.is_system).length} OS Core Services
          </div>
        </div>

        <div style={{ background: '#FFFFFF', border: '1px solid #E5E7EB', borderRadius: 10, padding: 18 }}>
          <div style={{ fontSize: 12, fontWeight: 500, color: '#6B7280', marginBottom: 4 }}>Active Operating Mode</div>
          <div style={{ fontSize: 18, fontWeight: 700, color: activeMode?.is_active ? '#2B5FC7' : '#111827', marginTop: 4 }}>
            {activeMode?.name || 'Standard / Balanced'}
          </div>
          <div style={{ fontSize: 12, color: '#6B7280', marginTop: 6 }}>
            {activeMode?.battery?.status_text || 'AC Power'}
          </div>
        </div>

        <div style={{ background: '#FFFFFF', border: '1px solid #E5E7EB', borderRadius: 10, padding: 18 }}>
          <div style={{ fontSize: 12, fontWeight: 500, color: '#6B7280', marginBottom: 4 }}>Pending Recommendations</div>
          <div style={{ fontSize: 26, fontWeight: 700, color: recommendations.length > 0 ? '#9A5B00' : '#1E7F4F' }}>
            {recommendations.length}
          </div>
          <div style={{ fontSize: 12, color: '#6B7280', marginTop: 4 }}>
            Strategy: <span style={{ textTransform: 'capitalize', fontWeight: 600 }}>{optimizerStatus?.strategy?.replace('_', ' ') || 'Recommendation'}</span>
          </div>
        </div>
      </div>

      {/* ── Tabs Navigation ──────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 20, borderBottom: '1px solid #E5E7EB', paddingBottom: 10 }}>
        {[
          { key: 'applications', label: 'Detected Applications', icon: Layers },
          { key: 'modes', label: 'Operating Modes', icon: Sliders },
          { key: 'optimizer', label: `Optimization Panel (${recommendations.length})`, icon: Sparkles },
          { key: 'history', label: 'Audit History', icon: RefreshCw },
        ].map((t) => {
          const Icon = t.icon
          const isActive = activeTab === t.key
          return (
            <button
              key={t.key}
              onClick={() => setActiveTab(t.key as any)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '8px 16px',
                borderRadius: 6,
                fontSize: 13,
                fontWeight: isActive ? 600 : 500,
                border: 'none',
                background: isActive ? '#2B5FC7' : 'transparent',
                color: isActive ? '#FFFFFF' : '#4B5563',
                cursor: 'pointer',
              }}
            >
              <Icon size={15} />
              {t.label}
            </button>
          )
        })}
      </div>

      {/* ── TAB 1: APPLICATIONS LIST ─────────────────────────────────────────── */}
      {activeTab === 'applications' && (
        <div>
          {/* Controls bar */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1, maxWidth: 360 }}>
              <div style={{ position: 'relative', width: '100%' }}>
                <Search size={15} color="#9CA3AF" style={{ position: 'absolute', left: 10, top: 10 }} />
                <input
                  type="text"
                  placeholder="Search applications or executables..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '8px 10px 8px 32px',
                    borderRadius: 6,
                    border: '1px solid #D1D5DB',
                    fontSize: 13,
                    outline: 'none',
                  }}
                />
              </div>
            </div>

            {/* Category filter pills */}
            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
              {categories.map((cat) => (
                <button
                  key={cat}
                  onClick={() => setCategoryFilter(cat)}
                  style={{
                    border: 'none',
                    borderRadius: 20,
                    padding: '4px 12px',
                    fontSize: 12,
                    fontWeight: 500,
                    background: categoryFilter === cat ? '#2B5FC7' : '#F3F4F6',
                    color: categoryFilter === cat ? '#FFFFFF' : '#4B5563',
                    cursor: 'pointer',
                  }}
                >
                  {cat}
                </button>
              ))}
            </div>
          </div>

          {/* Applications Table */}
          <div style={{ background: '#FFFFFF', border: '1px solid #E5E7EB', borderRadius: 10, overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: 13 }}>
              <thead>
                <tr style={{ background: '#F9FAFB', borderBottom: '1px solid #E5E7EB', color: '#6B7280', fontSize: 12, fontWeight: 600 }}>
                  <th style={{ padding: '12px 16px' }}>APPLICATION</th>
                  <th style={{ padding: '12px 16px' }}>CATEGORY</th>
                  <th style={{ padding: '12px 16px' }}>IMPORTANCE</th>
                  <th style={{ padding: '12px 16px' }}>CPU</th>
                  <th style={{ padding: '12px 16px' }}>MEMORY</th>
                  <th style={{ padding: '12px 16px' }}>PROTECTION</th>
                  <th style={{ padding: '12px 16px', textAlign: 'right' }}>ACTIONS</th>
                </tr>
              </thead>
              <tbody>
                {filteredApps.length === 0 ? (
                  <tr>
                    <td colSpan={7} style={{ padding: 32, textAlign: 'center', color: '#6B7280' }}>
                      No applications match the current search or filter.
                    </td>
                  </tr>
                ) : (
                  filteredApps.map((app) => {
                    const impBadge = getImportanceBadge(app.importance)
                    return (
                      <tr
                        key={app.app_id}
                        style={{ borderBottom: '1px solid #F3F4F6', transition: 'background 0.15s' }}
                        onMouseEnter={(e) => (e.currentTarget.style.background = '#F9FAFB')}
                        onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                      >
                        <td style={{ padding: '12px 16px' }}>
                          <div style={{ fontWeight: 600, color: '#111827' }}>{app.name}</div>
                          <div style={{ fontSize: 11, color: '#9CA3AF', fontFamily: 'monospace', maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {app.executable_path || `PID ${app.root_pid}`}
                          </div>
                        </td>

                        <td style={{ padding: '12px 16px' }}>
                          <select
                            value={app.category}
                            onChange={(e) => handleCategoryChange(app.app_id, e.target.value)}
                            style={{
                              padding: '3px 8px',
                              borderRadius: 6,
                              fontSize: 12,
                              border: '1px solid #E5E7EB',
                              background: '#F9FAFB',
                              fontWeight: 500,
                              cursor: 'pointer',
                            }}
                          >
                            {categories.filter((c) => c !== 'All').map((c) => (
                              <option key={c} value={c}>{c}</option>
                            ))}
                          </select>
                        </td>

                        <td style={{ padding: '12px 16px' }}>
                          <span
                            style={{
                              background: impBadge.bg,
                              color: impBadge.text,
                              padding: '3px 8px',
                              borderRadius: 6,
                              fontSize: 11,
                              fontWeight: 600,
                            }}
                          >
                            {app.importance || 'Normal'}
                          </span>
                        </td>

                        <td style={{ padding: '12px 16px', fontFamily: 'IBM Plex Mono, monospace', fontWeight: 600 }}>
                          <span style={{ color: app.total_cpu_percent > 20 ? '#B42318' : '#111827' }}>
                            {app.total_cpu_percent}%
                          </span>
                        </td>

                        <td style={{ padding: '12px 16px', fontFamily: 'IBM Plex Mono, monospace' }}>
                          <div>{app.total_memory_mb} MB</div>
                          <div style={{ fontSize: 11, color: '#9CA3AF' }}>{app.total_memory_percent}% RAM</div>
                        </td>

                        <td style={{ padding: '12px 16px' }}>
                          <button
                            onClick={() => handleToggleProtection(app)}
                            disabled={app.is_system}
                            style={{
                              border: 'none',
                              background: 'transparent',
                              cursor: app.is_system ? 'not-allowed' : 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              gap: 6,
                              color: app.is_protected || app.is_system ? '#1E7F4F' : '#9CA3AF',
                              fontSize: 12,
                              fontWeight: 500,
                            }}
                          >
                            {app.is_protected || app.is_system ? <ShieldCheck size={16} /> : <Shield size={16} />}
                            {app.is_system ? 'System' : app.is_protected ? 'Protected' : 'Standard'}
                          </button>
                        </td>

                        <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                          <button
                            onClick={() => openAppDrawer(app)}
                            style={{
                              background: '#FFFFFF',
                              color: '#2B5FC7',
                              border: '1px solid #D1D5DB',
                              borderRadius: 6,
                              padding: '5px 10px',
                              fontSize: 12,
                              fontWeight: 600,
                              cursor: 'pointer',
                            }}
                          >
                            Inspect
                          </button>
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── TAB 2: OPERATING MODES ────────────────────────────────────────────── */}
      {activeTab === 'modes' && (
        <div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 18 }}>
            {availableModes.map((m) => {
              const isCurrent = activeMode?.is_active && activeMode?.mode_id === m.id
              let ModeIcon = Gamepad2
              if (m.id === 'study') ModeIcon = BookOpen
              if (m.id === 'meeting') ModeIcon = Video
              if (m.id === 'battery_saver') ModeIcon = BatteryCharging

              return (
                <div
                  key={m.id}
                  style={{
                    background: '#FFFFFF',
                    border: isCurrent ? '2px solid #2B5FC7' : '1px solid #E5E7EB',
                    borderRadius: 10,
                    padding: 20,
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                    boxShadow: isCurrent ? '0 4px 12px rgba(43, 95, 199, 0.12)' : '0 1px 3px rgba(0,0,0,0.05)',
                  }}
                >
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <div
                          style={{
                            background: isCurrent ? '#2B5FC7' : '#F3F4F6',
                            color: isCurrent ? '#FFFFFF' : '#374151',
                            padding: '8px 9px',
                            borderRadius: 8,
                            display: 'flex',
                            alignItems: 'center',
                          }}
                        >
                          <ModeIcon size={20} />
                        </div>
                        <div>
                          <div style={{ fontSize: 16, fontWeight: 700 }}>{m.name}</div>
                          {isCurrent && (
                            <span style={{ fontSize: 11, fontWeight: 700, color: '#1E7F4F' }}>
                              ● ACTIVE NOW
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    <p style={{ fontSize: 13, color: '#4B5563', lineHeight: 1.5, margin: '0 0 14px' }}>
                      {m.description}
                    </p>

                    <div style={{ marginBottom: 12 }}>
                      <div style={{ fontSize: 11, fontWeight: 600, color: '#6B7280', marginBottom: 6 }}>
                        PROTECTED CATEGORIES
                      </div>
                      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                        {m.protected_categories?.map((c) => (
                          <span
                            key={c}
                            style={{
                              background: '#EFF6FF',
                              color: '#1E40AF',
                              padding: '2px 8px',
                              borderRadius: 4,
                              fontSize: 11,
                              fontWeight: 500,
                            }}
                          >
                            {c}
                          </span>
                        ))}
                      </div>
                    </div>

                    {m.protected_apps && m.protected_apps.length > 0 && (
                      <div style={{ marginBottom: 16 }}>
                        <div style={{ fontSize: 11, fontWeight: 600, color: '#6B7280', marginBottom: 6 }}>
                          PROTECTED APPS
                        </div>
                        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                          {m.protected_apps.map((app) => (
                            <span
                              key={app}
                              style={{
                                background: '#DEF7EC',
                                color: '#03543F',
                                padding: '2px 8px',
                                borderRadius: 4,
                                fontSize: 11,
                                fontFamily: 'monospace',
                              }}
                            >
                              {app}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  <div style={{ display: 'flex', gap: 10, marginTop: 14 }}>
                    {isCurrent ? (
                      <button
                        onClick={handleDeactivateMode}
                        style={{
                          flex: 1,
                          background: '#FFFFFF',
                          color: '#B42318',
                          border: '1px solid #B42318',
                          borderRadius: 6,
                          padding: '8px 14px',
                          fontSize: 13,
                          fontWeight: 600,
                          cursor: 'pointer',
                        }}
                      >
                        Deactivate Mode
                      </button>
                    ) : (
                      <button
                        onClick={() => handleActivateMode(m.id)}
                        style={{
                          flex: 1,
                          background: '#2B5FC7',
                          color: '#FFFFFF',
                          border: 'none',
                          borderRadius: 6,
                          padding: '8px 14px',
                          fontSize: 13,
                          fontWeight: 600,
                          cursor: 'pointer',
                        }}
                      >
                        Activate {m.name}
                      </button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* ── TAB 3: SMART OPTIMIZER PANEL ────────────────────────────────────── */}
      {activeTab === 'optimizer' && (
        <div>
          {/* Optimizer controls banner */}
          <div
            style={{
              background: '#FFFFFF',
              border: '1px solid #E5E7EB',
              borderRadius: 10,
              padding: 18,
              marginBottom: 18,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <div>
              <div style={{ fontSize: 14, fontWeight: 700 }}>Autonomous Optimization Controls</div>
              <div style={{ fontSize: 12, color: '#6B7280' }}>
                Mode directives analyze background contention and lower CPU scheduling priorities safely.
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
                <span style={{ color: '#6B7280' }}>Execution Strategy:</span>
                <select
                  value={optimizerStatus?.strategy || 'recommendation_only'}
                  onChange={(e) => handleStrategyChange(e.target.value)}
                  style={{
                    padding: '6px 10px',
                    borderRadius: 6,
                    border: '1px solid #D1D5DB',
                    fontSize: 13,
                    fontWeight: 600,
                    background: '#FFFFFF',
                  }}
                >
                  <option value="recommendation_only">Recommendation Only</option>
                  <option value="manual_approval">Manual Approval</option>
                  <option value="autonomous">Autonomous (Auto-Execute Low Risk)</option>
                </select>
              </div>

              {optimizerStatus?.is_enabled ? (
                <button
                  onClick={async () => {
                    await api.disableOptimizer()
                    fetchAllData()
                  }}
                  style={{
                    background: '#FFFFFF',
                    color: '#B42318',
                    border: '1px solid #D1D5DB',
                    borderRadius: 6,
                    padding: '6px 12px',
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  Disable Optimizer
                </button>
              ) : (
                <button
                  onClick={async () => {
                    await api.enableOptimizer()
                    fetchAllData()
                  }}
                  style={{
                    background: '#1E7F4F',
                    color: '#FFFFFF',
                    border: 'none',
                    borderRadius: 6,
                    padding: '6px 12px',
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  Enable Optimizer
                </button>
              )}
            </div>
          </div>

          {/* Recommendations List */}
          <div style={{ background: '#FFFFFF', border: '1px solid #E5E7EB', borderRadius: 10, padding: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <div style={{ fontSize: 15, fontWeight: 700 }}>
                Active Recommendations ({recommendations.length})
              </div>
              <div style={{ fontSize: 12, color: '#6B7280' }}>
                All actions validated against OS and Nexus Blacklist
              </div>
            </div>

            {recommendations.length === 0 ? (
              <div style={{ padding: '36px 20px', textAlign: 'center', color: '#6B7280' }}>
                <CheckCircle2 size={32} color="#1E7F4F" style={{ margin: '0 auto 10px' }} />
                <div style={{ fontWeight: 600, fontSize: 14, color: '#111827' }}>No optimization intervention needed</div>
                <div style={{ fontSize: 12, marginTop: 4 }}>
                  System resource allocations are balanced with no contending background processes.
                </div>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {recommendations.map((rec) => {
                  const actBadge = getActionBadgeColor(rec.proposed_action)
                  return (
                    <div
                      key={rec.plan_item_id}
                      style={{
                        border: '1px solid #E5E7EB',
                        borderRadius: 8,
                        padding: 16,
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                      }}
                    >
                      <div style={{ flex: 1, paddingRight: 16 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                          <span style={{ fontWeight: 700, fontSize: 14 }}>{rec.app_name}</span>
                          <span style={{ fontSize: 12, color: '#6B7280', fontFamily: 'monospace' }}>
                            ({rec.process_name} • PID {rec.pid})
                          </span>
                          <span
                            style={{
                              background: actBadge.bg,
                              color: actBadge.text,
                              padding: '2px 8px',
                              borderRadius: 4,
                              fontSize: 11,
                              fontWeight: 600,
                              textTransform: 'uppercase',
                            }}
                          >
                            {rec.proposed_action}
                          </span>
                          <span style={{ background: '#DEF7EC', color: '#03543F', padding: '2px 6px', borderRadius: 4, fontSize: 11 }}>
                            {rec.safety_validation}
                          </span>
                        </div>

                        <div style={{ fontSize: 13, color: '#374151', marginBottom: 4 }}>
                          {rec.reason}
                        </div>
                        <div style={{ fontSize: 12, color: '#6B7280' }}>
                          Expected Effect: {rec.expected_effect}
                        </div>
                      </div>

                      <div style={{ display: 'flex', gap: 8 }}>
                        <button
                          onClick={() => handleRejectRecommendation(rec.plan_item_id)}
                          style={{
                            background: '#FFFFFF',
                            color: '#6B7280',
                            border: '1px solid #D1D5DB',
                            borderRadius: 6,
                            padding: '6px 12px',
                            fontSize: 12,
                            fontWeight: 600,
                            cursor: 'pointer',
                          }}
                        >
                          Reject
                        </button>

                        <button
                          onClick={() => handleApproveRecommendation(rec.plan_item_id)}
                          style={{
                            background: '#2B5FC7',
                            color: '#FFFFFF',
                            border: 'none',
                            borderRadius: 6,
                            padding: '6px 14px',
                            fontSize: 12,
                            fontWeight: 600,
                            cursor: 'pointer',
                          }}
                        >
                          Approve Action
                        </button>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── TAB 4: AUDIT HISTORY ──────────────────────────────────────────────── */}
      {activeTab === 'history' && (
        <div style={{ background: '#FFFFFF', border: '1px solid #E5E7EB', borderRadius: 10, overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: 13 }}>
            <thead>
              <tr style={{ background: '#F9FAFB', borderBottom: '1px solid #E5E7EB', color: '#6B7280', fontSize: 12, fontWeight: 600 }}>
                <th style={{ padding: '12px 16px' }}>TIMESTAMP</th>
                <th style={{ padding: '12px 16px' }}>APPLICATION</th>
                <th style={{ padding: '12px 16px' }}>MODE</th>
                <th style={{ padding: '12px 16px' }}>ACTION</th>
                <th style={{ padding: '12px 16px' }}>REASON</th>
                <th style={{ padding: '12px 16px' }}>STATUS</th>
              </tr>
            </thead>
            <tbody>
              {history.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ padding: 32, textAlign: 'center', color: '#6B7280' }}>
                    No optimization actions executed yet.
                  </td>
                </tr>
              ) : (
                history.map((h) => (
                  <tr key={h.id} style={{ borderBottom: '1px solid #F3F4F6' }}>
                    <td style={{ padding: '12px 16px', color: '#6B7280', fontSize: 12, whiteSpace: 'nowrap' }}>
                      {h.created_at ? new Date(h.created_at).toLocaleTimeString() : 'N/A'}
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      <div style={{ fontWeight: 600 }}>{h.app_name}</div>
                      <div style={{ fontSize: 11, color: '#9CA3AF' }}>PID {h.pid}</div>
                    </td>
                    <td style={{ padding: '12px 16px', textTransform: 'capitalize' }}>
                      {h.operating_mode ? h.operating_mode.replace('_', ' ') : 'Standard'}
                    </td>
                    <td style={{ padding: '12px 16px', fontWeight: 600, textTransform: 'uppercase' }}>
                      {h.action_type}
                    </td>
                    <td style={{ padding: '12px 16px', maxWidth: 320, color: '#4B5563', fontSize: 12 }}>
                      {h.reason}
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      <span
                        style={{
                          background: h.status === 'executed' ? '#DEF7EC' : '#FEE2E2',
                          color: h.status === 'executed' ? '#03543F' : '#991B1B',
                          padding: '2px 8px',
                          borderRadius: 4,
                          fontSize: 11,
                          fontWeight: 600,
                          textTransform: 'uppercase',
                        }}
                      >
                        {h.status}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Slide-Over Application Detail Drawer ──────────────────────────────── */}
      {drawerOpen && selectedApp && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.4)',
            zIndex: 1000,
            display: 'flex',
            justifyContent: 'flex-end',
          }}
          onClick={() => setDrawerOpen(false)}
        >
          <div
            style={{
              width: 520,
              background: '#FFFFFF',
              height: '100%',
              padding: 24,
              overflowY: 'auto',
              boxShadow: '-4px 0 24px rgba(0,0,0,0.15)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <div>
                <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>{selectedApp.name}</h2>
                <div style={{ fontSize: 12, color: '#6B7280', fontFamily: 'monospace' }}>
                  {selectedApp.app_id}
                </div>
              </div>
              <button
                onClick={() => setDrawerOpen(false)}
                style={{ border: 'none', background: 'transparent', cursor: 'pointer', padding: 4 }}
              >
                <X size={20} color="#6B7280" />
              </button>
            </div>

            {/* Profile Config Box */}
            <div style={{ background: '#F9FAFB', border: '1px solid #E5E7EB', borderRadius: 8, padding: 16, marginBottom: 20 }}>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12 }}>Application Profile Settings</div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <div>
                  <label style={{ fontSize: 12, fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>
                    Importance Level
                  </label>
                  <select
                    value={editImportance}
                    onChange={(e) => setEditImportance(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '8px 10px',
                      borderRadius: 6,
                      border: '1px solid #D1D5DB',
                      fontSize: 13,
                      background: '#FFFFFF',
                    }}
                  >
                    <option value="Critical">Critical (Never de-prioritize)</option>
                    <option value="High">High (Protected interactive)</option>
                    <option value="Normal">Normal (Standard application)</option>
                    <option value="Low">Low (Eligible for priority reduction)</option>
                    <option value="Background">Background (Aggressive de-prioritization)</option>
                  </select>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input
                    type="checkbox"
                    id="prot-check"
                    checked={editProtected}
                    onChange={(e) => setEditProtected(e.target.checked)}
                    disabled={selectedApp.is_system}
                    style={{ cursor: 'pointer' }}
                  />
                  <label htmlFor="prot-check" style={{ fontSize: 13, fontWeight: 500, cursor: 'pointer' }}>
                    Protect this application from automated throttling
                  </label>
                </div>

                <button
                  onClick={handleSaveProfile}
                  disabled={savingProfile}
                  style={{
                    background: '#2B5FC7',
                    color: '#FFFFFF',
                    border: 'none',
                    borderRadius: 6,
                    padding: '8px 14px',
                    fontSize: 13,
                    fontWeight: 600,
                    cursor: 'pointer',
                    marginTop: 6,
                  }}
                >
                  {savingProfile ? 'Saving...' : 'Save Profile'}
                </button>
              </div>
            </div>

            {/* Child Processes List */}
            <div>
              <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 10 }}>
                Associated Child Processes ({selectedApp.process_count})
              </div>

              <div style={{ border: '1px solid #E5E7EB', borderRadius: 8, overflow: 'hidden' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: 12 }}>
                  <thead>
                    <tr style={{ background: '#F9FAFB', borderBottom: '1px solid #E5E7EB', color: '#6B7280' }}>
                      <th style={{ padding: '8px 12px' }}>PID</th>
                      <th style={{ padding: '8px 12px' }}>NAME</th>
                      <th style={{ padding: '8px 12px' }}>PRIORITY</th>
                      <th style={{ padding: '8px 12px' }}>CPU</th>
                      <th style={{ padding: '8px 12px' }}>RAM</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedApp.processes.map((p) => (
                      <tr key={p.pid} style={{ borderBottom: '1px solid #F3F4F6' }}>
                        <td style={{ padding: '8px 12px', fontFamily: 'monospace' }}>{p.pid}</td>
                        <td style={{ padding: '8px 12px', fontWeight: 500 }}>{p.name}</td>
                        <td style={{ padding: '8px 12px', fontFamily: 'monospace' }}>{p.priority || 'NORMAL'}</td>
                        <td style={{ padding: '8px 12px', fontFamily: 'monospace' }}>{p.cpu_percent}%</td>
                        <td style={{ padding: '8px 12px', fontFamily: 'monospace' }}>{p.memory_mb} MB</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
