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
