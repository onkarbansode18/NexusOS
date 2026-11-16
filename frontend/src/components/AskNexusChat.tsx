import React, { useState, useRef, useEffect } from 'react'
import { MessageCircle, X, Send, Bot, User, Loader2, Sparkles } from 'lucide-react'
import { useNexusStore } from '../store'

interface ChatMsg {
  role: 'user' | 'assistant'
  content: string
  suggested?: string[]
}

const BASE = (import.meta as any).env?.VITE_API_BASE_URL ?? 'http://localhost:8000'

const SUGGESTIONS = [
  'Why is my PC slow right now?',
  'Which process is using the most RAM?',
  'Is it safe to kill this process?',
  'How do I free up memory?',
  'What happened in the last 30 minutes?',
]

export function AskNexusChat() {
  const [open, setOpen] = useState(false)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [history, setHistory] = useState<ChatMsg[]>([
    {
      role: 'assistant',
      content: "Hi! I'm Nexus AI 👋 Ask me anything about your system — like why it's slow, which process is hogging memory, or whether it's safe to kill something.",
      suggested: SUGGESTIONS.slice(0, 3),
    },
  ])
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const { metrics, processes, incidents, recentActions } = useNexusStore()

  useEffect(() => {
    if (open) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }, [open, history])

  const buildContext = () => ({
    cpu_percent: metrics?.cpu_percent ?? 0,
    ram_percent: metrics?.ram_percent ?? 0,
    ram_used_mb: metrics?.ram_used_mb ?? 0,
    ram_total_mb: metrics?.ram_total_mb ?? 8192,
    disk_percent: metrics?.disk_percent ?? 0,
    top_processes: processes.slice(0, 10).map((p) => ({
      pid: p.pid,
      name: p.name,
      cpu_percent: p.cpu_percent,
      memory_mb: p.memory_mb,
      health_status: p.health_status,
    })),
    incidents: incidents.slice(0, 5).map((i) => ({
      title: i.title,
      severity: i.severity,
      status: i.status,
      description: i.description,
    })),
    recent_actions: recentActions.slice(0, 3).map((a) => ({
      action_type: a.action_type,
      process_name: a.process_name,
      executed_at: a.executed_at,
    })),
  })

  const sendMessage = async (question: string) => {
    if (!question.trim() || loading) return
    const userMsg: ChatMsg = { role: 'user', content: question }
    const newHistory = [...history, userMsg]
    setHistory(newHistory)
    setInput('')
    setLoading(true)

    try {
      const token = localStorage.getItem('nexus_token')
      const resp = await fetch(`${BASE}/chatbot/ask`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          question,
          history: newHistory.slice(-6).map((m) => ({ role: m.role, content: m.content })),
          context: buildContext(),
        }),
      })

      if (!resp.ok) throw new Error('API error')
      const data = await resp.json()
      setHistory((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: data.answer,
          suggested: data.suggested_actions?.length ? data.suggested_actions : undefined,
        },
      ])
    } catch {
      setHistory((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: "Sorry, I couldn't reach the backend right now. Please check that the Nexus server is running.",
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage(input)
    }
  }

  return (
    <>
      {/* Floating Trigger Button */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        title="Ask Nexus AI"
        style={{
          position: 'fixed',
          bottom: 28,
          right: 28,
          width: 52,
          height: 52,
          borderRadius: '50%',
          background: open ? '#111827' : 'linear-gradient(135deg, #2563EB, #7C3AED)',
          border: 'none',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: '0 4px 20px rgba(37,99,235,0.4)',
          zIndex: 10000,
          transition: 'all 0.2s ease',
          color: '#fff',
        }}
      >
        {open ? <X size={22} /> : <MessageCircle size={22} />}
      </button>

      {/* Chat Panel */}
      {open && (
        <div
          style={{
            position: 'fixed',
            bottom: 92,
            right: 28,
            width: 380,
            height: 520,
            background: '#FFFFFF',
            borderRadius: 16,
            border: '1px solid #E5E7EB',
            boxShadow: '0 20px 60px rgba(0,0,0,0.15)',
            display: 'flex',
            flexDirection: 'column',
            zIndex: 9999,
            overflow: 'hidden',
            animation: 'slideUp 0.2s ease',
          }}
        >
          {/* Header */}
          <div
            style={{
              padding: '14px 16px',
              background: 'linear-gradient(135deg, #2563EB, #7C3AED)',
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              flexShrink: 0,
            }}
          >
            <Sparkles size={18} color="#fff" />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 14, fontWeight: 700, color: '#fff' }}>Ask Nexus AI</div>
              <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.7)' }}>
                Powered by Gemini • System-aware
              </div>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(255,255,255,0.7)', padding: 2 }}
            >
              <X size={16} />
            </button>
          </div>

          {/* Messages */}
          <div
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: '14px 14px 8px',
              display: 'flex',
              flexDirection: 'column',
              gap: 10,
            }}
          >
            {history.map((msg, i) => (
              <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <div
                  style={{
                    display: 'flex',
                    gap: 8,
                    alignItems: 'flex-start',
                    flexDirection: msg.role === 'user' ? 'row-reverse' : 'row',
                  }}
                >
                  {/* Avatar */}
                  <div
                    style={{
                      width: 28,
                      height: 28,
                      borderRadius: '50%',
                      background: msg.role === 'user' ? '#E0E7FF' : 'linear-gradient(135deg, #2563EB, #7C3AED)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                    }}
                  >
                    {msg.role === 'user' ? (
                      <User size={14} color="#2563EB" />
                    ) : (
                      <Bot size={14} color="#fff" />
                    )}
                  </div>
                  {/* Bubble */}
                  <div
                    style={{
                      maxWidth: '78%',
                      padding: '9px 12px',
                      borderRadius: msg.role === 'user' ? '14px 4px 14px 14px' : '4px 14px 14px 14px',
                      background: msg.role === 'user' ? '#EFF6FF' : '#F9FAFB',
                      border: `1px solid ${msg.role === 'user' ? '#BFDBFE' : '#E5E7EB'}`,
                      fontSize: 13,
                      color: '#111827',
                      lineHeight: 1.5,
                      whiteSpace: 'pre-wrap',
                    }}
                  >
                    {msg.content}
                  </div>
                </div>

                {/* Suggested actions chips */}
                {msg.suggested && msg.suggested.length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, paddingLeft: 36 }}>
                    {msg.suggested.map((s, j) => (
                      <button
                        key={j}
                        type="button"
                        onClick={() => sendMessage(s)}
                        style={{
                          padding: '4px 10px',
                          borderRadius: 20,
                          border: '1px solid #BFDBFE',
                          background: '#EFF6FF',
                          color: '#2563EB',
                          fontSize: 11,
                          fontWeight: 500,
                          cursor: 'pointer',
                          transition: 'all 0.15s ease',
                        }}
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}

            {loading && (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <div
                  style={{
                    width: 28,
                    height: 28,
                    borderRadius: '50%',
                    background: 'linear-gradient(135deg, #2563EB, #7C3AED)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}
                >
                  <Bot size={14} color="#fff" />
                </div>
                <div
                  style={{
                    padding: '9px 12px',
                    borderRadius: '4px 14px 14px 14px',
                    background: '#F9FAFB',
                    border: '1px solid #E5E7EB',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    fontSize: 12,
                    color: '#6B7280',
                  }}
                >
                  <Loader2 size={13} className="animate-spin" />
                  Thinking...
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input Bar */}
          <div
            style={{
              padding: '10px 12px',
              borderTop: '1px solid #F3F4F6',
              display: 'flex',
              gap: 8,
              alignItems: 'center',
              flexShrink: 0,
              background: '#FAFAFA',
            }}
          >
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about your system..."
              disabled={loading}
              style={{
                flex: 1,
                height: 36,
                padding: '0 12px',
                borderRadius: 8,
                border: '1px solid #E5E7EB',
                fontSize: 13,
                color: '#111827',
                background: '#FFFFFF',
                outline: 'none',
              }}
            />
            <button
              type="button"
              onClick={() => sendMessage(input)}
              disabled={loading || !input.trim()}
              style={{
                width: 36,
                height: 36,
                borderRadius: 8,
                background: input.trim() && !loading ? 'linear-gradient(135deg, #2563EB, #7C3AED)' : '#E5E7EB',
                border: 'none',
                cursor: input.trim() && !loading ? 'pointer' : 'not-allowed',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
                transition: 'background 0.2s ease',
              }}
            >
              <Send size={15} color={input.trim() && !loading ? '#fff' : '#9CA3AF'} />
            </button>
          </div>
        </div>
      )}
    </>
  )
}

