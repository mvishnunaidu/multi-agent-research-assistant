import { useState, useRef, useEffect, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import {
  Send, Upload, MessageSquare, FlaskConical,
  History, Zap, FileText, ChevronDown, ChevronUp,
  Paperclip, X, Cpu
} from 'lucide-react'
import './index.css'

// Robust response parsing: on free-tier hosts the backend can return an
// empty body if it crashed mid-request or is still cold-starting, which
// makes response.json() throw a cryptic "Unexpected end of JSON input".
// This gives the user something actionable instead.
async function safeJson(response) {
  const text = await response.text()
  if (!text) {
    throw new Error(
      response.ok
        ? 'The server returned an empty response. It may still be starting up (free-tier hosts can take ~50s to wake) — please try again.'
        : `Request failed (${response.status}). The server may be restarting — please try again in a moment.`
    )
  }
  try {
    return JSON.parse(text)
  } catch {
    throw new Error(`Request failed (${response.status}). Please try again.`)
  }
}

const API = import.meta.env.VITE_API_BASE_URL || '/api/v1'

// ── Utilities ────────────────────────────────────────────────────────────────
function fmt(bytes) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

function ts() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function fileIcon(name) {
  const ext = name?.split('.').pop()?.toLowerCase()
  if (ext === 'pdf')  return '📄'
  if (ext === 'docx' || ext === 'doc') return '📝'
  if (ext === 'txt')  return '📃'
  return '📎'
}

// ── Toast System ─────────────────────────────────────────────────────────────
function useToast() {
  const [toasts, setToasts] = useState([])
  const add = useCallback((msg, type = 'info') => {
    const id = Date.now()
    setToasts(p => [...p, { id, msg, type }])
    setTimeout(() => setToasts(p => p.filter(t => t.id !== id)), 4000)
  }, [])
  return { toasts, add }
}

// ── Agent Steps Accordion ─────────────────────────────────────────────────────
function AgentSteps({ steps }) {
  const [open, setOpen] = useState(false)
  if (!steps || steps.length === 0) return null
  const icons = { Planner: '🗺️', Researcher: '🔍', Summarizer: '📋', 'Report Generator': '📊' }
  return (
    <div>
      <button className="steps-toggle" onClick={() => setOpen(o => !o)}>
        <Cpu size={12} />
        {open ? 'Hide' : 'Show'} agent trace ({steps.length} steps)
        {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
      </button>
      {open && (
        <div className="steps-list">
          {steps.map((s, i) => (
            <div className="step-item" key={i}>
              <span className="step-icon">{icons[s.agent] || '⚙️'}</span>
              <div>
                <div className="step-name">
                  {s.agent}
                  <span className={`step-status-${s.status === 'completed' ? 'ok' : 'err'}`}>
                    {' '}{s.status === 'completed' ? '✓' : '✗'}
                  </span>
                </div>
                {s.output_preview && <div className="step-preview">{s.output_preview}</div>}
                {s.error && <div className="step-preview" style={{ color: 'var(--error)' }}>{s.error}</div>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Message Bubble ────────────────────────────────────────────────────────────
function Message({ msg }) {
  const isUser = msg.role === 'user'
  return (
    <div className={`msg ${isUser ? 'user' : 'agent'}`}>
      <div className="msg-avatar">
        {isUser ? '👤' : '🤖'}
      </div>
      <div style={{ maxWidth: '72%', display: 'flex', flexDirection: 'column' }}>
        <div className="msg-bubble">
          {isUser
            ? <span>{msg.content}</span>
            : <ReactMarkdown>{msg.content}</ReactMarkdown>
          }
          {msg.sources && msg.sources.length > 0 && (
            <div className="sources-row">
              {msg.sources.map((s, i) => (
                <span className="source-tag" key={i}>📎 {s}</span>
              ))}
            </div>
          )}
        </div>
        {msg.steps && <AgentSteps steps={msg.steps} />}
        <div className={`msg-meta ${isUser ? 'user' : ''}`}>{msg.time}</div>
      </div>
    </div>
  )
}

// ── Typing Indicator ──────────────────────────────────────────────────────────
function TypingIndicator() {
  return (
    <div className="msg agent">
      <div className="msg-avatar">🤖</div>
      <div className="msg-bubble">
        <div className="typing">
          <span /><span /><span />
        </div>
      </div>
    </div>
  )
}

// ── Upload Panel ──────────────────────────────────────────────────────────────
function UploadPanel({ sessionId, onUploaded, uploadedFiles }) {
  const [dragging, setDragging] = useState(false)
  const [loading, setLoading] = useState(null) // filename being uploaded
  const [localFiles, setLocalFiles] = useState([]) // [{name, size, status, error}]
  const inputRef = useRef()
  const { toasts, add } = useToast()

  const doUpload = async (file) => {
    const entry = { name: file.name, size: file.size, status: 'loading' }
    setLocalFiles(p => [...p, entry])
    const fd = new FormData()
    fd.append('file', file)
    try {
      const r = await fetch(`${API}/upload?session_id=${sessionId}`, { method: 'POST', body: fd })
      const data = await safeJson(r)
      if (!r.ok) throw new Error(data.detail || 'Upload failed')
      setLocalFiles(p => p.map(f => f.name === file.name ? { ...f, status: 'ok', chunks: data.num_chunks } : f))
      onUploaded(file.name)
      add(`"${file.name}" ingested — ${data.num_chunks} chunks`, 'success')
    } catch (e) {
      setLocalFiles(p => p.map(f => f.name === file.name ? { ...f, status: 'error', error: e.message } : f))
      add(`Upload failed: ${e.message}`, 'error')
    }
  }

  const handleFiles = (files) => {
    for (const f of files) doUpload(f)
  }

  return (
    <div className="upload-panel">
      <div className="panel-header">
        <h2>📂 Document Upload</h2>
        <p>Upload PDF, DOCX, or TXT files. They'll be chunked, embedded, and added to your session's knowledge base.</p>
      </div>

      <div
        className={`dropzone ${dragging ? 'drag-over' : ''}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={e => { e.preventDefault(); setDragging(false); handleFiles([...e.dataTransfer.files]) }}
      >
        <input ref={inputRef} type="file" accept=".pdf,.docx,.doc,.txt" multiple onChange={e => handleFiles([...e.target.files])} />
        <div className="dropzone-icon">📤</div>
        <h3>Drop files here or click to browse</h3>
        <p>Supported: PDF · DOCX · DOC · TXT</p>
        <button className="upload-btn" onClick={e => { e.stopPropagation(); inputRef.current?.click() }}>
          <Upload size={14} /> Choose Files
        </button>
      </div>

      {(localFiles.length > 0 || uploadedFiles.length > 0) && (
        <div>
          <div className="panel-header" style={{ marginBottom: 12 }}>
            <h2 style={{ fontSize: 14 }}>Session Documents</h2>
          </div>
          <div className="files-list">
            {localFiles.map((f, i) => (
              <div className="file-card" key={i}>
                <span className="file-icon">{fileIcon(f.name)}</span>
                <div className="file-info">
                  <div className="file-name">{f.name}</div>
                  <div className="file-meta">{fmt(f.size)}{f.chunks ? ` · ${f.chunks} chunks` : ''}{f.error ? ` · ${f.error}` : ''}</div>
                </div>
                <span className={`file-status ${f.status}`}>
                  {f.status === 'ok' ? '✓ Ready' : f.status === 'loading' ? '⏳ Processing…' : '✗ Error'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Toast container */}
      <div className="toast-container">
        {toasts.map(t => <div key={t.id} className={`toast ${t.type}`}>{t.msg}</div>)}
      </div>
    </div>
  )
}

// ── History Panel ─────────────────────────────────────────────────────────────
function HistoryPanel({ history, onSelect }) {
  if (history.length === 0) return (
    <div className="history-panel">
      <div className="panel-header"><h2>🕑 History</h2><p>No queries yet for this session.</p></div>
    </div>
  )
  return (
    <div className="history-panel">
      <div className="panel-header"><h2>🕑 History</h2><p>{history.length} messages in this session.</p></div>
      {history.filter(m => m.role === 'user').map((m, i) => (
        <div className="history-item" key={i} onClick={() => onSelect(m.content)}>
          <div className="history-query">{m.content}</div>
          <div className="history-meta">{m.time} · {m.mode === 'research' ? '🔬 Research' : '💬 Chat'}</div>
        </div>
      ))}
    </div>
  )
}

// ── Main App ──────────────────────────────────────────────────────────────────
export default function App() {
  const [view, setView]           = useState('chat')         // 'chat' | 'upload' | 'history'
  const [mode, setMode]           = useState('chat')         // 'chat' | 'research'
  const [messages, setMessages]   = useState([])
  const [input, setInput]         = useState('')
  const [loading, setLoading]     = useState(false)
  const [sessionId, setSessionId] = useState(null)
  const [uploadedFiles, setUploadedFiles] = useState([])
  const [apiOnline, setApiOnline] = useState(false)
  const [llmProvider, setLlmProvider] = useState('…')
  const [toasts, setToasts]       = useState([])
  const bottomRef = useRef()
  const textareaRef = useRef()

  // ── Session init ────────────────────────────────────────────────
  useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${API}/session/new`, { method: 'POST' })
        const d = await safeJson(r)
        setSessionId(d.session_id)

        const h = await fetch(`${API}/health`)
        const hd = await safeJson(h)
        setApiOnline(hd.status === 'ok')
        setLlmProvider(hd.llm_provider)
      } catch {
        setApiOnline(false)
      }
    })()
  }, [])

  // ── Auto-scroll ─────────────────────────────────────────────────
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  // ── Toast ───────────────────────────────────────────────────────
  const addToast = (msg, type = 'info') => {
    const id = Date.now()
    setToasts(p => [...p, { id, msg, type }])
    setTimeout(() => setToasts(p => p.filter(t => t.id !== id)), 4000)
  }

  // ── Send ─────────────────────────────────────────────────────────
  const send = async (text) => {
    const q = (text || input).trim()
    if (!q || loading || !sessionId) return

    const userMsg = { role: 'user', content: q, time: ts(), mode }
    setMessages(p => [...p, userMsg])
    setInput('')
    setLoading(true)

    try {
      const hasDocs = uploadedFiles.length > 0
      let reply, sources = [], steps = []

      if (mode === 'research') {
        const r = await fetch(`${API}/research`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sessionId, query: q, has_documents: hasDocs }),
        })
        const d = await safeJson(r)
        if (!r.ok) throw new Error(d.detail || 'Research failed')
        reply   = d.final_report
        sources = d.sources || []
        steps   = d.agent_steps || []
      } else {
        const r = await fetch(`${API}/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sessionId, message: q, has_documents: hasDocs }),
        })
        const d = await safeJson(r)
        if (!r.ok) throw new Error(d.detail || 'Chat failed')
        reply   = d.reply
        sources = d.sources || []
      }

      setMessages(p => [...p, { role: 'agent', content: reply, sources, steps, time: ts(), mode }])
    } catch (e) {
      const em = e.message || 'Something went wrong'
      setMessages(p => [...p, {
        role: 'agent', content: `❌ **Error:** ${em}`, time: ts(), mode
      }])
      addToast(em, 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  const handleChip = (text) => { setInput(text); textareaRef.current?.focus() }

  const suggestions = [
    'Explain quantum entanglement',
    'Summarize the uploaded document',
    'What are the key findings?',
    'Compare and contrast the main topics',
  ]

  // ── Sidebar nav ──────────────────────────────────────────────────
  const navItems = [
    { id: 'chat',    icon: <MessageSquare size={15} />, label: 'Chat' },
    { id: 'upload',  icon: <Upload size={15} />,        label: 'Documents', badge: uploadedFiles.length > 0 ? uploadedFiles.length : null },
    { id: 'history', icon: <History size={15} />,       label: 'History' },
  ]

  return (
    <>
      <aside className="sidebar">
        <div className="sidebar-logo">
          <div className="sidebar-logo-icon">🤖</div>
          <div>
            <div className="sidebar-logo-text">Research Assistant</div>
            <div className="sidebar-logo-sub">Multi-Agent AI Pipeline</div>
          </div>
        </div>

        <div className="sidebar-section">Navigation</div>
        {navItems.map(n => (
          <button
            key={n.id}
            className={`sidebar-btn ${view === n.id ? 'active' : ''}`}
            onClick={() => setView(n.id)}
            id={`nav-${n.id}`}
          >
            {n.icon}
            {n.label}
            {n.badge && <span className="mode-badge">{n.badge}</span>}
          </button>
        ))}

        <div className="sidebar-spacer" />

        <div className="sidebar-section">Status</div>
        <div className="sidebar-btn" style={{ cursor: 'default' }}>
          <span className={`status-dot ${apiOnline ? '' : 'offline'}`} />
          {apiOnline ? 'API Online' : 'API Offline'}
        </div>

        {uploadedFiles.length > 0 && (
          <div className="sidebar-btn" style={{ cursor: 'default' }}>
            <FileText size={15} />
            {uploadedFiles.length} doc{uploadedFiles.length > 1 ? 's' : ''} loaded
          </div>
        )}
      </aside>

      <div className="main">
        {/* Top bar */}
        <header className="topbar">
          <span className={`status-dot ${apiOnline ? '' : 'offline'}`} />
          <div>
            <div className="topbar-title">
              {view === 'chat'    && (mode === 'research' ? '🔬 Research Mode' : '💬 Chat Mode')}
              {view === 'upload'  && '📂 Document Manager'}
              {view === 'history' && '🕑 Session History'}
            </div>
            <div className="topbar-sub">
              {sessionId ? `Session: ${sessionId.slice(0, 8)}…` : 'Initializing…'}
            </div>
          </div>
          <div className="topbar-right">
            {uploadedFiles.length > 0 && (
              <div className="topbar-pill">
                <FileText size={12} />
                {uploadedFiles.length} document{uploadedFiles.length > 1 ? 's' : ''}
              </div>
            )}

          </div>
        </header>

        {/* Views */}
        {view === 'upload' && (
          <UploadPanel
            sessionId={sessionId}
            uploadedFiles={uploadedFiles}
            onUploaded={name => setUploadedFiles(p => p.includes(name) ? p : [...p, name])}
          />
        )}

        {view === 'history' && (
          <HistoryPanel
            history={messages}
            onSelect={q => { setView('chat'); handleChip(q) }}
          />
        )}

        {view === 'chat' && (
          <div className="chat-view">
            <div className="messages-area">
              {messages.length === 0 ? (
                <div className="welcome-hero">
                  <div className="welcome-icon">🤖</div>
                  <h1>Multi-Agent Research Assistant</h1>
                  <p>
                    Upload documents and ask questions — or just chat. Switch to
                    <strong> Research Mode</strong> to run the full 4-agent pipeline:
                    Planner → Researcher → Summarizer → Report Generator.
                  </p>
                  <div className="welcome-chips">
                    {suggestions.map((s, i) => (
                      <button className="chip" key={i} onClick={() => handleChip(s)}>{s}</button>
                    ))}
                  </div>
                </div>
              ) : (
                messages.map((m, i) => <Message msg={m} key={i} />)
              )}
              {loading && <TypingIndicator />}
              <div ref={bottomRef} />
            </div>

            {/* Input */}
            <div className="input-area">
              <div className="input-row">
                <button
                  id="mode-toggle-btn"
                  className={`mode-toggle ${mode === 'research' ? 'research' : ''}`}
                  onClick={() => setMode(m => m === 'chat' ? 'research' : 'chat')}
                  title="Toggle between Chat and Research mode"
                >
                  {mode === 'research' ? <FlaskConical size={13} /> : <MessageSquare size={13} />}
                  {mode === 'research' ? 'Research' : 'Chat'}
                </button>

                <div className="input-wrap">
                  <textarea
                    ref={textareaRef}
                    id="chat-input"
                    className="input-textarea"
                    placeholder={mode === 'research'
                      ? 'Enter your research question — the 4-agent pipeline will run…'
                      : 'Ask anything, or upload docs to chat with them…'}
                    value={input}
                    onChange={e => setInput(e.target.value)}
                    onKeyDown={handleKey}
                    rows={1}
                    disabled={loading || !sessionId}
                  />
                  <div className="input-actions">
                    {uploadedFiles.length > 0 && (
                      <span style={{ fontSize: 11, color: 'var(--success)', display: 'flex', gap: 4, alignItems: 'center' }}>
                        <Paperclip size={11} /> {uploadedFiles.length} doc{uploadedFiles.length > 1 ? 's' : ''} in context
                      </span>
                    )}
                    <span className="input-hint">Enter to send · Shift+Enter for new line</span>
                  </div>
                </div>

                <button
                  id="send-btn"
                  className="send-btn"
                  onClick={() => send()}
                  disabled={loading || !input.trim() || !sessionId}
                  aria-label="Send message"
                >
                  {loading ? <div className="spinner" /> : <Send size={18} color="white" />}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Global Toasts */}
      <div className="toast-container">
        {toasts.map(t => <div key={t.id} className={`toast ${t.type}`}>{t.msg}</div>)}
      </div>
    </>
  )
}
