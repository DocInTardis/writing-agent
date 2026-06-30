import { writable } from 'svelte/store'
import type { WorkbenchState } from '../flows/workbenchStateMachine'

export const workbenchState = writable<WorkbenchState>('idle')
export const streamHealth = writable<{ stalled: boolean; retries: number }>({ stalled: false, retries: 0 })
export const lastErrorPath = writable<string>('')
