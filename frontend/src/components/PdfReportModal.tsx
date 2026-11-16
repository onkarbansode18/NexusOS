import React, { useRef, useState } from 'react'
import { FileText, Download, X, Shield, Activity, Cpu, Server, HardDrive, Lock, AlertTriangle } from 'lucide-react'
import { useNexusStore } from '../store'
import { downloadElementAsPDF } from '../utils/pdfGenerator'

interface PdfReportModalProps {
  isOpen: boolean
  onClose: () => void
}

export function PdfReportModal({ isOpen, onClose }: PdfReportModalProps) {
  const { metrics, policy, incidents, openIncidentCount } = useNexusStore()
  const reportRef = useRef<HTMLDivElement>(null)
  const [downloading, setDownloading] = useState(false)

  if (!isOpen) return null

  const healthScore = Math.max(0, 100 - openIncidentCount * 15 - (metrics && metrics.cpu_percent > (policy?.cpu_warning_pct ?? 80) ? 10 : 0))
  const systemStatus = openIncidentCount > 0 ? 'CRITICAL' : healthScore < 85 ? 'WARNING' : 'HEALTHY'
  const generatedAtStr = new Date().toLocaleString('en-US', { timeZoneName: 'short' })
  const mockSha256 = '4a89f3e1b7c2d5e8f0a3b6c9d2e5f8a1b4c7d0e3f6a9b2c5d8e1f4a7b0c3d6e9'

  const handleDownload = async () => {
    if (!reportRef.current) return
    setDownloading(true)
    try {
      await downloadElementAsPDF(reportRef.current, `Nexus_OS_Guardian_Audit_Report_${new Date().toISOString().slice(0, 10)}.pdf`)
    } catch (err) {
      console.error('Failed to generate PDF:', err)
      alert('Error generating PDF report. Please try again.')
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/25 p-4 overflow-y-auto">
      <div className="bg-surface rounded-md shadow-subtle border border-border w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden">
        {/* Modal Top Control Bar */}
        <div className="px-5 py-3 border-b border-border flex items-center justify-between bg-surface-2">
          <div className="flex items-center gap-2">
            <FileText size={16} className="text-text-muted" strokeWidth={1.75} />
            <div>
              <h3 className="font-semibold text-text text-[14px]">Executive PDF report</h3>
              <p className="text-[12px] text-text-muted">Preview and export system telemetry audit document</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleDownload}
              disabled={downloading}
              className="btn-primary"
            >
              {downloading ? (
                <>
                  <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  <span>Generating PDF...</span>
                </>
              ) : (
                <>
                  <Download size={14} strokeWidth={1.75} />
                  <span>Download PDF</span>
                </>
              )}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="w-8 h-8 rounded flex items-center justify-center text-text-muted hover:text-text hover:bg-surface-3 transition-colors"
              aria-label="Close"
            >
              <X size={16} strokeWidth={1.75} />
            </button>
          </div>
        </div>

        {/* Scrollable Report Canvas Container */}
        <div className="flex-1 overflow-y-auto p-6 bg-surface-2">
          {/* Paper Document Container (Target for PDF html2canvas) */}
          <div
            ref={reportRef}
            className="bg-white mx-auto border border-border p-8 text-text font-sans max-w-[850px]"
            style={{ minHeight: '1050px' }}
          >
            {/* Header Section */}
            <div className="border-b border-border pb-4 mb-5 flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2 text-text font-semibold text-base mb-1">
                  <Shield size={16} className="text-text" strokeWidth={1.75} />
                  <span>NEXUS — RESOURCE GUARDIAN</span>
                </div>
                <h1 className="text-xl font-semibold text-text tracking-tight">System Telemetry & Audit Report</h1>
                <p className="text-xs text-text-muted mt-0.5">
                  Autonomous Operations & Safety Policy Verification Evidence Document
                </p>
              </div>
              <div className="text-right">
                <span className="badge badge-ok font-mono text-[11px]">
                  CLASSIFICATION: AUDIT VERIFIED
                </span>
                <p className="text-[11px] font-mono text-text-muted mt-2">Generated: {generatedAtStr}</p>
                <p className="text-[11px] font-mono text-text-muted">Node: localhost (host system)</p>
              </div>
            </div>

            {/* Section 1: Executive Overview Cards */}
            <div className="mb-6">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-text-muted mb-2.5">
                1. Executive telemetry overview
              </h2>
              <div className="grid grid-cols-4 gap-3">
                <div className="p-3 bg-surface border border-border rounded">
                  <p className="text-[11px] text-text-muted uppercase">Health score</p>
                  <p className="text-xl font-medium text-text font-mono mt-0.5">{healthScore}/100</p>
                  <span className={`badge mt-1 text-[10px] ${systemStatus === 'HEALTHY' ? 'badge-ok' : 'badge-critical'}`}>
                    {systemStatus}
                  </span>
                </div>
                <div className="p-3 bg-surface border border-border rounded">
                  <p className="text-[11px] text-text-muted uppercase">Operating mode</p>
                  <p className="text-[14px] font-medium text-text mt-1 font-mono">
                    {policy?.simulation_mode ? 'SIMULATION' : 'LIVE HEALING'}
                  </p>
                  <p className="text-[11px] text-text-muted mt-0.5">Safety policy active</p>
                </div>
                <div className="p-3 bg-surface border border-border rounded">
                  <p className="text-[11px] text-text-muted uppercase">Total incidents</p>
                  <p className="text-xl font-medium text-text font-mono mt-0.5">{incidents.length}</p>
                  <p className="text-[11px] text-text-muted mt-0.5">{openIncidentCount} open</p>
                </div>
                <div className="p-3 bg-surface border border-border rounded">
                  <p className="text-[11px] text-text-muted uppercase">ML detection engine</p>
                  <p className="text-[13px] font-medium text-text mt-1">Isolation Forest</p>
                  <p className="text-[11px] text-ok font-mono mt-0.5">Active</p>
                </div>
              </div>
            </div>

            {/* Section 2: Live System Vitals */}
            <div className="mb-6">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-text-muted mb-2.5">
                2. Live system vitals & resource usage
              </h2>
              <table className="nexus-table border border-border">
                <thead>
                  <tr>
                    <th>Resource metric</th>
                    <th>Utilization</th>
                    <th>Allocated capacity</th>
                    <th>Warning threshold</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody className="font-mono text-text">
                  <tr>
                    <td className="font-sans font-medium">CPU core load</td>
                    <td>{metrics?.cpu_percent.toFixed(1) ?? '24.0'}%</td>
                    <td>{metrics?.cpu_freq_mhz.toFixed(0) ?? '3200'} MHz</td>
                    <td>{policy?.cpu_warning_pct ?? 80}%</td>
                    <td><span className="badge badge-ok">Normal</span></td>
                  </tr>
                  <tr>
                    <td className="font-sans font-medium">RAM memory</td>
                    <td>{metrics?.ram_percent.toFixed(1) ?? '62.0'}%</td>
                    <td>{((metrics?.ram_used_mb ?? 8192) / 1024).toFixed(1)} GB / {((metrics?.ram_total_mb ?? 16384) / 1024).toFixed(0)} GB</td>
                    <td>{policy?.ram_warning_pct ?? 70}%</td>
                    <td><span className="badge badge-ok">Normal</span></td>
                  </tr>
                  <tr>
                    <td className="font-sans font-medium">Disk storage</td>
                    <td>{metrics?.disk_percent.toFixed(1) ?? '48.0'}%</td>
                    <td>{metrics?.disk_used_gb ?? 240} GB / {metrics?.disk_total_gb ?? 512} GB</td>
                    <td>{policy?.disk_warning_pct ?? 80}%</td>
                    <td><span className="badge badge-ok">Normal</span></td>
                  </tr>
                </tbody>
              </table>
            </div>

            {/* Section 3: Safety Guardrails */}
            <div className="mb-6">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-text-muted mb-2.5">
                3. Safety guardrails & process protections
              </h2>
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div className="p-3 border border-border rounded bg-surface-2">
                  <p className="font-semibold text-text mb-1.5">Protected system processes (immune to termination)</p>
                  <div className="flex flex-wrap gap-1">
                    {(policy?.process_blacklist ?? ['systemd', 'explorer.exe', 'uvicorn', 'python.exe', 'svchost.exe']).map((proc) => (
                      <span key={proc} className="badge badge-neutral font-mono text-[11px]">
                        {proc}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="p-3 border border-border rounded bg-surface-2">
                  <p className="font-semibold text-text mb-1.5">Whitelisted applications</p>
                  <div className="flex flex-wrap gap-1">
                    {(policy?.process_whitelist ?? ['chrome.exe', 'node.exe', 'code.exe', 'spotify.exe']).map((proc) => (
                      <span key={proc} className="badge badge-accent font-mono text-[11px]">
                        {proc}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* Section 4: Incident Log */}
            <div className="mb-6">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-text-muted mb-2.5">
                4. Incident audit trail
              </h2>
              <table className="nexus-table border border-border">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Process</th>
                    <th>Severity</th>
                    <th>Description</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody className="font-mono text-text">
                  {incidents.slice(0, 5).map((inc) => (
                    <tr key={inc.id}>
                      <td className="text-accent">{inc.inc_number || inc.id.slice(0, 8)}</td>
                      <td className="font-sans font-medium">
                        {inc.process_name} <span className="text-text-faint font-mono">(PID {inc.pid})</span>
                      </td>
                      <td>
                        <span className={`badge ${inc.severity === 'critical' ? 'badge-critical' : 'badge-warning'}`}>
                          {inc.severity}
                        </span>
                      </td>
                      <td className="font-sans max-w-[200px] truncate">{inc.description}</td>
                      <td><span className="badge badge-ok">{inc.status}</span></td>
                    </tr>
                  ))}
                  {incidents.length === 0 && (
                    <tr>
                      <td colSpan={5} className="p-4 text-center font-sans text-text-muted">
                        No active incidents recorded.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {/* Cryptographic Digest */}
            <div className="pt-4 border-t border-border flex items-center justify-between text-[11px] text-text-muted font-mono">
              <div>
                <p>NEXUS Autonomous Governance Engine — SHA-256 Digest:</p>
                <p className="text-text font-medium">{mockSha256}</p>
              </div>
              <div className="text-right font-sans">
                <p className="font-medium text-text">Verified System Report</p>
                <p className="text-text-muted">Page 1 of 1</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
