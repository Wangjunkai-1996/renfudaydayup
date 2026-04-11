import fs from 'node:fs'
import path from 'node:path'
import { spawn } from 'node:child_process'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(scriptDir, '..')
const cacheDir = path.join(repoRoot, '.cache')
const lockFile = path.join(cacheDir, 'vitest-run.lock')
const vitestBin = path.join(repoRoot, 'node_modules', 'vitest', 'vitest.mjs')

fs.mkdirSync(cacheDir, { recursive: true })

function isProcessAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false
  try {
    process.kill(pid, 0)
    return true
  } catch {
    return false
  }
}

function readExistingLock() {
  try {
    return JSON.parse(fs.readFileSync(lockFile, 'utf8'))
  } catch {
    return null
  }
}

function acquireLock() {
  try {
    const fd = fs.openSync(lockFile, 'wx')
    const payload = JSON.stringify({
      pid: process.pid,
      startedAt: new Date().toISOString(),
      args: process.argv.slice(2)
    }, null, 2)
    fs.writeFileSync(fd, payload)
    fs.closeSync(fd)
    return
  } catch (error) {
    if (error?.code !== 'EEXIST') throw error
  }

  const existing = readExistingLock()
  if (existing && isProcessAlive(existing.pid)) {
    const startedAt = existing.startedAt ? `, started ${existing.startedAt}` : ''
    console.error(`Vitest already running in this repo (pid ${existing.pid}${startedAt}). Stop the old run first.`)
    process.exit(1)
  }

  fs.rmSync(lockFile, { force: true })
  acquireLock()
}

let cleaned = false
function cleanupLock() {
  if (cleaned) return
  cleaned = true
  fs.rmSync(lockFile, { force: true })
}

acquireLock()

for (const signal of ['SIGINT', 'SIGTERM', 'SIGHUP']) {
  process.on(signal, () => {
    cleanupLock()
    process.exit(130)
  })
}

process.on('exit', cleanupLock)

const env = {
  ...process.env,
  VITEST_MAX_FORKS: process.env.VITEST_MAX_FORKS || '2',
  VITEST_MIN_FORKS: process.env.VITEST_MIN_FORKS || '1'
}

const child = spawn(process.execPath, [vitestBin, ...process.argv.slice(2)], {
  cwd: repoRoot,
  env,
  stdio: 'inherit'
})

child.on('exit', (code, signal) => {
  cleanupLock()
  if (signal) {
    process.kill(process.pid, signal)
    return
  }
  process.exit(code ?? 1)
})

child.on('error', (error) => {
  cleanupLock()
  console.error(error)
  process.exit(1)
})
