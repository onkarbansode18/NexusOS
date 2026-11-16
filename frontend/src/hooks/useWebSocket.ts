/// <reference types="vite/client" />
/**
 * WebSocket custom hook — manages WS connection to backend orchestrator.
 * Auto-reconnects with 3s backoff.
 */

import { useEffect, useRef } from 'react'
import { useNexusStore } from '../store'
import type { Incident, Policy } from '../types'

const WS_URL = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000/ws'

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const { setWsConnected, setMetrics, setProcesses, addIncident, resolveIncident, addAction, setPolicy, fetchPolicy, loadIncidents, loadProcesses } = useNexusStore()

  useEffect(() => {
    let alive = true

    function connect() {
      if (!alive) return
      try {
        const ws = new WebSocket(WS_URL)
        wsRef.current = ws

        ws.onopen = () => {
          if (!alive) return
          setWsConnected(true)
          fetchPolicy()
          loadIncidents()
          loadProcesses()
          console.log('[Nexus WS] connected')
        }

        ws.onmessage = (event) => {
          if (!alive) return
          try {
            const msg = JSON.parse(event.data)
            if (msg.event === 'metrics') {
              const d = msg.data
              // Map backend payload → SystemMetrics shape
              setMetrics({
                timestamp:      msg.ts ?? new Date().toISOString(),
                cpu_percent:    d.cpu_percent     ?? 0,
                cpu_freq_mhz:   d.cpu_freq_mhz    ?? 0,
                ram_used_mb:    d.ram_used_mb      ?? 0,
                ram_total_mb:   d.ram_total_mb     ?? 0,
                ram_percent:    d.ram_percent      ?? 0,
                disk_used_gb:   d.disk_used_gb     ?? 0,
                disk_total_gb:  d.disk_total_gb    ?? 0,
                disk_percent:   d.disk_percent     ?? 0,
                net_bytes_sent: d.net_bytes_sent   ?? 0,
                net_bytes_recv: d.net_bytes_recv   ?? 0,
              })
              if (Array.isArray(d.processes)) {
                setProcesses(
                  d.processes.map((p: any) => ({
                    pid:             p.pid,
                    name:            p.name,
                    cpu_percent:     p.cpu_percent    ?? 0,
                    memory_mb:       p.memory_mb      ?? 0,
                    memory_percent:  p.memory_percent ?? 0,
                    status:          p.status         ?? 'unknown',
                    username:        p.username       ?? '',
                    created_at:      p.created_at     ?? '',
                    health_status:   p.health_status  ?? 'healthy',
                    anomaly_score:   p.anomaly_score,
                  }))
                )
              }
            } else if (msg.event === 'incident') {
              const d = msg.data
              if (d) {
                addIncident({
                  id:           d.id           ?? crypto.randomUUID(),
                  pid:          d.pid          ?? 0,
                  process_name: d.process_name ?? 'unknown',
                  title:        d.reason       ? d.reason.slice(0, 60) : `Anomaly on ${d.process_name ?? 'process'}`,
                  severity:     d.severity     ?? 'warning',
                  status:       'open',
                  description:  d.reason       ?? d.description ?? '',
                  prediction:   d.prediction,
                  anomaly_score: d.anomaly_score ?? 0,
                  nl_summary:   d.nl_summary,
                  detected_at:  msg.ts         ?? new Date().toISOString(),
                  actions:      [],
                })
              }
            } else if (msg.event === 'action') {
              const d = msg.data
              if (d) {
                addAction({
                  id: d.id || `act-${Date.now()}`,
                  incident_id: d.incident_id || 'manual',
                  action_type: d.action_type,
                  action_title: d.action_title || `${d.action_type} ${d.process_name}`,
                  pid: d.pid,
                  process_name: d.process_name,
                  simulated: d.simulated,
                  status_text: d.simulated ? 'Simulated' : 'Executed',
                  before_cpu: d.before_cpu ?? 0,
                  before_memory_mb: d.before_memory_mb ?? 0,
                  after_cpu: d.after_cpu,
                  after_memory_mb: d.after_memory_mb,
                  executed_at: d.executed_at || new Date().toLocaleTimeString(),
                  reason: d.reason || '',
                })
                if (d.action_type === 'kill' && !d.simulated && d.success) {
                  loadProcesses()
                }
              }
            } else if (msg.event === 'incident_resolved') {
              const d = msg.data
              if (d && d.id) {
                resolveIncident(d.id)
              }
            } else if (msg.event === 'policy_update') {
              setPolicy(msg.data as Partial<Policy>)
            }
          } catch (e) {
            console.error('[Nexus WS] parse error', e)
          }
        }

        ws.onclose = () => {
          if (!alive) return
          setWsConnected(false)
          console.warn('[Nexus WS] disconnected — reconnecting in 3s')
          reconnectRef.current = setTimeout(connect, 3000)
        }

        ws.onerror = () => {
          ws.close()
        }
      } catch (e) {
        reconnectRef.current = setTimeout(connect, 3000)
      }
    }

    connect()

    return () => {
      alive = false
      if (reconnectRef.current) clearTimeout(reconnectRef.current)
      wsRef.current?.close()
    }
  }, [setWsConnected, setMetrics, setProcesses, addIncident, setPolicy, fetchPolicy, loadIncidents])
}
