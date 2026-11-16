import React, { useEffect } from 'react'
import { AlertTriangle, CheckCircle2, Loader2, XCircle } from 'lucide-react'
import { useNexusStore } from '../store'

export function ActionConfirmationModal() {
  const {
    confirmingAction,
    setConfirmingAction,
    executeAction,
    executingAction,
    lastActionResult,
    clearLastActionResult,
    policy,
  } = useNexusStore()

  const isLiveMode = !policy.simulation_mode

  // Auto-dismiss the result toast after 5 seconds
  useEffect(() => {
    if (lastActionResult) {
      const timer = setTimeout(() => clearLastActionResult(), 5000)
      return () => clearTimeout(timer)
    }
  }, [lastActionResult, clearLastActionResult])

  // Result Toast (bottom-right, white, 1px border, 3px left border in status color)
  if (!confirmingAction && lastActionResult) {
    const isSuccess = lastActionResult.success
    const borderColor = isSuccess ? 'var(--ok)' : 'var(--critical)'

    return (
      <div className="fixed bottom-6 right-6 z-50 max-w-sm w-full">
        <div
          className="bg-surface border border-border rounded p-3 flex items-start gap-3"
          style={{
            borderLeftWidth: 3,
            borderLeftColor: borderColor,
            boxShadow: '0 8px 24px rgba(16,24,40,.12)',
          }}
        >
          {isSuccess ? (
            <CheckCircle2 size={16} className="text-ok flex-shrink-0 mt-0.5" strokeWidth={1.75} />
          ) : (
            <XCircle size={16} className="text-critical flex-shrink-0 mt-0.5" strokeWidth={1.75} />
          )}
          <div>
            <p className="text-[13px] font-medium text-text">{lastActionResult.message}</p>
            <p className="text-[12px] text-text-muted mt-0.5">
              {lastActionResult.simulated
                ? 'Simulation mode — no OS change was made'
                : 'Live mode — executed on host process'}
            </p>
          </div>
        </div>
      </div>
    )
  }

  if (!confirmingAction) return null

  const { actionType, actionTitle, pid, processName, incidentId } = confirmingAction

  const handleApprove = () => {
    executeAction(actionType, pid || 0, processName || 'process', incidentId)
  }

  const isDestructive = ['kill', 'restart', 'suspend'].includes(actionType)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop: rgba(16,24,40,.40), no blur */}
      <div
        className="fixed inset-0 dialog-overlay"
        onClick={() => !executingAction && setConfirmingAction(null)}
      />

      {/* Modal Dialog: 420px, 8px radius */}
      <div
        className="relative bg-surface rounded-lg max-w-[420px] w-full p-5 border border-border z-10 space-y-4"
        style={{ boxShadow: '0 8px 24px rgba(16,24,40,.12)' }}
        role="dialog"
        aria-modal="true"
      >
        {/* Header */}
        <div className="flex items-center gap-2">
          {isDestructive ? (
            <AlertTriangle size={18} className="text-critical flex-shrink-0" strokeWidth={1.75} />
          ) : null}
          <h2 className="text-[15px] font-semibold text-text">
            Confirm {actionTitle}
          </h2>
        </div>

        {/* Live / Simulated Context */}
        {isLiveMode ? (
          <div className="p-2.5 rounded border border-critical-border bg-critical-bg text-critical text-[12px]">
            <span className="font-semibold block mb-0.5">Live mode active</span>
            This action will execute directly on the operating system process.
          </div>
        ) : (
          <div className="p-2.5 rounded border border-border bg-surface-2 text-text-muted text-[12px]">
            <span className="font-semibold text-text block mb-0.5">Simulation mode active</span>
            This action will be logged only. No OS state will be changed.
          </div>
        )}

        {/* Process Details */}
        <div className="p-2.5 rounded border border-border bg-surface-2 text-[12px] font-mono space-y-1">
          <div className="flex justify-between">
            <span className="text-text-muted font-sans">Target process:</span>
            <span className="text-text font-medium">{processName}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-text-muted font-sans">PID:</span>
            <span className="text-text font-medium">{pid}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-text-muted font-sans">Action:</span>
            <span className="text-text font-medium">{actionType}</span>
          </div>
        </div>

        {/* Action description note */}
        {actionType === 'kill' && (
          <p className="text-[12px] text-text-muted leading-relaxed">
            The target process will be terminated immediately via SIGKILL / TerminateProcess. Unsaved state may be lost.
          </p>
        )}
        {actionType === 'restart' && (
          <p className="text-[12px] text-text-muted leading-relaxed">
            The process will be stopped and restarted with its original command-line arguments.
          </p>
        )}
        {actionType === 'throttle' && (
          <p className="text-[12px] text-text-muted leading-relaxed">
            The process scheduling priority will be lowered to idle background class.
          </p>
        )}

        {/* Footer Actions */}
        <div className="flex items-center justify-end gap-2 pt-2 border-t border-border">
          <button
            type="button"
            onClick={() => setConfirmingAction(null)}
            disabled={executingAction}
            className="btn-secondary h-8 px-3 text-[12px]"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleApprove}
            disabled={executingAction}
            className={isDestructive ? 'btn-danger h-8 px-3 text-[12px]' : 'btn-primary h-8 px-3 text-[12px]'}
          >
            {executingAction ? (
              <>
                <Loader2 size={13} className="animate-spin" />
                <span>Executing…</span>
              </>
            ) : (
              <span>Confirm {actionTitle}</span>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
