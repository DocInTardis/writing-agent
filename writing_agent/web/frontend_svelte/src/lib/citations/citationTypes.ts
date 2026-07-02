export interface Citation {
  id: string
  author: string
  title: string
  year: string
  source: string
}

export interface VerifyItem {
  id: string
  status: 'verified' | 'possible' | 'not_found' | 'error'
  provider?: string
  score?: number
  matched_title?: string
  matched_year?: string
  matched_source?: string
  reason?: string
}

export interface VerifySummary {
  total: number
  verified: number
  possible: number
  not_found: number
  error: number
}

export type VerifyDebugLevel = 'safe' | 'strict' | 'full'

export interface VerifyDebugItem {
  id: string
  cache_hit: boolean
  query: string
  providers: Record<string, number>
  errors: string[]
  picked_provider: string
  picked_title_score: number
  picked_year_score: number
  picked_total_score: number
  elapsed_ms: number
}

export interface VerifyDebugSampling {
  input_items: number
  output_items: number
  limit: number
  truncated: boolean
}

export interface VerifyDebugRequest {
  persist: boolean
  debug: boolean
  input_count: number
  workers: number
}

export interface VerifyDebugCache {
  size: number
  ttl_s: number
  max_entries: number
  hit: number
  miss: number
  set: number
  expired: number
  evicted: number
}

export interface VerifyObserveCacheDelta {
  hit: number
  miss: number
  set: number
  expired: number
  evicted: number
  hit_rate: number
}

export interface VerifyObserveRequest {
  elapsed_ms: number
  item_count: number
  worker_count: number
  error_count: number
  cache_delta: VerifyObserveCacheDelta
}

export interface VerifyObserveWindow {
  window_s: number
  max_runs: number
  runs: number
  elapsed_ms: { avg: number; p50: number; p95: number; max: number }
  items: { total: number; avg: number; p50: number; p95: number; max: number }
  workers: { avg: number; max: number }
  errors: { total: number; rate_per_run: number }
  cache_delta: VerifyObserveCacheDelta
}

export interface VerifyDebugObserve {
  request: VerifyObserveRequest
  window: VerifyObserveWindow
}

export interface VerifyDebugPayload {
  request: VerifyDebugRequest
  requested_level: VerifyDebugLevel
  level: VerifyDebugLevel
  sanitized: boolean
  rate_limited_full: boolean
  cache: VerifyDebugCache
  observe: VerifyDebugObserve | null
  sampling: VerifyDebugSampling
  elapsed_ms: number
  items: Record<string, VerifyDebugItem>
}

export interface VerifyDebugHistoryEntry {
  id: string
  at_label: string
  level: VerifyDebugLevel
  workers: number
  elapsed_ms: number
  cache_size: number
  cache_max: number
  hit_rate: number
  evict_rate: number
  sampled_output: number
  sampled_input: number
}
