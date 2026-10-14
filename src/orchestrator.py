"""
Copilot Orchestrator & Compliance Engine.
Ties together: Router → SQL/RAG/Hybrid → LLM Synthesis → Compliance Check.
"""

import re
from typing import Dict, Any
from openai import OpenAI
from src.config import GROQ_API_KEY, GROQ_BASE_URL, MODEL_NAME
from src.router import route_question, RouteType
from src.sql_generator import ask_sql
from src.rag_engine import retrieve, format_citations


def _get_client() -> OpenAI:
    return OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL)


def _synthesize_answer(question: str, context: str, role_hint: str = "") -> str:
    system_prompt = f"""You are a helpful Pharma Sales & Brand Copilot assistant.
Answer the user's question based ONLY on the provided context.
{role_hint}

Rules:
- Be concise and professional.
- If the context contains numerical data, include the exact numbers in your answer.
- Format large INR values with ₹ symbol (e.g., ₹3.07 Cr or ₹30,76,816).
- ALWAYS mention specific entity names (product names, region names, brand names) from the context.
- ALWAYS extract and present relevant information from the context, even if it does not perfectly match the question's wording.
- For example, if asked about "market share" and the context discusses market position, prescriber trends, or competitive landscape, USE that information to form your answer.
- If the context contains information RELATED to the question, you MUST use it to answer. Only say "I don't have enough information" if the context is truly about a completely different topic.
- NEVER make up or hallucinate information not present in the context.
- When citing documents, mention the source document and section.
- Include ALL relevant details from the context — do not omit key data points."""

    client = _get_client()
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Question: {question}\n\nContext:\n{context}"},
        ],
        max_tokens=800,
        temperature=0.1,
    )
    return response.choices[0].message.content.strip()


def _check_compliance(answer: str) -> Dict[str, Any]:
    banned_chunks = retrieve("messages that must NOT be used for Respira", n_results=2)

    banned_text = ""
    for chunk in banned_chunks:
        if "respira_brand_playbook" in chunk["source"]:
            banned_text += chunk["text"] + "\n"

    if not banned_text:
        return {"is_compliant": True, "violations": []}

    if not re.search(r"\brespira\b", answer.lower()):
        return {"is_compliant": True, "violations": []}

    client = _get_client()
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": f"""You are a pharmaceutical compliance checker.
Check if the following answer violates any of the banned messaging rules.

BANNED MESSAGING RULES:
{banned_text}

Respond in this exact JSON format:
{{"is_compliant": true/false, "violations": ["list of specific violations if any"]}}

