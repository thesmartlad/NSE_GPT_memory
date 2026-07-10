# NSE_GPT_memory
# 🏦 NSE GPT: Unified 3-Tier Memory Engine for Corporate Compliance

An enterprise-grade, privacy-compliant hybrid memory architecture for local Large Language Models (LLMs). This project addresses a critical challenge in corporate AI deployment: **How do you provide an AI with deep long-term project context while strictly adhering to corporate data-retention and privacy mandates?**

In secure financial or corporate environments (like NSE India), keeping permanent records of raw daily chat logs violates strict data security policies. This framework introduces a self-cleaning memory pipeline that completely purges daily conversation histories while cleanly distilling and saving permanent user preferences and high-level project milestones.

---

## 🧠 System Architecture

The system operates three distinct memory layers in parallel to balance immediate context window performance with absolute corporate compliance:

1. **👤 Semantic Profile (Permanent User Identity):** Captures user-specific background traits, organizational roles, and strict formatting preferences instantly (e.g., *"I am a Senior IT Analyst"* or *"Format code in Python"*). This layer bypasses daily wipes and remains in the database persistently. (Stored via SQLite).
2. **📜 Episodic Staging (Daytime Scaffolding):** A temporary, high-performance vector-database staging area that logs raw daytime user interactions. This provides the AI with seamless cross-chat multitasking and crash-recovery context during the workday. (Stored via ChromaDB).
3. **📁 Project Vault (Long-Term Work History):** A consolidated ledger that tracks up to **5 active technical initiatives** (e.g., *"Options Trading Engine Latency"* or *"Automated Report Generator"*), summarizing conversational milestones into clean, high-level structural logs. (Stored via SQLite).

---

## ⏰ Accelerated 7-Minute "End of Day" Purge Lifecycle

To facilitate real-time demonstrations and evaluation without waiting 24 hours, this application features an accelerated **7-Minute EOD Lifecycle Timer**:

* **Staging Phase:** During active work sessions, raw queries build up safely in the *Episodic Staging* layer, allowing the local LLM to leverage high-dimensional vector search matching.
* **The Midnight Purge (Automated every 7 minutes):** A background compaction agent triggers automatically, reads the day's raw logs, matches the details to existing or new projects, updates the *Project Vault*, and then **completely wipes the Episodic Staging log to 0 Bytes**.
* **Strict 5-Project Cap:** Database logic automatically enforces a strict ceiling limit—if a user attempts to work on more than 5 initiatives across days, the engine cleanly prunes the oldest or least relevant project tracking folder to prevent data bloat.

---

## 📊 3-Tier Storage & Memory Dashboard

The workspace includes a comprehensive graphical telemetry dashboard tracking your digital memory footprint:
* **Total Vault Size:** Tracks the precise real-time cumulative cost of your AI's intelligence.
* **Live Buffer Tracking:** A running clock visual displaying the countdown until the next automated data purge.
* **Data Flow Transparency:** Separate panels visually confirming the instantaneous population of your Semantic Profile alongside the isolation of your Episodic Staging logs.

---

## 🛠️ Complete Installation & Local Deployment

This project runs completely locally, ensuring that no enterprise data ever leaves your host computer. Open your system terminal and execute the following steps to deploy the system:

```bash
# STEP 1: Model Requirements
# Ensure you have Ollama installed on your machine.
# Pull the required inference and embedding models via your terminal:
ollama pull qwen2.5:1.5b
ollama pull nomic-embed-text

# STEP 2: Environment Setup
# Clone your repository or create a clean project directory, navigate inside it,
# and install the required core Python frameworks:
pip install streamlit requests chromadb

# STEP 3: Launching the Application
# Execute the Streamlit framework file to boot up the engine 
# and automatically open the interactive web interface in your default browser:
streamlit run nse_memory_app.py
