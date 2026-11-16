import React, { useEffect } from 'react'
import { X, Lock, RefreshCw, Gauge, Sliders, Eye, Power, Pause, Play } from 'lucide-react'
import { ResponsiveContainer, LineChart, Line, YAxis } from 'recharts'
import { useNexusStore } from '../store'

export function ProcessDrawer() {
  const { selectedProcess, setSelectedProcess, setConfirmingAction, policy } = useNexusStore()

  // Close drawer on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSelectedProcess(null)
    }
    if (selectedProcess) window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [selectedProcess, setSelectedProcess])

  if (!selectedProcess) return null

  const isProtected = policy?.process_blacklist?.includes(selectedProcess.name.toLowerCase()) || false

  const chartData = selectedProcess.memory_trend
    ? selectedProcess.memory_trend.map((val, idx) => ({ idx, val }))
    : [
        { idx: 0, val: selectedProcess.memory_mb * 0.7 },
        { idx: 1, val: selectedProcess.memory_mb * 0.8 },
        { idx: 2, val: selectedProcess.memory_mb * 0.88 },
        { idx: 3, val: selectedProcess.memory_mb * 0.94 },
        { idx: 4, val: selectedProcess.memory_mb },
      ]

  const handleActionClick = (actionType: string, actionTitle: string) => {
    if (isProtected) return
    setConfirmingAction({
      pid: selectedProcess.pid,
      processName: selectedProcess.name,
      actionType,
      actionTitle,
    })
  }

  return (
    <div className="fixed inset-0 z-50 overflow-hidden flex justify-end">
      {/* Backdrop */}
      <div
        className="fixed inset-0 dialog-overlay"
        onClick={() => setSelectedProcess(null)}
      />

      {/* Slide-over panel: 440px, white, 1px left border, no radius on screen edge */}
      <div className="relative w-full max-w-[440px] bg-surface h-full flex flex-col z-10 border-l border-border drawer-shadow">
        {/* Sticky Header */}
        <div className="h-12 px-4 border-b border-border flex items-center justify-between bg-surface sticky top-0 z-20">
          <div className="flex items-center gap-2 min-w-0">
            <span className="font-mono text-[14px] font-semibold text-text truncate">
              {selectedProcess.name}
            </span>
            <span className="font-mono text-[12px] text-text-muted">
              PID {selectedProcess.pid}
            </span>
          </div>
          <button
            type="button"
            onClick={() => setSelectedProcess(null)}
            className="w-7 h-7 rounded flex items-center justify-center text-text-muted hover:text-text hover:bg-surface-2 transition-colors"
            aria-label="Close drawer"
          >
            <X size={16} strokeWidth={1.75} />
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto divide-y divide-border">
          {/* Status note if protected or warning */}
          {isProtected ? (
            <div className="p-4 bg-neutral-bg flex items-center gap-2 text-neutral text-[12px]">
              <Lock size={14} className="flex-shrink-0" />
              <span>Protected system process. Automated and manual actions disabled.</span>
            </div>
          ) : selectedProcess.health_status !== 'healthy' ? (
            <div className="p-3 bg-warning-bg flex items-center gap-2 text-warning text-[12px]">
              <span className="status-dot warning" />
              <span>Elevated resource pressure detected on this process.</span>
            </div>
          ) : null}

          {/* Section: Process Meta */}
          <div className="p-4 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <span className="text-[12px] text-text-muted block mb-0.5">User</span>
                <span className="font-mono text-[13px] text-text">{selectedProcess.username || 'system'}</span>
              </div>
              <div>
                <span className="text-[12px] text-text-muted block mb-0.5">Uptime</span>
                <span className="font-mono text-[13px] text-text">{selectedProcess.uptime || '2h 15m'}</span>
              </div>
              <div>
                <span className="text-[12px] text-text-muted block mb-0.5">Status</span>
                <span className="text-[13px] text-text capitalize">{selectedProcess.status || 'Running'}</span>
              </div>
              <div>
                <span className="text-[12px] text-text-muted block mb-0.5">Threads</span>
                <span className="font-mono tabular-nums text-[13px] text-text">{selectedProcess.threads || 32}</span>
              </div>
            </div>

            <div>
              <span className="text-[12px] text-text-muted block mb-1">Command line</span>
              <div className="p-2.5 rounded bg-surface-2 border border-border font-mono text-[12px] text-text break-all select-all">
                {selectedProcess.cmdline || `${selectedProcess.name} --worker --pid=${selectedProcess.pid}`}
              </div>
            </div>
          </div>

          {/* Section: Resource Metrics */}
          <div className="p-4 space-y-3">
            <div className="grid grid-cols-2 gap-4">
              <div className="p-3 rounded border border-border bg-surface">
                <span className="text-[12px] text-text-muted block mb-1">CPU usage</span>
                <span className="font-mono tabular-nums text-[24px] font-medium text-text">
                  {selectedProcess.cpu_percent.toFixed(1)}%
                </span>
                <div className="w-full bg-surface-3 h-1 rounded mt-2 overflow-hidden">
                  <div
                    className="h-full bg-accent"
                    style={{ width: `${Math.min(selectedProcess.cpu_percent, 100)}%` }}
                  />
                </div>
              </div>

              <div className="p-3 rounded border border-border bg-surface">
                <span className="text-[12px] text-text-muted block mb-1">Memory (RSS)</span>
                <span className="font-mono tabular-nums text-[24px] font-medium text-text">
                  {selectedProcess.memory_mb.toFixed(0)} <span className="text-[13px] text-text-muted font-normal">MB</span>
                </span>
                <div className="w-full bg-surface-3 h-1 rounded mt-2 overflow-hidden">
                  <div
                    className="h-full"
                    style={{ background: 'var(--chart-mem)', width: `${Math.min(selectedProcess.memory_percent, 100)}%` }}
                  />
                </div>
              </div>
            </div>

            {/* Sparkline Memory Trend */}
            <div className="pt-2">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[12px] text-text-muted">Memory trend</span>
                <span className="font-mono text-[11px] text-text-faint">last 5 samples</span>
              </div>
              <div className="h-20 w-full border border-border rounded p-2 bg-surface">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData}>
                    <YAxis hide domain={['dataMin - 10', 'dataMax + 10']} />
                    <Line
                      type="monotone"
                      dataKey="val"
                      stroke="var(--chart-mem)"
                      strokeWidth={1.5}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          {/* Section: Manual Actions (7 manual actions) */}
          <div className="p-4 space-y-4">
            <div>
              <span className="text-[12px] font-medium text-text-muted block mb-2">
                Standard actions
              </span>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => handleActionClick('throttle', 'Throttle')}
                  disabled={isProtected}
                  className="btn-secondary justify-start text-[12px]"
                >
                  <Gauge size={14} className="text-text-muted" strokeWidth={1.75} />
                  <span>Throttle priority</span>
                </button>

                <button
                  type="button"
                  onClick={() => handleActionClick('renice', 'Renice')}
                  disabled={isProtected}
                  className="btn-secondary justify-start text-[12px]"
                >
                  <Sliders size={14} className="text-text-muted" strokeWidth={1.75} />
                  <span>Renice</span>
                </button>

                <button
                  type="button"
                  onClick={() => handleActionClick('suspend', 'Suspend')}
                  disabled={isProtected}
                  className="btn-secondary justify-start text-[12px]"
                >
                  <Pause size={14} className="text-text-muted" strokeWidth={1.75} />
                  <span>Suspend process</span>
                </button>

                <button
                  type="button"
                  onClick={() => handleActionClick('resume', 'Resume')}
                  disabled={isProtected}
                  className="btn-secondary justify-start text-[12px]"
                >
                  <Play size={14} className="text-text-muted" strokeWidth={1.75} />
                  <span>Resume process</span>
                </button>

                <button
                  type="button"
                  onClick={() => handleActionClick('observe', 'Observe')}
                  className="btn-secondary col-span-2 justify-start text-[12px]"
                >
                  <Eye size={14} className="text-text-muted" strokeWidth={1.75} />
                  <span>Observe only (log baseline)</span>
                </button>
              </div>
            </div>

            {/* Destructive Actions: separated with border */}
            <div className="pt-3 border-t border-border">
              <span className="text-[12px] font-medium text-critical block mb-2">
                Destructive interventions
              </span>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => handleActionClick('restart', 'Restart Process')}
                  disabled={isProtected}
                  className="btn-danger justify-start text-[12px]"
                >
                  <RefreshCw size={14} strokeWidth={1.75} />
                  <span>Restart process</span>
                </button>

                <button
                  type="button"
                  onClick={() => handleActionClick('kill', 'Kill Process')}
                  disabled={isProtected}
                  className="btn-danger justify-start text-[12px]"
                >
                  <Power size={14} strokeWidth={1.75} />
                  <span>Kill process</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
