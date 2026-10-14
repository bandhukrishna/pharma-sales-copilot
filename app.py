"""
Pharma Sales & Brand Copilot — Streamlit Chat UI.
Run: streamlit run app.py
"""

import streamlit as st
import pandas as pd
from src.orchestrator import process_question
from src.rag_engine import ingest_documents

# --- Page Config ---
st.set_page_config(
    page_title="Pharma Sales & Brand Copilot",
    page_icon="💊",
    layout="wide",
)


# --- Initialize RAG on first run ---
@st.cache_resource
def init_rag():
    """Ingest documents into ChromaDB (runs once)."""
    ingest_documents()
    return True


# --- Session State ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# --- Sidebar ---
with st.sidebar:
    st.title("💊 Pharma Copilot")
    st.markdown("---")
    st.markdown("""
    **What I can help with:**
    - 📊 Sales data & analytics
    - 💰 Incentive policy & targets
    - 🏥 Brand guidelines (Respira)
    - 📈 Market & competitor reports
    - ❓ Sales operations FAQ
    """)
    st.markdown("---")

    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    st.markdown("---")
    st.caption("Powered by Groq + LLaMA | Built for AI Architect Case Study")

# --- Main Chat Area ---
st.title("💊 Pharma Sales & Brand Copilot")
st.caption(
    "Ask me about sales data, incentive policies, brand guidelines, and market reports."
)

# Initialize RAG
with st.spinner("Initializing knowledge base..."):
    init_rag()

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

        # Show expandable details for assistant messages
        if msg["role"] == "assistant" and "details" in msg:
            details = msg["details"]

            # Route badge
            route = details.get("route", "")
            route_method = details.get("route_method", "")
            compliance = details.get("compliance", {})

            col1, col2, col3 = st.columns(3)
            with col1:
                st.caption(f"🔀 Route: **{route}** ({route_method})")
            with col2:
                comp_status = (
                    "✅ Compliant"
                    if compliance.get("is_compliant", True)
                    else "⚠️ Violations"
                )
                st.caption(f"🛡️ {comp_status}")
            with col3:
                if details.get("sql"):
                    st.caption("💾 SQL query available")

            # SQL details
            if details.get("sql"):
                with st.expander("🔍 View SQL Query"):
                    st.code(details["sql"], language="sql")

            # Data table
            if details.get("data") is not None and not details["data"].empty:
                with st.expander(f"📋 View Data ({len(details['data'])} rows)"):
                    st.dataframe(details["data"], use_container_width=True)

            # Chart
            if details.get("chart") is not None:
                st.plotly_chart(details["chart"], use_container_width=True)

            # Citations
            if details.get("citations"):
                with st.expander("📚 Document Citations"):
                    st.text(details["citations"])

# Chat input
if prompt := st.chat_input(
    "Ask a question about pharma sales, brand guidelines, or policies..."
):
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    # Process and respond
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            result = process_question(prompt)

        # Display answer
        st.markdown(result["answer"])

        # Route and compliance info
        col1, col2, col3 = st.columns(3)
        with col1:
            st.caption(f"🔀 Route: **{result['route']}** ({result['route_method']})")
        with col2:
            comp_status = (
                "✅ Compliant"
                if result["compliance"].get("is_compliant", True)
                else "⚠️ Violations"
            )
            st.caption(f"🛡️ {comp_status}")
        with col3:
            if result.get("sql"):
                st.caption("💾 SQL query available")

        # SQL details
        if result.get("sql"):
            with st.expander("🔍 View SQL Query"):
                st.code(result["sql"], language="sql")

        # Data table
        if result.get("data") is not None and not result["data"].empty:
            with st.expander(f"📋 View Data ({len(result['data'])} rows)"):
                st.dataframe(result["data"], use_container_width=True)

        # Chart
        if result.get("chart") is not None:
            st.plotly_chart(result["chart"], use_container_width=True)

        # Citations
        if result.get("citations"):
            with st.expander("📚 Document Citations"):
                st.text(result["citations"])

    # Save to history (convert DataFrame to dict for serialization)
    details = {
        "route": result["route"],
        "route_method": result["route_method"],
        "compliance": result["compliance"],
        "sql": result.get("sql"),
        "data": result.get("data"),
        "chart": result.get("chart"),
        "citations": result.get("citations"),
    }
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": result["answer"],
            "details": details,
        }
    )
