"""
Text-to-SQL Generator & Chart Generator.
- Converts natural language questions to SQL using LLM.
- Validates generated SQL before execution.
- Generates Plotly charts for time-series / trend queries.
"""

import json
import re
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from openai import OpenAI
from src.config import (
    GROQ_API_KEY,
    GROQ_BASE_URL,
    MODEL_NAME,
    load_schema,
    FISCAL_YEAR_DEFINITION,
    QUARTER_DEFINITIONS,
    BUSINESS_RULES,
    QUOTA_ATTAINMENT_FORMULA,
)
from src.sql_engine import execute_sql, validate_sql, SQLValidationError


def generate_sql(question: str) -> str:
    """
    Use LLM to convert a natural language question into a SQL query.
    Returns the generated SQL string.
    """
    schema = load_schema()

    system_prompt = f"""You are a SQL expert for a pharmaceutical sales database. 
Generate a single SQLite-compatible SELECT query to answer the user's question.

DATABASE SCHEMA:
{schema}

CRITICAL BUSINESS RULES:
- Fiscal Year: Indian FY (April to March). FY27 = {FISCAL_YEAR_DEFINITION["FY27"]}. FY26 = {FISCAL_YEAR_DEFINITION["FY26"]}.
- Quarters: Q1={QUARTER_DEFINITIONS["Q1"]["label"]} (months 04,05,06), Q2={QUARTER_DEFINITIONS["Q2"]["label"]} (months 07,08,09), Q3={QUARTER_DEFINITIONS["Q3"]["label"]} (months 10,11,12), Q4={QUARTER_DEFINITIONS["Q4"]["label"]} (months 01,02,03).
- sale_month format: {BUSINESS_RULES["sale_month_format"]}
- To filter by quarter, use: substr(sale_month, 6, 2) IN ('04','05','06') for Q1, etc.
- To filter by fiscal year FY27: sale_month >= '2026-04-01' AND sale_month <= '2027-03-01'
- {QUOTA_ATTAINMENT_FORMULA}
- Currency: {BUSINESS_RULES["currency"]}
- Regions: North, South, East, West (case-sensitive in data)
- When asked about a brand (e.g., "Cardivex"), join with products table and filter by brand.
- When asked about a specific product, filter by product_name.
- Always use net_sales_inr for revenue/sales amount questions.
- Always use units for volume questions.

RESPONSE FORMAT:
Return ONLY the SQL query. No explanations, no markdown, no code fences.
Do NOT wrap in ```sql``` blocks.
Just the raw SQL query ending with a semicolon."""

    client = OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL)

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
        max_tokens=500,
        temperature=0,
    )

    sql = response.choices[0].message.content.strip()

    # Clean up: remove markdown code fences if LLM adds them anyway
    sql = re.sub(r"^```sql\s*", "", sql)
    sql = re.sub(r"^```\s*", "", sql)
    sql = re.sub(r"\s*```$", "", sql)
    sql = sql.strip()

    return sql


def detect_chart_type(question: str, df: pd.DataFrame) -> str:
    """
    Determine if and what type of chart to generate.
    Returns: 'line', 'bar', 'none'
    """
    question_lower = question.lower()

    # Check for time-series / trend signals
    trend_signals = [
        r"\btrend\b",
        r"\bmonth[\s-]?over[\s-]?month\b",
        r"\bover\s+time\b",
        r"\bmonthly\b",
        r"\bquarterly\b",
        r"\bgrowth\b",
        r"\btime\s+series\b",
    ]
    is_trend = any(re.search(p, question_lower) for p in trend_signals)

    # Check if dataframe has time-like column
    has_time_col = False
    for col in df.columns:
        if "month" in col.lower() or "date" in col.lower() or "quarter" in col.lower():
            has_time_col = True
            break

    if is_trend and has_time_col:
        return "line"

    # Check for comparison signals
    comparison_signals = [
        r"\bcompare\b",
        r"\bregion[\s-]?wise\b",
        r"\bproduct[\s-]?wise\b",
        r"\bby\s+(region|product|brand)\b",
        r"\btop\b",
        r"\branking\b",
    ]
    is_comparison = any(re.search(p, question_lower) for p in comparison_signals)

    if is_comparison and len(df) <= 20:
        return "bar"

    # Auto-detect: if there's a time column and multiple rows, show line
    if has_time_col and len(df) > 1:
        return "line"

    # If there's a categorical column and a numeric, show bar
    if len(df) > 1 and len(df) <= 20:
        return "bar"

    return "none"


