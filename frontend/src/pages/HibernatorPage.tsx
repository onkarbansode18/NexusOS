import React, { useState, useEffect, useCallback } from 'react'
import { PageTopbar } from '../components/PageTopbar'
import { useNexusStore } from '../store'
import {
  BrainCircuit,
  RefreshCw,
  Snowflake,
  Play,
  Zap,
  MemoryStick,
  CheckCircle2,
  AlertTriangle,
  X,
  Info,
} from 'lucide-react'

const BASE = (import.meta as any).env?.VITE_API_BASE_URL ?? 'http://localhost:8000'

interface HibernateCandidate {
  pid: number
  name: string
  memory_mb: number
  cpu_percent: number
  status: string
  username: string
  hibernatable: boolean
  reason: string
}

interface HibernateResult {
  pid: number
  name: string
  action: string
  success: boolean
  memory_before_mb: number
  memory_after_mb?: number
  freed_mb?: number
  simulated: boolean
  message: string
}

type ActionLog = { timestamp: string } & HibernateResult

function formatMB(mb: number) {
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`
  return `${mb.toFixed(0)} MB`
}

async function apiFetch(path: string, options: RequestInit = {}) {
  const token = localStorage.getItem('nexus_token')
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  })
  if (!res.ok) throw new Error(`API ${res.status}`)
  return res.json()
}

function buildCandidatesFromProcesses(processes: import('../types').ProcessSnapshot[], minMemoryMb = 50): HibernateCandidate[] {
  return processes
    .filter((p) => (p.memory_mb ?? 0) >= minMemoryMb)
    .map((p) => {
      const raw = p.name.toLowerCase().replace(/\.exe$/i, '')
      const isSys = ['system', 'registry', 'smss', 'csrss', 'services', 'lsass', 'svchost', 'dwm', 'explorer', 'python', 'node', 'uvicorn', 'vite'].includes(raw)
      return {
        pid: p.pid,
        name: p.name,
        memory_mb: p.memory_mb,
        cpu_percent: p.cpu_percent,
        status: p.status || 'running',
        username: p.username || 'system',
        hibernatable: !isSys,
        reason: isSys ? `Protected system process (${p.name})` : 'Eligible for hibernation',
      }
    })
    .sort((a, b) => b.memory_mb - a.memory_mb)
}

export function HibernatorPage() {
  const { policy, processes, loadProcesses } = useNexusStore()

  // Instant initial state: if store already has live processes, populate instantly on frame 0!
  const [candidates, setCandidates] = useState<HibernateCandidate[]>(() => {
    const procs = useNexusStore.getState().processes
    if (procs && procs.length > 0) {
      return buildCandidatesFromProcesses(procs, 50)
    }
    return []
  })
  const [loading, setLoading] = useState(false)
  const [actionLog, setActionLog] = useState<ActionLog[]>([])
  const [activeActions, setActiveActions] = useState<Record<number, boolean>>({})
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null)
  const [suspendedPids, setSuspendedPids] = useState<Set<number>>(new Set())

  // Real-time synchronization: if candidates is empty, populate from live processes immediately
  useEffect(() => {
    if (candidates.length === 0 && processes && processes.length > 0) {
      setCandidates(buildCandidatesFromProcesses(processes, 50))
    }
  }, [processes, candidates.length])

  const showToast = (msg: string, ok: boolean) => {
    setToast({ msg, ok })
    setTimeout(() => setToast(null), 3500)
  }

  const loadCandidates = useCallback(async () => {
    try {
      const data: HibernateCandidate[] = await apiFetch('/hibernator/candidates?min_memory_mb=50')
      if (Array.isArray(data) && data.length > 0) {
        setCandidates(data)
      } else {
        const liveProcs = useNexusStore.getState().processes
        if (liveProcs && liveProcs.length > 0) {
          setCandidates(buildCandidatesFromProcesses(liveProcs, 50))
        }
      }
    } catch {
      const liveProcs = useNexusStore.getState().processes
      if (liveProcs && liveProcs.length > 0) {
        setCandidates(buildCandidatesFromProcesses(liveProcs, 50))
      }
    }
  }, [])

  useEffect(() => {
    // Ensure processes are loaded immediately
    loadProcesses().then(() => {
      const liveProcs = useNexusStore.getState().processes
      if (liveProcs && liveProcs.length > 0) {
        setCandidates(buildCandidatesFromProcesses(liveProcs, 50))
      }
    }).catch(() => {})

    loadCandidates()
    const timer = setInterval(() => {
      apiFetch('/hibernator/candidates?min_memory_mb=50')
        .then((data: HibernateCandidate[]) => {
          if (Array.isArray(data) && data.length > 0) setCandidates(data)
        })
        .catch(() => { })
    }, 3000)
    return () => clearInterval(timer)
  }, [loadCandidates, loadProcesses])

  const executeAction = async (candidate: HibernateCandidate, action: 'trim' | 'suspend' | 'resume') => {
    setActiveActions((prev) => ({ ...prev, [candidate.pid]: true }))
    try {
      let result: HibernateResult
      if (action === 'resume') {
        result = await apiFetch(`/hibernator/resume/${candidate.pid}?process_name=${encodeURIComponent(candidate.name)}`, {
          method: 'POST',
        })
        if (result.success) {
          setSuspendedPids((prev) => { const s = new Set(prev); s.delete(candidate.pid); return s })
        }
      } else {
        result = await apiFetch('/hibernator/hibernate', {
          method: 'POST',
          body: JSON.stringify({
            pid: candidate.pid,
            process_name: candidate.name,
            action,
            simulation_mode: policy.simulation_mode,
          }),
        })
        if (result.success && action === 'suspend') {
          setSuspendedPids((prev) => new Set([...prev, candidate.pid]))
        }
      }

      const log: ActionLog = { ...result, timestamp: new Date().toLocaleTimeString() }
      setActionLog((prev) => [log, ...prev].slice(0, 20))
      showToast(result.message, result.success)
      if (result.success) loadCandidates()
    } catch (e: any) {
      showToast(`Action failed: ${e.message}`, false)
    } finally {
      setActiveActions((prev) => { const n = { ...prev }; delete n[candidate.pid]; return n })
    }
  }

  const totalHibernatable = candidates.filter((c) => c.hibernatable).length
  const totalMemory = candidates.reduce((s, c) => s + c.memory_mb, 0)
  const potentialSavings = candidates.filter((c) => c.hibernatable).reduce((s, c) => s + c.memory_mb * 0.4, 0)

  return (
    <div className="dashboard-page" style={{ paddingBottom: 60 }}>
      <PageTopbar
        current="Smart Hibernator"
        subtitle="Trim idle app memory or suspend background processes to reclaim RAM without closing anything"
        actions={
          <button
            type="button"
            onClick={loadCandidates}
            disabled={loading}
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
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        }
      />

      {/* Toast */}
      {toast && (
        <div style={{
          position: 'fixed', bottom: 24, right: 24,
          background: toast.ok ? '#111827' : '#7F1D1D',
          color: '#fff', padding: '12px 18px', borderRadius: 8,
          fontSize: 13, fontWeight: 500,
          boxShadow: '0 10px 25px -5px rgba(0,0,0,0.25)',
          display: 'flex', alignItems: 'center', gap: 10, zIndex: 9999,
        }}>
          {toast.ok ? <CheckCircle2 size={16} color="#10B981" /> : <AlertTriangle size={16} color="#F87171" />}
          <span style={{ maxWidth: 320 }}>{toast.msg}</span>
          <button type="button" onClick={() => setToast(null)} style={{ background: 'none', border: 'none', color: '#9CA3AF', cursor: 'pointer' }}><X size={14} /></button>
        </div>
      )}

      {/* Stats Row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 20 }}>
        {[
          { label: 'Processes Monitored', value: candidates.length, icon: BrainCircuit, color: '#2563EB', bg: '#EFF6FF' },
          { label: 'Hibernatable Apps', value: totalHibernatable, icon: Snowflake, color: '#7C3AED', bg: '#F5F3FF' },
          { label: 'Potential RAM Savings', value: formatMB(potentialSavings), icon: MemoryStick, color: '#059669', bg: '#ECFDF5' },
        ].map(({ label, value, icon: Icon, color, bg }) => (
          <div key={label} style={{ background: '#FFFFFF', border: '1px solid #E5E7EB', borderRadius: 12, padding: '18px 20px', display: 'flex', alignItems: 'center', gap: 14 }}>
            <div style={{ width: 40, height: 40, borderRadius: 10, background: bg, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
              <Icon size={20} color={color} />
            </div>
            <div>
              <div style={{ fontSize: 20, fontWeight: 700, color: '#111827' }}>{value}</div>
              <div style={{ fontSize: 12, color: '#6B7280', marginTop: 1 }}>{label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Sim Mode Banner */}
      {policy.simulation_mode && (
        <div style={{ background: '#EFF6FF', border: '1px solid #BFDBFE', borderRadius: 10, padding: '10px 16px', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 10, fontSize: 13, color: '#1D4ED8' }}>
          <Info size={15} />
          <span><strong>Simulation Mode:</strong> Actions will be logged but no real changes made to processes. Toggle Live Healing in Settings to apply real changes.</span>
        </div>
      )}

      {/* Process Table */}
      <div style={{ background: '#FFFFFF', border: '1px solid #E5E7EB', borderRadius: 12, overflow: 'hidden', marginBottom: 24 }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #F3F4F6', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 700, color: '#111827' }}>Memory-Heavy Processes</div>
            <div style={{ fontSize: 12, color: '#6B7280', marginTop: 1 }}>Sorted by RAM usage. Trim frees ~40% RAM without closing. Suspend frees ~80% but pauses the app.</div>
          </div>
        </div>

        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6B7280', fontSize: 13 }}>
            <RefreshCw size={18} className="animate-spin" style={{ margin: '0 auto 8px', display: 'block' }} />
            Loading processes...
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ background: '#F9FAFB' }}>
                {['Process', 'Memory', 'CPU', 'Status', 'Actions'].map((h) => (
                  <th key={h} style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6B7280', letterSpacing: '0.05em', textTransform: 'uppercase' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {candidates.map((c, idx) => {
                const isSuspended = suspendedPids.has(c.pid)
                const isActing = !!activeActions[c.pid]
                return (
                  <tr key={c.pid} style={{ borderTop: idx === 0 ? 'none' : '1px solid #F3F4F6', background: isSuspended ? '#F5F3FF' : 'transparent' }}>
                    <td style={{ padding: '12px 16px' }}>
                      <div style={{ fontWeight: 600, color: '#111827' }}>{c.name}</div>
                      <div style={{ fontSize: 11, color: '#9CA3AF', marginTop: 1 }}>PID {c.pid} · {c.username}</div>
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      <div style={{ fontWeight: 600, color: c.memory_mb > 500 ? '#DC2626' : c.memory_mb > 200 ? '#D97706' : '#059669' }}>
                        {formatMB(c.memory_mb)}
                      </div>
                    </td>
                    <td style={{ padding: '12px 16px', color: '#374151' }}>{c.cpu_percent.toFixed(1)}%</td>
                    <td style={{ padding: '12px 16px' }}>
                      {isSuspended ? (
                        <span style={{ padding: '2px 8px', borderRadius: 12, background: '#F5F3FF', color: '#7C3AED', fontSize: 11, fontWeight: 600 }}>Suspended</span>
                      ) : c.hibernatable ? (
                        <span style={{ padding: '2px 8px', borderRadius: 12, background: '#ECFDF5', color: '#059669', fontSize: 11, fontWeight: 600 }}>Eligible</span>
                      ) : (
                        <span title={c.reason} style={{ padding: '2px 8px', borderRadius: 12, background: '#F9FAFB', color: '#6B7280', fontSize: 11, fontWeight: 600 }}>Protected</span>
                      )}
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      {c.hibernatable ? (
                        <div style={{ display: 'flex', gap: 6 }}>
                          {isSuspended ? (
                            <button
                              type="button"
                              disabled={isActing}
                              onClick={() => executeAction(c, 'resume')}
                              style={{ padding: '5px 10px', borderRadius: 6, border: '1px solid #C4B5FD', background: '#F5F3FF', color: '#7C3AED', fontSize: 11, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4 }}
                            >
                              <Play size={11} /> Resume
                            </button>
                          ) : (
                            <>
                              <button
                                type="button"
                                disabled={isActing}
                                onClick={() => executeAction(c, 'trim')}
                                style={{ padding: '5px 10px', borderRadius: 6, border: '1px solid #BFDBFE', background: '#EFF6FF', color: '#2563EB', fontSize: 11, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4 }}
                              >
                                <Zap size={11} /> Trim RAM
                              </button>
                              <button
                                type="button"
                                disabled={isActing}
                                onClick={() => executeAction(c, 'suspend')}
                                style={{ padding: '5px 10px', borderRadius: 6, border: '1px solid #C4B5FD', background: '#F5F3FF', color: '#7C3AED', fontSize: 11, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4 }}
                              >
                                <Snowflake size={11} /> Suspend
                              </button>
                            </>
                          )}
                        </div>
                      ) : (
                        <span style={{ fontSize: 11, color: '#9CA3AF' }} title={c.reason}>—</span>
                      )}
                    </td>
                  </tr>
                )
              })}
              {candidates.length === 0 && !loading && (
                <tr>
                  <td colSpan={5} style={{ padding: 32, textAlign: 'center', color: '#9CA3AF', fontSize: 13 }}>
                    No processes found. Make sure the backend is running.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      {/* Action Log */}
      {actionLog.length > 0 && (
        <div style={{ background: '#FFFFFF', border: '1px solid #E5E7EB', borderRadius: 12, overflow: 'hidden' }}>
          <div style={{ padding: '14px 20px', borderBottom: '1px solid #F3F4F6' }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: '#111827' }}>Hibernation Action Log</div>
          </div>
          <div style={{ padding: '12px 20px', display: 'flex', flexDirection: 'column', gap: 8 }}>
            {actionLog.map((log, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 12, color: '#374151', padding: '8px 12px', borderRadius: 8, background: log.success ? '#F0FDF4' : '#FEF2F2', border: `1px solid ${log.success ? '#BBF7D0' : '#FECACA'}` }}>
                {log.success ? <CheckCircle2 size={14} color="#059669" /> : <AlertTriangle size={14} color="#DC2626" />}
                <span style={{ fontFamily: 'monospace', color: '#6B7280', fontSize: 11 }}>{log.timestamp}</span>
                <span style={{ fontWeight: 600 }}>{log.action.toUpperCase()}</span>
                <span style={{ color: '#6B7280' }}>{log.name} (PID {log.pid})</span>
                {log.freed_mb && log.freed_mb > 0 && (
                  <span style={{ marginLeft: 'auto', fontWeight: 600, color: '#059669' }}>−{formatMB(log.freed_mb)}</span>
                )}
                {log.simulated && (
                  <span style={{ padding: '1px 6px', borderRadius: 10, background: '#EFF6FF', color: '#2563EB', fontSize: 10, fontWeight: 600 }}>SIM</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

