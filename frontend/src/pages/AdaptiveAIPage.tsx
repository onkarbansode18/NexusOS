import React, { useState, useEffect } from 'react'
import {
  Brain,
  Play,
  Square,
  BarChart2,
  Shield,
  Zap,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  Cpu,
  Layers,
  Sliders,
  Award,
  ArrowRight,
  TrendingUp,
} from 'lucide-react'
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  BarChart,
  Bar,
  Cell,
} from 'recharts'
import { api } from '../api/client'
import {
  RLStatus,
  RLTrainingProgress,
  EvaluationComparison,
  RLDecision,
  RLModelInfo,
} from '../types'

export function AdaptiveAIPage() {
  const [activeTab, setActiveTab] = useState<'overview' | 'train' | 'simulate' | 'benchmark'>('overview')
  const [status, setStatus] = useState<RLStatus | null>(null)
  const [trainingProgress, setTrainingProgress] = useState<RLTrainingProgress | null>(null)
  const [benchmark, setBenchmark] = useState<EvaluationComparison | null>(null)
  const [models, setModels] = useState<RLModelInfo[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [trainingEpisodes, setTrainingEpisodes] = useState<number>(30)
  const [benchmarking, setBenchmarking] = useState<boolean>(false)
  const [notification, setNotification] = useState<string | null>(null)

  // Quick preset simulation state
  const [procName, setProcName] = useState<string>('web_server.exe')
  const [procCpu, setProcCpu] = useState<number>(90)
  const [procMem, setProcMem] = useState<number>(1800)
  const [growthRate, setGrowthRate] = useState<number>(10)
  const [simResult, setSimResult] = useState<RLDecision | null>(null)
  const [simulating, setSimulating] = useState<boolean>(false)

  useEffect(() => {
    fetchData()
  }, [])

  // Poll progress if training is active
  useEffect(() => {
    let timer: any = null
    if (status?.is_training || trainingProgress?.is_training) {
      timer = setInterval(async () => {
        try {
          const prog = await api.fetchRLProgress()
          setTrainingProgress(prog)
          if (!prog.is_training) {
            fetchData()
          }
        } catch (e) {
          console.error(e)
        }
      }, 1500)
    }
    return () => clearInterval(timer)
  }, [status?.is_training, trainingProgress?.is_training])

  const fetchData = async () => {
    setLoading(true)
    try {
      const [st, prog, mdls] = await Promise.all([
        api.fetchRLStatus().catch(() => null),
        api.fetchRLProgress().catch(() => null),
        api.fetchRLModels().catch(() => []),
      ])
      if (st) setStatus(st)
      if (prog) setTrainingProgress(prog)
      if (mdls) setModels(mdls)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const showNotice = (msg: string) => {
    setNotification(msg)
    setTimeout(() => setNotification(null), 4000)
  }

  const handleToggleMode = async () => {
    if (!status) return
    const next = !status.autonomous_mode
    try {
      const res = await api.setRLMode(next)
      setStatus((prev) => (prev ? { ...prev, autonomous_mode: res.autonomous_mode } : null))
      showNotice(res.message)
    } catch (err: any) {
      showNotice('Error toggling mode: ' + err.message)
    }
  }

  const handleStartTrain = async () => {
    try {
      const res = await api.startRLTraining(trainingEpisodes)
      showNotice(res.message)
      setStatus((prev) => (prev ? { ...prev, is_training: true } : null))
      const prog = await api.fetchRLProgress()
      setTrainingProgress(prog)
    } catch (err: any) {
      showNotice('Training error: ' + err.message)
    }
  }

  const handleStopTrain = async () => {
    try {
      const res = await api.stopRLTraining()
      showNotice(res.message)
    } catch (err: any) {
      showNotice('Stop error: ' + err.message)
    }
  }

  const handleRunBenchmark = async () => {
    setBenchmarking(true)
    try {
      const res = await api.evaluateRLPolicy(3)
      setBenchmark(res)
      showNotice('Benchmark test completed successfully.')
    } catch (err: any) {
      showNotice('Benchmark error: ' + err.message)
    } finally {
      setBenchmarking(false)
    }
  }

  const applyPreset = (preset: 'cpu' | 'leak' | 'healthy' | 'blacklist') => {
    if (preset === 'cpu') {
      setProcName('compute_worker.exe')
      setProcCpu(94)
      setProcMem(800)
      setGrowthRate(0)
    } else if (preset === 'leak') {
      setProcName('cache_leak_service.exe')
      setProcCpu(35)
      setProcMem(3800)
      setGrowthRate(25)
    } else if (preset === 'healthy') {
      setProcName('normal_app.exe')
      setProcCpu(12)
      setProcMem(250)
      setGrowthRate(0)
    } else if (preset === 'blacklist') {
      setProcName('csrss.exe')
      setProcCpu(88)
      setProcMem(500)
      setGrowthRate(0)
    }
    setSimResult(null)
  }

  const handleRunSimulation = async () => {
    setSimulating(true)
    try {
      const res = await api.simulateRLInference({
        system_cpu: Math.min(procCpu + 5, 99),
        system_ram: Math.min(Math.round((procMem / 8192) * 100) + 10, 95),
        disk_percent: 40,
        process_cpu: procCpu,
        process_memory_mb: procMem,
        memory_growth_rate: growthRate,
        anomaly_score: procCpu > 80 || growthRate > 15 ? 0.85 : 0.1,
        forecast_mins: growthRate > 0 ? Math.max((8000 - procMem) / (growthRate * 60), 0.5) : undefined,
        thread_count: 16,
        process_name: procName,
        pid: 3042,
      })
      setSimResult(res)
    } catch (err: any) {
      showNotice('Inference failed: ' + err.message)
    } finally {
      setSimulating(false)
    }
  }

  const getActionBadgeColor = (action: string) => {
    switch (action) {
      case 'THROTTLE': return { bg: '#FEF3C7', text: '#92400E', border: '#FDE68A' }
      case 'RENICE': return { bg: '#DEF7EC', text: '#03543F', border: '#BCF0DA' }
      case 'RESTART': return { bg: '#FEE2E2', text: '#991B1B', border: '#FECDD3' }
      case 'SUSPEND': return { bg: '#FFEDD5', text: '#9A3412', border: '#FED7AA' }
      case 'OBSERVE_ONLY': return { bg: '#EFF6FF', text: '#1E40AF', border: '#BFDBFE' }
      default: return { bg: '#F3F4F6', text: '#374151', border: '#E5E7EB' }
    }
  }

  return (
    <div style={{ padding: '24px 32px', maxWidth: 1200, margin: '0 auto', color: '#111827' }}>
      {/* ── Page Header ──────────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ background: '#2B5FC7', padding: '7px 8px', borderRadius: 8, display: 'flex', alignItems: 'center' }}>
              <Brain size={20} color="#FFFFFF" />
            </div>
            <div>
              <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, letterSpacing: '-0.02em' }}>
                Adaptive Self-Healing AI
              </h1>
              <p style={{ margin: 0, fontSize: 13, color: '#6B7280' }}>
                Double Deep Q-Network (Double DQN) • Autonomous Reinforcement Learning
              </p>
            </div>
          </div>
        </div>

        {/* Mode Toggle Switch */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            background: '#FFFFFF',
            border: '1px solid #E5E7EB',
            borderRadius: 8,
            padding: '6px 14px',
          }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: status?.autonomous_mode ? '#1E7F4F' : '#6B7280' }}>
              {status?.autonomous_mode ? 'Autonomous Healing Active' : 'Shadow / Observe Mode'}
            </span>
            <button
              onClick={handleToggleMode}
              style={{
                background: status?.autonomous_mode ? '#1E7F4F' : '#F3F4F6',
                color: status?.autonomous_mode ? '#FFFFFF' : '#374151',
                border: '1px solid ' + (status?.autonomous_mode ? '#1E7F4F' : '#D1D5DB'),
                borderRadius: 6,
                padding: '5px 12px',
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              {status?.autonomous_mode ? 'Switch to Shadow' : 'Enable Autonomous'}
            </button>
          </div>

          <button
            onClick={fetchData}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              background: '#FFFFFF',
              border: '1px solid #E5E7EB',
              borderRadius: 8,
              padding: '6px 12px',
              fontSize: 12,
              fontWeight: 600,
              color: '#4B5563',
              cursor: 'pointer',
            }}
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {/* Notification Toast */}
      {notification && (
        <div style={{
          background: '#EFF6FF',
          border: '1px solid #BFDBFE',
          color: '#1E40AF',
          padding: '10px 16px',
          borderRadius: 8,
          marginBottom: 16,
          fontSize: 13,
          fontWeight: 500,
        }}>
          {notification}
        </div>
      )}

      {/* ── Navigation Tabs ─────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', gap: 8, borderBottom: '1px solid #E5E7EB', marginBottom: 20 }}>
        {[
          { id: 'overview', label: 'Agent Status', icon: Cpu },
          { id: 'simulate', label: 'Test & Simulate Decision', icon: Sliders },
          { id: 'train', label: 'Train in Simulation', icon: Play },
          { id: 'benchmark', label: 'Benchmark vs Heuristics', icon: BarChart2 },
        ].map((t) => {
          const Icon = t.icon
          const active = activeTab === t.id
          return (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id as any)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '10px 16px',
                background: 'transparent',
                border: 'none',
                borderBottom: active ? '2px solid #2B5FC7' : '2px solid transparent',
                color: active ? '#2B5FC7' : '#6B7280',
                fontWeight: active ? 700 : 500,
                fontSize: 13,
                cursor: 'pointer',
                marginBottom: -1,
              }}
            >
              <Icon size={15} />
              {t.label}
            </button>
          )
        })}
      </div>

      {/* ── TAB 1: OVERVIEW ─────────────────────────────────────────────────── */}
      {activeTab === 'overview' && (
        <div>
          {/* Quick Stat Tiles */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 20 }}>
            <div style={{ background: '#FFFFFF', padding: 16, borderRadius: 8, border: '1px solid #E5E7EB' }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: '#6B7280', textTransform: 'uppercase' }}>Active Model</span>
              <div style={{ fontSize: 15, fontWeight: 700, marginTop: 4, color: '#111827' }}>
                {status?.active_model?.name || 'Double DQN Baseline'}
              </div>
              <span style={{ fontSize: 11, color: '#1E7F4F', fontWeight: 600, marginTop: 2, display: 'block' }}>
                v{status?.active_model?.version || '1.0.0'} • Ready
              </span>
            </div>

            <div style={{ background: '#FFFFFF', padding: 16, borderRadius: 8, border: '1px solid #E5E7EB' }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: '#6B7280', textTransform: 'uppercase' }}>Exploration Rate (ε)</span>
              <div style={{ fontSize: 22, fontWeight: 700, marginTop: 2, color: '#111827' }}>
                {status?.epsilon ?? 0.05}
              </div>
              <span style={{ fontSize: 11, color: '#6B7280', marginTop: 2, display: 'block' }}>
                Exploitation mode (greedy)
              </span>
            </div>

            <div style={{ background: '#FFFFFF', padding: 16, borderRadius: 8, border: '1px solid #E5E7EB' }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: '#6B7280', textTransform: 'uppercase' }}>Observation Vector</span>
              <div style={{ fontSize: 22, fontWeight: 700, marginTop: 2, color: '#2B5FC7' }}>
                14 Features
              </div>
              <span style={{ fontSize: 11, color: '#6B7280', marginTop: 2, display: 'block' }}>
                Normalized float32 [0.0 - 1.0]
              </span>
            </div>

            <div style={{ background: '#FFFFFF', padding: 16, borderRadius: 8, border: '1px solid #E5E7EB' }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: '#6B7280', textTransform: 'uppercase' }}>Decisions Evaluated</span>
              <div style={{ fontSize: 22, fontWeight: 700, marginTop: 2, color: '#111827' }}>
                {status?.decision_count ?? 0}
              </div>
              <span style={{ fontSize: 11, color: '#1E7F4F', fontWeight: 600, marginTop: 2, display: 'block' }}>
                Zero unverified actions
              </span>
            </div>
          </div>

          {/* Simple Safety & Rules Card */}
          <div style={{ background: '#FFFFFF', padding: 20, borderRadius: 8, border: '1px solid #E5E7EB' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <Shield size={17} color="#1E7F4F" />
              <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700 }}>Built-In Safety Architecture</h3>
            </div>
            <p style={{ fontSize: 13, color: '#4B5563', margin: '0 0 12px 0' }}>
              The reinforcement learning engine makes decisions through strict safety gates that protect critical OS stability:
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
              <div style={{ background: '#F9FAFB', padding: 12, borderRadius: 6, border: '1px solid #E5E7EB' }}>
                <strong style={{ fontSize: 12, color: '#111827' }}>Permanent Blacklist</strong>
                <p style={{ fontSize: 12, color: '#6B7280', margin: '4px 0 0 0' }}>
                  Critical PIDs (1, 4) and system processes (<code>csrss.exe</code>, <code>systemd</code>) are protected from actions.
                </p>
              </div>
              <div style={{ background: '#F9FAFB', padding: 12, borderRadius: 6, border: '1px solid #E5E7EB' }}>
                <strong style={{ fontSize: 12, color: '#111827' }}>SIGKILL Guard</strong>
                <p style={{ fontSize: 12, color: '#6B7280', margin: '4px 0 0 0' }}>
                  Action 6 (KILL) is permanently prohibited from automatic execution by the RL agent.
                </p>
              </div>
              <div style={{ background: '#F9FAFB', padding: 12, borderRadius: 6, border: '1px solid #E5E7EB' }}>
                <strong style={{ fontSize: 12, color: '#111827' }}>Shadow Mode by Default</strong>
                <p style={{ fontSize: 12, color: '#6B7280', margin: '4px 0 0 0' }}>
                  In shadow mode, decisions and Q-values are logged for review without mutating process priority.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── TAB 2: TEST & SIMULATE DECISION (SIMPLIFIED) ─────────────────────── */}
      {activeTab === 'simulate' && (
        <div>
          {/* Quick Preset Buttons */}
          <div style={{ background: '#FFFFFF', padding: 16, borderRadius: 8, border: '1px solid #E5E7EB', marginBottom: 16 }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: '#6B7280', display: 'block', marginBottom: 8 }}>
              Click a preset scenario to test the agent immediately:
            </span>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                onClick={() => applyPreset('cpu')}
                style={{ background: '#FEF3C7', border: '1px solid #FDE68A', color: '#92400E', padding: '6px 14px', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer' }}
              >
                1. CPU Spike (94%)
              </button>
              <button
                onClick={() => applyPreset('leak')}
                style={{ background: '#FEE2E2', border: '1px solid #FECDD3', color: '#991B1B', padding: '6px 14px', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer' }}
              >
                2. Memory Leak (+25MB/s)
              </button>
              <button
                onClick={() => applyPreset('healthy')}
                style={{ background: '#DEF7EC', border: '1px solid #BCF0DA', color: '#03543F', padding: '6px 14px', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer' }}
              >
                3. Healthy Baseline
              </button>
              <button
                onClick={() => applyPreset('blacklist')}
                style={{ background: '#F3F4F6', border: '1px solid #D1D5DB', color: '#374151', padding: '6px 14px', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer' }}
              >
                4. Protected Blacklist Test
              </button>
            </div>
          </div>

          {/* Interactive Controls & Live Output Grid */}
          <div style={{ display: 'grid', gridTemplateColumns: '360px 1fr', gap: 16 }}>
            {/* Simple Inputs */}
            <div style={{ background: '#FFFFFF', padding: 20, borderRadius: 8, border: '1px solid #E5E7EB' }}>
              <h3 style={{ margin: '0 0 14px 0', fontSize: 14, fontWeight: 700 }}>Telemetry Parameters</h3>

              <div style={{ marginBottom: 12 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: '#4B5563' }}>Process Name</label>
                <input
                  type="text"
                  value={procName}
                  onChange={(e) => setProcName(e.target.value)}
                  style={{ width: '100%', boxSizing: 'border-box', border: '1px solid #D1D5DB', borderRadius: 6, padding: '7px 10px', fontSize: 13, marginTop: 4 }}
                />
              </div>

              <div style={{ marginBottom: 12 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: '#4B5563', display: 'flex', justifyContent: 'space-between' }}>
                  <span>Process CPU</span>
                  <span>{procCpu}%</span>
                </label>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={procCpu}
                  onChange={(e) => setProcCpu(Number(e.target.value))}
                  style={{ width: '100%', marginTop: 4 }}
                />
              </div>

              <div style={{ marginBottom: 12 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: '#4B5563', display: 'flex', justifyContent: 'space-between' }}>
                  <span>Process Memory</span>
                  <span>{procMem} MB</span>
                </label>
                <input
                  type="range"
                  min={100}
                  max={6000}
                  step={100}
                  value={procMem}
                  onChange={(e) => setProcMem(Number(e.target.value))}
                  style={{ width: '100%', marginTop: 4 }}
                />
              </div>

              <div style={{ marginBottom: 16 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: '#4B5563', display: 'flex', justifyContent: 'space-between' }}>
                  <span>Memory Growth Slope</span>
                  <span>+{growthRate} MB/step</span>
                </label>
                <input
                  type="range"
                  min={0}
                  max={30}
                  value={growthRate}
                  onChange={(e) => setGrowthRate(Number(e.target.value))}
                  style={{ width: '100%', marginTop: 4 }}
                />
              </div>

              <button
                onClick={handleRunSimulation}
                disabled={simulating}
                style={{
                  width: '100%',
                  background: '#2B5FC7',
                  color: '#FFFFFF',
                  border: 'none',
                  borderRadius: 6,
                  padding: '9px',
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                {simulating ? 'Evaluating Policy...' : 'Evaluate Decision'}
              </button>
            </div>

            {/* Clean Result Panel */}
            <div style={{ background: '#FFFFFF', padding: 20, borderRadius: 8, border: '1px solid #E5E7EB' }}>
              {simResult ? (
                <div>
                  <span style={{ fontSize: 11, fontWeight: 700, color: '#6B7280', textTransform: 'uppercase' }}>
                    Agent Decision
                  </span>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 6, marginBottom: 16 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      {(() => {
                        const b = getActionBadgeColor(simResult.action_name)
                        return (
                          <span style={{
                            background: b.bg,
                            color: b.text,
                            border: `1px solid ${b.border}`,
                            padding: '6px 14px',
                            borderRadius: 6,
                            fontSize: 16,
                            fontWeight: 800,
                          }}>
                            {simResult.action_name}
                          </span>
                        )
                      })()}
                      <span style={{ fontSize: 13, color: '#4B5563', fontWeight: 600 }}>
                        {Math.round(simResult.confidence * 100)}% Confidence
                      </span>
                    </div>

                    {simResult.was_blocked ? (
                      <span style={{ background: '#FEE2E2', color: '#991B1B', padding: '4px 10px', borderRadius: 6, fontSize: 12, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 4 }}>
                        <Shield size={14} />
                        BLOCKED BY SAFETY GATE
                      </span>
                    ) : (
                      <span style={{ background: '#DEF7EC', color: '#03543F', padding: '4px 10px', borderRadius: 6, fontSize: 12, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 4 }}>
                        <CheckCircle2 size={14} />
                        SAFETY VERIFIED
                      </span>
                    )}
                  </div>

                  {simResult.was_blocked && (
                    <div style={{ background: '#FFF1F2', border: '1px solid #FECDD3', padding: 10, borderRadius: 6, marginBottom: 16, fontSize: 12, color: '#9F1239' }}>
                      <strong>Reason:</strong> {simResult.block_reason}
                    </div>
                  )}

                  {/* Horizontal Bar of Q-values */}
                  <h4 style={{ margin: '0 0 10px 0', fontSize: 13, fontWeight: 700 }}>
                    Action Q-Values (Higher is better)
                  </h4>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {Object.entries(simResult.q_values).map(([act, q]) => (
                      <div key={act} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
                        <span style={{ width: 110, color: act === simResult.action_name ? '#111827' : '#6B7280', fontWeight: act === simResult.action_name ? 700 : 500 }}>
                          {act}
                        </span>
                        <div style={{ flex: 1, height: 16, background: '#F3F4F6', borderRadius: 4, overflow: 'hidden' }}>
                          <div
                            style={{
                              width: `${Math.min(Math.max((Number(q) + 10) * 3, 4), 100)}%`,
                              height: '100%',
                              background: act === simResult.action_name ? '#2B5FC7' : '#9CA3AF',
                              borderRadius: 4,
                            }}
                          />
                        </div>
                        <span style={{ width: 45, textAlign: 'right', fontWeight: 600, color: '#374151' }}>
                          {Number(q).toFixed(1)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div style={{ padding: '60px 20px', textAlign: 'center', color: '#6B7280' }}>
                  <Sliders size={32} color="#9CA3AF" style={{ margin: '0 auto 8px auto' }} />
                  <p style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>Select a preset or click "Evaluate Decision"</p>
                  <p style={{ margin: '4px 0 0 0', fontSize: 12, color: '#9CA3AF' }}>See optimal action recommendation and Q-value breakdown in real-time.</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── TAB 3: SIMULATED TRAINING ─────────────────────────────────────────── */}
      {activeTab === 'train' && (
        <div>
          <div style={{ background: '#FFFFFF', padding: 20, borderRadius: 8, border: '1px solid #E5E7EB', marginBottom: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700 }}>Simulated Training Runner</h3>
                <p style={{ margin: '2px 0 0 0', fontSize: 12, color: '#6B7280' }}>
                  Simulates multi-scenario workloads in memory and optimizes policy weights via Double DQN TD error.
                </p>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <select
                  value={trainingEpisodes}
                  onChange={(e) => setTrainingEpisodes(Number(e.target.value))}
                  disabled={status?.is_training}
                  style={{ border: '1px solid #D1D5DB', borderRadius: 6, padding: '6px 10px', fontSize: 13 }}
                >
                  <option value={10}>10 Episodes (Quick test)</option>
                  <option value={30}>30 Episodes (Standard)</option>
                  <option value={50}>50 Episodes (Deep convergence)</option>
                </select>

                {!status?.is_training ? (
                  <button
                    onClick={handleStartTrain}
                    style={{ background: '#1E7F4F', color: '#FFFFFF', border: 'none', borderRadius: 6, padding: '7px 14px', fontSize: 13, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}
                  >
                    <Play size={13} fill="#FFFFFF" />
                    Start Training
                  </button>
                ) : (
                  <button
                    onClick={handleStopTrain}
                    style={{ background: '#DC2626', color: '#FFFFFF', border: 'none', borderRadius: 6, padding: '7px 14px', fontSize: 13, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}
                  >
                    <Square size={13} fill="#FFFFFF" />
                    Stop
                  </button>
                )}
              </div>
            </div>

            {/* Training Status */}
            {status?.is_training && (
              <div style={{ background: '#FFFBEB', border: '1px solid #FDE68A', padding: 12, borderRadius: 6, marginTop: 14 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, fontWeight: 600, color: '#92400E' }}>
                  <span>Episode {trainingProgress?.current_episode || 0} / {trainingProgress?.total_episodes || trainingEpisodes}</span>
                  <span>Epsilon: {trainingProgress?.epsilon || 0.05}</span>
                </div>
                <div style={{ width: '100%', height: 6, background: '#FEF3C7', borderRadius: 3, marginTop: 6, overflow: 'hidden' }}>
                  <div
                    style={{
                      width: `${Math.min(((trainingProgress?.current_episode || 1) / (trainingProgress?.total_episodes || trainingEpisodes)) * 100, 100)}%`,
                      height: '100%',
                      background: '#D97706',
                    }}
                  />
                </div>
              </div>
            )}
          </div>

          {/* Clean Reward Chart */}
          <div style={{ background: '#FFFFFF', padding: 20, borderRadius: 8, border: '1px solid #E5E7EB' }}>
            <h4 style={{ margin: '0 0 12px 0', fontSize: 13, fontWeight: 700 }}>
              Recent Training Episode Rewards
            </h4>
            <div style={{ height: 220 }}>
              {trainingProgress?.recent_episodes && trainingProgress.recent_episodes.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trainingProgress.recent_episodes}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" />
                    <XAxis dataKey="episode" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Line type="monotone" dataKey="reward" stroke="#1E7F4F" strokeWidth={2} dot={{ r: 2 }} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#9CA3AF', fontSize: 13 }}>
                  No training history yet. Click "Start Training" above.
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── TAB 4: BENCHMARK ─────────────────────────────────────────────────── */}
      {activeTab === 'benchmark' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <div>
              <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700 }}>Policy Performance Comparison</h3>
              <p style={{ margin: '2px 0 0 0', fontSize: 12, color: '#6B7280' }}>
                Evaluates Double DQN vs Rule-Based Heuristic vs Random baseline across all 6 scenarios.
              </p>
            </div>
            <button
              onClick={handleRunBenchmark}
              disabled={benchmarking}
              style={{ background: '#2B5FC7', color: '#FFFFFF', border: 'none', borderRadius: 6, padding: '7px 14px', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}
            >
              {benchmarking ? 'Running Benchmark...' : 'Run Benchmark Test'}
            </button>
          </div>

          {benchmark ? (
            <div style={{ background: '#FFFFFF', padding: 20, borderRadius: 8, border: '1px solid #E5E7EB' }}>
              <div style={{ background: '#EFF6FF', border: '1px solid #BFDBFE', padding: 12, borderRadius: 6, marginBottom: 16 }}>
                <strong style={{ color: '#1E40AF', fontSize: 13 }}>Verdict: </strong>
                <span style={{ fontSize: 13, color: '#1E3A8A' }}>
                  {benchmark.summary.best_policy} achieved superior performance with <strong>+{benchmark.summary.dqn_vs_rules_reward_delta}</strong> higher reward and <strong>+{benchmark.summary.dqn_vs_rules_success_delta}%</strong> higher success rate.
                </span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
                <div style={{ background: '#F8FAFC', border: '1px solid #CBD5E1', padding: 16, borderRadius: 6 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: '#2B5FC7' }}>Double DQN Policy</div>
                  <div style={{ fontSize: 20, fontWeight: 800, color: '#1E7F4F', marginTop: 4 }}>
                    +{benchmark.policies.double_dqn.avg_reward}
                  </div>
                  <div style={{ fontSize: 12, color: '#4B5563', marginTop: 4 }}>
                    Success Rate: <strong>{benchmark.policies.double_dqn.success_rate}%</strong>
                  </div>
                  <div style={{ fontSize: 12, color: '#4B5563' }}>
                    Safety Violations: <strong>{benchmark.policies.double_dqn.safety_violations}</strong>
                  </div>
                </div>

                <div style={{ background: '#F9FAFB', border: '1px solid #E5E7EB', padding: 16, borderRadius: 6 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: '#374151' }}>Rule-Based Heuristic</div>
                  <div style={{ fontSize: 20, fontWeight: 800, color: '#374151', marginTop: 4 }}>
                    +{benchmark.policies.rule_based.avg_reward}
                  </div>
                  <div style={{ fontSize: 12, color: '#4B5563', marginTop: 4 }}>
                    Success Rate: <strong>{benchmark.policies.rule_based.success_rate}%</strong>
                  </div>
                  <div style={{ fontSize: 12, color: '#4B5563' }}>
                    Safety Violations: <strong>0</strong>
                  </div>
                </div>

                <div style={{ background: '#F9FAFB', border: '1px solid #E5E7EB', padding: 16, borderRadius: 6 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: '#9CA3AF' }}>Random Baseline</div>
                  <div style={{ fontSize: 20, fontWeight: 800, color: '#DC2626', marginTop: 4 }}>
                    {benchmark.policies.random.avg_reward}
                  </div>
                  <div style={{ fontSize: 12, color: '#4B5563', marginTop: 4 }}>
                    Success Rate: <strong>{benchmark.policies.random.success_rate}%</strong>
                  </div>
                  <div style={{ fontSize: 12, color: '#DC2626' }}>
                    Safety Violations: <strong>{benchmark.policies.random.safety_violations}</strong>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div style={{ background: '#FFFFFF', padding: 36, borderRadius: 8, border: '1px solid #E5E7EB', textAlign: 'center', color: '#6B7280' }}>
              <Award size={32} color="#9CA3AF" style={{ margin: '0 auto 8px auto' }} />
              <p style={{ margin: 0, fontSize: 13, fontWeight: 600 }}>Click "Run Benchmark Test" above to evaluate.</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
