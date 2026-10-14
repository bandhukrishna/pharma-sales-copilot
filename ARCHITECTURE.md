# Pharma Sales & Brand Copilot — Architecture Document

**Version:** 1.0
**Date:** October 2026
**Author:** AI Architect Case Study Submission

---

## 1. System Overview

The Pharma Sales & Brand Copilot is a conversational AI assistant designed for pharmaceutical field sales teams. It provides a unified natural language interface to query structured sales data, retrieve information from business documents, and ensure compliance with brand messaging guidelines.

The system combines three core AI capabilities:

- **Text-to-SQL:** Translates natural language into validated SQL queries against a pharma sales database.
- **RAG (Retrieval-Augmented Generation):** Retrieves and synthesizes answers from chunked business documents with source citations.
- **Compliance Checking:** Validates generated responses against the Respira brand playbook to prevent non-compliant messaging.

---

## 2. Architecture Diagram

```text
┌─────────────────────────────────────────────────────────────────────┐
│                        STREAMLIT CHAT UI                            │
│              (app.py — Chat, SQL, Tables, Charts, Citations)        │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ User Question
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      ORCHESTRATOR (orchestrator.py)                  │
│                                                                     │
│  ┌──────────────┐    Routes to appropriate handler:                 │
│  │   ROUTER      │──► SQL ──► handle_sql()                          │
│  │  (router.py)  │──► RAG ──► handle_rag()                          │
│  │               │──► HYBRID ──► handle_hybrid()                    │
│  │  Rule-based   │──► CLARIFICATION ──► handle_clarification()      │
│  │  + LLM        │──► REFUSAL ──► handle_refusal()                  │
│  └──────────────┘                                                   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    HANDLER PIPELINES                          │   │
│  │                                                              │   │
│  │  SQL Pipeline:        RAG Pipeline:      HYBRID Pipeline:    │   │
│  │  ┌──────────────┐    ┌──────────────┐   ┌───────────────┐   │   │
│  │  │ sql_generator │    │  rag_engine  │   │ rag_engine +  │   │   │
│  │  │  (LLM → SQL)  │    │  (ChromaDB   │   │ sql_generator │   │   │
│  │  └──────┬───────┘    │   retrieve)  │   └───────────────┘   │   │
│  │         ▼            └──────┬───────┘                        │   │
│  │  ┌──────────────┐          │                                 │   │
│  │  │  sql_engine   │          │                                 │   │
│  │  │ (validate +   │          │                                 │   │
│  │  │  execute RO)  │          │                                 │   │
│  │  └──────┬───────┘          │                                 │   │
│  │         ▼                  ▼                                  │   │
│  │  ┌──────────────────────────────────────────────────────┐    │   │
│  │  │           LLM SYNTHESIS (Groq API)                    │    │   │
│  │  │     Generates natural language answer from context     │    │   │
│  │  └──────────────────────────┬───────────────────────────┘    │   │
│  └─────────────────────────────┼────────────────────────────────┘   │
│                                ▼                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              COMPLIANCE CHECKER                               │   │
│  │   Validates answer against Respira brand playbook rules       │   │
│  └──────────────────────────────────────────────────────────────┘   │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ Response (answer + SQL + data + chart + citations)
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        STREAMLIT CHAT UI                            │
│         Displays: Answer, SQL, DataTable, Chart, Citations          │
└─────────────────────────────────────────────────────────────────────┘

DATA LAYER:
┌─────────────────────┐    ┌─────────────────────────┐
│  pharma_sales.db     │    │  ChromaDB (chroma_db/)   │
│  (SQLite, read-only) │    │  (Vector embeddings of   │
│  - products (5 rows) │    │   20 document chunks)    │
│  - sales (348 rows)  │    │                          │
└─────────────────────┘    └─────────────────────────┘
```

---

## 3. Component Design Details

### 3.1 Question Router (router.py)

The router classifies every incoming question into one of five categories using a two-tier approach:

**Tier 1 — Deterministic Rule-Based Matching (No LLM cost):**

- Pattern-matched regex rules scan for SQL signals (e.g., "total sales", "how many", "trend"), RAG signals (e.g., "policy", "approved messages", "market share"), HYBRID signals (e.g., "did North achieve its target"), and REFUSAL signals (e.g., "delete", "ignore instructions", "DROP TABLE").
- A RAG-priority layer distinguishes conceptual policy questions ("how is quota calculated?") from actual-data-needed questions ("did North hit its quota?").
- If confidence is above 0.6, the rule-based route is used directly.

**Tier 2 — LLM Fallback:**

- For ambiguous questions (confidence below 0.6), the LLM classifies the question with a structured system prompt.
- This ensures coverage for edge cases while minimizing API costs.

**Design Choice:** Rule-based first reduces latency and API costs by approximately 80% of queries. The LLM fallback ensures robustness for novel phrasings.

### 3.2 Text-to-SQL Pipeline (sql_generator.py + sql_engine.py)

**Generation:**

- The LLM receives the database schema, business rules (fiscal year definitions, quarter mappings, currency conventions), and the user question.
- Business definitions from `sales_ops_faq.md` are hardcoded in `config.py` to ensure deterministic SQL generation (the LLM does not need to guess fiscal year boundaries).

**Validation (Two Independent Layers):**

