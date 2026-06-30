export const HEADING_GLUE_PREFIXES = [
  '摘要',
  '引言',
  '绪论',
  '背景',
  '研究背景',
  '目标',
  '范围',
  '术语',
  '定义',
  '需求',
  '需求分析',
  '总体设计',
  '系统设计',
  '架构设计',
  '详细设计',
  '模块设计',
  '实现',
  '关键技术',
  '应用',
  '方法',
  '数据',
  '分析',
  '讨论',
  '评估',
  '结果',
  '结论',
  '总结',
  '展望',
  '风险',
  '问题',
  '计划',
  '本周工作',
  '下周计划',
  '问题与风险',
  '需协助事项',
  '参考文献',
  '附录',
  '致谢'
]

export const HEADING_GLUE_PUNCT = /[。！？!?；;，、]/

const HEADING_GLUE_BODY_STARTERS = [
  '本文',
  '本研究',
  '本项目',
  '作为',
  '通过',
  '基于',
  '采用',
  '利用',
  '借助',
  '随着',
  '本周',
  '本次',
  '本节',
  '我们',
  '由于',
  '因此',
  '此外',
  '同时',
  '首先',
  '其次',
  '最后'
]

const HEADING_GLUE_BODY_MARKERS = [
  '作为',
  '尽管',
  '通过',
  '基于',
  '采用',
  '利用',
  '借助',
  '随着',
  '为了',
  '针对',
  '此外',
  '同时',
  '首先',
  '其次',
  '最后'
]

const HEADING_GLUE_TRIM_SUFFIXES = ['模型', '系统']

function trimHeadingGlueLeft(text: string): string {
  return String(text || '').replace(/^[：:、\-—\s]+/g, '').trim()
}

function trimHeadingGlueRight(text: string): string {
  return String(text || '').replace(/[：:、\-—\s]+$/g, '').trim()
}

function shiftRepeatedHeadingTail(left: string, right: string): { left: string; right: string } {
  let l = String(left || '').trim()
  let r = String(right || '').trim()
  if (!l || !r || l.length < 8) return { left: l, right: r }

  const maxLen = Math.min(8, Math.floor(l.length / 2))
  for (let size = maxLen; size >= 3; size -= 1) {
    const suffix = l.slice(-size)
    if (!suffix || !l.startsWith(suffix)) continue
    const candidate = l.slice(0, l.length - size).trim()
    if (!candidate || candidate.length < 4) continue
    if (r.startsWith(suffix)) return { left: candidate, right: r }
    return { left: candidate, right: `${suffix}${r}` }
  }
  return { left: l, right: r }
}

export function looksLikeBodySentence(text: string): boolean {
  const s = String(text || '').trim()
  if (!s) return false
  if (s.length >= 24) return true
  if (HEADING_GLUE_PUNCT.test(s)) return true

  const starterHit = HEADING_GLUE_BODY_STARTERS.some((starter) => {
    const idx = s.indexOf(starter)
    return idx >= 1 && idx <= 18
  })
  if (starterHit) return true

  if (s.length >= 14 && /(是|为|通过|随着|由于|因此|并且|能够|可以|实现|提升|优化)/.test(s)) {
    return true
  }
  return false
}

