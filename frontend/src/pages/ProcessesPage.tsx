import React, { useState, useEffect, useMemo } from 'react'
import { useNexusStore } from '../store'
import { PageTopbar } from '../components/PageTopbar'
import { Search, X, Shield, Terminal, ArrowUpDown } from 'lucide-react'

interface ProcessDisplayItem {
  name: string
  pid: number
  user: string
  cpu: number
  mem: number
  status: 'Running' | 'Sleeping'
  anomaly: number
  policy: 'Eligible' | 'Watching' | 'Protected'
  cmd?: string
}

const FALLBACK_PROCESSES: ProcessDisplayItem[] = [
  { name: 'python3',      pid: 4821, user: 'operator', cpu: 91.2, mem: 420,  status: 'Running',  anomaly: -0.74, policy: 'Eligible',  cmd: 'python3 -c "while True: pass"' },
  { name: 'node',         pid: 7730, user: 'operator', cpu: 18.0, mem: 1420, status: 'Running',  anomaly: -0.31, policy: 'Watching',  cmd: 'node ./server.js --cluster' },
  { name: 'chrome',       pid: 2210, user: 'operator', cpu: 12.4, mem: 860,  status: 'Running',  anomaly: -0.08, policy: 'Eligible',  cmd: 'chrome.exe --type=renderer --site-per-process' },
  { name: 'docker',       pid: 4410, user: 'SYSTEM',   cpu: 4.2,  mem: 780,  status: 'Running',  anomaly: -0.06, policy: 'Eligible',  cmd: 'dockerd.exe -H npipe://' },
  { name: 'svchost.exe',  pid: 1204, user: 'SYSTEM',   cpu: 3.1,  mem: 95,   status: 'Running',  anomaly: -0.12, policy: 'Protected', cmd: 'svchost.exe -k LocalServiceNetworkRestricted' },
  { name: 'slack',        pid: 6644, user: 'operator', cpu: 2.6,  mem: 410,  status: 'Sleeping', anomaly: +0.02, policy: 'Eligible',  cmd: 'slack.exe --disable-gpu' },
  { name: 'postgres',     pid: 3388, user: 'postgres', cpu: 2.2,  mem: 310,  status: 'Running',  anomaly: +0.04, policy: 'Eligible',  cmd: 'postgres.exe -D /var/lib/postgresql/data' },
  { name: 'explorer.exe', pid: 988,  user: 'operator', cpu: 1.9,  mem: 210,  status: 'Running',  anomaly: -0.02, policy: 'Protected', cmd: 'C:\\Windows\\explorer.exe' },
  { name: 'code',         pid: 5120, user: 'operator', cpu: 6.8,  mem: 540,  status: 'Running',  anomaly: -0.05, policy: 'Eligible',  cmd: 'Code.exe --unity-launch' },
  { name: 'csrss.exe',    pid: 612,  user: 'SYSTEM',   cpu: 0.4,  mem: 12,   status: 'Running',  anomaly: +0.01, policy: 'Protected', cmd: 'C:\\Windows\\system32\\csrss.exe' },
  { name: 'nginx',        pid: 1840, user: 'SYSTEM',   cpu: 1.1,  mem: 64,   status: 'Running',  anomaly: -0.01, policy: 'Eligible',  cmd: 'nginx.exe -g "daemon off;"' },
  { name: 'redis-server', pid: 2904, user: 'SYSTEM',   cpu: 0.8,  mem: 128,  status: 'Running',  anomaly: +0.03, policy: 'Eligible',  cmd: 'redis-server.exe --port 6379' },
]

