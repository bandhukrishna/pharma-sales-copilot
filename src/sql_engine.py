"""
Deterministic Read-Only SQL Validator & Executor.
Two-layer safety:
  1. Code-level: regex blocks any non-SELECT statement.
  2. SQLite-level: connection opened in read-only mode (mode=ro).
"""

import re
import sqlite3
import pandas as pd
from typing import Tuple, Optional
from src.config import DB_PATH

# --- Dangerous SQL patterns (case-insensitive) ---
# These are blocked BEFORE the query reaches the database.
BLOCKED_PATTERNS = [
    r"\bINSERT\b",
    r"\bUPDATE\b",
    r"\bDELETE\b",
    r"\bDROP\b",
    r"\bALTER\b",
    r"\bCREATE\b",
    r"\bTRUNCATE\b",
    r"\bREPLACE\b",
    r"\bATTACH\b",
    r"\bDETACH\b",
    r"\bPRAGMA\b(?!\s+table_info)",  # allow PRAGMA table_info only
    r"\bGRANT\b",
    r"\bREVOKE\b",
    r"\bEXEC\b",
    r"\bMERGE\b",
    r"\bVACUUM\b",
    r"\bREINDEX\b",
]

# Compile into a single regex for performance
BLOCKED_REGEX = re.compile("|".join(BLOCKED_PATTERNS), re.IGNORECASE)

# --- Maximum rows to return (safety limit) ---
MAX_ROWS = 500


class SQLValidationError(Exception):
    """Raised when SQL fails safety validation."""

    pass


def validate_sql(sql: str) -> Tuple[bool, Optional[str]]:
    """
    Validate that a SQL query is safe to execute.

    Returns:
        (True, None) if valid
        (False, reason) if blocked
    """
    if not sql or not sql.strip():
        return False, "Empty query"

    cleaned = sql.strip()

    # Remove SQL comments (-- and /* */)
    cleaned_no_comments = re.sub(r"--.*?$", " ", cleaned, flags=re.MULTILINE)
    cleaned_no_comments = re.sub(
        r"/\*.*?\*/", " ", cleaned_no_comments, flags=re.DOTALL
    )

    # Check for blocked patterns
    match = BLOCKED_REGEX.search(cleaned_no_comments)
    if match:
        return (
            False,
            f"Blocked: '{match.group()}' statements are not allowed. Only SELECT queries are permitted.",
        )

    # Must start with SELECT or WITH (for CTEs)
    first_keyword = (
        cleaned_no_comments.strip().split()[0].upper()
        if cleaned_no_comments.strip()
        else ""
    )
    if first_keyword not in ("SELECT", "WITH"):
        return False, f"Query must start with SELECT or WITH. Found: '{first_keyword}'"

    # Check for multiple statements (SQL injection via semicolons)
    # Remove semicolons inside string literals first
    test_str = re.sub(r"'[^']*'", "''", cleaned_no_comments)
    statements = [s.strip() for s in test_str.split(";") if s.strip()]
    if len(statements) > 1:
        return (
            False,
            "Multiple SQL statements detected. Only single SELECT queries are allowed.",
        )

    return True, None


def execute_sql(sql: str) -> Tuple[pd.DataFrame, str]:
    """
    Validate and execute a read-only SQL query.

    Returns:
        (dataframe, clean_sql) on success

    Raises:
        SQLValidationError if query is blocked
        sqlite3.Error if query fails to execute
    """
    # Layer 1: Code-level validation
    is_valid, reason = validate_sql(sql)
    if not is_valid:
        raise SQLValidationError(f"SQL BLOCKED: {reason}")

    cleaned_sql = sql.strip().rstrip(";")

    # Add LIMIT if not present (safety)
    if "LIMIT" not in cleaned_sql.upper():
        cleaned_sql += f" LIMIT {MAX_ROWS}"

    # Layer 2: SQLite read-only connection
    # Using URI with mode=ro ensures the database cannot be modified
    # even if Layer 1 somehow misses a dangerous query
    db_uri = f"file:{DB_PATH}?mode=ro"
    conn = sqlite3.connect(db_uri, uri=True)

    try:
        df = pd.read_sql_query(cleaned_sql, conn)
        return df, cleaned_sql
    except sqlite3.Error as e:
        raise sqlite3.Error(f"SQL execution error: {e}\nQuery: {cleaned_sql}")
    finally:
        conn.close()


# --- CLI Test ---
if __name__ == "__main__":
    print("=== SQL Validator & Executor Tests ===\n")

    # Test 1: Valid SELECT
    print("Test 1: Valid SELECT query")
    try:
        df, sql = execute_sql("SELECT product_name, brand FROM products LIMIT 3;")
        print(f"  ✅ PASSED — {len(df)} rows returned")
        print(df.to_string(index=False))
    except Exception as e:
        print(f"  ❌ FAILED — {e}")

    print()

    # Test 2: Valid aggregate
    print("Test 2: Valid aggregate query")
    try:
        df, sql = execute_sql("""
            SELECT region, SUM(net_sales_inr) as total_sales 
            FROM sales 
            GROUP BY region 
            ORDER BY total_sales DESC;
        """)
        print(f"  ✅ PASSED — {len(df)} rows returned")
        print(df.to_string(index=False))
    except Exception as e:
        print(f"  ❌ FAILED — {e}")

    print()

    # Test 3: Block DELETE
    print("Test 3: Block DELETE query")
    try:
        execute_sql("DELETE FROM products WHERE product_id = 1;")
        print("  ❌ FAILED — DELETE was NOT blocked!")
    except SQLValidationError as e:
        print(f"  ✅ PASSED — Correctly blocked: {e}")

    print()

    # Test 4: Block DROP
    print("Test 4: Block DROP TABLE")
    try:
        execute_sql("DROP TABLE products;")
        print("  ❌ FAILED — DROP was NOT blocked!")
    except SQLValidationError as e:
        print(f"  ✅ PASSED — Correctly blocked: {e}")

    print()

    # Test 5: Block INSERT
    print("Test 5: Block INSERT")
    try:
        execute_sql(
            "INSERT INTO products VALUES (99, 'Hack', 'Bad', 'Evil', '2025-01-01', 0);"
        )
        print("  ❌ FAILED — INSERT was NOT blocked!")
    except SQLValidationError as e:
        print(f"  ✅ PASSED — Correctly blocked: {e}")

    print()

    # Test 6: Block multiple statements
    print("Test 6: Block multiple statements (SQL injection)")
    try:
        execute_sql("SELECT 1; DROP TABLE products;")
        print("  ❌ FAILED — Multi-statement was NOT blocked!")
    except SQLValidationError as e:
        print(f"  ✅ PASSED — Correctly blocked: {e}")

    print()

    # Test 7: Valid WITH (CTE)
    print("Test 7: Valid WITH/CTE query")
    try:
        df, sql = execute_sql("""
            WITH monthly AS (
                SELECT sale_month, SUM(units) as total_units
                FROM sales
                GROUP BY sale_month
            )
            SELECT * FROM monthly ORDER BY sale_month LIMIT 3;
        """)
        print(f"  ✅ PASSED — {len(df)} rows returned")
        print(df.to_string(index=False))
    except Exception as e:
        print(f"  ❌ FAILED — {e}")

    print("\n=== All SQL Engine Tests Complete ===")
