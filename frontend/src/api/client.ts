/// <reference types="vite/client" />
/**
 * Nexus API client — typed REST helpers.
 * All methods return typed data or throw on failure.
 */

const BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('nexus_token')
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  })
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`)
  return res.json()
}

export const api = {
  // ── Incidents ──────────────────────────────────────────────────────────────
  fetchIncidents: (status?: string, limit = 500) => {
    const params = new URLSearchParams({ limit: String(limit) })
    if (status) params.set('status', status)
    return request<unknown[]>(`/incidents/?${params}`)
  },

  resolveIncident: (id: string) =>
    request(`/incidents/${id}/resolve`, { method: 'POST' }),

  // ── Policy ─────────────────────────────────────────────────────────────────
  fetchPolicy: () => request<unknown>('/policy/'),

  updatePolicy: (patch: Record<string, unknown>) =>
    request('/policy/', {
      method: 'PATCH',
      body: JSON.stringify(patch),
    }),

  // ── Metrics & Processes ───────────────────────────────────────────────────
  fetchMetricsHistory: (minutes = 30) =>
    request<unknown[]>(`/metrics/history?minutes=${minutes}`),

  fetchProcesses: () => request<unknown[]>('/processes/'),

  // ── Actions ────────────────────────────────────────────────────────────────
  executeAction: (
    action_type: string,
    pid: number,
    process_name: string,
    reason = '',
    incident_id?: string,
    simulation_mode?: boolean,
  ) =>
    request('/actions/execute', {
      method: 'POST',
      body: JSON.stringify({ action_type, pid, process_name, reason, incident_id, simulation_mode }),
    }),

  // ── Reports ────────────────────────────────────────────────────────────────
  fetchReportSummary: () => request<unknown>('/reports/summary'),

  generateReport: (format = 'markdown', include_history_minutes = 60) =>
    request<{ status: string; content_type: string; report: string }>('/reports/generate', {
      method: 'POST',
      body: JSON.stringify({ format, include_history_minutes }),
    }),

  exportReportUrl: (format = 'markdown') => `${BASE}/reports/export?format=${format}`,

  generateComplianceReport: () =>
    request<{ status: string; format: string; digest: string; generated_at: string; report_html: string }>(
      '/reports/compliance',
      { method: 'POST' }
    ),

  // ── AI Summarizer ─────────────────────────────────────────────────────────
  summarizeIncident: (id: string) =>
    request<{ incident_id: string; nl_summary: string; nl_slack_message: string; provider: string }>(
      `/incidents/${id}/summarize`,
      { method: 'POST' }
    ),

  // ── Feedback Loop ──────────────────────────────────────────────────────────
  submitFeedback: (incident_id: string, label: string, user_note?: string) =>
    request<{ status: string; fp_rate: number; current_contamination: number }>(`/feedback/`, {
      method: 'POST',
      body: JSON.stringify({ incident_id, label, user_note }),
    }),

  fetchFeedbackStats: () =>
    request<{
      total_feedback: number
      correct_count: number
      false_positive_count: number
      too_aggressive_count: number
      false_positive_rate: number
      current_contamination: number
      auto_tuning_active: boolean
    }>('/feedback/stats'),

  // ── Maintenance Windows ────────────────────────────────────────────────────
  fetchMaintenanceWindows: () => request<any[]>('/maintenance/'),

  createMaintenanceWindow: (data: any) =>
    request('/maintenance/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateMaintenanceWindow: (id: number, data: any) =>
    request(`/maintenance/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deleteMaintenanceWindow: (id: number) =>
    request(`/maintenance/${id}`, { method: 'DELETE' }),

  checkMaintenanceActive: () =>
    request<{ is_active: boolean; has_defined_windows: boolean; active_windows: any[] }>(
      '/maintenance/active'
    ),

  // ── Self-Healing Guardian APIs ──────────────────────────────────────────────
  fetchCooldownStatus: () =>
    request<{ emergency_stop_active: boolean; emergency_stop_reason: string; active_cooldown_processes_count: number }>('/healing/cooldown/status'),

  triggerEmergencyStop: (reason?: string) =>
    request<{ status: string; emergency_stop_active: boolean; reason: string }>('/healing/emergency-stop', {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),

  clearEmergencyStop: () =>
    request<{ status: string; emergency_stop_active: boolean }>('/healing/emergency-stop/clear', {
      method: 'POST',
    }),

  fetchMemoryFindings: () =>
    request<any[]>('/healing/memory/findings'),

  fetchProcessMemoryAnalysis: (pid: number) =>
    request<any>(`/healing/memory/analysis/${pid}`),

  restorePriority: (pid: number, process_name: string) =>
    request<any>('/healing/priority/restore', {
      method: 'POST',
      body: JSON.stringify({ pid, process_name }),
    }),

  fetchDiskReport: () =>
    request<{
      timestamp: string
      disk_path: string
      total_gb: number
      used_gb: number
      free_gb: number
      used_percent: number
      total_reclaimable_mb: number
      warning: boolean
      critical: boolean
      temp_dirs_scanned: any[]
    }>('/healing/disk/report'),

  executeDiskCleanup: (simulation_mode?: boolean, min_age_hours?: number) =>
    request<any>('/healing/disk/cleanup', {
      method: 'POST',
      body: JSON.stringify({ simulation_mode, min_age_hours }),
    }),

  fetchDiskHistory: (limit = 20) =>
    request<any[]>(`/healing/disk/history?limit=${limit}`),

  fetchRecentRcas: (limit = 20) =>
    request<any[]>(`/healing/rca/recent?limit=${limit}`),

  fetchIncidentRca: (incident_id: string) =>
    request<any>(`/healing/rca/${incident_id}`),

  fetchRecoveryVerifications: (limit = 50) =>
    request<any[]>(`/healing/verifications?limit=${limit}`),

  fetchHealingActionsHistory: (limit = 50) =>
    request<any[]>(`/healing/actions-history?limit=${limit}`),

  // ── Auth ───────────────────────────────────────────────────────────────────
  login: async (username: string, password: string): Promise<string> => {
    const form = new URLSearchParams({ username, password })
    const res = await fetch(`${BASE}/auth/token`, {
      method: 'POST',
      body: form,
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
    if (!res.ok) throw new Error('Login failed')
    const data = await res.json()
    return data.access_token
  },

  // ── Adaptive AI (Double DQN) ────────────────────────────────────────────────
  fetchRLStatus: () => request<import('../types').RLStatus>('/rl/status'),

  setRLMode: (autonomous: boolean) =>
    request<{ autonomous_mode: boolean; message: string }>('/rl/mode', {
      method: 'POST',
      body: JSON.stringify({ autonomous }),
    }),

  fetchRLProgress: () => request<import('../types').RLTrainingProgress>('/rl/training/progress'),

  startRLTraining: (episodes: number) =>
    request<{ started: boolean; episodes_scheduled: number; message: string }>('/rl/train', {
      method: 'POST',
      body: JSON.stringify({ episodes }),
    }),

  stopRLTraining: () =>
    request<{ message: string }>('/rl/stop', {
      method: 'POST',
    }),

  evaluateRLPolicy: (episodes_per_scenario = 5) =>
    request<import('../types').EvaluationComparison>('/rl/evaluate', {
      method: 'POST',
      body: JSON.stringify({ episodes_per_scenario }),
    }),

  fetchRLModels: () => request<import('../types').RLModelInfo[]>('/rl/models'),

  setActiveRLModel: (model_id: string) =>
    request<{ success: boolean; active_model: import('../types').RLModelInfo }>('/rl/models/active', {
      method: 'POST',
      body: JSON.stringify({ model_id }),
    }),

  deleteRLModel: (model_id: string) =>
    request<{ success: boolean; model_id: string }>(`/rl/models/${model_id}`, {
      method: 'DELETE',
    }),

  fetchRLDecisions: () => request<import('../types').RLDecision[]>('/rl/decisions'),

  simulateRLInference: (payload: import('../types').SimulateInferencePayload) =>
    request<import('../types').RLDecision>('/rl/simulate', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  // ── Application-Aware Resource Management APIs ─────────────────────────────
  fetchApplications: () =>
    request<{
      total_applications: number
      total_processes: number
      total_cpu_percent: number
      total_memory_mb: number
      applications: import('../types').ApplicationItem[]
    }>('/api/applications'),

  fetchApplicationDetail: (appId: string) =>
    request<import('../types').ApplicationItem>(`/api/applications/${appId}`),

  fetchApplicationProcesses: (appId: string) =>
    request<{
      app_id: string
      name: string
      root_pid: number
      process_count: number
      processes: import('../types').ApplicationProcessDetail[]
    }>(`/api/applications/${appId}/processes`),

  scanApplications: () =>
    request<{ status: string; detected_count: number }>('/api/applications/scan', { method: 'POST' }),

  updateApplicationCategory: (appId: string, category: string) =>
    request<{ status: string; app_id: string; category: string }>(`/api/applications/${appId}/category`, {
      method: 'PUT',
      body: JSON.stringify({ category }),
    }),

  fetchApplicationProfiles: () =>
    request<import('../types').ApplicationProfile[]>('/api/application-profiles'),

  saveApplicationProfile: (profile: Partial<import('../types').ApplicationProfile>) =>
    request<{ status: string; profile_id: string; app_id: string }>('/api/application-profiles', {
      method: 'POST',
      body: JSON.stringify(profile),
    }),

  updateApplicationProfile: (appId: string, updates: Partial<import('../types').ApplicationProfile>) =>
    request<{ status: string; app_id: string }>(`/api/application-profiles/${appId}`, {
      method: 'PUT',
      body: JSON.stringify(updates),
    }),

  deleteApplicationProfile: (appId: string) =>
    request<{ status: string; app_id: string }>(`/api/application-profiles/${appId}`, { method: 'DELETE' }),

  fetchOperatingModes: () =>
    request<{
      active_mode: import('../types').OperatingModeInfo
      available_modes: import('../types').OperatingModeCardItem[]
      battery: any
    }>('/api/application-modes'),

  activateOperatingMode: (modeId: string, targetAppId?: string | null, configuration?: Record<string, any>) =>
    request<{ status: string; active_mode: import('../types').OperatingModeInfo }>('/api/application-modes/activate', {
      method: 'POST',
      body: JSON.stringify({ mode_id: modeId, target_app_id: targetAppId, configuration }),
    }),

  deactivateOperatingMode: () =>
    request<{ status: string; active_mode: import('../types').OperatingModeInfo }>('/api/application-modes/deactivate', {
      method: 'POST',
    }),

  fetchOptimizerStatus: () =>
    request<import('../types').OptimizerStatus>('/api/application-optimizer/status'),

  analyzeAndOptimize: () =>
    request<{
      plan_id: string
      timestamp: string
      active_mode: string | null
      system_cpu_percent: number
      system_ram_percent: number
      recommendations: import('../types').OptimizationRecommendation[]
      total_items: number
      actionable_items: number
      executed_autonomous_actions?: any[]
    }>('/api/application-optimizer/analyze', { method: 'POST' }),

  enableOptimizer: () =>
    request<{ status: string; is_enabled: boolean }>('/api/application-optimizer/enable', { method: 'POST' }),

  disableOptimizer: () =>
    request<{ status: string; is_enabled: boolean }>('/api/application-optimizer/disable', { method: 'POST' }),

  setOptimizerStrategy: (strategy: string) =>
    request<{ status: string; strategy: string }>('/api/application-optimizer/strategy', {
      method: 'POST',
      body: JSON.stringify({ strategy }),
    }),

  emergencyStopOptimizer: () =>
    request<{ status: string; message: string }>('/api/application-optimizer/emergency-stop', { method: 'POST' }),

  fetchOptimizerRecommendations: () =>
    request<import('../types').OptimizationRecommendation[]>('/api/application-optimizer/recommendations'),

  approveOptimizerRecommendation: (planItemId: string) =>
    request<{ status: string; action_result: any }>(`/api/application-optimizer/recommendations/${planItemId}/approve`, {
      method: 'POST',
    }),

  rejectOptimizerRecommendation: (planItemId: string) =>
    request<{ status: string; plan_item_id: string; action: string }>(`/api/application-optimizer/recommendations/${planItemId}/reject`, {
      method: 'POST',
    }),

  fetchOptimizerHistory: (limit = 50) =>
    request<import('../types').OptimizationHistoryItem[]>(`/api/application-optimizer/history?limit=${limit}`),

  // ── Critical Email Alert Notifications ─────────────────────────────────────
  fetchAlertSettings: () =>
    request<{
      email: string
      email_enabled: boolean
      critical_threshold_score: number
      cooldown_seconds: number
      smtp_user?: string
      smtp_password?: string
    }>('/alerts/settings'),

  updateAlertSettings: (data: {
    email: string
    email_enabled?: boolean
    smtp_user?: string
    smtp_password?: string
    phone_number?: string
  }) =>
    request<{
      email: string
      email_enabled: boolean
    }>('/alerts/settings', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  sendTestAlert: (phone_number = '', email = '') =>
    request<{
      id: string
      timestamp: string
      target_phone?: string
      target_email: string
      channel: string
      severity: string
      process_name: string
      message: string
      status: string
      provider: string
      details?: string
    }>('/alerts/test', {
      method: 'POST',
      body: JSON.stringify({ phone_number, email }),
    }),

  fetchAlertHistory: (limit = 50) =>
    request<Array<{
      id: string
      timestamp: string
      target_phone: string
      target_email: string
      channel: string
      severity: string
      process_name: string
      message: string
      status: string
      provider: string
      details?: string
    }>>(`/alerts/history?limit=${limit}`),
}




