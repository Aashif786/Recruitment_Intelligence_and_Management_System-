/** Display-only helpers for terminated / non-completed interviews (no API or scoring changes). */

export function isAnswerEmpty(answer: string | null | undefined): boolean {
  if (answer === null || answer === undefined) return true
  return String(answer).trim() === ''
}

export function getDisplayedQuestionScore(q: {
  evaluation?: { technical_accuracy?: number; overall?: number }
  score?: number
}): number {
  return q.evaluation?.technical_accuracy ?? q.evaluation?.overall ?? q.score ?? 0
}

export function isInterviewNotCompleted(report: {
  termination_reason?: string | null
  question_evaluations?: Array<{
    answer?: string | null
    evaluation?: { technical_accuracy?: number; overall?: number }
    score?: number
  }>
}): boolean {
  if (report.termination_reason) return true
  const evals = report.question_evaluations ?? []
  if (evals.length === 0) return false
  return evals.every((q) => isAnswerEmpty(q.answer) && getDisplayedQuestionScore(q) === 0)
}

export function isProgressionAllZeros(
  lineData: Array<{ Tech?: number }>
): boolean {
  if (!lineData.length) return true
  return lineData.every((d) => (d.Tech ?? 0) === 0)
}

export function isRadarAllZeros(radarData: Array<{ A?: number }>): boolean {
  if (!radarData.length) return true
  return radarData.every((r) => (r.A ?? 0) === 0)
}