export function ProcessesPage() {
  const { processes, loadProcesses, policy, setConfirmingAction } = useNexusStore()
  const [search, setSearch] = useState('')
  const [selectedPid, setSelectedPid] = useState<number | null>(null)
  const [sortBy, setSortBy] = useState<'cpu' | 'mem' | 'anomaly' | 'name'>('cpu')
  const [sortDesc, setSortDesc] = useState<boolean>(true)

  useEffect(() => {
    loadProcesses()
    const timer = setInterval(() => {
      loadProcesses()
    }, 4000)
    return () => clearInterval(timer)
  }, [loadProcesses])

  // Combine live processes from store / API
  const processList: ProcessDisplayItem[] = useMemo(() => {
    if (processes && processes.length > 0) {
      return processes.map((p) => {
        const isProtected = policy?.process_blacklist?.some(
          (b) => b.toLowerCase() === p.name.toLowerCase()
        )
        const isWatching = p.health_status === 'warning' || p.health_status === 'under_observation'
        const score = typeof p.anomaly_score === 'number'
          ? p.anomaly_score
          : (p.health_status === 'critical' ? -0.85 : p.health_status === 'warning' ? -0.65 : isWatching ? -0.25 : 0.02)

        return {
          name: p.name,
          pid: p.pid,
          user: p.username || 'system',
          cpu: +(p.cpu_percent ?? 0).toFixed(1),
          mem: Math.round(p.memory_mb ?? 0),
          status: (p.status?.toLowerCase() === 'sleeping' ? 'Sleeping' : 'Running') as 'Running' | 'Sleeping',
          anomaly: score,
          policy: isProtected ? 'Protected' : (isWatching ? 'Watching' : 'Eligible'),
          cmd: (p as any).cmdline || `${p.name} --pid ${p.pid}`,
        }
      })
    }
    return FALLBACK_PROCESSES
  }, [processes, policy])

  // Filtered and sorted processes
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    let list = processList
    if (q) {
      list = list.filter((p) =>
        p.name.toLowerCase().includes(q) ||
        String(p.pid).includes(q)
      )
    }

    return [...list].sort((a, b) => {
      let cmp = 0
      if (sortBy === 'cpu') cmp = a.cpu - b.cpu
      else if (sortBy === 'mem') cmp = a.mem - b.mem
      else if (sortBy === 'anomaly') cmp = a.anomaly - b.anomaly
      else if (sortBy === 'name') cmp = a.name.localeCompare(b.name)
      return sortDesc ? -cmp : cmp
    })
  }, [processList, search, sortBy, sortDesc])

  // Selected process (null on initial load so full screen is occupied by list)
  const selected = useMemo(() => {
    if (selectedPid === null) return null
    return processList.find((p) => p.pid === selectedPid) || null
  }, [processList, selectedPid])

  const handleExportCsv = () => {
    const rows = [['Process Name', 'PID', 'CPU Usage (%)', 'Memory Usage (MB)', 'Anomaly Score']]
    filtered.forEach((p) => {
      rows.push([p.name, String(p.pid), `${p.cpu}%`, `${p.mem} MB`, String(p.anomaly)])
    })
    const csv = rows.map((r) => r.map((c) => `"${c}"`).join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `nexus-processes-${Date.now()}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleTriggerAction = (actionType: string, actionTitle: string) => {
    if (!selected) return
    setConfirmingAction({
      pid: selected.pid,
      processName: selected.name,
      actionType,
      actionTitle,
    })
  }

  const toggleSort = (field: 'cpu' | 'mem' | 'anomaly' | 'name') => {
    if (sortBy === field) {
      setSortDesc(!sortDesc)
    } else {
      setSortBy(field)
      setSortDesc(true)
    }
  }

  return (
    <div className="dashboard-page">
      <PageTopbar
        current="Processes"
        subtitle={`Live process guardian · ${processList.length} active running processes on host`}
        actions={
          <button
            type="button"
            onClick={handleExportCsv}
            style={{
              height: 32,
              padding: '0 14px',
              background: '#FFFFFF',
              color: '#111827',
              border: '1px solid #E5E7EB',
              borderRadius: 8,
              fontSize: 12,
              fontWeight: 500,
              cursor: 'pointer',
              whiteSpace: 'nowrap',
              transition: 'background 0.12s ease',
            }}
          >
            Export CSV
          </button>
        }
      />

      {/* Main Grid: Occupies whole screen when no process is selected; displays action sidebar on click */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: selected ? 'minmax(0, 1.8fr) minmax(360px, 1fr)' : '1fr',
        gap: 16,
        alignItems: 'start',
        width: '100%',
        transition: 'grid-template-columns 0.2s ease',
      }}>

        {/* Process Table Card — Full Width by Default */}
        <div className="dash-card" style={{ padding: 0, minHeight: 640, width: '100%' }}>
          {/* Card Top Toolbar */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '14px 20px',
            borderBottom: '1px solid #E5E7EB',
            gap: 12,
            flexWrap: 'wrap',
          }}>
            {/* Process count & instructions */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{ fontSize: 14, fontWeight: 700, color: '#111827' }}>
                All Running Processes
              </div>
              <span style={{
                fontSize: 11,
                fontWeight: 600,
                color: '#4B5563',
                background: '#F3F4F6',
                padding: '2px 8px',
                borderRadius: 12,
              }}>
                {filtered.length} total
              </span>
              <span style={{ fontSize: 12, color: '#9CA3AF' }}>
                · Click any process to open remediation actions
              </span>
            </div>

            {/* Search Input with search icon */}
            <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
              <Search size={14} style={{ position: 'absolute', left: 12, color: '#9CA3AF', pointerEvents: 'none' }} />
              <input
                type="text"
                placeholder="Search by name or PID..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                style={{
                  width: 260,
                  height: 34,
                  background: '#F9FAFB',
                  border: '1px solid #E5E7EB',
                  borderRadius: 17,
                  padding: '0 32px 0 34px',
                  fontSize: 12,
                  color: '#111827',
                  outline: 'none',
                  transition: 'border-color 0.15s ease',
                }}
              />
              {search && (
                <button
                  type="button"
                  onClick={() => setSearch('')}
                  style={{
                    position: 'absolute',
                    right: 10,
                    border: 'none',
                    background: 'transparent',
                    color: '#9CA3AF',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                  }}
                >
                  <X size={14} />
                </button>
              )}
            </div>
          </div>

          {/* Table: Shows ONLY the 4 requested columns */}
          <div style={{ overflowX: 'auto', maxHeight: 'calc(100vh - 210px)', overflowY: 'auto' }}>
            <table className="dash-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead style={{ position: 'sticky', top: 0, background: '#FFFFFF', zIndex: 1, boxShadow: '0 1px 0 #E5E7EB' }}>
                <tr>
                  <th
                    onClick={() => toggleSort('name')}
                    style={{ paddingLeft: 22, textAlign: 'left', cursor: 'pointer', userSelect: 'none' }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      Process & PID
                      <ArrowUpDown size={12} style={{ color: sortBy === 'name' ? '#111827' : '#9CA3AF' }} />
                    </div>
                  </th>
                  <th
                    onClick={() => toggleSort('cpu')}
                    style={{ textAlign: 'right', cursor: 'pointer', userSelect: 'none', width: '18%' }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 4 }}>
                      CPU Usage
                      <ArrowUpDown size={12} style={{ color: sortBy === 'cpu' ? '#111827' : '#9CA3AF' }} />
                    </div>
                  </th>
                  <th
                    onClick={() => toggleSort('mem')}
                    style={{ textAlign: 'right', cursor: 'pointer', userSelect: 'none', width: '20%' }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 4 }}>
                      Memory Usage
                      <ArrowUpDown size={12} style={{ color: sortBy === 'mem' ? '#111827' : '#9CA3AF' }} />
                    </div>
                  </th>
                  <th
                    onClick={() => toggleSort('anomaly')}
                    style={{ paddingRight: 22, paddingLeft: 30, textAlign: 'left', cursor: 'pointer', userSelect: 'none', width: '22%' }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      Anomaly Score
                      <ArrowUpDown size={12} style={{ color: sortBy === 'anomaly' ? '#111827' : '#9CA3AF' }} />
                    </div>
                  </th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((p) => {
                  const isSelected = selected?.pid === p.pid
                  const barColor = p.anomaly <= -0.5 ? '#DC2626' : (p.anomaly <= -0.2 ? '#D97706' : '#10B981')

                  return (
                    <tr
                      key={p.pid}
                      onClick={() => setSelectedPid(isSelected ? null : p.pid)}
                      style={{
                        cursor: 'pointer',
                        background: isSelected ? '#EFF6FF' : 'transparent',
                        transition: 'background 0.1s ease',
                      }}
                      title="Click to open remediation action sidebar"
                    >
                      {/* Column 1: Process Name and PID */}
                      <td style={{ paddingLeft: 22, paddingTop: 12, paddingBottom: 12 }}>
                        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                          <span className="proc-name" style={{ fontWeight: 600, color: '#111827', fontSize: 13 }}>
                            {p.name}
                          </span>
                          <span className="proc-pid" style={{ color: '#6B7280', fontSize: 12, fontFamily: 'monospace' }}>
                            · PID {p.pid}
                          </span>
                        </div>
                      </td>

                      {/* Column 2: CPU Usage */}
                      <td className="proc-num" style={{
                        textAlign: 'right',
                        fontWeight: 600,
                        fontFamily: 'monospace',
                        color: p.cpu >= 50 ? '#DC2626' : p.cpu >= 20 ? '#D97706' : '#111827',
                        fontSize: 13,
                      }}>
                        {p.cpu.toFixed(1)}%
                      </td>

                      {/* Column 3: Memory Usage */}
                      <td className="proc-num" style={{
                        textAlign: 'right',
                        fontWeight: 600,
                        fontFamily: 'monospace',
                        color: '#111827',
                        fontSize: 13,
                      }}>
                        {p.mem >= 1024 ? `${(p.mem / 1024).toFixed(2)} GB` : `${p.mem.toLocaleString()} MB`}
                      </td>

                      {/* Column 4: Anomaly Score */}
                      <td style={{ paddingRight: 22, paddingLeft: 30 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          <div style={{
                            width: 64,
                            height: 6,
                            background: '#E5E7EB',
                            borderRadius: 3,
                            overflow: 'hidden',
                          }}>
                            <div style={{
                              width: `${Math.min(100, Math.max(12, Math.abs(p.anomaly) * 100))}%`,
                              height: '100%',
                              background: barColor,
                              borderRadius: 3,
                            }} />
                          </div>
                          <span style={{
                            fontSize: 12,
                            fontFamily: 'monospace',
                            fontWeight: 600,
                            color: p.anomaly < -0.3 ? '#DC2626' : p.anomaly < 0 ? '#D97706' : '#059669',
                            minWidth: 46,
                          }}>
                            {p.anomaly > 0 ? `+${p.anomaly.toFixed(2)}` : p.anomaly.toFixed(2)}
                          </span>
                        </div>
                      </td>
                    </tr>
                  )
                })}

                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={4} style={{ textAlign: 'center', padding: '40px 20px', color: '#6B7280', fontSize: 13 }}>
                      No processes match "{search}".
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Action Sidebar: Opens ONLY when a particular process is clicked */}
        {selected && (
          <div
            className="dash-card"
            style={{
              padding: '22px 24px',
              minHeight: 640,
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              position: 'sticky',
              top: 20,
              boxShadow: '0 4px 16px rgba(0, 0, 0, 0.06)',
            }}
          >
            <div>
              {/* Header with Title and Close ✕ Button */}
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 14 }}>
                <div>
                  <div style={{ fontSize: 18, fontWeight: 700, color: '#111827', letterSpacing: '-0.02em' }}>
                    {selected.name}
                  </div>
                  <div style={{ fontSize: 12, color: '#6B7280', marginTop: 2, fontFamily: 'monospace' }}>
                    PID {selected.pid} · user: {selected.user}
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  {selected.policy === 'Eligible' && <span className="pill-eligible">● Eligible</span>}
                  {selected.policy === 'Watching' && <span className="pill-watching">● Watching</span>}
                  {selected.policy === 'Protected' && <span className="pill-protected">● Protected</span>}
                  <button
                    type="button"
                    onClick={() => setSelectedPid(null)}
                    title="Close actions sidebar"
                    style={{
                      border: 'none',
                      background: '#F3F4F6',
                      color: '#4B5563',
                      width: 28,
                      height: 28,
                      borderRadius: 6,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      cursor: 'pointer',
                      transition: 'background 0.12s ease',
                    }}
                  >
                    <X size={16} />
                  </button>
                </div>
              </div>

              {/* Quick telemetry metrics banner */}
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(3, 1fr)',
                gap: 8,
                background: '#F9FAFB',
                border: '1px solid #E5E7EB',
                borderRadius: 8,
                padding: '10px 12px',
                marginBottom: 16,
              }}>
                <div>
                  <div style={{ fontSize: 10, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.04em' }}>CPU</div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: '#111827', fontFamily: 'monospace', marginTop: 2 }}>
                    {selected.cpu.toFixed(1)}%
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: 10, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Memory</div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: '#111827', fontFamily: 'monospace', marginTop: 2 }}>
                    {selected.mem >= 1024 ? `${(selected.mem / 1024).toFixed(1)} GB` : `${selected.mem} MB`}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: 10, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Anomaly</div>
                  <div style={{
                    fontSize: 13,
                    fontWeight: 700,
                    fontFamily: 'monospace',
                    marginTop: 2,
                    color: selected.anomaly < -0.3 ? '#DC2626' : selected.anomaly < 0 ? '#D97706' : '#059669',
                  }}>
                    {selected.anomaly > 0 ? `+${selected.anomaly.toFixed(2)}` : selected.anomaly.toFixed(2)}
                  </div>
                </div>
              </div>

              {/* Command line box */}
              <div style={{
                background: '#F9FAFB',
                border: '1px solid #E5E7EB',
                borderRadius: 8,
                padding: '10px 12px',
                fontFamily: 'monospace',
                fontSize: 11,
                color: '#374151',
                marginBottom: 16,
                overflowX: 'auto',
                lineHeight: 1.4,
                maxHeight: 64,
              }}>
                {selected.cmd || `${selected.name} --pid ${selected.pid}`}
              </div>

              {/* Remediation Actions Header */}
              <div style={{ fontSize: 11, fontWeight: 700, color: '#4B5563', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 10 }}>
                Remediation Actions
              </div>

              {/* 6 Action buttons in a 2x3 grid */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                <button
                  type="button"
                  onClick={() => handleTriggerAction('kill', 'Kill Process')}
                  disabled={selected.policy === 'Protected'}
                  style={{
                    height: 36,
                    background: '#FFFFFF',
                    border: '1px solid #FCA5A5',
                    color: '#DC2626',
                    borderRadius: 8,
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: selected.policy === 'Protected' ? 'not-allowed' : 'pointer',
                    opacity: selected.policy === 'Protected' ? 0.4 : 1,
                    transition: 'all 0.12s ease',
                  }}
                >
                  Kill
                </button>
                <button
                  type="button"
                  onClick={() => handleTriggerAction('restart', 'Restart Process')}
                  disabled={selected.policy === 'Protected'}
                  style={{
                    height: 36,
                    background: '#FFFFFF',
                    border: '1px solid #E5E7EB',
                    color: '#111827',
                    borderRadius: 8,
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: selected.policy === 'Protected' ? 'not-allowed' : 'pointer',
                    opacity: selected.policy === 'Protected' ? 0.4 : 1,
                    transition: 'all 0.12s ease',
                  }}
                >
                  Restart
                </button>
                <button
                  type="button"
                  onClick={() => handleTriggerAction('suspend', 'Suspend Process')}
                  disabled={selected.policy === 'Protected'}
                  style={{
                    height: 36,
                    background: '#FFFFFF',
                    border: '1px solid #E5E7EB',
                    color: '#111827',
                    borderRadius: 8,
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: selected.policy === 'Protected' ? 'not-allowed' : 'pointer',
                    opacity: selected.policy === 'Protected' ? 0.4 : 1,
                    transition: 'all 0.12s ease',
                  }}
                >
                  Suspend
                </button>
                <button
                  type="button"
                  onClick={() => handleTriggerAction('resume', 'Resume Process')}
                  disabled={selected.policy === 'Protected'}
                  style={{
                    height: 36,
                    background: '#FFFFFF',
                    border: '1px solid #E5E7EB',
                    color: '#111827',
                    borderRadius: 8,
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: selected.policy === 'Protected' ? 'not-allowed' : 'pointer',
                    opacity: selected.policy === 'Protected' ? 0.4 : 1,
                    transition: 'all 0.12s ease',
                  }}
                >
                  Resume
                </button>
                <button
                  type="button"
                  onClick={() => handleTriggerAction('throttle', 'Throttle Priority')}
                  disabled={selected.policy === 'Protected'}
                  style={{
                    height: 36,
                    background: '#FFFFFF',
                    border: '1px solid #E5E7EB',
                    color: '#111827',
                    borderRadius: 8,
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: selected.policy === 'Protected' ? 'not-allowed' : 'pointer',
                    opacity: selected.policy === 'Protected' ? 0.4 : 1,
                    transition: 'all 0.12s ease',
                  }}
                >
                  Throttle
                </button>
                <button
                  type="button"
                  onClick={() => handleTriggerAction('renice', 'Renice Priority')}
                  disabled={selected.policy === 'Protected'}
                  style={{
                    height: 36,
                    background: '#FFFFFF',
                    border: '1px solid #E5E7EB',
                    color: '#111827',
                    borderRadius: 8,
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: selected.policy === 'Protected' ? 'not-allowed' : 'pointer',
                    opacity: selected.policy === 'Protected' ? 0.4 : 1,
                    transition: 'all 0.12s ease',
                  }}
                >
                  Renice
                </button>
              </div>

              {/* Observe only button full width */}
              <button
                type="button"
                onClick={() => handleTriggerAction('observe', 'Observe Process')}
                style={{
                  width: '100%',
                  height: 36,
                  marginTop: 8,
                  background: '#FFFFFF',
                  border: '1px solid #E5E7EB',
                  color: '#111827',
                  borderRadius: 8,
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: 'pointer',
                  transition: 'background 0.12s ease',
                }}
              >
                Observe only
              </button>
            </div>

            {/* Footer note */}
            <p style={{
              fontSize: 11,
              color: '#6B7280',
              textAlign: 'center',
              margin: '16px 0 0',
              lineHeight: 1.4,
            }}>
              Simulation mode is on. Actions are verified and logged safely.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
