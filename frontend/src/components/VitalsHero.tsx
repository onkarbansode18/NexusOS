import React from 'react'
import { useNexusStore } from '../store'

export function VitalsHero() {
  const { metrics } = useNexusStore()

  if (!metrics) {
    return (
      <div className="nexus-panel p-6 text-center text-text-muted font-mono text-[12px]">
        INITIALIZING TELEMETRY STREAM...
      </div>
    )
  }

  const cpu = Math.round(metrics.cpu_percent)
  const ram = Math.round(metrics.ram_percent)
  const disk = Math.round(metrics.disk_percent)

  return (
    <div className="nexus-panel grid grid-cols-3 divide-x divide-border">
      <div className="p-4 space-y-1">
        <span className="text-[12px] text-text-muted block">CPU core load</span>
        <span className="text-[24px] font-medium font-mono text-text tabular-nums">{cpu}%</span>
        <div className="w-full bg-surface-3 h-1 rounded overflow-hidden mt-2">
          <div className="h-full bg-accent" style={{ width: `${Math.min(cpu, 100)}%` }} />
        </div>
      </div>

      <div className="p-4 space-y-1">
        <span className="text-[12px] text-text-muted block">Memory capacity</span>
        <span className="text-[24px] font-medium font-mono text-text tabular-nums">{ram}%</span>
        <div className="w-full bg-surface-3 h-1 rounded overflow-hidden mt-2">
          <div className="h-full bg-[#6B7A90]" style={{ width: `${Math.min(ram, 100)}%` }} />
        </div>
      </div>

      <div className="p-4 space-y-1">
        <span className="text-[12px] text-text-muted block">Disk storage</span>
        <span className="text-[24px] font-medium font-mono text-text tabular-nums">{disk}%</span>
        <div className="w-full bg-surface-3 h-1 rounded overflow-hidden mt-2">
          <div className="h-full bg-[#94A3B8]" style={{ width: `${Math.min(disk, 100)}%` }} />
        </div>
      </div>
    </div>
  )
}