def generate_chart(df: pd.DataFrame, chart_type: str, question: str):
    """
    Generate a Plotly figure based on the data and chart type.
    Returns a Plotly figure object or None.
    """
    if chart_type == "none" or df.empty or len(df) < 2:
        return None

    # Identify x and y columns
    cols = df.columns.tolist()

    # Find time/category column (x-axis)
    x_col = None
    for col in cols:
        if any(
            kw in col.lower()
            for kw in ["month", "date", "quarter", "region", "product", "brand", "name"]
        ):
            x_col = col
            break
    if x_col is None:
        x_col = cols[0]

    # Find numeric columns (y-axis)
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    if not numeric_cols:
        return None

    y_col = numeric_cols[0]

    # Check if there's a grouping column (for multi-line/grouped bar)
    group_col = None
    for col in cols:
        if col != x_col and col not in numeric_cols and df[col].nunique() <= 10:
            group_col = col
            break

    try:
        if chart_type == "line":
            if group_col:
                fig = px.line(
                    df,
                    x=x_col,
                    y=y_col,
                    color=group_col,
                    title=f"{y_col} over {x_col}",
                    markers=True,
                )
            else:
                fig = px.line(
                    df,
                    x=x_col,
                    y=y_col,
                    title=f"{y_col} over {x_col}",
                    markers=True,
                )
        elif chart_type == "bar":
            if group_col:
                fig = px.bar(
                    df,
                    x=x_col,
                    y=y_col,
                    color=group_col,
                    title=f"{y_col} by {x_col}",
                    barmode="group",
                )
            else:
                fig = px.bar(
                    df,
                    x=x_col,
                    y=y_col,
                    title=f"{y_col} by {x_col}",
                )
        else:
            return None

        fig.update_layout(
            template="plotly_white",
            height=400,
            margin=dict(l=50, r=50, t=50, b=50),
        )
        return fig

    except Exception:
        return None


def ask_sql(question: str) -> dict:
    """
    Full pipeline: question → SQL → validate → execute → chart.

    Returns dict with keys:
        'sql': generated SQL string
        'data': pandas DataFrame
        'chart': Plotly figure or None
        'error': error message or None
    """
    result = {
        "sql": None,
        "data": None,
        "chart": None,
        "error": None,
    }

    try:
        # Step 1: Generate SQL
        sql = generate_sql(question)
        result["sql"] = sql

        # Step 2: Validate + Execute
        df, clean_sql = execute_sql(sql)
        result["sql"] = clean_sql
        result["data"] = df

        # Step 3: Generate chart if appropriate
        chart_type = detect_chart_type(question, df)
        if chart_type != "none":
            result["chart"] = generate_chart(df, chart_type, question)

    except SQLValidationError as e:
        result["error"] = f"SQL Safety Error: {e}"
    except Exception as e:
        result["error"] = f"SQL Error: {e}"

    return result


# --- CLI Test ---
if __name__ == "__main__":
    print("=== Text-to-SQL Generator Tests ===\n")

    test_questions = [
        "What are the total sales for Cardivex in Q1 FY27?",
        "Show me monthly sales trend for Respira Inhaler",
        "Which region had the highest revenue in FY27?",
        "List all products with their brand and therapeutic area",
    ]

    for q in test_questions:
        print(f'Q: "{q}"')
        result = ask_sql(q)

        if result["error"]:
            print(f"  ❌ Error: {result['error']}")
        else:
            print(f"  SQL: {result['sql'][:100]}...")
            print(f"  Rows: {len(result['data'])}")
            print(f"  Chart: {'Yes' if result['chart'] else 'No'}")
            if result["data"] is not None and not result["data"].empty:
                print(result["data"].head(5).to_string(index=False))
        print()

    print("✅ SQL Generator tests complete!")
