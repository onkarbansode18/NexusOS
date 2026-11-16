import React, { useState } from 'react'
import { Search } from 'lucide-react'
import { useNexusStore } from '../store'
import type { ProcessSnapshot } from '../types'

export function ProcessTable() {
  const { processes, policy, setSelectedProcess } = useNexusStore()
  const [searchTerm, setSearchTerm] = useState('')
  const [activeTab, setActiveTab] = useState<'all' | 'critical' | 'warning' | 'healthy'>('all')

  const getHealthStatus = (p: ProcessSnapshot): 'critical' | 'warning' | 'healthy' => {
    if (p.health_status && p.health_status !== 'healthy') return p.health_status as any
    const cpuCrit = policy?.cpu_critical_pct ?? 80
    const ramCrit = policy?.ram_critical_pct ?? 90
    const cpuWarn = policy?.cpu_warning_pct ?? 60
    const ramWarn = policy?.ram_warning_pct ?? 70

    if (p.cpu_percent >= cpuCrit || p.memory_percent >= ramCrit) return 'critical'
    if (p.cpu_percent >= cpuWarn || p.memory_percent >= ramWarn) return 'warning'
    return 'healthy'
  }

  const counts = {
    all: processes.length,
    critical: processes.filter((p) => getHealthStatus(p) === 'critical').length,
    warning: processes.filter((p) => getHealthStatus(p) === 'warning').length,
    healthy: processes.filter((p) => getHealthStatus(p) === 'healthy').length,
  }

  const filtered = processes.filter((p) => {
    const matchesSearch =
      p.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      p.pid.toString().includes(searchTerm) ||
      p.username.toLowerCase().includes(searchTerm.toLowerCase())

    if (!matchesSearch) return false

    const status = getHealthStatus(p)
    if (activeTab === 'critical') return status === 'critical'
    if (activeTab === 'warning') return status === 'warning'
    if (activeTab === 'healthy') return status === 'healthy'
    return true
  })

  return (
    <div className="nexus-panel">
      {/* Header Toolbar */}
      <div className="nexus-panel-header">
        <div className="relative w-64">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted" strokeWidth={1.75} />
          <input
            type="text"
            placeholder="Filter processes..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="nexus-input pl-8 w-full text-[12px]"
          />
        </div>

        {/* Tab filters */}
        <div className="inline-flex rounded border border-border p-0.5 bg-surface-2 text-[11px] font-mono">
          <button
            type="button"
            onClick={() => setActiveTab('all')}
            className={`px-2 py-0.5 rounded-xs transition-colors ${
              activeTab === 'all' ? 'bg-surface text-text font-semibold shadow-xs' : 'text-text-muted hover:text-text'
            }`}
          >
            All ({counts.all})
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('critical')}
            className={`px-2 py-0.5 rounded-xs transition-colors ${
              activeTab === 'critical' ? 'bg-surface text-critical font-semibold shadow-xs' : 'text-text-muted hover:text-text'
            }`}
          >
            Critical ({counts.critical})
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('warning')}
            className={`px-2 py-0.5 rounded-xs transition-colors ${
              activeTab === 'warning' ? 'bg-surface text-warning font-semibold shadow-xs' : 'text-text-muted hover:text-text'
            }`}
          >
            Warning ({counts.warning})
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('healthy')}
            className={`px-2 py-0.5 rounded-xs transition-colors ${
              activeTab === 'healthy' ? 'bg-surface text-ok font-semibold shadow-xs' : 'text-text-muted hover:text-text'
            }`}
          >
            Healthy ({counts.healthy})
          </button>
        </div>
      </div>

      <div className="nexus-table-wrap">
        <table className="nexus-table">
          <thead>
            <tr>
              <th style={{ width: 80 }}>PID</th>
              <th>Process name</th>
              <th>User</th>
              <th style={{ width: 140 }}>CPU %</th>
              <th style={{ width: 140 }}>Memory (MB)</th>
              <th style={{ width: 100 }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={6} className="p-6 text-center text-text-muted">
                  No matching processes found.
                </td>
              </tr>
            ) : (
              filtered.map((proc) => {
                const status = getHealthStatus(proc)
                return (
                  <tr
                    key={proc.pid}
                    onClick={() => setSelectedProcess(proc)}
                    className="cursor-pointer"
                  >
                    <td className="font-mono text-text-muted text-[12px]">{proc.pid}</td>
                    <td className="font-mono text-text font-medium text-[13px]">{proc.name}</td>
                    <td className="text-text-muted text-[12px]">{proc.username}</td>
                    <td>
                      <div className="flex items-center gap-2">
                        <span className="font-mono tabular-nums text-[12px] w-12 text-right">
                          {proc.cpu_percent.toFixed(1)}%
                        </span>
                        <div className="flex-1 bg-surface-3 h-1 rounded overflow-hidden max-w-[60px]">
                          <div className="h-full bg-accent" style={{ width: `${Math.min(proc.cpu_percent, 100)}%` }} />
                        </div>
                      </div>
                    </td>
                    <td>
                      <div className="flex items-center gap-2">
                        <span className="font-mono tabular-nums text-[12px] w-12 text-right">
                          {proc.memory_mb.toFixed(0)}
                        </span>
                        <div className="flex-1 bg-surface-3 h-1 rounded overflow-hidden max-w-[60px]">
                          <div className="h-full bg-[#6B7A90]" style={{ width: `${Math.min(proc.memory_percent, 100)}%` }} />
                        </div>
                      </div>
                    </td>
                    <td>
                      <span className={`badge ${status === 'critical' ? 'badge-critical' : status === 'warning' ? 'badge-warning' : 'badge-ok'}`}>
                        {status}
                      </span>
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
