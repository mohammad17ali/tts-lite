import { useState, useEffect, useRef, useCallback } from 'react'
import './App.css'

const API_BASE = 'http://localhost:8800'

const LANGUAGES = [
  { code: 'en', label: 'English' },
  { code: 'hi', label: 'Hindi' },
]

const VOICES = {
  en: [
    { id: 'af_heart', name: 'Heart', gender: 'Female', accent: 'American' },
    { id: 'af_alloy', name: 'Alloy', gender: 'Female', accent: 'American' },
    { id: 'af_aoede', name: 'Aoede', gender: 'Female', accent: 'American' },
    { id: 'af_bella', name: 'Bella', gender: 'Female', accent: 'American' },
    { id: 'af_jessica', name: 'Jessica', gender: 'Female', accent: 'American' },
    { id: 'af_kore', name: 'Kore', gender: 'Female', accent: 'American' },
    { id: 'af_nicole', name: 'Nicole', gender: 'Female', accent: 'American' },
    { id: 'af_nova', name: 'Nova', gender: 'Female', accent: 'American' },
    { id: 'af_river', name: 'River', gender: 'Female', accent: 'American' },
    { id: 'af_sarah', name: 'Sarah', gender: 'Female', accent: 'American' },
    { id: 'af_sky', name: 'Sky', gender: 'Female', accent: 'American' },
    { id: 'am_adam', name: 'Adam', gender: 'Male', accent: 'American' },
    { id: 'am_echo', name: 'Echo', gender: 'Male', accent: 'American' },
    { id: 'am_eric', name: 'Eric', gender: 'Male', accent: 'American' },
    { id: 'am_fenrir', name: 'Fenrir', gender: 'Male', accent: 'American' },
    { id: 'am_liam', name: 'Liam', gender: 'Male', accent: 'American' },
    { id: 'am_michael', name: 'Michael', gender: 'Male', accent: 'American' },
    { id: 'am_onyx', name: 'Onyx', gender: 'Male', accent: 'American' },
    { id: 'am_puck', name: 'Puck', gender: 'Male', accent: 'American' },
    { id: 'am_santa', name: 'Santa', gender: 'Male', accent: 'American' },
    { id: 'bf_alice', name: 'Alice', gender: 'Female', accent: 'British' },
    { id: 'bf_emma', name: 'Emma', gender: 'Female', accent: 'British' },
    { id: 'bf_isabella', name: 'Isabella', gender: 'Female', accent: 'British' },
    { id: 'bf_lily', name: 'Lily', gender: 'Female', accent: 'British' },
    { id: 'bm_daniel', name: 'Daniel', gender: 'Male', accent: 'British' },
    { id: 'bm_fable', name: 'Fable', gender: 'Male', accent: 'British' },
    { id: 'bm_george', name: 'George', gender: 'Male', accent: 'British' },
    { id: 'bm_lewis', name: 'Lewis', gender: 'Male', accent: 'British' },
  ],
  hi: [
    { id: 'hf_alpha', name: 'Alpha', gender: 'Female' },
    { id: 'hf_beta', name: 'Beta', gender: 'Female' },
    { id: 'hm_omega', name: 'Omega', gender: 'Male' },
    { id: 'hm_psi', name: 'Psi', gender: 'Male' },
  ],
}

function getLangCode(voiceId) {
  return voiceId.charAt(0)
}

function voiceLabel(v) {
  const parts = [v.name, `(${v.gender})`]
  if (v.accent) parts.splice(1, 0, `— ${v.accent}`)
  return parts.join(' ')
}

function truncate(str, len = 48) {
  return str.length > len ? str.slice(0, len) + '…' : str
}

