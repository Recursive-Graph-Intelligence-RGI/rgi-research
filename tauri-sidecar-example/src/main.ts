import { invoke } from '@tauri-apps/api/core'
import { open } from '@tauri-apps/plugin-dialog'

let selectedPath = ''
let currentJobId = ''

const folderPathEl = document.getElementById('folder-path') as HTMLSpanElement
const objectiveEl = document.getElementById('objective') as HTMLInputElement
const statusEl = document.getElementById('status') as HTMLDivElement
const resultEl = document.getElementById('result') as HTMLPreElement
const runBtn = document.getElementById('run-analysis') as HTMLButtonElement

function setStatus(msg: string) {
  statusEl.textContent = msg
}

document.getElementById('pick-folder')!.addEventListener('click', async () => {
  const path = await open({ directory: true })
  if (path) {
    selectedPath = path as string
    folderPathEl.textContent = selectedPath
    runBtn.disabled = false
  }
})

document.getElementById('start-rgi')!.addEventListener('click', async () => {
  try {
    setStatus('Starting RGI engine...')
    const result = await invoke('start_rgi')
    setStatus(`Engine started: ${JSON.stringify(result)}`)
    runBtn.disabled = !selectedPath
  } catch (err) {
    setStatus(`Failed to start engine: ${err}`)
  }
})

document.getElementById('stop-rgi')!.addEventListener('click', async () => {
  try {
    setStatus('Stopping RGI engine...')
    await invoke('stop_rgi')
    setStatus('Engine stopped.')
    runBtn.disabled = true
  } catch (err) {
    setStatus(`Failed to stop engine: ${err}`)
  }
})

runBtn.addEventListener('click', async () => {
  if (!selectedPath) return
  try {
    setStatus('Submitting analysis...')
    currentJobId = await invoke('analyze_repo', {
      path: selectedPath,
      objective: objectiveEl.value,
    }) as string
    setStatus(`Job ${currentJobId} submitted.`)
    pollJob(currentJobId)
  } catch (err) {
    setStatus(`Analysis failed: ${err}`)
  }
})

async function pollJob(jobId: string) {
  for (let i = 0; i < 120; i++) {
    await new Promise((r) => setTimeout(r, 1000))
    try {
      const status = await invoke('get_status', { jobId }) as { status: string; progress: string[]; error: string | null }
      setStatus(`Job ${jobId}: ${status.status}\n${status.progress.slice(-5).join('\n')}`)
      if (status.status === 'completed' || status.status === 'failed') {
        const result = await invoke('get_result', { jobId }) as { status: string; result: unknown; error: string | null }
        resultEl.textContent = JSON.stringify(result, null, 2)
        break
      }
    } catch (err) {
      setStatus(`Polling error: ${err}`)
    }
  }
}
