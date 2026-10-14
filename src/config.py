"""
Configuration loader and business definitions.
Loads environment variables and defines business constants
derived from sales_ops_faq.md for deterministic use in SQL generation.
"""

import os
from dotenv import load_dotenv

# Load .env from project root
load_dotenv()

# --- API Configuration ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-oss-120b")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")

# --- Paths ---
DB_PATH = os.getenv("DB_PATH", "data/pharma_sales.db")
DOCS_DIR = os.getenv("DOCS_DIR", "docs")
SCHEMA_PATH = os.path.join("data", "schema.sql")

# --- Business Definitions (from sales_ops_faq.md) ---
# These are hardcoded from the FAQ to ensure deterministic SQL generation.
# The LLM should use these rather than guessing.

FISCAL_YEAR_DEFINITION = {
    "description": "Indian fiscal year: April to March",
    "FY27": {"start": "2026-04-01", "end": "2027-03-31"},
    "FY26": {"start": "2025-04-01", "end": "2026-03-31"},
}

QUARTER_DEFINITIONS = {
    "Q1": {"months": ["04", "05", "06"], "label": "April–June"},
    "Q2": {"months": ["07", "08", "09"], "label": "July–September"},
    "Q3": {"months": ["10", "11", "12"], "label": "October–December"},
    "Q4": {"months": ["01", "02", "03"], "label": "January–March"},
}

REGIONS = ["North", "South", "East", "West"]

QUOTA_ATTAINMENT_FORMULA = (
    "Quota attainment (%) = (Actual net sales / Target net sales) × 100. "
    "It is always based on net_sales_inr, NOT units."
)

BUSINESS_RULES = {
    "sale_month_format": "YYYY-MM-DD (first day of the month, e.g., '2026-04-01')",
    "currency": "INR (Indian Rupees)",
    "sales_metric": "net_sales_inr for revenue; units for volume",
    "primary_key_sales": "(sale_month, product_id, region)",
    "fiscal_year": "April to March (Indian FY)",
}


# --- Schema (loaded from file) ---
def load_schema() -> str:
    """Load the SQL schema definition from file."""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return f.read().strip()


# --- Validation ---
def validate_config():
    """Check that all required config values are present."""
    errors = []
    if not GROQ_API_KEY:
        errors.append("GROQ_API_KEY is not set in .env")
    if not os.path.exists(DB_PATH):
        errors.append(f"Database not found at {DB_PATH}")
    if not os.path.exists(DOCS_DIR):
        errors.append(f"Docs directory not found at {DOCS_DIR}")
    if not os.path.exists(SCHEMA_PATH):
        errors.append(f"Schema file not found at {SCHEMA_PATH}")
    if errors:
        raise EnvironmentError("Config validation failed:\n  " + "\n  ".join(errors))
    return True


if __name__ == "__main__":
    print("=== Config Validation ===")
    try:
        validate_config()
        print(f"  API Key:    {GROQ_API_KEY[:8]}...")
        print(f"  Model:      {MODEL_NAME}")
        print(f"  Base URL:   {GROQ_BASE_URL}")
        print(f"  DB Path:    {DB_PATH}")
        print(f"  Docs Dir:   {DOCS_DIR}")
        print(f"  Schema:     {SCHEMA_PATH}")
        print(f"\n  FY27:       {FISCAL_YEAR_DEFINITION['FY27']}")
        print(f"  Q1 months:  {QUARTER_DEFINITIONS['Q1']}")
        print(f"  Regions:    {REGIONS}")
        print(f"\n  Schema preview:")
        schema = load_schema()
        print(f"    {schema[:120]}...")
        print("\n✅ All config valid!")
    except EnvironmentError as e:
        print(f"\n❌ {e}")
