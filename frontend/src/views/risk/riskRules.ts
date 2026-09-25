/** 风险口径：与后端 app/services/assess.py 的 RISK_CONCLUSIONS / risk_level_of 保持一致。 */
export const RISK_LEVELS = ['高风险', '中风险', '低风险'] as const

export const RISK_CONCLUSIONS: Record<string, string> = {
  高风险: '评估结论：高风险，建议立即整治',
  中风险: '评估结论：中风险，建议限期整改',
  低风险: '评估结论：低风险，按计划维护',
}

/** 健康分值只接受 0~100；空值、文字、越界都视为缺失（与后端 _parse_score 对齐）。 */
export function parseScore(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null
  const score = typeof value === 'number' ? value : Number(String(value).trim())
  if (!Number.isFinite(score) || score < 0 || score > 100) return null
  return score
}

export function riskLevelOf(score: number): string {
  if (score < 60) return '高风险'
  if (score < 85) return '中风险'
  return '低风险'
}
