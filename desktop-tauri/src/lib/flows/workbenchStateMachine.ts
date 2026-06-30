export type WorkbenchState = 'idle' | 'generating' | 'editing' | 'recovering' | 'failed'

export interface WorkbenchTransition {
  from: WorkbenchState
  to: WorkbenchState
  reason: string
}

const ALLOWED: Record<WorkbenchState, WorkbenchState[]> = {
  idle: ['generating', 'editing', 'recovering'],
  generating: ['editing', 'failed', 'idle'],
  editing: ['generating', 'idle', 'failed'],
  recovering: ['editing', 'failed', 'idle'],
  failed: ['recovering', 'idle']
}

export function canTransition(from: WorkbenchState, to: WorkbenchState): boolean {
  return (ALLOWED[from] || []).includes(to)
}

export function transition(from: WorkbenchState, to: WorkbenchState, reason: string): WorkbenchTransition {
  if (!canTransition(from, to)) {
    return { from, to: 'failed', reason: `invalid_transition:${from}->${to}:${reason}` }
  }
  return { from, to, reason }
}
