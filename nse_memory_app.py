import streamlit as st
import requests
import chromadb
import sqlite3
import uuid
import json
import time
from datetime import datetime

# --- CONFIGURATION ---
OLLAMA_URL = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"
CHAT_MODEL = "qwen2.5:1.5b"
VECTOR_DIM = 768
VECTOR_BYTE_SIZE = VECTOR_DIM * 4
EOD_INTERVAL_MINUTES = 7

st.set_page_config(page_title="NSE GPT Unified Memory", layout="wide", page_icon="🏦")

# --- UTILS ---
def format_size(size_in_bytes):
    if size_in_bytes < 1024:
        return f"{size_in_bytes} B"
    elif size_in_bytes < 1024 * 1024:
        return f"{size_in_bytes / 1024:.2f} KB"
    else:
        return f"{size_in_bytes / (1024 * 1024):.2f} MB"

def get_text_bytes(text):
    return len(str(text).encode('utf-8'))

# --- DATABASE INITIALIZATION ---
@st.cache_resource
def get_chroma_client():
    client = chromadb.PersistentClient(path="./nse_hybrid_vault")
    return client.get_or_create_collection(name="episodic_vectors")

collection = get_chroma_client()

def init_sqlite():
    conn = sqlite3.connect("nse_memory_tracker.db", check_same_thread=False)
    cursor = conn.cursor()
    
    # 1. Permanent User Profile
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS semantic_kb (
            id TEXT PRIMARY KEY,
            timestamp TEXT,
            fact_text TEXT,
            byte_size INTEGER
        )
    """)
    # 2. Long-Term Projects
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS project_kb (
            project_name TEXT PRIMARY KEY,
            timestamp TEXT,
            summary_content TEXT,
            byte_size INTEGER
        )
    """)
    # 3. Daytime Staging
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS episodic_tracker (
            id TEXT PRIMARY KEY,
            timestamp TEXT,
            raw_text TEXT,
            total_bytes INTEGER
        )
    """)
    conn.commit()
    conn.close()

init_sqlite()

# --- AGENT 1: SEMANTIC PROFILE EXTRACTOR ---
def extract_and_save_semantic_fact(user_message):
    """Aggressively hardened prompt to prevent 1.5B model from extracting projects."""
    conn = sqlite3.connect("nse_memory_tracker.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT id, fact_text FROM semantic_kb")
    current_memory = cursor.fetchall()
    memory_context = "Empty." if not current_memory else "\n".join([f"ID: {row[0]} | Fact: {row[1]}" for row in current_memory])

    eval_prompt = f"""You are a STRICT Semantic Profile Extractor.

CRITICAL RULE: You must ONLY extract permanent personal facts (like job titles) and formatting preferences. 
YOU MUST COMPLETELY IGNORE ANY MENTION OF PROJECTS, TASKS, ASSIGNMENTS, OR DAILY WORK.

--- EXAMPLES ---
User: "I am a Senior IT Analyst."
{{"action": "ADD", "target_id": null, "fact": "The user is a Senior IT Analyst."}}

User: "Format your answers using bullet points."
{{"action": "ADD", "target_id": null, "fact": "The user prefers answers formatted in bullet points."}}

User: "I am working on the Trading Dashboard UI project."
{{"action": "IGNORE", "target_id": null, "fact": null}}

User: "I need to review the server latency logs today."
{{"action": "IGNORE", "target_id": null, "fact": null}}

--- REAL TASK ---
Current Profile: {memory_context}
User: "{user_message}"
"""
    try:
        response = requests.post(f"{OLLAMA_URL}/api/chat", json={
            "model": CHAT_MODEL, "messages": [{"role": "system", "content": eval_prompt}], "stream": False, "format": "json" 
        })
        raw_content = response.json()['message']['content'].strip()
        decision = json.loads(raw_content)
        action = str(decision.get("action")).upper() 
        new_fact = decision.get("fact")
        target_id = decision.get("target_id")

        if action == "ADD" and new_fact:
            mem_id = f"kb_{uuid.uuid4().hex[:8]}"
            cursor.execute("INSERT INTO semantic_kb (id, timestamp, fact_text, byte_size) VALUES (?, ?, ?, ?)",
                           (mem_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), new_fact, get_text_bytes(new_fact)))
            conn.commit()
            st.toast(f"🧠 Added Semantic Profile Fact: '{new_fact}'", icon="✅")
        elif action == "UPDATE" and new_fact and target_id:
            cursor.execute("DELETE FROM semantic_kb WHERE id = ?", (target_id,))
            cursor.execute("INSERT INTO semantic_kb (id, timestamp, fact_text, byte_size) VALUES (?, ?, ?, ?)",
                           (target_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), new_fact, get_text_bytes(new_fact)))
            conn.commit()
            st.toast(f"🔄 Updated Semantic Profile Fact: '{new_fact}'", icon="♻️")
    except Exception as e:
        print(f"[SEMANTIC ERROR]: {e}")
    finally:
        conn.close()

# --- AGENT 2: EOD PROJECT COMPILER ---
def run_eod_consolidation():
    st.toast("⚡ Starting End-of-Day Project Consolidation...", icon="⚙️")
    conn = sqlite3.connect("nse_memory_tracker.db", check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute("SELECT raw_text FROM episodic_tracker")
    logs = cursor.fetchall()
    
    if not logs:
        st.session_state.last_eod_time = time.time()
        conn.close()
        return

    flat_logs = "\n".join([f"- {row[0]}" for row in logs])
    cursor.execute("SELECT project_name, summary_content FROM project_kb")
    existing_projects = cursor.fetchall()
    current_kb_context = "None stored yet." if not existing_projects else "\n".join(
        [f"Project: {p[0]} | Current Knowledge: {p[1]}" for p in existing_projects]
    )

    consolidation_prompt = f"""You are the Project Memory Compiler. Read today's logs and map them to Target Projects.
