/**
 * Nexus — shared TypeScript types matching reference design & backend API.
 */

// ── System vitals ────────────────────────────────────────────────────────────
export interface SystemMetrics {
  timestamp: string          // ISO-8601
  cpu_percent: number        // 0–100
  cpu_freq_mhz: number
  ram_used_mb: number
  ram_total_mb: number
  ram_percent: number
  disk_used_gb: number
  disk_total_gb: number
  disk_percent: number
  net_bytes_sent: number
  net_bytes_recv: number
}

// ── Per-process snapshot ──────────────────────────────────────────────────────
export type ProcessHealthStatus = 'healthy' | 'under_observation' | 'warning' | 'critical' | 'unknown'

export interface ProcessSnapshot {
  pid: number
  name: string
  cpu_percent: number
  memory_mb: number
  memory_percent: number
  status: string             // 'running' | 'sleeping' | 'zombie' | …
  username: string
  created_at: string
  health_status: ProcessHealthStatus
  anomaly_score?: number     // -1 = anomalous (Isolation Forest)
  cmdline?: string
  uptime?: string
  threads?: number
  memory_trend?: number[]    // array of MB points for sparkline
}

// ── Incident ─────────────────────────────────────────────────────────────────
export type IncidentSeverity = 'info' | 'warning' | 'critical'
export type IncidentStatus = 'open' | 'investigating' | 'monitoring' | 'healing' | 'resolved' | 'dismissed'
export type ActionType =
  | 'renice'
  | 'throttle'
  | 'suspend'
  | 'restart'
  | 'kill'
  | 'observe'
  | 'alert_only'
  | 'no_action'

export interface HealingAction {
  id: string
  incident_id: string
  action_type: ActionType
  action_title?: string
  pid: number
  process_name: string
  simulated: boolean           // true = Simulation Mode
  status_text?: 'Executed' | 'No action' | 'Simulated' | 'Failed'
  before_cpu: number
  before_memory_mb: number
  after_cpu?: number
  after_memory_mb?: number
  executed_at: string
  reason: string
}

export interface IncidentTimelineItem {
  time: string
  text: string
  step: 'SENSE' | 'THINK' | 'DECIDE' | 'ACT' | 'RECORD'
}

export interface Incident {
  id: string
  inc_number?: string        // e.g. "INC-2041"
  pid: number
  process_name: string
  title?: string
  category?: string           // e.g. "Memory leak", "CPU saturation", "Transient I/O"
  severity: IncidentSeverity
  status: IncidentStatus
  description: string        // plain-English explanation
  prediction?: string        // e.g. "RAM exhausted in ~6 min"
  recommended_action?: ActionType
  recommendation_text?: string
  anomaly_score: number
  detected_at: string
  resolved_at?: string
  what_happened?: string
  why_detected?: string
  ml_explanation?: string
  nl_summary?: string
  nl_slack_message?: string
  before_memory?: string
  after_memory?: string
  slope?: string
  current_pipeline_step?: 'Sense' | 'Think' | 'Decide' | 'Act' | 'Record'
  timeline?: IncidentTimelineItem[]
  actions: HealingAction[]
}

// ── Policy settings ───────────────────────────────────────────────────────────
export interface Policy {
  simulation_mode: boolean
  cpu_warning_pct: number
  cpu_critical_pct: number
  ram_warning_pct: number
  ram_critical_pct: number
  disk_warning_pct: number
  disk_critical_pct: number
  process_whitelist: string[]  // process names safe to act on in Live Mode
  process_blacklist: string[]  // process names that must NEVER be touched
}

// ── WebSocket envelope ────────────────────────────────────────────────────────
export type WsEventType = 'metrics' | 'incident' | 'action' | 'policy_update'

export interface WsMessage<T = unknown> {
  event: WsEventType
  data: T
  ts: string
}

// ── Auth ─────────────────────────────────────────────────────────────────────
export interface AuthToken {
  access_token: string
  token_type: 'bearer'
}

// ── Adaptive AI (Double DQN) Types ───────────────────────────────────────────
export interface RLModelInfo {
  model_id: string
  name: string
  version: string
  filepath: string
  created_at: string
  episodes_trained: number
  best_reward: number
  success_rate: number
  is_active: boolean
  file_exists?: boolean
  notes?: string
}

export interface RLStatus {
  status: string
  autonomous_mode: boolean
  mode_label: string
  device: string
  epsilon: number
  is_training: boolean
  decision_count: number
  active_model: RLModelInfo | null
  models_available: number
  state_dimension: number
  action_dimension: number
  action_names: string[]
}

export interface RLTrainingEpisode {
  episode: number
  scenario: string
  reward: number
  steps: number
  loss: number
  epsilon: number
  success: boolean
  duration: number
}