| Layer | Mechanism | Purpose |
|-------|-----------|---------|
| Layer 1: Code-level | Regex blocks 16 dangerous SQL patterns (DELETE, DROP, INSERT, UPDATE, ALTER, TRUNCATE, etc.) | Catches obvious threats before DB connection |
| Layer 2: SQLite-level | Connection opened with `mode=ro` URI parameter | Failsafe — even if Layer 1 misses something, the DB physically cannot be modified |

Additional safety: multi-statement detection (blocks SQL injection via semicolons), automatic LIMIT clause injection, and result set capping at 500 rows.

**Design Choice:** Two independent safety layers ensure that even if the LLM generates malicious SQL, the database remains protected. This is a defense-in-depth approach that does not rely on LLM behavior for safety.

### 3.3 RAG Pipeline (rag_engine.py)

**Document Ingestion:**

- Four markdown documents are chunked by section headers (`##`).
- Each chunk is prefixed with the document title (`#` header) for context.
- Chunks smaller than 20 characters are discarded.
- Result: 20 chunks stored in ChromaDB with cosine similarity indexing.

**Retrieval:**

- User queries are embedded and matched against the 20 chunks.
- Top 3-4 chunks are returned with metadata (source filename and section name).
- Distance scores enable relevance ranking.

**Citations:**

- Every RAG answer includes explicit citations in the format: `[1] filename.md → Section Name`.
- The LLM synthesis prompt requires grounding all claims in the retrieved context.

**Design Choice:** Section-level chunking (rather than fixed-size) preserves semantic coherence of policy sections. The small document corpus (approximately 5,200 characters total) means all content is well-covered with 20 chunks.

### 3.4 Compliance Engine (orchestrator.py)

- After every answer is generated, a compliance check runs for Respira-related content.
- The checker retrieves banned messaging rules from the brand playbook and asks the LLM to verify the answer against them.
- Violations are appended as warnings to the response.

**Design Choice:** Post-generation checking (rather than pre-generation filtering) ensures the user always receives an answer, with compliance warnings clearly flagged. This mirrors real pharmaceutical compliance review workflows.

### 3.5 Chart Generation (sql_generator.py)

- Automatic detection of chart-appropriate queries based on question keywords ("trend", "monthly", "compare") and data shape (time columns, multiple rows).
- Line charts for time-series data and bar charts for categorical comparisons.
- Built with Plotly for interactive hover tooltips and zoom.

---

## 4. Data Flow Examples

### Example 1: SQL Query ("Total Cardivex sales in Q1 FY27")

```text
User Question → Router [SQL, rule-based] → sql_generator [LLM → SQL]
→ sql_engine [validate → execute read-only] → DataFrame
→ LLM synthesis [data → natural language] → Compliance check → UI
```

### Example 2: RAG Query ("Approved Respira messages")

```text
User Question → Router [RAG, rule-based] → rag_engine [ChromaDB retrieve top 4]
→ LLM synthesis [chunks → answer with citations] → Compliance check → UI
```

### Example 3: HYBRID Query ("Did North hit its Cardivex quota?")

```text
User Question → Router [HYBRID, rule-based]
→ PARALLEL: rag_engine [retrieve targets] + sql_generator [get actual sales]
→ LLM synthesis [combine targets + actuals → comparison] → Compliance check → UI
```

---

## 5. Trade-offs and Design Decisions

| Decision | Choice Made | Alternative Considered | Rationale |
|----------|-------------|----------------------|-----------|
| Routing approach | Rule-based + LLM fallback | Pure LLM routing | Reduces latency and cost by approximately 80%, deterministic for common patterns |
| SQL safety | Two independent layers | LLM-only guardrails | Safety must not depend on LLM behavior — defense in depth |
| RAG chunking | Section-based (by ## headers) | Fixed-size (512 tokens) | Documents are small and section-aligned; preserves semantic units |
| Vector store | ChromaDB (local) | Pinecone, Weaviate | No external dependencies, simple setup, sufficient for 20 chunks |
| LLM provider | Groq (GPT-OSS-120B) | OpenAI GPT-4o | Free tier available, fast inference, OpenAI-compatible API |
| Compliance check | Post-generation validation | Pre-generation filtering | Users always get an answer; violations are flagged transparently |
| Chart generation | Auto-detection | Always generate or never | Only generates when data shape and question suggest visual value |

---

## 6. Known Limitations

1. **Single-turn only:** The copilot does not maintain multi-turn conversation context. Each question is processed independently.
2. **No authentication:** The Streamlit UI has no user authentication or role-based access control.
3. **Fixed document corpus:** Adding new documents requires re-running the ingestion pipeline. There is no dynamic document upload.
4. **LLM variability:** While routing is mostly deterministic, SQL generation and synthesis depend on LLM output, which may occasionally vary between runs.
5. **English only:** The system is designed for English-language queries and documents.
6. **No caching:** Repeated identical questions trigger fresh LLM calls. A response cache could reduce latency and cost.
7. **Rate limits:** Groq free tier has rate limits that may affect batch evaluation runs. The system does not implement automatic retry with backoff.

---

## 7. Future Improvements

- **Multi-turn conversation:** Add session memory for follow-up questions.
- **Response caching:** Cache LLM responses for repeated queries.
- **Dynamic document ingestion:** Allow uploading new documents via the UI.
- **Confidence scoring:** Display routing and answer confidence to users.
- **Streaming responses:** Use LLM streaming for faster perceived response times.
- **Observability:** Add logging and tracing for production monitoring.