1. Identify technical projects/tasks.
2. Update existing projects or create new ones. Keep descriptions to 2 sentences.
3. Return STRICTLY as JSON: {{"projects": [{{"project_name": "...", "summary_content": "..."}}]}}

--- CURRENT PROJECTS ---
{current_kb_context}

--- TODAY'S LOGS ---
{flat_logs}
"""
    try:
        response = requests.post(f"{OLLAMA_URL}/api/chat", json={
            "model": CHAT_MODEL, "messages": [{"role": "system", "content": consolidation_prompt}], "stream": False, "format": "json"
        })
        data = json.loads(response.json()['message']['content'].strip())
        project_list = data.get("projects", [])

        for proj in project_list:
            p_name = proj.get("project_name").strip()
            p_content = proj.get("summary_content").strip()
            if p_name and p_content:
                cursor.execute("""
                    INSERT INTO project_kb (project_name, timestamp, summary_content, byte_size)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(project_name) DO UPDATE SET
                        summary_content = excluded.summary_content, byte_size = excluded.byte_size, timestamp = excluded.timestamp
                """, (p_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), p_content, get_text_bytes(p_content)))
        
        conn.commit()

        # Enforce 5-Project Cap
        cursor.execute("SELECT project_name FROM project_kb ORDER BY timestamp DESC")
        all_projs = cursor.fetchall()
        if len(all_projs) > 5:
            for excess in all_projs[5:]:
                cursor.execute("DELETE FROM project_kb WHERE project_name = ?", (excess[0],))
            conn.commit()

        # PURGE DAILY EPISODIC
        cursor.execute("SELECT id FROM episodic_tracker")
        all_ep_ids = [r[0] for r in cursor.fetchall()]
        if all_ep_ids:
            collection.delete(ids=all_ep_ids)
            
        cursor.execute("DELETE FROM episodic_tracker")
        conn.commit()
        
        st.session_state.last_eod_time = time.time()
        st.toast("🌙 Simulated End-of-Day Complete! Episodic purged, Projects updated.", icon="🧹")
    except Exception as e:
        print(f"[EOD ERROR]: {e}")
    finally:
        conn.close()

# --- EPISODIC WRITE ---
def get_embedding(text):
    try:
        response = requests.post(f"{OLLAMA_URL}/api/embeddings", json={"model": EMBED_MODEL, "prompt": text})
        return response.json().get("embedding", [])
    except:
        return []

def save_raw_turn_to_episodic(role, content):
    """Now ONLY saves the user inputs to keep the DB clean."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mem_id = f"ep_{uuid.uuid4().hex[:8]}"
    formatted_log = f"[{role.upper()}]: {content}"
    vector = get_embedding(formatted_log)
    if not vector: return

    collection.add(embeddings=[vector], documents=[formatted_log], ids=[mem_id])
    
    conn = sqlite3.connect("nse_memory_tracker.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO episodic_tracker (id, timestamp, raw_text, total_bytes) VALUES (?, ?, ?, ?)",
                   (mem_id, timestamp, formatted_log, get_text_bytes(formatted_log) + VECTOR_BYTE_SIZE))
    conn.commit()
    conn.close()

