# 💊 Pharma Sales & Brand Copilot

An AI-powered conversational assistant for pharmaceutical sales teams. It answers questions about sales data, incentive policies, brand guidelines, and market reports using a combination of Text-to-SQL, Retrieval-Augmented Generation (RAG), and compliance checking.

---

## 🎯 Key Features

| Feature | Description |
|---------|-------------|
| **Text-to-SQL** | Converts natural language to SQL queries against a pharma sales database |
| **RAG** | Retrieves and cites information from 4 business documents |
| **Hybrid Queries** | Combines database results with document context (e.g., quota vs target) |
| **Compliance Engine** | Validates answers against Respira brand playbook rules |
| **Safety Guardrails** | Two-layer read-only SQL enforcement + prompt injection blocking |
| **Smart Routing** | Rule-based + LLM fallback routing across 5 categories |
| **Interactive UI** | Streamlit chat with SQL display, data tables, charts, and citations |

---

## 📋 Prerequisites

- **Python 3.11+** (tested with 3.11.9)
- **Git** (for version control)
- **Make** (for one-command execution)
- **Groq API Key** ([Get one free](https://console.groq.com))

---

## 🚀 Quick Start

### 1. Clone and enter the project

```bash
git clone https://github.com/your-username/pharma-sales-copilot.git
cd pharma-sales-copilot
```

### 2. Set up environment

```bash
py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Configure API key

```bash
cp .env.example .env
```

Edit `.env` and set `GROQ_API_KEY=your-key-here`

### 4. Run the app

```bash
make run
```

### 5. Run tests and evaluation

```bash
make test    # 40 unit tests
make eval    # 10 Golden Questions → eval_results.md
```

---

## 📁 Project Structure

```text
pharma-sales-copilot/
├── app.py                    # Streamlit chat UI
├── eval.py                   # Automated evaluation (10 Golden Questions)
├── Makefile                  # One-command runners
├── requirements.txt          # Python dependencies
├── .env.example              # Environment template (safe to commit)
├── .gitignore                # Git exclusions
├── golden_questions.md       # Evaluation benchmark questions
├── data/
│   ├── pharma_sales.db       # SQLite database (products + sales)
│   ├── products.csv          # 5 pharma products
│   ├── sales.csv             # 348 monthly sales records
│   └── schema.sql            # Database schema definition
├── docs/
│   ├── incentive_policy_fy27.md    # FY27 incentive targets and payout bands
│   ├── market_report_q1_fy27.md    # Q1 FY27 competitor and market report
│   ├── respira_brand_playbook.md   # Respira approved and banned messaging
│   └── sales_ops_faq.md            # Business definitions and FAQ
├── src/
│   ├── __init__.py
│   ├── config.py             # Configuration and business definitions
│   ├── sql_engine.py         # Read-only SQL validator and executor
│   ├── rag_engine.py         # Document chunking and ChromaDB retrieval
│   ├── router.py             # Question routing (SQL/RAG/HYBRID/CLARIFICATION/REFUSAL)
│   ├── sql_generator.py      # Text-to-SQL and chart generation
│   └── orchestrator.py       # End-to-end pipeline and compliance engine
├── tests/
│   ├── __init__.py
│   ├── test_sql_validation.py  # SQL safety unit tests (20 tests)
│   └── test_router.py          # Routing logic unit tests (20 tests)
└── .streamlit/
    └── config.toml           # Streamlit theme configuration
```

---

## 📊 Database Schema

| Table | Rows | Description |
|-------|------|-------------|
| `products` | 5 | Product catalog (Cardivex, Respira, Glucora, Neurolyn) |
| `sales` | 348 | Monthly sales by product and region (Apr 2025 to Sep 2026) |

**Key fields:** `sale_month` (YYYY-MM-DD), `product_id`, `region` (North/South/East/West), `units`, `net_sales_inr`

---

## 🧠 Documented Assumptions

1. **Fiscal Year:** Indian FY (April to March). FY27 = Apr 2026 to Mar 2027.
2. **Quarters:** Q1=Apr-Jun, Q2=Jul-Sep, Q3=Oct-Dec, Q4=Jan-Mar.
3. **Quota Attainment:** Always calculated on `net_sales_inr`, never units.
4. **Currency:** All monetary values in INR (Indian Rupees).
5. **Date Format:** `sale_month` stores the first day of each month (e.g., `2026-04-01`).
6. **Brand Compliance:** Respira messaging is checked against `respira_brand_playbook.md` Section 4 (banned messages).
7. **Read-Only:** The database is never modified. SQL validation blocks all non-SELECT statements at both code and SQLite connection levels.

---

## 🔒 Safety and Compliance

- **Two-layer SQL safety:** Regex-based blocking + SQLite `mode=ro` connection
- **Prompt injection detection:** Rule-based pattern matching for manipulation attempts
- **Brand compliance:** Automated checking against Respira banned messaging rules
- **Honest uncertainty:** Returns "I don't have enough information" when context is insufficient
- **No hallucination:** LLM answers are grounded in retrieved context only

---

## 📈 Evaluation Results

Run `make eval` to generate `eval_results.md`. Current score: **10/10 Golden Questions passed.**

| Category | Questions | Pass Rate |
|----------|-----------|-----------|
| SQL (data queries) | Q1, Q2, Q3, Q10 | 4/4 |
| RAG (document queries) | Q4, Q5, Q7, Q8 | 4/4 |
| HYBRID (data + docs) | Q6 | 1/1 |
| REFUSAL (safety) | Q9 | 1/1 |

---

## 🛠️ Technology Stack

| Component | Technology |
|-----------|------------|
| LLM | GPT-OSS-120B via Groq API |
| Vector Store | ChromaDB (local, persistent) |
| Database | SQLite (read-only) |
| Web UI | Streamlit |
| Charts | Plotly |
| Testing | pytest |
| Language | Python 3.11 |