export function splitHeadingGlue(text: string): { heading: string; rest: string } | null {
  const raw = String(text || '').trim()
  if (!raw) return null
  if (raw.length <= 12 && !HEADING_GLUE_PUNCT.test(raw)) return null

  const colon = /^(.{1,12})[:：](.+)$/.exec(raw)
  if (colon) {
    const left = String(colon[1] || '').trim()
    const right = String(colon[2] || '').trim()
    if (left && right && (HEADING_GLUE_PUNCT.test(right) || right.length >= 12)) {
      return { heading: trimHeadingGlueRight(left), rest: trimHeadingGlueLeft(right) }
    }
  }

  const repeated = /^(.{2,10})\s*\1(.+)$/.exec(raw)
  if (repeated) {
    const left = String(repeated[1] || '').trim()
    const right = String(repeated[2] || '').trim()
    if (left && right && (HEADING_GLUE_PUNCT.test(right) || right.length >= 6)) {
      return { heading: trimHeadingGlueRight(left), rest: trimHeadingGlueLeft(right) }
    }
  }

  const prefixes = HEADING_GLUE_PREFIXES.slice().sort((a, b) => b.length - a.length)
  for (const prefix of prefixes) {
    if (raw.startsWith(prefix) && raw.length > prefix.length + 1) {
      const rest = trimHeadingGlueLeft(raw.slice(prefix.length).trim())
      if (rest && (HEADING_GLUE_PUNCT.test(rest) || rest.length >= 12)) {
        return { heading: prefix, rest }
      }
    }
  }

  for (const kw of prefixes) {
    const idx = raw.indexOf(kw)
    if (idx <= 0) continue
    const headEnd = idx + kw.length
    if (headEnd > 10) continue
    const left = raw.slice(0, headEnd).trim()
    const rest = trimHeadingGlueLeft(raw.slice(headEnd).trim())
    if (left && rest && (HEADING_GLUE_PUNCT.test(rest) || rest.length >= 12)) {
      return { heading: trimHeadingGlueRight(left), rest }
    }
  }

  const numIdx = raw.search(/\b\d+(?:\.\d+)+\b/)
  if (numIdx > 0 && numIdx <= 12) {
    const left = raw.slice(0, numIdx).trim()
    const rest = trimHeadingGlueLeft(raw.slice(numIdx).trim())
    if (left && rest && (HEADING_GLUE_PUNCT.test(rest) || rest.length >= 12)) {
      return { heading: trimHeadingGlueRight(left), rest }
    }
  }

  for (const marker of HEADING_GLUE_BODY_MARKERS) {
    const idx = raw.indexOf(marker)
    if (idx < 2 || idx > 24) continue
    let left = raw.slice(0, idx).trim()
    let right = trimHeadingGlueLeft(raw.slice(idx).trim())
    if (!left || !right) continue
    if (left.length > 20 || right.length < 6) continue
    if (['作为', '通过', '基于', '采用', '利用', '借助'].includes(marker)) {
      const shifted = shiftRepeatedHeadingTail(left, right)
      left = shifted.left
      right = shifted.right
      for (const suffix of HEADING_GLUE_TRIM_SUFFIXES) {
        if (left.endsWith(suffix) && left.length - suffix.length >= 4) {
          right = `${suffix}${right}`
          left = left.slice(0, left.length - suffix.length).trim()
          break
        }
      }
    }
    if (left && left.length <= 16 && !HEADING_GLUE_PUNCT.test(left)) {
      return { heading: trimHeadingGlueRight(left), rest: right }
    }
  }

  for (const starter of HEADING_GLUE_BODY_STARTERS) {
    const idx = raw.indexOf(starter)
    if (idx > 0 && idx <= 10) {
      const left = raw.slice(0, idx).trim()
      const right = trimHeadingGlueLeft(raw.slice(idx).trim())
      if (left && right && right.length >= 6 && !HEADING_GLUE_PUNCT.test(left)) {
        return { heading: trimHeadingGlueRight(left), rest: right }
      }
    }
  }

  return null
}

export function splitParagraphForBlocks(text: string): string[] {
  const src = String(text || '').replace(/\r/g, '').trim()
  if (!src) return []

  const hardParts = src
    .split(/\n+/)
    .map((part) => part.trim())
    .filter(Boolean)

  const out: string[] = []
  const splitChunk = (chunk: string) => {
    const clean = String(chunk || '').trim()
    if (!clean) return
    if (clean.length <= 92) {
      out.push(clean)
      return
    }

    let parts = clean
      .split(/(?<=[。！？!?；;])(?=[^”’」』）》】\]\s])/g)
      .map((part) => part.trim())
      .filter(Boolean)

    if (parts.length <= 1 && clean.length > 118) {
      const commas: number[] = []
      for (let i = 0; i < clean.length; i += 1) {
        const ch = clean[i]
        if (ch === '，' || ch === ',' || ch === '、') commas.push(i)
      }
      if (commas.length) {
        const target = Math.floor(clean.length / 2)
        let pick = commas[0]
        let best = Number.POSITIVE_INFINITY
        for (const idx of commas) {
          if (idx < 24 || idx > clean.length - 18) continue
          const d = Math.abs(idx - target)
          if (d < best) {
            best = d
            pick = idx
          }
        }
        const left = clean.slice(0, pick + 1).trim()
        const right = clean.slice(pick + 1).trim()
        parts = [left, right].filter(Boolean)
      }
    }

    if (parts.length <= 1) {
      out.push(clean)
      return
    }

    const merged: string[] = []
    for (const part of parts) {
      if (!part) continue
      if (merged.length && part.length < 24) {
        merged[merged.length - 1] = `${merged[merged.length - 1]}${part}`
      } else {
        merged.push(part)
      }
    }
    out.push(...merged.filter(Boolean))
  }

  for (const part of hardParts.length ? hardParts : [src]) splitChunk(part)
  return out.length ? out : [src]
}