# --- UNIFIED RETRIEVAL ENGINE ---
def retrieve_hybrid_context(query):
    context_blocks = []
    
    query_vector = get_embedding(query)
    if query_vector:
        results = collection.query(query_embeddings=[query_vector], n_results=2)
        if results['documents'] and len(results['documents'][0]) > 0:
            matches = "\n".join(results['documents'][0])
            context_blocks.append(f"[TODAY'S ACTIVE CHAT LOG]:\n{matches}")

    conn = sqlite3.connect("nse_memory_tracker.db", check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute("SELECT fact_text FROM semantic_kb")
    semantic_rows = cursor.fetchall()
    if semantic_rows:
        semantic_context = "\n".join([f"- {r[0]}" for r in semantic_rows])
        context_blocks.append(f"[PERMANENT USER PROFILE & RULES]:\n{semantic_context}")

    cursor.execute("SELECT project_name, summary_content FROM project_kb")
    proj_rows = cursor.fetchall()
    if proj_rows:
        proj_context = "\n".join([f"Project ({r[0]}): {r[1]}" for r in proj_rows])
        context_blocks.append(f"[ACTIVE PROJECTS]:\n{proj_context}")
        
    conn.close()
    return "\n\n".join(context_blocks)

# --- APP STATE & TIMER ---
if "messages" not in st.session_state: st.session_state.messages = []
if "last_eod_time" not in st.session_state: st.session_state.last_eod_time = time.time()

elapsed_seconds = time.time() - st.session_state.last_eod_time
time_remaining = max(0.0, (EOD_INTERVAL_MINUTES * 60) - elapsed_seconds)

if elapsed_seconds >= (EOD_INTERVAL_MINUTES * 60):
    run_eod_consolidation()
    st.rerun()

# --- STREAMLIT UI ---
left_col, right_col = st.columns([6, 4], gap="large")

with left_col:
    st.subheader("🏦 NSE GPT Unified Workspace")
    
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if user_input := st.chat_input("Discuss your tasks, or tell me your preferences..."):
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"): st.markdown(user_input)
        
        # ONLY save the user's message to Episodic Staging now
        save_raw_turn_to_episodic("user", user_input)
        
        extract_and_save_semantic_fact(user_input)
        
        hybrid_context = retrieve_hybrid_context(user_input)
        system_prompt = "You are NSE GPT. Use the provided context to personalize your response. Be precise."
        if hybrid_context:
            system_prompt += f"\n\n{hybrid_context}"
            with st.expander("🔍 View All 3 Memory Layers Injected"):
                st.text(hybrid_context)

        payload = [{"role": "system", "content": system_prompt}] + [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
        
        with st.chat_message("assistant"):
            with st.spinner("Analyzing..."):
                try:
                    res = requests.post(f"{OLLAMA_URL}/api/chat", json={"model": CHAT_MODEL, "messages": payload, "stream": False})
                    ai_reply = res.json()['message']['content']
                    st.markdown(ai_reply)
                    st.session_state.messages.append({"role": "assistant", "content": ai_reply})
                    
                    # NOTE: We no longer save ai_reply to the episodic database here!
                except Exception as e:
                    st.error(f"LLM Error: {e}")
        st.rerun()

with right_col:
    st.subheader("📊 3-Tier Memory Dashboard")
    
    mins_left = int(time_remaining // 60)
    secs_left = int(time_remaining % 60)
    st.warning(f"⏳ **Next Simulated EOD Purge In:** `{mins_left:02d}:{secs_left:02d}`")
    
    col_trigger, col_clear = st.columns(2)
    if col_trigger.button("⚡ Force EOD Trigger", use_container_width=True):
        run_eod_consolidation()
        st.rerun()
    if col_clear.button("🗑️ Clear Screen UI", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    conn = sqlite3.connect("nse_memory_tracker.db", check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute("SELECT SUM(byte_size) FROM project_kb")
    proj_bytes = cursor.fetchone()[0] or 0
    cursor.execute("SELECT SUM(total_bytes) FROM episodic_tracker")
    ep_bytes = cursor.fetchone()[0] or 0
    cursor.execute("SELECT SUM(byte_size) FROM semantic_kb")
    sem_bytes = cursor.fetchone()[0] or 0
    
    m_col1, m_col2, m_col3 = st.columns(3)
    m_col1.metric("Total Vault Size", format_size(proj_bytes + ep_bytes + sem_bytes))
    m_col2.metric("Episodic Log", format_size(ep_bytes))
    m_col3.metric("Project + Semantic", format_size(proj_bytes + sem_bytes))
    
    st.divider()

    st.markdown("### 👤 Semantic Profile (Permanent)")
    st.caption("Extracts preferences instantly. Unaffected by EOD purges.")
    cursor.execute("SELECT fact_text FROM semantic_kb ORDER BY timestamp DESC")
    sem_rows = cursor.fetchall()
    if not sem_rows:
        st.info("No personal preferences or traits detected yet.")
    else:
        for r in sem_rows: st.markdown(f"- {r[0]}")

    st.divider()

    st.markdown("### 📜 Episodic Staging (Today)")
    st.caption("Raw chat feed. Completely wiped at EOD.")
    cursor.execute("SELECT timestamp, raw_text FROM episodic_tracker ORDER BY timestamp ASC")
    staging_rows = cursor.fetchall()
    if not staging_rows:
        st.info("No logs in current cycle staging.")
    else:
        with st.expander(f"View {len(staging_rows)} Active Messages", expanded=False):
            for r_time, r_text in staging_rows:
                label = "🧑‍💻 User" if "[USER]" in r_text else "🤖 AI"
                clean_text = r_text.replace("[USER]: ", "").replace("[ASSISTANT]: ", "")
                st.markdown(f"**{label}**: {clean_text}")

    st.divider()

    st.markdown("### 📁 Project Vault (Max 5)")
    st.caption("Consolidated task history updated only at EOD.")
    cursor.execute("SELECT project_name, summary_content FROM project_kb ORDER BY timestamp DESC")
    kb_rows = cursor.fetchall()
    if not kb_rows:
        st.info("No projects consolidated yet.")
    else:
        for p_name, p_content in kb_rows:
            with st.expander(f"{p_name}", expanded=True):
                st.write(p_content)

    conn.close()