function App() {
  const [healthStatus, setHealthStatus] = useState('checking')
  const [text, setText] = useState('')
  const [language, setLanguage] = useState('en')
  const [voice, setVoice] = useState('af_heart')
  const [loading, setLoading] = useState(false)
  const [loadingMsg, setLoadingMsg] = useState('')
  const [audioUrl, setAudioUrl] = useState(null)
  const [audioFilename, setAudioFilename] = useState('')
  const [error, setError] = useState('')
  const [tasks, setTasks] = useState([])
  const [selectedTask, setSelectedTask] = useState(null)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const abortRef = useRef(null)

  // ---- Health check ----
  const checkHealth = async () => {
    setHealthStatus('checking')
    try {
      const res = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(10000) })
      setHealthStatus(res.ok ? 'ok' : 'error')
    } catch {
      setHealthStatus('error')
    }
  }

  // ---- Load tasks from backend ----
  const fetchTasks = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/tts/tasks`)
      if (res.ok) {
        const data = await res.json()
        setTasks(data.tasks || [])
      }
    } catch { /* silent */ }
  }, [])

  useEffect(() => { checkHealth() }, [])

  useEffect(() => {
    if (healthStatus === 'ok') fetchTasks()
  }, [healthStatus, fetchTasks])

  // Reset voice when language changes
  useEffect(() => {
    const voices = VOICES[language]
    if (voices?.length) setVoice(voices[0].id)
  }, [language])

  // ---- Generate speech ----
  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!text.trim()) return

    setError('')
    setAudioUrl(null)
    setAudioFilename('')
    setSelectedTask(null)
    setLoading(true)
    setLoadingMsg('Generating speech…')

    const controller = new AbortController()
    abortRef.current = controller
    const timeout = setTimeout(() => controller.abort(), 120000)

    try {
      const langCode = getLangCode(voice)
      const res = await fetch(`${API_BASE}/tts/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text.trim(), voice, lang_code: langCode }),
        signal: controller.signal,
      })
      clearTimeout(timeout)

      if (!res.ok) {
        const body = await res.json().catch(() => null)
        throw new Error(body?.detail || `Server error (${res.status})`)
      }

      const data = await res.json()
      const fileName = data.file_name

      setLoadingMsg('Fetching audio file…')
      const audioRes = await fetch(`${API_BASE}/tts/files/${encodeURIComponent(fileName)}`)
      if (!audioRes.ok) throw new Error('Failed to fetch the generated audio file')

      const blob = await audioRes.blob()
      const url = URL.createObjectURL(blob)
      setAudioUrl(url)
      setAudioFilename(fileName)

      // Refresh task list
      await fetchTasks()
    } catch (err) {
      if (err.name === 'AbortError') {
        setError('Request timed out (2 minutes). Please try with shorter text.')
      } else {
        setError(err.message || 'Something went wrong')
      }
    } finally {
      setLoading(false)
      setLoadingMsg('')
      abortRef.current = null
    }
  }

  // ---- Load a past task ----
  const handleTaskClick = async (task) => {
    setSelectedTask(task.task_number)
    setText(task.text)
    setError('')
    if (audioUrl) URL.revokeObjectURL(audioUrl)
    setAudioUrl(null)
    setAudioFilename('')

    try {
      const audioRes = await fetch(`${API_BASE}/tts/files/${encodeURIComponent(task.file_name)}`)
      if (!audioRes.ok) {
        setError('Audio file no longer available')
        return
      }
      const blob = await audioRes.blob()
      setAudioUrl(URL.createObjectURL(blob))
      setAudioFilename(task.file_name)
    } catch {
      setError('Failed to load audio for this task')
    }
  }

  const handleReset = () => {
    if (audioUrl) URL.revokeObjectURL(audioUrl)
    setAudioUrl(null)
    setAudioFilename('')
    setSelectedTask(null)
    setError('')
  }

  // ---- Render: health check spinner ----
  if (healthStatus === 'checking') {
    return (
      <div className="fullscreen-center">
        <div className="spinner" />
        <p className="loading-text">Connecting to TTS service…</p>
      </div>
    )
  }

  // ---- Render: health error ----
  if (healthStatus === 'error') {
    return (
      <div className="fullscreen-center">
        <div className="health-error">
          <div className="health-error-icon">⚠</div>
          <h2>Service Unavailable</h2>
          <p>Unable to reach the Kokoro TTS backend at <strong>{API_BASE}</strong></p>
          <button className="retry-btn" onClick={checkHealth}>Retry</button>
        </div>
      </div>
    )
  }

  // ---- Render: main app ----
  const voices = VOICES[language] || []

  return (
    <div className="app-shell">
      {/* ---- Top bar ---- */}
      <header className="topbar">
        <div className="topbar-left">
          <button className="sidebar-toggle" onClick={() => setSidebarOpen((o) => !o)} title="Toggle sidebar">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><rect y="3" width="20" height="2" rx="1" fill="currentColor"/><rect y="9" width="20" height="2" rx="1" fill="currentColor"/><rect y="15" width="20" height="2" rx="1" fill="currentColor"/></svg>
          </button>
          <span className="topbar-brand">intel tinyspeech</span>
        </div>
        <span className="topbar-tagline">Text-to-Speech &middot; Kokoro-82M</span>
        <div className="topbar-status">
          <span className="status-dot" />
          <span>Connected</span>
        </div>
      </header>

      <div className="app-body">
        {/* ---- Sidebar ---- */}
        <aside className={`sidebar ${sidebarOpen ? 'open' : 'closed'}`}>
          <div className="sidebar-header">
            <h2>History</h2>
            <span className="task-count">{tasks.length} task{tasks.length !== 1 ? 's' : ''}</span>
          </div>
          <div className="sidebar-list">
            {tasks.length === 0 && (
              <p className="sidebar-empty">No tasks yet. Generate your first speech!</p>
            )}
            {[...tasks].reverse().map((t) => (
              <button
                key={t.task_number}
                className={`task-item ${selectedTask === t.task_number ? 'active' : ''}`}
                onClick={() => handleTaskClick(t)}
              >
                <span className="task-number">Task {t.task_number}</span>
                <span className="task-voice">{t.voice}</span>
                <span className="task-preview">{truncate(t.text, 52)}</span>
              </button>
            ))}
          </div>
        </aside>

        {/* ---- Main content ---- */}
        <main className="main-content">
          <div className="tts-card">
            <h2 className="card-title">Generate Speech</h2>
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label htmlFor="tts-text">Text</label>
                <textarea
                  id="tts-text"
                  placeholder="Enter text to convert to speech…"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  disabled={loading}
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="tts-lang">Language</label>
                  <select id="tts-lang" value={language} onChange={(e) => setLanguage(e.target.value)} disabled={loading}>
                    {LANGUAGES.map((l) => (
                      <option key={l.code} value={l.code}>{l.label}</option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label htmlFor="tts-voice">Voice</label>
                  <select id="tts-voice" value={voice} onChange={(e) => setVoice(e.target.value)} disabled={loading}>
                    {voices.map((v) => (
                      <option key={v.id} value={v.id}>{voiceLabel(v)}</option>
                    ))}
                  </select>
                </div>
              </div>

              <button type="submit" className="submit-btn" disabled={loading || !text.trim()}>
                {loading ? 'Generating…' : 'Generate Speech'}
              </button>
            </form>

            {loading && (
              <div className="inline-loading">
                <div className="spinner small" />
                <p>{loadingMsg}</p>
              </div>
            )}

            {error && <div className="error-msg">{error}</div>}

            {audioUrl && (
              <div className="audio-section">
                <h3>Generated Audio</h3>
                <div className="audio-player-box">
                  <audio controls src={audioUrl} />
                  <span className="audio-filename">{audioFilename}</span>
                </div>
                <button className="new-btn" onClick={handleReset}>Generate Another</button>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}

export default App
