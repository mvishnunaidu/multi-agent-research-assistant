import { useState, useRef, useEffect, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import {
  Send,
  Upload,
  MessageSquare,
  FlaskConical,
  Clock,
  Copy,
  Check,
  Download,
  AlertCircle,
  AlertTriangle,
  Info,
  CheckCircle2,
  Cpu,
  FileText,
  FileCode,
  FolderOpen,
  Menu,
  X,
  Paperclip,
  Trash2
} from 'lucide-react'
import './index.css'

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'

async function safeFetchJson(url, options = {}) {
  const response = await fetch(url, options)
  const text = await response.text()
  if (!text) {
    if (response.ok) return {}
    throw new Error(`Server returned status ${response.status}. The server may be starting up.`)
  }
  try {
    const data = JSON.parse(text)
    if (!response.ok) {
      throw new Error(data.detail || `Request failed (${response.status})`)
    }
    return data
  } catch (err) {
    if (err instanceof SyntaxError) {
      throw new Error(`Invalid response from server (${response.status}).`, { cause: err })
    }
    throw err
  }
}

function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

function formatDuration(seconds) {
  if (typeof seconds !== 'number' || isNaN(seconds)) return '0.0s'
  return `${seconds.toFixed(2)}s`
}

export default function App() {
  const [navTab, setNavTab] = useState('research') // 'research' | 'documents' | 'history'
  const [mode, setMode] = useState('research')     // 'research' | 'chat'
  const [sessionId, setSessionId] = useState(null)
  const [apiOnline, setApiOnline] = useState(false)
  const [llmProvider, setLlmProvider] = useState('Checking...')
  const [coldStartNotice, setColdStartNotice] = useState(false)
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)

  // Document management
  const [documents, setDocuments] = useState([])
  const [isUploading, setIsUploading] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const fileInputRef = useRef(null)
  const workspaceRef = useRef(null)
  const reportRef = useRef(null)

  // Input & Execution
  const [inputQuery, setInputQuery] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  // Research state
  const [activeResearch, setActiveResearch] = useState(null)
  const [copiedReport, setCopiedReport] = useState(false)
  const [copiedSession, setCopiedSession] = useState(false)

  // Conversational chat state
  const [chatMessages, setChatMessages] = useState([])
  const chatBottomRef = useRef(null)

  // Session history
  const [sessionHistory, setSessionHistory] = useState([])

  // Toast system
  const [toasts, setToasts] = useState([])
  const addToast = useCallback((message, type = 'info') => {
    const id = Date.now() + Math.random()
    setToasts(prev => [...prev, { id, message, type }])
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id))
    }, 4000)
  }, [])

  // ── Session & Health Check ──────────────────────────────────────────────────
  const initSession = useCallback(async () => {
    try {
      const data = await safeFetchJson(`${API_BASE}/session/new`, { method: 'POST' })
      if (data?.session_id) {
        setSessionId(data.session_id)
        return data.session_id
      }
      return null
    } catch {
      return null
    }
  }, [])

  const checkHealth = useCallback(async () => {
    try {
      const health = await safeFetchJson(`${API_BASE}/health`)
      const isOk = health.status === 'ok'
      setApiOnline(isOk)
      setLlmProvider(health.llm_provider || 'Active')
      setColdStartNotice(!isOk)
      return isOk
    } catch {
      setApiOnline(false)
      setLlmProvider('Offline / Initializing')
      setColdStartNotice(true)
      return false
    }
  }, [])

  const loadDocuments = useCallback(async (sid) => {
    if (!sid) return
    try {
      const data = await safeFetchJson(`${API_BASE}/documents/${sid}`)
      setDocuments(data.documents || [])
    } catch {
      // In-memory sessions return empty documents before upload
    }
  }, [])

  const loadHistory = useCallback(async (sid) => {
    if (!sid) return
    try {
      const data = await safeFetchJson(`${API_BASE}/history/${sid}`)
      setSessionHistory(data.messages || [])
    } catch {
      // Empty history
    }
  }, [])

  // Auto-polling health and auto-recovery
  useEffect(() => {
    let isMounted = true

    const runCheck = async () => {
      const ok = await checkHealth()
      if (ok && isMounted) {
        setSessionId((currSid) => {
          if (!currSid) {
            initSession().then((newSid) => {
              if (newSid && isMounted) {
                loadDocuments(newSid)
                loadHistory(newSid)
              }
            })
          }
          return currSid
        })
      }
    }

    runCheck()
    const timer = setInterval(runCheck, apiOnline ? 25000 : 6000)
    return () => {
      isMounted = false
      clearInterval(timer)
    }
  }, [apiOnline, checkHealth, initSession, loadDocuments, loadHistory])

  useEffect(() => {
    if (chatBottomRef.current) {
      chatBottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [chatMessages, isLoading])

  // ── File Upload Handler ─────────────────────────────────────────────────────
  const handleFileUpload = async (files) => {
    if (!files || files.length === 0) return

    let currentSessionId = sessionId
    if (!currentSessionId) {
      currentSessionId = await initSession()
      if (!currentSessionId) {
        addToast('Server is connecting... Please retry upload in a few seconds.', 'error')
        return
      }
    }

    for (let i = 0; i < files.length; i++) {
      const file = files[i]
      const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase()

      if (ext === '.doc') {
        addToast(`"${file.name}" rejected: Legacy .doc format not supported. Please use .docx or .pdf.`, 'error')
        continue
      }

      if (!['.pdf', '.docx', '.txt'].includes(ext)) {
        addToast(`"${file.name}" rejected: Unsupported format. Allowed: .pdf, .docx, .txt`, 'error')
        continue
      }

      if (file.size > 20 * 1024 * 1024) {
        addToast(`"${file.name}" exceeds 20MB limit.`, 'error')
        continue
      }

      setIsUploading(true)
      const formData = new FormData()
      formData.append('file', file)

      try {
        const res = await safeFetchJson(`${API_BASE}/upload?session_id=${currentSessionId}`, {
          method: 'POST',
          body: formData,
        })
        addToast(res.message, res.is_duplicate ? 'info' : 'success')
        await loadDocuments(currentSessionId)
      } catch (err) {
        addToast(`Upload failed for "${file.name}": ${err.message}`, 'error')
      } finally {
        setIsUploading(false)
      }
    }
  }

  // ── Dispatch Action (Research vs Chat) ──────────────────────────────────────
  const handleSend = async (overrideText) => {
    const text = (overrideText || inputQuery).trim()
    if (!text || isLoading) return

    let currentSessionId = sessionId
    if (!currentSessionId) {
      addToast('Connecting session to server...', 'info')
      currentSessionId = await initSession()
      if (!currentSessionId) {
        addToast('Server is offline or warming up. Please click "Retry" in the status bar.', 'error')
        return
      }
    }

    setInputQuery('')
    setIsLoading(true)

    if (mode === 'research') {
      setNavTab('research')
      // Temporary optimistic running steps
      setActiveResearch({
        query: text,
        plan: [],
        plan_reasoning: '',
        sources: [],
        final_report: '',
        agent_steps: [
          { agent: 'Planner', status: 'running', output_preview: 'Decomposing query into 2 to 4 atomic sub-tasks...' },
          { agent: 'Researcher', status: 'pending', output_preview: 'Waiting for decomposition...' },
          { agent: 'Summarizer', status: 'pending', output_preview: 'Waiting for research findings...' },
          { agent: 'Report Generator', status: 'pending', output_preview: 'Waiting for synthesized evidence...' },
        ],
        overall_status: 'running',
      })

      try {
        const response = await safeFetchJson(`${API_BASE}/research`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: currentSessionId,
            query: text,
            has_documents: documents.length > 0,
          }),
        })

        setActiveResearch({
          query: response.query,
          plan: response.plan || [],
          plan_reasoning: response.plan_reasoning || '',
          sources: response.sources || [],
          final_report: response.final_report || '',
          agent_steps: response.agent_steps || [],
          overall_status: response.overall_status || 'completed',
          timestamp: response.timestamp,
        })
        await loadHistory(currentSessionId)
        addToast('Multi-agent research report generated.', 'success')

        setTimeout(() => {
          reportRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
        }, 120)
      } catch (err) {
        setActiveResearch(prev => ({
          ...(prev || {}),
          query: text,
          final_report: `### Research Execution Notice\n\nThe pipeline encountered an issue:\n\n**Error:** ${err.message}`,
          overall_status: 'error',
          agent_steps: [
            { agent: 'Planner', status: 'error', output_preview: 'Pipeline halted.', error: err.message },
            { agent: 'Researcher', status: 'skipped', output_preview: 'Skipped.' },
            { agent: 'Summarizer', status: 'skipped', output_preview: 'Skipped.' },
            { agent: 'Report Generator', status: 'skipped', output_preview: 'Skipped.' },
          ],
        }))
        addToast(`Research failed: ${err.message}`, 'error')
      } finally {
        setIsLoading(false)
      }
    } else {
      // Conversational Chat Mode
      setNavTab('chat')
      const userMsg = {
        role: 'user',
        content: text,
        timestamp: new Date().toLocaleTimeString(),
        attachments: documents.map(d => ({
          filename: d.filename,
          file_size_bytes: d.file_size_bytes,
        })),
      }
      setChatMessages(prev => [...prev, userMsg])

      try {
        const chatRes = await safeFetchJson(`${API_BASE}/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: currentSessionId,
            message: text,
            has_documents: documents.length > 0,
          }),
        })
        const botMsg = {
          role: 'assistant',
          content: chatRes.reply,
          sources: chatRes.sources || [],
          timestamp: new Date().toLocaleTimeString(),
        }
        setChatMessages(prev => [...prev, botMsg])
      } catch (err) {
        setChatMessages(prev => [
          ...prev,
          { role: 'assistant', content: `**Error:** ${err.message}`, sources: [], timestamp: new Date().toLocaleTimeString() },
        ])
        addToast(`Chat failed: ${err.message}`, 'error')
      } finally {
        setIsLoading(false)
      }
    }
  }

  // ── Utilities ───────────────────────────────────────────────────────────────
  const copyReport = () => {
    if (!activeResearch?.final_report) return
    navigator.clipboard.writeText(activeResearch.final_report)
    setCopiedReport(true)
    setTimeout(() => setCopiedReport(false), 2000)
    addToast('Report copied to clipboard.', 'success')
  }

  const downloadMarkdown = () => {
    if (!activeResearch?.final_report) return
    const blob = new Blob([activeResearch.final_report], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `Research_Report_${Date.now()}.md`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    addToast('Markdown file downloaded.', 'info')
  }

  const copySession = () => {
    if (!sessionId) return
    navigator.clipboard.writeText(sessionId)
    setCopiedSession(true)
    setTimeout(() => setCopiedSession(false), 2000)
    addToast('Session UUID copied.', 'info')
  }

  const clearHistory = async () => {
    if (!sessionId) return
    try {
      await safeFetchJson(`${API_BASE}/history/${sessionId}`, { method: 'DELETE' })
      setSessionHistory([])
      addToast('Session history cleared.', 'info')
    } catch (err) {
      addToast(`Could not clear history: ${err.message}`, 'error')
    }
  }

  const handleDeleteDocument = async (filename) => {
    if (!sessionId || !filename) return
    try {
      await safeFetchJson(`${API_BASE}/documents/${sessionId}/${encodeURIComponent(filename)}`, {
        method: 'DELETE',
      })
      addToast(`"${filename}" removed from knowledge base.`, 'info')
      await loadDocuments(sessionId)
    } catch (err) {
      addToast(`Could not remove "${filename}": ${err.message}`, 'error')
    }
  }

  const handleClearAllDocuments = async () => {
    if (!sessionId) return
    try {
      await safeFetchJson(`${API_BASE}/documents/${sessionId}`, { method: 'DELETE' })
      addToast('All session documents and vector indexes cleared.', 'info')
      await loadDocuments(sessionId)
    } catch (err) {
      addToast(`Could not clear documents: ${err.message}`, 'error')
    }
  }

  const resetAll = () => {
    setInputQuery('')
    setActiveResearch(null)
    setChatMessages([])
    setNavTab(mode === 'research' ? 'research' : 'chat')
  }

  const samplePrompts = [
    'Explain quantum entanglement',
    'Summarize the uploaded document',
    'What are the key findings?',
    'Compare and contrast the main topics',
  ]

  return (
    <>
      {/* ── Mobile Sidebar Backdrop Overlay ─────────────────────────────────── */}
      <div
        className={`mobile-sidebar-backdrop ${isMobileMenuOpen ? 'visible' : ''}`}
        onClick={() => setIsMobileMenuOpen(false)}
        aria-hidden="true"
      />

      {/* ── Sidebar (Matching Screenshot 1) ────────────────────────────────── */}
      <aside className={`sidebar ${isMobileMenuOpen ? 'mobile-open' : ''}`}>
        <div className="sidebar-brand">
          <div className="brand-icon-box">
            <Cpu size={22} />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="brand-title">Research Assistant</div>
            <div className="brand-subtitle">MULTI-AGENT AI PIPELINE</div>
          </div>
          <button
            className="mobile-sidebar-close"
            onClick={() => setIsMobileMenuOpen(false)}
            aria-label="Close navigation"
          >
            <X size={18} />
          </button>
        </div>

        <button
          className="new-action-btn"
          onClick={() => {
            resetAll()
            setIsMobileMenuOpen(false)
          }}
        >
          + New Research
        </button>

        <div className="sidebar-nav">
          <div className="nav-section-title">NAVIGATION</div>
          <button
            className={`nav-item ${navTab === 'research' || navTab === 'chat' ? 'active' : ''}`}
            onClick={() => {
              setNavTab(mode === 'research' ? 'research' : 'chat')
              setIsMobileMenuOpen(false)
            }}
          >
            {mode === 'research' ? <FlaskConical size={16} /> : <MessageSquare size={16} />}
            <span>{mode === 'research' ? 'Research' : 'Chat'}</span>
          </button>

          <button
            className={`nav-item ${navTab === 'documents' ? 'active' : ''}`}
            onClick={() => {
              setNavTab('documents')
              setIsMobileMenuOpen(false)
            }}
          >
            <Upload size={16} />
            <span>Documents</span>
            {documents.length > 0 && <span className="nav-badge">{documents.length}</span>}
          </button>

          <button
            className={`nav-item ${navTab === 'history' ? 'active' : ''}`}
            onClick={() => {
              setNavTab('history')
              setIsMobileMenuOpen(false)
            }}
          >
            <Clock size={16} />
            <span>History</span>
          </button>
        </div>

        <div className="sidebar-footer">
          <div className="nav-section-title" style={{ padding: 0 }}>STATUS</div>
          <div className="status-badge-row">
            <span className={`status-indicator ${apiOnline ? '' : 'offline'}`} />
            <span>{apiOnline ? 'API Online' : 'API Offline'}</span>
            {!apiOnline && (
              <button
                className="copy-mini-btn"
                style={{ marginLeft: 'auto', padding: '2px 8px', fontSize: 10, background: 'rgba(255,255,255,0.06)' }}
                onClick={() => {
                  checkHealth().then(ok => {
                    if (ok && !sessionId) initSession()
                  })
                }}
                title="Retry connection"
              >
                Retry
              </button>
            )}
          </div>

          <div className="session-info-card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: 10, letterSpacing: '0.05em' }}>SESSION ID</span>
              <button className="copy-mini-btn" onClick={copySession} title="Copy Session ID">
                {copiedSession ? <Check size={11} color="#00e682" /> : <Copy size={11} />}
              </button>
            </div>
            <div className="session-id-display">
              {sessionId ? `${sessionId.slice(0, 18)}...` : 'Initializing...'}
            </div>
            <div style={{ fontSize: 10, color: 'var(--text-cyan)', marginTop: 2 }}>
              Provider: {llmProvider}
            </div>
          </div>
        </div>
      </aside>

      {/* ── Main Area ──────────────────────────────────────────────────────── */}
      <div className="main-content">
        {/* Global hidden file input for paperclip and dropzone */}
        <input
          type="file"
          ref={fileInputRef}
          accept=".pdf,.docx,.txt"
          multiple
          style={{ display: 'none' }}
          onChange={(e) => {
            if (e.target.files && e.target.files.length > 0) {
              handleFileUpload(e.target.files)
              e.target.value = ''
            }
          }}
        />

        {/* Top Header */}
        <header className="top-header">
          <div className="header-left">
            <button
              className="mobile-menu-btn"
              onClick={() => setIsMobileMenuOpen(true)}
              aria-label="Open navigation menu"
            >
              <Menu size={18} />
            </button>
            <span className={`status-indicator ${apiOnline ? '' : 'offline'}`} />
            <div className="workspace-title">
              {navTab === 'research' && '🔬 Research Mode'}
              {navTab === 'chat' && '💬 Chat Mode'}
              {navTab === 'documents' && '📂 Document Manager'}
              {navTab === 'history' && '🕑 Session History'}
            </div>
            <span className="workspace-badge">
              {sessionId ? `Session: ${sessionId.slice(0, 8)}...` : 'Connecting...'}
            </span>
          </div>

          <div className="header-right">
            {documents.length > 0 && (
              <div className="header-pill">
                <FileCode size={13} />
                <span>{documents.length} document{documents.length > 1 ? 's' : ''} in context</span>
              </div>
            )}
          </div>
        </header>

        {/* Cold-start banner */}
        {coldStartNotice && (
          <div className="cold-start-banner" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <AlertTriangle size={14} />
              <span>Connecting to backend... On Render free tier, server instances spin down after inactivity and take 30–50s to wake up.</span>
            </div>
            <button
              className="copy-mini-btn"
              style={{ background: 'rgba(255,255,255,0.1)', padding: '4px 10px', fontSize: 11, cursor: 'pointer', whiteSpace: 'nowrap' }}
              onClick={() => {
                checkHealth().then(ok => {
                  if (ok && !sessionId) initSession()
                })
              }}
            >
              Retry Connection
            </button>
          </div>
        )}

        {/* ── Scrollable Workspace Body ────────────────────────────────────── */}
        <div className="workspace-body" ref={workspaceRef}>
          {/* TAB 1: RESEARCH MODE */}
          {navTab === 'research' && (
            <>
              {/* If no research executed yet, show the iconic Hero Card from Screenshot 1 */}
              {!activeResearch && (
                <div className="welcome-hero-card">
                  <div className="hero-avatar-glow">
                    <Cpu size={40} />
                  </div>
                  <h1>Multi-Agent Research Assistant</h1>
                  <p>
                    Upload documents and ask questions — or just chat. Switch to{' '}
                    <strong>Research Mode</strong> to run the full 4-agent pipeline:{' '}
                    Planner → Researcher → Summarizer → Report Generator.
                  </p>

                  <div className="prompt-chips-grid">
                    {samplePrompts.map((p, idx) => (
                      <button
                        key={idx}
                        className="chip-btn"
                        onClick={() => handleSend(p)}
                        disabled={isLoading}
                      >
                        {p}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Four-Agent Pipeline Trace Card */}
              {activeResearch && (
                <div className="agent-pipeline-card">
                  <div className="pipeline-header">
                    <h3>
                      <Cpu size={16} color="var(--cyan-primary)" />
                      Four-Agent Sequential Pipeline Trace
                    </h3>
                    <span className={`overall-status-pill ${activeResearch.overall_status === 'fallback' ? 'completed' : (activeResearch.overall_status || 'completed')}`}>
                      Overall: {activeResearch.overall_status === 'fallback' ? 'completed' : (activeResearch.overall_status || 'completed')}
                    </span>
                  </div>

                  <div className="pipeline-grid">
                    {['Planner', 'Researcher', 'Summarizer', 'Report Generator'].map((agentName, idx) => {
                      const stepData = activeResearch.agent_steps?.find(s => s.agent === agentName) || {
                        status: isLoading ? 'pending' : 'completed',
                        output_preview: '',
                      }

                      const displayStatus = stepData.status === 'fallback' ? 'completed' : (stepData.status || 'completed')

                      return (
                        <div className="agent-col" key={agentName}>
                          <div className="agent-col-top">
                            <span className="agent-step-number">STAGE 0{idx + 1}</span>
                            {stepData.duration_seconds !== undefined && stepData.duration_seconds > 0 && (
                              <span className="agent-duration">{formatDuration(stepData.duration_seconds)}</span>
                            )}
                          </div>

                          <div className="agent-name-title">
                            {agentName}
                          </div>

                          <span className={`agent-status-badge ${displayStatus}`}>
                            {displayStatus === 'completed' && <CheckCircle2 size={11} />}
                            {displayStatus === 'error' && <AlertCircle size={11} />}
                            {displayStatus === 'running' && <div className="spinner-sm" style={{ width: 10, height: 10 }} />}
                            {displayStatus}
                          </span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* Report Viewer */}
              {activeResearch?.final_report && (
                <div className="report-result-card" ref={reportRef}>
                  <div className="report-header-toolbar">
                    <div className="report-title-area">
                      <h3>Synthesized Research Report</h3>
                    </div>

                    <div className="report-actions">
                      <button
                        className={`toolbar-btn ${copiedReport ? 'copied' : ''}`}
                        onClick={copyReport}
                      >
                        {copiedReport ? <Check size={13} /> : <Copy size={13} />}
                        {copiedReport ? 'Copied' : 'Copy Markdown'}
                      </button>

                      <button className="toolbar-btn" onClick={downloadMarkdown}>
                        <Download size={13} /> Download .md
                      </button>
                    </div>
                  </div>

                  <div className="report-meta-section">
                    {activeResearch.plan && activeResearch.plan.length > 0 && (
                      <div className="meta-row">
                        <span className="meta-label">Sub-Tasks:</span>
                        <div className="subtasks-pills-row">
                          {activeResearch.plan.map((t, idx) => (
                            <span className="subtask-tag" key={idx}>
                              {idx + 1}. {t}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    <div className="meta-row">
                      <span className="meta-label">Sources:</span>
                      <div className="sources-pills-row">
                        {activeResearch.sources && activeResearch.sources.length > 0 ? (
                          activeResearch.sources.map((s, idx) => (
                            <span className="source-badge" key={idx}>
                              <FileText size={11} /> {s}
                            </span>
                          ))
                        ) : (
                          <span style={{ fontSize: 12, color: 'var(--text-dim)' }}>
                            General foundational knowledge (no document citations)
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="report-markdown-body">
                    <ReactMarkdown>{activeResearch.final_report}</ReactMarkdown>
                  </div>
                </div>
              )}
            </>
          )}

          {/* TAB 2: CHAT MODE */}
          {navTab === 'chat' && (
            <div className="chat-messages-container">
              {chatMessages.length === 0 ? (
                <div className="welcome-hero-card" style={{ margin: '30px auto' }}>
                  <div className="hero-avatar-glow">
                    <MessageSquare size={38} />
                  </div>
                  <h1>Conversational Chat Mode</h1>
                  <p>
                    Ask questions directly with conversational memory. If documents are uploaded, relevant excerpts will be retrieved into context automatically.
                  </p>
                </div>
              ) : (
                chatMessages.map((msg, idx) => (
                  <div key={idx} className={`chat-bubble ${msg.role}`}>
                    <div className="chat-avatar">
                      {msg.role === 'user' ? 'U' : 'AI'}
                    </div>
                    <div className="chat-card">
                      {/* ChatGPT-style attached document badges inside user message */}
                      {msg.role === 'user' && msg.attachments && msg.attachments.length > 0 && (
                        <div className="chat-bubble-attachments">
                          {msg.attachments.map((att, aIdx) => (
                            <div key={aIdx} className="chat-attached-file-badge">
                              <div className="chat-attached-file-icon">
                                <FileText size={15} />
                              </div>
                              <div className="chat-attached-file-details">
                                <span className="chat-attached-file-name">{att.filename}</span>
                                <span className="chat-attached-file-size">
                                  {att.file_size_bytes ? formatBytes(att.file_size_bytes) : 'Document'} · Knowledge Context
                                </span>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
                      {msg.sources && msg.sources.length > 0 && (
                        <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid rgba(255,255,255,0.08)', display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                          {msg.sources.map((s, sidx) => (
                            <span key={sidx} className="source-badge">
                              <FileText size={10} /> {s}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ))
              )}
              {isLoading && (
                <div className="chat-bubble assistant">
                  <div className="chat-avatar">AI</div>
                  <div className="chat-card" style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-muted)' }}>
                    <div className="spinner-sm" style={{ borderColor: 'rgba(255,255,255,0.2)', borderTopColor: 'var(--cyan-primary)' }} />
                    Generating response...
                  </div>
                </div>
              )}
              <div ref={chatBottomRef} />
            </div>
          )}

          {/* TAB 3: DOCUMENTS WORKSPACE (Matching Screenshot 2) */}
          {navTab === 'documents' && (
            <div className="documents-panel">
              <div className="docs-panel-header">
                <h2>📂 Document Upload</h2>
                <p>Upload PDF, DOCX, or TXT files. They&apos;ll be chunked, embedded, and added to your session&apos;s knowledge base.</p>
              </div>

              <div
                className={`dropzone-box ${isDragging ? 'drag-over' : ''}`}
                onClick={() => fileInputRef.current?.click()}
                onDragOver={(e) => {
                  e.preventDefault()
                  setIsDragging(true)
                }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={(e) => {
                  e.preventDefault()
                  setIsDragging(false)
                  if (e.dataTransfer.files) {
                    handleFileUpload(e.dataTransfer.files)
                  }
                }}
              >
                <div className="dropzone-icon-wrap">
                  <Upload size={28} />
                </div>
                <h3>Drop files here or click to browse</h3>
                <p>Supported: PDF · DOCX · TXT · Max 20MB</p>
                <button
                  className="cyan-glow-btn"
                  onClick={(e) => {
                    e.stopPropagation()
                    fileInputRef.current?.click()
                  }}
                  disabled={isUploading}
                >
                  <FolderOpen size={16} />
                  {isUploading ? 'Ingesting into FAISS...' : 'Choose Files'}
                </button>
              </div>

              <div className="docs-list-card">
                <div className="docs-list-header">
                  <div>
                    <h3>Session Documents in Vector Index</h3>
                    <span style={{ fontSize: 12, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
                      {documents.length} document{documents.length === 1 ? '' : 's'} indexed
                    </span>
                  </div>
                  {documents.length > 0 && (
                    <button
                      type="button"
                      className="copy-mini-btn"
                      style={{
                        background: 'rgba(255, 77, 77, 0.12)',
                        border: '1px solid rgba(255, 77, 77, 0.35)',
                        color: '#ff4d4d',
                        padding: '5px 12px',
                        borderRadius: 8,
                        fontSize: 11.5,
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6
                      }}
                      onClick={handleClearAllDocuments}
                      title="Clear all documents from knowledge base"
                    >
                      <Trash2 size={12} />
                      Clear All Documents
                    </button>
                  )}
                </div>

                {documents.length === 0 ? (
                  <div style={{ padding: '40px 24px', textAlign: 'center', color: 'var(--text-dim)', fontSize: 13.5 }}>
                    No documents ingested for this session yet. Upload files above to build your FAISS knowledge base.
                  </div>
                ) : (
                  <div className="docs-table-wrapper">
                    <table className="docs-table">
                      <thead>
                        <tr>
                          <th>Document Name</th>
                          <th>Chunks in FAISS</th>
                          <th>File Size</th>
                          <th>Ingested At</th>
                          <th>Status</th>
                          <th style={{ textAlign: 'right' }}>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {documents.map((doc, idx) => (
                          <tr key={idx}>
                            <td className="doc-name-cell">
                              <FileText size={16} color="var(--cyan-primary)" />
                              <span>{doc.filename}</span>
                            </td>
                            <td style={{ fontFamily: 'var(--font-mono)' }}>{doc.num_chunks} chunks</td>
                            <td style={{ fontFamily: 'var(--font-mono)' }}>{formatBytes(doc.file_size_bytes)}</td>
                            <td style={{ fontSize: 12, color: 'var(--text-dim)' }}>
                              {doc.uploaded_at ? new Date(doc.uploaded_at).toLocaleTimeString() : 'Recent'}
                            </td>
                            <td>
                              <span className="agent-status-badge completed">
                                <CheckCircle2 size={11} /> Ready
                              </span>
                            </td>
                            <td style={{ textAlign: 'right' }}>
                              <button
                                type="button"
                                className="doc-table-delete-btn"
                                onClick={() => handleDeleteDocument(doc.filename)}
                                title={`Remove "${doc.filename}" from knowledge base`}
                              >
                                <Trash2 size={13} />
                                <span>Remove</span>
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* TAB 4: SESSION HISTORY */}
          {navTab === 'history' && (
            <div className="history-list-card">
              <div className="docs-list-header">
                <div>
                  <h3>Session Query History</h3>
                  <span style={{ fontSize: 12, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
                    {sessionHistory.length} query record{sessionHistory.length === 1 ? '' : 's'}
                  </span>
                </div>
                {sessionHistory.length > 0 && (
                  <button
                    className="copy-mini-btn"
                    style={{ background: 'rgba(255, 77, 77, 0.12)', border: '1px solid rgba(255, 77, 77, 0.35)', color: '#ff4d4d', padding: '4px 10px', borderRadius: 8, fontSize: 11, cursor: 'pointer' }}
                    onClick={clearHistory}
                    title="Clear history"
                  >
                    Clear History
                  </button>
                )}
              </div>

              {sessionHistory.length === 0 ? (
                <div style={{ padding: '40px 24px', textAlign: 'center', color: 'var(--text-dim)', fontSize: 13.5 }}>
                  No queries in this session yet. All research runs and conversational turns will be audited here.
                </div>
              ) : (
                sessionHistory.map((item, idx) => (
                  <div
                    key={idx}
                    className="history-item-row"
                    onClick={() => {
                      if (item.query) {
                        setInputQuery(item.query)
                        setNavTab('research')
                      }
                    }}
                  >
                    <div className="history-item-left">
                      <div className="history-query-text">{item.query || item.content}</div>
                      <div className="history-time-meta">
                        {item.role?.toUpperCase()} · {item.timestamp ? new Date(item.timestamp).toLocaleTimeString() : 'Recent'}
                        {item.overall_status && ` · Status: ${item.overall_status}`}
                      </div>
                    </div>
                    <span style={{ fontSize: 12, color: 'var(--cyan-primary)', fontFamily: 'var(--font-mono)' }}>
                      Re-run →
                    </span>
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        {/* ── Floating Input Dock (Matching Screenshot 1 & ChatGPT Style) ─────── */}
        <div className="floating-input-dock">
          <div
            className="dock-outer-wrapper"
            onWheel={(e) => {
              if (workspaceRef.current && e.target.tagName !== 'TEXTAREA') {
                workspaceRef.current.scrollTop += e.deltaY
              }
            }}
          >
            {/* ChatGPT-style attached document chips tray */}
            {documents.length > 0 && (
              <div className="dock-attached-tray">
                <div className="dock-attached-tray-label">
                  <FileText size={12} color="var(--cyan-primary)" />
                  <span>Context ({documents.length}):</span>
                </div>
                <div className="dock-attached-chips-scroll">
                  {documents.map((doc, dIdx) => (
                    <div
                      key={dIdx}
                      className="dock-attached-chip"
                      title={`${doc.filename} (${formatBytes(doc.file_size_bytes)})`}
                    >
                      <div className="chip-file-icon">
                        <FileText size={12} />
                      </div>
                      <span className="chip-file-name">{doc.filename}</span>
                      <span className="chip-file-size">{formatBytes(doc.file_size_bytes)}</span>
                      <button
                        type="button"
                        className="chip-remove-btn"
                        onClick={(e) => {
                          e.stopPropagation()
                          handleDeleteDocument(doc.filename)
                        }}
                        title={`Remove "${doc.filename}" from context`}
                      >
                        <X size={12} />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="dock-inner">
              <button
                type="button"
                className="dock-attach-btn"
                onClick={() => fileInputRef.current?.click()}
                title="Attach PDF, DOCX, or TXT document"
                disabled={isUploading}
              >
                <Paperclip size={16} />
              </button>

              <button
                className={`mode-toggle-btn ${mode === 'research' ? 'research' : ''}`}
                onClick={() => {
                  const nextMode = mode === 'research' ? 'chat' : 'research'
                  setMode(nextMode)
                  setNavTab(nextMode)
                }}
                title="Click to toggle between 4-Agent Research and Direct Chat"
              >
                {mode === 'research' ? <FlaskConical size={14} /> : <MessageSquare size={14} />}
                <span>{mode === 'research' ? 'Research' : 'Chat'}</span>
              </button>

              <textarea
                className="dock-textarea"
                placeholder={
                  mode === 'research'
                    ? 'Enter research question — the 4-agent pipeline will run...'
                    : 'Ask anything, or upload docs to chat with them...'
                }
                value={inputQuery}
                onChange={(e) => setInputQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    handleSend()
                  }
                }}
                rows={1}
                disabled={isLoading}
              />

              <span className="dock-hint">
                Enter to send · Shift+Enter for new line
              </span>

              <button
                className="dock-send-btn"
                onClick={() => handleSend()}
                disabled={isLoading || !inputQuery.trim()}
                aria-label="Send message"
              >
                {isLoading ? (
                  <div className="spinner-sm" />
                ) : (
                  <Send size={18} />
                )}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* ── Toast Notifications Stack ──────────────────────────────────────── */}
      <div className="toast-stack">
        {toasts.map((t) => (
          <div key={t.id} className={`toast-item ${t.type}`}>
            {t.type === 'success' && <CheckCircle2 size={15} color="var(--status-ok)" />}
            {t.type === 'error' && <AlertCircle size={15} color="var(--status-err)" />}
            {t.type === 'info' && <Info size={15} color="var(--cyan-primary)" />}
            <span>{t.message}</span>
          </div>
        ))}
      </div>
    </>
  )
}