If the answer does not mention Respira or does not violate any rules, return:
{{"is_compliant": true, "violations": []}}""",
            },
            {"role": "user", "content": f"Answer to check:\n{answer}"},
        ],
        max_tokens=200,
        temperature=0,
    )

    reply = response.choices[0].message.content.strip()

    try:
        json_match = re.search(r"\{.*\}", reply, re.DOTALL)
        if json_match:
            import json

            return json.loads(json_match.group())
    except (json.JSONDecodeError, AttributeError):
        pass

    return {"is_compliant": True, "violations": []}


def handle_sql(question: str) -> Dict[str, Any]:
    result = ask_sql(question)

    if result["error"]:
        return {
            "answer": f"I encountered an error generating the SQL query: {result['error']}",
            "sql": result["sql"],
            "data": None,
            "chart": None,
            "citations": None,
            "route": "SQL",
        }

    data_str = (
        result["data"].to_string(index=False)
        if result["data"] is not None
        else "No data"
    )
    context = f"SQL Query: {result['sql']}\n\nQuery Results:\n{data_str}"
    answer = _synthesize_answer(
        question,
        context,
        role_hint="You are interpreting SQL query results from a pharma sales database.",
    )

    return {
        "answer": answer,
        "sql": result["sql"],
        "data": result["data"],
        "chart": result["chart"],
        "citations": None,
        "route": "SQL",
    }


def handle_rag(question: str) -> Dict[str, Any]:
    chunks = retrieve(question, n_results=4)

    if not chunks:
        return {
            "answer": "I couldn't find relevant information in the business documents to answer this question.",
            "sql": None,
            "data": None,
            "chart": None,
            "citations": None,
            "route": "RAG",
        }

    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        context_parts.append(
            f"[Source {i}: {chunk['source']} → {chunk['section']}]\n{chunk['text']}"
        )
    context = "\n\n---\n\n".join(context_parts)

    answer = _synthesize_answer(
        question,
        context,
        role_hint=(
            "You are answering from business documents. ALWAYS cite the source document and section. "
            "Include ALL specific details: names, numbers, percentages, and key terms from the documents. "
            "Do NOT summarize away important details. "
            "If the context discusses market position, competitive landscape, prescriber trends, or threats, "
            "present ALL of that information in your answer."
        ),
    )
    citations = format_citations(chunks)

    return {
        "answer": answer,
        "sql": None,
        "data": None,
        "chart": None,
        "citations": citations,
        "route": "RAG",
    }


def handle_hybrid(question: str) -> Dict[str, Any]:
    # Step 1: Get relevant documents (more chunks for hybrid)
    chunks = retrieve(question, n_results=4)
    doc_context = ""
    for i, chunk in enumerate(chunks, 1):
        doc_context += (
            f"[Source {i}: {chunk['source']} → {chunk['section']}]\n{chunk['text']}\n\n"
        )

    # Step 2: Get SQL data
    sql_result = ask_sql(question)
    sql_context = ""
    if sql_result["error"]:
        sql_context = f"Database query error: {sql_result['error']}"
    elif sql_result["data"] is not None:
        sql_context = f"SQL: {sql_result['sql']}\nResults:\n{sql_result['data'].to_string(index=False)}"

    # Step 3: Synthesize with explicit comparison instruction
    combined_context = f"=== Document Context (targets, policies, rules) ===\n{doc_context}\n\n=== Database Results (actual data) ===\n{sql_context}"

    answer = _synthesize_answer(
        question,
        combined_context,
        role_hint=(
            "You MUST combine information from BOTH the business documents AND the database results. "
            "Specifically:\n"
            "1. State the TARGET or POLICY value from the documents (cite the source).\n"
            "2. State the ACTUAL value from the database query results.\n"
            "3. COMPARE actual vs target — calculate the percentage attainment if relevant.\n"
            "4. State clearly whether the target was achieved or missed.\n"
            "5. Use ₹ symbol for currency values. Include exact numbers.\n"
            "If either the target or actual data is missing, state what is missing."
        ),
    )
    citations = format_citations(chunks)

    return {
        "answer": answer,
        "sql": sql_result.get("sql"),
        "data": sql_result.get("data"),
        "chart": sql_result.get("chart"),
        "citations": citations,
        "route": "HYBRID",
    }


def handle_clarification(question: str) -> Dict[str, Any]:
    return {
        "answer": (
            "I'd like to help, but your question is a bit ambiguous. Could you clarify?\n\n"
            "Here are some things I can help with:\n"
            "- **Sales data**: Total sales, regional breakdowns, product trends, monthly comparisons\n"
            "- **Incentive policy**: FY27 targets, payout bands, eligibility rules\n"
            "- **Brand guidelines**: Approved/banned Respira messaging, brand positioning\n"
            "- **Market reports**: Competitor analysis, market share updates\n"
            "- **Sales operations FAQ**: Fiscal year definitions, quota calculations\n\n"
            "Please rephrase with more specifics!"
        ),
        "sql": None,
        "data": None,
        "chart": None,
        "citations": None,
        "route": "CLARIFICATION",
    }


def handle_refusal(question: str) -> Dict[str, Any]:
    return {
        "answer": (
            "I'm unable to process this request. This could be because:\n"
            "- The question is outside my scope (pharma sales & brand operations)\n"
            "- The request involves modifying data (I only support read-only queries)\n"
            "- The question asks for sensitive or personal information\n\n"
            "I'm here to help with sales analytics, brand guidelines, incentive policies, and market reports."
        ),
        "sql": None,
        "data": None,
        "chart": None,
        "citations": None,
        "route": "REFUSAL",
    }


def process_question(question: str) -> Dict[str, Any]:
    route, method = route_question(question)

    handlers = {
        RouteType.SQL: handle_sql,
        RouteType.RAG: handle_rag,
        RouteType.HYBRID: handle_hybrid,
        RouteType.CLARIFICATION: handle_clarification,
        RouteType.REFUSAL: handle_refusal,
    }

    result = handlers[route](question)
    result["route_method"] = method

    compliance = _check_compliance(result["answer"])
    result["compliance"] = compliance

    if not compliance["is_compliant"]:
        result["answer"] += (
            "\n\n⚠️ **Compliance Warning**: This response may contain messaging that "
            "conflicts with the Respira Brand Playbook. Violations detected:\n"
            + "\n".join(f"- {v}" for v in compliance["violations"])
        )

    return result


# --- CLI Test ---
if __name__ == "__main__":
    print("=" * 70)
    print("  PHARMA SALES & BRAND COPILOT — End-to-End Test")
    print("=" * 70)

    test_questions = [
        "What are the total sales for Cardivex in Q1 FY27?",
        "What are the approved key messages for Respira?",
        "Did the North region achieve its Cardivex quota in Q1 FY27?",
        "How is quota attainment calculated and what is the payout at 95%?",
        "What is our market share for Neurolyn and what competitive threats were noted in Q1 FY27?",
        "Tell me about performance",
        "Delete all records from the database",
    ]

    for q in test_questions:
        print(f"\n{'─' * 70}")
        print(f"Q: {q}")
        print(f"{'─' * 70}")

        result = process_question(q)

        print(f"  Route:      {result['route']} (via {result['route_method']})")
        print(f"  Compliant:  {result['compliance']['is_compliant']}")

        if result["sql"]:
            print(f"  SQL:        {result['sql'][:80]}...")
        if result["citations"]:
            print(
                f"  Citations:\n    {result['citations'].replace(chr(10), chr(10) + '    ')}"
            )

        print(f"\n  Answer:\n    {result['answer'][:400]}...")

    print(f"\n{'=' * 70}")
    print("✅ End-to-end orchestrator tests complete!")
