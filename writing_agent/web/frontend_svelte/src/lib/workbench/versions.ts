export function formatVersionTime(ts: number) {
  if (!ts) return ''
  try {
    return new Date(ts * 1000).toLocaleString()
  } catch {
    return String(ts)
  }
}

export function formatVersionSummary(summary: any) {
  if (!summary || typeof summary !== 'object') return ''
  const ins = Number(summary.insert || 0)
  const del = Number(summary.delete || 0)
  const rep = Number(summary.replace || 0)
  const parts: string[] = []
  if (ins) parts.push(`新增${ins}`)
  if (rep) parts.push(`修改${rep}`)
  if (del) parts.push(`删除${del}`)
  return parts.join(' / ')
}

export function buildVersionGroups(list: Array<any>) {
  const groups: Array<any> = []
  let current: any = null
  list.forEach((v) => {
    const tags = Array.isArray(v?.tags) ? v.tags : []
    const kind = v?.kind || (tags.includes('major') ? 'major' : tags.includes('minor') ? 'minor' : '')
    const isMajor = kind === 'major'
    if (isMajor || !current) {
      current = { major: v, minors: [] }
      groups.push(current)
    } else {
      current.minors.push(v)
    }
  })
  return groups
}