export interface RLTrainingProgress {
  is_training: boolean
  status: string
  current_episode: number
  total_episodes: number
  epsilon: number
  best_reward: number
  buffer_size: number
  recent_episodes: RLTrainingEpisode[]
}

export interface RLDecision {
  pid: number
  process_name: string
  action_index: number
  action_name: string
  nexus_action: string
  effective_action: string
  confidence: number
  is_exploration: boolean
  q_values: Record<string, number>
  probabilities: Record<string, number>
  state_vector: number[]
  state_summary: {
    system_cpu: number
    system_ram: number
    process_cpu: number
    process_memory_mb: number
    anomaly_score: number
    urgency: number
    health: number
  }
  was_blocked: boolean
  block_reason: string | null
  autonomous_mode: boolean
}

export interface PolicyBenchmarkData {
  policy_name: string
  avg_reward: number
  success_rate: number
  avg_steps: number
  recovery_rate: number
  invasive_action_rate: number
  safety_violations: number
  episodes_evaluated: number
  scenario_breakdown: Record<string, { avg_reward: number; success_rate: number }>
}

export interface EvaluationComparison {
  summary: {
    dqn_vs_rules_reward_delta: number
    dqn_vs_rules_success_delta: number
    best_policy: string
    episodes_per_scenario: number
    total_episodes: number
  }
  policies: {
    double_dqn: PolicyBenchmarkData
    rule_based: PolicyBenchmarkData
    random: PolicyBenchmarkData
  }
}

export interface SimulateInferencePayload {
  scenario?: string
  system_cpu: number
  system_ram: number
  disk_percent: number
  process_cpu: number
  process_memory_mb: number
  memory_growth_rate: number
  anomaly_score: number
  forecast_mins?: number
  thread_count: number
  process_name: string
  pid: number
}

// ── Application-Aware Resource Management Types ──────────────────────────────
export interface ApplicationProcessDetail {
  pid: number
  ppid: number | null
  name: string
  exe: string | null
  cmdline: string[] | null
  cpu_percent: number
  memory_mb: number
  memory_percent: number
  num_threads: number
  status: string
  created_at: string
  priority: string | null
  read_bytes: number | null
  write_bytes: number | null
}

export interface ApplicationProfileData {
  importance: string
  is_protected: boolean
  preferred_priority: string
  allowed_actions: string[]
  associated_modes: string[]
  user_notes?: string
}

export interface ApplicationItem {
  app_id: string
  name: string
  category: string
  executable_path: string | null
  root_pid: number
  pids: number[]
  process_count: number
  processes: ApplicationProcessDetail[]
  total_cpu_percent: number
  total_memory_mb: number
  total_memory_percent: number
  total_threads: number
  is_system: boolean
  is_protected: boolean
  started_at: string
  status: string
  user_classified: boolean
  importance?: string
  associated_modes?: string[]
  profile?: ApplicationProfileData
}

export interface ApplicationProfile {
  id: string
  app_id: string
  name: string
  executable_path?: string
  category: string
  importance: string
  preferred_priority: string
  is_protected: boolean
  is_enabled: boolean
  allowed_actions: string[]
  max_cpu_percent?: number
  max_memory_mb?: number
  associated_modes: string[]
  user_notes?: string
  updated_at?: string
}

export interface OperatingModeInfo {
  is_active: boolean
  mode_id: string | null
  name: string
  description: string
  icon?: string
  target_app_id?: string | null
  activated_at?: string | null
  configuration?: Record<string, any>
  battery?: {
    has_battery: boolean
    percent: number
    power_plugged: boolean
    secsleft: number
    status_text: string
  }
  modified_processes_count?: number
}

export interface OperatingModeCardItem {
  id: string
  name: string
  description: string
  icon: string
  is_active: boolean
  protected_categories: string[]
  protected_apps: string[]
  target_app_id: string | null
  activated_at: string | null
}

export interface OptimizationRecommendation {
  plan_item_id: string
  app_id: string
  app_name: string
  pid: number
  process_name: string
  current_priority: string
  proposed_action: string
  reason: string
  expected_effect: string
  risk_level: string
  safety_validation: string
  is_safe: boolean
  current_cpu: number
  current_mem_mb: number
}

export interface OptimizationHistoryItem {
  id: string
  app_id?: string
  app_name: string
  pid: number
  action_type: string
  operating_mode?: string
  status: string
  risk_level: string
  reason: string
  before_priority?: string
  after_priority?: string
  before_cpu?: number
  after_cpu?: number
  before_memory_mb?: number
  after_memory_mb?: number
  executed_at?: string
  created_at?: string
}

export interface OptimizerStatus {
  is_enabled: boolean
  strategy: string
  pending_recommendations_count: number
  active_mode: string | null
  action_cooldown_seconds: number
}


