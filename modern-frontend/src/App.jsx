import { useState, useRef, useEffect } from 'react'
import axios from 'axios'
import { v4 as uuidv4 } from 'uuid'
import { 
  Send, UploadCloud, FileText, Trash2, Plus, 
  Activity, LayoutDashboard, BrainCircuit, Loader2, 
  Terminal, Sparkles, CheckCircle2 
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import './index.css'

const API_BASE = 'http://localhost:8000/api/v1'

function App() {
  const [sessionId, setSessionId] = useState(uuidv4())
  const [chatHistory, setChatHistory] = useState([])
  const [uploadedDocs, setUploadedDocs] = useState([])
  const [query, setQuery] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [agentSteps, setAgentSteps] = useState([])
  const chatEndRef = useRef(null)
  const fileInputRef = useRef(null)

  const scrollToBottom = () => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [chatHistory, agentSteps])

  const handleNewSession = () => {
    setSessionId(uuidv4())
    setChatHistory([])
    setUploadedDocs([])
    setAgentSteps([])
  }

  const handleClearChat = async () => {
    setChatHistory([])
    setAgentSteps([])
    try {
      await axios.delete(`${API_BASE}/history/${sessionId}`)
    } catch (e) {
      console.error('Failed to clear history on backend')
    }
  }

  const handleFileUpload = async (e) => {
    const files = e.target.files
    if (!files.length) return

    for (let i = 0; i < files.length; i++) {
      const file = files[i]
      if (uploadedDocs.includes(file.name)) continue

      const formData = new FormData()
      formData.append('file', file)

      try {
        await axios.post(`${API_BASE}/upload`, formData, {
          params: { session_id: sessionId },
          headers: { 'Content-Type': 'multipart/form-data' }
        })
        setUploadedDocs(prev => [...prev, file.name])
      } catch (err) {
        alert(`Failed to upload ${file.name}`)
      }
    }
  }

  const handleSend = async () => {
    if (!query.trim() || isLoading) return
    
    const userQuery = query.trim()
    setQuery('')
    setChatHistory(prev => [...prev, { role: 'user', content: userQuery }])
    setIsLoading(true)
    
    // Simulate real-time tracing start
    setAgentSteps([
      { agent: 'Planner', status: 'Thinking...', icon: Terminal },
      { agent: 'Researcher', status: 'Pending', icon: Activity },
      { agent: 'Summarizer', status: 'Pending', icon: FileText },
      { agent: 'Report Generator', status: 'Pending', icon: Sparkles }
    ])

    try {
      const resp = await axios.post(`${API_BASE}/research`, {
        session_id: sessionId,
        query: userQuery,
        has_documents: uploadedDocs.length > 0
      })

      const data = resp.data
      setAgentSteps([]) 
      setChatHistory(prev => [...prev, { role: 'bot', content: data.final_report || 'No report generated.' }])
    } catch (err) {
      setAgentSteps([])
      setChatHistory(prev => [...prev, { role: 'bot', content: '❌ **Error:** API request failed. Ensure the Uvicorn backend is running and `GEMINI_API_KEY` is set in your `.env` file.' }])
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="app-layout">
      {/* Background FX */}
      <div className="background-fx">
        <div className="blob blob-1"></div>
        <div className="blob blob-2"></div>
      </div>

      {/* Sidebar */}
      <aside className="sidebar-advanced">
        <div className="brand-header">
          <BrainCircuit size={28} color="var(--neon-cyan)" />
          MARA AI
        </div>

        <div className="glass-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <span style={{ fontSize: '0.85rem', color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '1px' }}>
              <LayoutDashboard size={14} style={{ display: 'inline', marginRight: '6px', verticalAlign: 'text-bottom' }}/>
              Session ID
            </span>
          </div>
          <p style={{ fontSize: '0.8rem', color: 'var(--neon-purple)', fontFamily: 'monospace', marginBottom: '16px' }}>
            {sessionId.substring(0, 12)}...
          </p>
          
          <div style={{ display: 'flex', gap: '8px' }}>
            <button className="btn-cyber" style={{ flex: 1 }} onClick={handleNewSession}>
              <Plus size={16} /> New
            </button>
            <button className="btn-cyber" style={{ flex: 1 }} onClick={handleClearChat}>
              <Trash2 size={16} /> Clear
            </button>
          </div>
        </div>

        <div className="glass-card" style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
          <div style={{ marginBottom: '16px', fontSize: '0.85rem', color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '1px' }}>
            <FileText size={14} style={{ display: 'inline', marginRight: '6px', verticalAlign: 'text-bottom' }}/>
            Knowledge Base
          </div>
          
          <div 
            className="upload-modern"
            onClick={() => fileInputRef.current?.click()}
          >
            <UploadCloud className="upload-icon" size={32} color="var(--text-dim)" />
            <div>
              <span style={{ color: 'var(--text-main)', fontWeight: 600 }}>Click to upload</span>
              <p>PDF, DOCX, TXT</p>
            </div>
            <input 
              type="file" 
              ref={fileInputRef} 
              style={{ display: 'none' }} 
              multiple 
              accept=".pdf,.docx,.txt"
              onChange={handleFileUpload}
            />
          </div>

          <div style={{ marginTop: '20px', overflowY: 'auto', flex: 1, display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {uploadedDocs.map(doc => (
              <div key={doc} style={{ 
                background: 'rgba(255,255,255,0.03)', 
                border: '1px solid var(--border-glass)',
                padding: '10px 14px', 
                borderRadius: '8px',
                fontSize: '0.85rem',
                display: 'flex',
                alignItems: 'center',
                gap: '10px'
              }}>
                <FileText size={16} color="var(--neon-pink)" />
                <span style={{ textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>{doc}</span>
                <CheckCircle2 size={14} color="var(--neon-cyan)" style={{ marginLeft: 'auto' }} />
              </div>
            ))}
          </div>
        </div>
      </aside>

      {/* Main Chat Area */}
      <main className="chat-wrapper">
        <div className="messages-area">
          {chatHistory.length === 0 && (
            <div style={{ margin: 'auto', textAlign: 'center', opacity: 0.7, transform: 'translateY(-20px)' }}>
              <div style={{ position: 'relative', display: 'inline-block', marginBottom: '24px' }}>
                <BrainCircuit size={80} color="var(--neon-cyan)" style={{ filter: 'drop-shadow(0 0 20px rgba(6, 182, 212, 0.5))' }} />
              </div>
              <h2 style={{ fontSize: '2rem', background: 'var(--gradient-glow)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                System Online.
              </h2>
              <p style={{ color: 'var(--text-dim)', marginTop: '8px', fontSize: '1.1rem' }}>Upload intelligence files and initialize a query.</p>
            </div>
          )}

          {chatHistory.map((msg, idx) => (
            <div key={idx} className={`msg-row ${msg.role}`}>
              <div className="msg-avatar">
                {msg.role === 'user' ? <Terminal size={20} /> : <BrainCircuit size={22} />}
              </div>
              <div className="msg-bubble">
                <ReactMarkdown>{msg.content}</ReactMarkdown>
              </div>
            </div>
          ))}

          {/* Active Agent Tracing UI */}
          {isLoading && agentSteps.length > 0 && (
            <div className="msg-row bot">
              <div className="msg-avatar">
                <Activity size={22} />
              </div>
              <div className="msg-bubble" style={{ minWidth: '320px' }}>
                <div style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--neon-cyan)', textTransform: 'uppercase', letterSpacing: '1.5px' }}>
                  Execution Pipeline Active
                </div>
                
                <div className="trace-container">
                  {agentSteps.map((step, idx) => (
                    <div key={idx} className={`agent-item ${step.status === 'Thinking...' ? 'active' : ''}`}>
                      <div className="agent-icon-box">
                        {step.status === 'Thinking...' ? <Loader2 size={16} className="spin" color="var(--neon-purple)" /> : <step.icon size={16} />}
                      </div>
                      <div>
                        <div style={{ fontWeight: 600, color: 'white', fontSize: '0.9rem' }}>{step.agent}</div>
                        <div style={{ fontSize: '0.75rem', color: step.status === 'Thinking...' ? 'var(--neon-cyan)' : 'var(--text-dim)' }}>
                          {step.status}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>

        <div className="input-zone">
          <div className="input-glass">
            <input 
              type="text" 
              placeholder="Initialize research directive..." 
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
              disabled={isLoading}
              autoFocus
            />
            <button className="btn-send" onClick={handleSend} disabled={isLoading || !query.trim()}>
              <Send size={20} style={{ marginLeft: '-2px' }} />
            </button>
          </div>
        </div>
      </main>
    </div>
  )
}

export default App
