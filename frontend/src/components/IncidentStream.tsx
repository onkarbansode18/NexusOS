import React from 'react'
import { CheckCircle2, ShieldAlert } from 'lucide-react'
import { useNexusStore } from '../store'
import { api } from '../api/client'

export function IncidentStream({ limit }: { limit?: number }) {
  const { incidents, resolveIncident } = useNexusStore()

  let displayedIncidents = [...incidents]
  if (limit) {
    displayedIncidents = displayedIncidents.slice(0, limit)
  }

  const handleResolve = async (incidentId: string) => {
    try {
      await api.resolveIncident(incidentId)
      resolveIncident(incidentId)
    } catch (err) {
      console.error('Failed to resolve incident:', err)
      resolveIncident(incidentId)
    }
  }

  if (incidents.length === 0) {
    return (
      <div className="nexus-panel p-8 text-center text-text-muted">
        <CheckCircle2 className="w-8 h-8 mx-auto mb-2 text-ok" strokeWidth={1.75} />
        <h3 className="font-semibold text-text text-[14px]">All telemetry optimal</h3>
        <p className="text-[12px] text-text-muted mt-0.5">No active incidents or resource anomalies detected.</p>
      </div>
    )
  }

  return (
    <div className="nexus-panel">
      <div className="nexus-panel-header">
        <div className="flex items-center gap-2">
          <ShieldAlert size={16} className="text-warning" strokeWidth={1.75} />
          <h3 className="nexus-panel-title">Incident stream</h3>
        </div>
        <span className="badge badge-warning font-mono text-[11px]">
          {incidents.filter((i) => i.status === 'open').length} open
        </span>
      </div>

      <div className="divide-y divide-border">
        {displayedIncidents.map((incident) => {
          const isResolved = incident.status === 'resolved'

          return (
            <div key={incident.id} className="p-4 hover:bg-surface-2 transition-colors space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className={`status-dot ${incident.severity === 'critical' ? 'critical' : 'warning'}`} />
                  <span className="font-mono text-accent font-medium text-[12px]">
                    {incident.inc_number || incident.id.slice(0, 8)}
                  </span>
                  <span className="font-mono text-[12px] text-text font-medium">
                    {incident.process_name}
                  </span>
                  <span className="font-mono text-[11px] text-text-faint">
                    (PID {incident.pid})
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  <span className={`badge ${incident.severity === 'critical' ? 'badge-critical' : 'badge-warning'}`}>
                    {incident.severity}
                  </span>
                  {!isResolved && (
                    <button
                      type="button"
                      onClick={() => handleResolve(incident.id)}
                      className="btn-secondary h-6 px-2 text-[11px]"
                    >
                      Resolve
                    </button>
                  )}
                </div>
              </div>

              <p className="text-[12px] text-text-muted leading-relaxed">
                {incident.description}
              </p>
            </div>
          )
        })}
      </div>
    </div>
  )
}
