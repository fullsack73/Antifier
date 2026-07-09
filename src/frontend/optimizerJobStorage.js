export const OPTIMIZER_JOB_STORAGE_KEY = "antifier.optimizer.job.v1"

const canUseLocalStorage = () => (
  typeof window !== "undefined" && typeof window.localStorage !== "undefined"
)

export const readOptimizerJob = () => {
  if (!canUseLocalStorage()) return null

  try {
    const raw = window.localStorage.getItem(OPTIMIZER_JOB_STORAGE_KEY)
    if (!raw) return null

    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== "object" || typeof parsed.requestId !== "string") {
      return null
    }
    return parsed
  } catch {
    return null
  }
}

export const writeOptimizerJob = (job) => {
  if (!canUseLocalStorage() || !job?.requestId) return null

  const now = new Date().toISOString()
  const record = {
    ...job,
    updatedAt: job.updatedAt || now,
  }

  try {
    window.localStorage.setItem(OPTIMIZER_JOB_STORAGE_KEY, JSON.stringify(record))
    return record
  } catch {
    return null
  }
}

export const clearOptimizerJob = () => {
  if (!canUseLocalStorage()) return

  try {
    window.localStorage.removeItem(OPTIMIZER_JOB_STORAGE_KEY)
  } catch {
    // Ignore storage failures; job recovery is a convenience path.
  }
}

export const isRunningOptimizerJob = (job) => job?.status === "running"
