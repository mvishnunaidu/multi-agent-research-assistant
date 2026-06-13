"""
app.py — Streamlit frontend for Multi-Agent Research Assistant.

Start with:
    streamlit run frontend/app.py
"""
import os
import uuid
import streamlit as st
import requests

API_BASE = os.getenv("BACKEND_URL", "http://localhost:8000/api/v1")

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Research Assistant",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* App Background */
.stApp {
    background-color: #0e1117;
}

/* Sidebar Styling */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0f131a 0%, #161b22 100%);
    border-right: 1px solid rgba(255,255,255,0.05);
}

/* Gradient Title */
h1 {
    background: linear-gradient(90deg, #a5b4fc 0%, #6366f1 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 800;
    letter-spacing: -0.5px;
}

/* Glassmorphism Agent Cards */
.agent-card {
    background: rgba(30, 36, 51, 0.7);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    border: 1px solid rgba(255,255,255,0.05);
    border-left: 4px solid #6366f1;
    border-radius: 8px;
    padding: 14px 16px;
    margin: 8px 0;
    font-size: 0.9rem;
    color: #e2e8f0;
    transition: all 0.3s ease;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
}

.agent-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3), 0 4px 6px -2px rgba(0, 0, 0, 0.15);
    border-left: 4px solid #818cf8;
}

.agent-name {
    font-weight: 700;
    color: #a5b4fc;
    text-transform: uppercase;
    font-size: 0.75rem;
    letter-spacing: 0.08em;
    margin-bottom: 6px;
    display: flex;
    align-items: center;
    gap: 6px;
}

/* Source Badges */
.source-badge {
    display: inline-flex;
    align-items: center;
    background: rgba(99, 102, 241, 0.1);
    border: 1px solid rgba(99, 102, 241, 0.2);
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 0.8rem;
    color: #c7d2fe;
    margin: 3px 4px;
    transition: all 0.2s ease;
}
.source-badge:hover {
    background: rgba(99, 102, 241, 0.2);
    border-color: rgba(99, 102, 241, 0.4);
}

/* Chat Input Styling */
[data-testid="stChatInput"] {
    background-color: #161b22 !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 12px !important;
    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
}

/* Hide Streamlit Branding */
#MainMenu, footer { visibility: hidden; }
header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ── Session state ──────────────────────────────────────────────────────────────
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "uploaded_docs" not in st.session_state:
    st.session_state.uploaded_docs = []
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🔬 Research Assistant")
    st.caption(f"Session `{st.session_state.session_id[:8]}…`")
    st.divider()

    st.markdown("### 📄 Upload Documents")
    files = st.file_uploader(
        "PDF · DOCX · TXT",
        type=["pdf", "docx", "txt"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

    if files:
        for f in files:
            if f.name not in st.session_state.uploaded_docs:
                with st.spinner(f"Ingesting {f.name}…"):
                    try:
                        resp = requests.post(
                            f"{API_BASE}/upload",
                            files={"file": (f.name, f.getvalue(), f.type)},
                            params={"session_id": st.session_state.session_id},
                            timeout=60,
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            st.session_state.uploaded_docs.append(f.name)
                            st.success(f"✅ {f.name} — {data['num_chunks']} chunks indexed")
                        else:
                            st.error(f"Upload failed ({resp.status_code}): {resp.text[:200]}")
                    except requests.exceptions.ConnectionError:
                        st.error(
                            "❌ Backend not reachable.\n\n"
                            "Run in a terminal:\n```\nuvicorn backend.main:app --reload\n```"
                        )

    if st.session_state.uploaded_docs:
        st.divider()
        st.markdown("**Indexed documents:**")
        for doc in st.session_state.uploaded_docs:
            st.markdown(f"<span class='source-badge'>📎 {doc}</span>", unsafe_allow_html=True)

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🆕 New Session", use_container_width=True):
            st.session_state.session_id = str(uuid.uuid4())
            st.session_state.uploaded_docs = []
            st.session_state.chat_history = []
            st.rerun()
    with col2:
        if st.button("🗑️ Clear Chat", use_container_width=True):
            st.session_state.chat_history = []
            try:
                requests.delete(
                    f"{API_BASE}/history/{st.session_state.session_id}", timeout=5
                )
            except Exception:
                pass
            st.rerun()

    st.divider()
    st.markdown("#### Agent Pipeline")
    for icon, agent in [("🗺️", "Planner"), ("🔍", "Researcher"),
                         ("📝", "Summarizer"), ("📊", "Report Generator")]:
        st.markdown(f"{icon} {agent}")


# ── Main area ──────────────────────────────────────────────────────────────────
st.markdown("# Multi-Agent Research Assistant")
st.markdown(
    "Ask any question. Upload documents for RAG-powered answers, "
    "or ask without documents for general research."
)

# Render existing chat history
for msg in st.session_state.chat_history:
    avatar = "🔬" if msg["role"] == "assistant" else None
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])

# ── Query input ────────────────────────────────────────────────────────────────
query = st.chat_input("Ask a research question…")

if query:
    st.session_state.chat_history.append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.markdown(query)

    with st.chat_message("assistant", avatar="🔬"):
        with st.spinner("Running agent pipeline…"):
            try:
                payload = {
                    "session_id": st.session_state.session_id,
                    "query": query,
                    "has_documents": len(st.session_state.uploaded_docs) > 0,
                }
                resp = requests.post(
                    f"{API_BASE}/research", json=payload, timeout=180
                )

                if resp.status_code == 200:
                    data = resp.json()

                    # Agent trace
                    with st.expander("🔄 Agent Pipeline Trace", expanded=False):
                        for step in data.get("agent_steps", []):
                            st.markdown(
                                f"<div class='agent-card'>"
                                f"<div class='agent-name'>{step['agent']} — {step['status']}</div>"
                                f"{step.get('output_preview', '')}"
                                f"</div>",
                                unsafe_allow_html=True,
                            )

                    # Research plan
                    if data.get("plan"):
                        with st.expander("🗺️ Research Plan", expanded=False):
                            for i, task in enumerate(data["plan"], 1):
                                st.markdown(f"**{i}.** {task}")
                            if data.get("plan_reasoning"):
                                st.caption(f"_Strategy: {data['plan_reasoning']}_")

                    # Sources
                    if data.get("sources"):
                        badges = "".join(
                            f"<span class='source-badge'>📎 {s}</span>"
                            for s in data["sources"]
                        )
                        st.markdown(f"**Sources:** {badges}", unsafe_allow_html=True)
                        st.markdown("")

                    # Final report
                    st.divider()
                    report = data.get("final_report", "No report generated.")
                    st.markdown(report)

                    st.session_state.chat_history.append(
                        {"role": "assistant", "content": report}
                    )

                else:
                    err_msg = f"❌ Error {resp.status_code}: {resp.text[:300]}"
                    st.error(err_msg)

            except requests.exceptions.ConnectionError:
                st.error(
                    "❌ Cannot connect to the FastAPI backend.\n\n"
                    "Start it with:\n```\nuvicorn backend.main:app --reload\n```"
                )
            except requests.exceptions.Timeout:
                st.error("⏱️ Request timed out. The LLM may be slow — try again.")
            except Exception as e:
                st.error(f"Unexpected error: {str(e)}")
