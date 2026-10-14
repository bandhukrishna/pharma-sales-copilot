"""
Unit tests for SQL validation logic.
Run: pytest tests/test_sql_validation.py -v
"""

import pytest
from src.sql_engine import validate_sql, execute_sql, SQLValidationError


class TestSQLValidation:
    """Test the deterministic SQL safety validator."""

    # --- ALLOWED queries ---

    def test_simple_select(self):
        is_valid, reason = validate_sql("SELECT * FROM products;")
        assert is_valid is True
        assert reason is None

    def test_select_with_join(self):
        sql = "SELECT p.product_name, s.units FROM products p JOIN sales s ON p.product_id = s.product_id;"
        is_valid, reason = validate_sql(sql)
        assert is_valid is True

    def test_select_with_aggregation(self):
        sql = "SELECT region, SUM(net_sales_inr) FROM sales GROUP BY region;"
        is_valid, reason = validate_sql(sql)
        assert is_valid is True

    def test_select_with_where(self):
        sql = (
            "SELECT * FROM sales WHERE region = 'North' AND sale_month >= '2026-04-01';"
        )
        is_valid, reason = validate_sql(sql)
        assert is_valid is True

    def test_cte_query(self):
        sql = "WITH cte AS (SELECT * FROM products) SELECT * FROM cte;"
        is_valid, reason = validate_sql(sql)
        assert is_valid is True

    def test_subquery(self):
        sql = "SELECT * FROM sales WHERE product_id IN (SELECT product_id FROM products WHERE brand = 'Cardivex');"
        is_valid, reason = validate_sql(sql)
        assert is_valid is True

    # --- BLOCKED queries ---

    def test_block_delete(self):
        is_valid, reason = validate_sql("DELETE FROM products WHERE product_id = 1;")
        assert is_valid is False
        assert "DELETE" in reason

    def test_block_drop(self):
        is_valid, reason = validate_sql("DROP TABLE products;")
        assert is_valid is False
        assert "DROP" in reason

    def test_block_insert(self):
        is_valid, reason = validate_sql(
            "INSERT INTO products VALUES (99, 'Hack', 'Bad', 'Evil', '2025-01-01', 0);"
        )
        assert is_valid is False
        assert "INSERT" in reason

    def test_block_update(self):
        is_valid, reason = validate_sql("UPDATE products SET net_price_inr = 0;")
        assert is_valid is False
        assert "UPDATE" in reason

    def test_block_alter(self):
        is_valid, reason = validate_sql("ALTER TABLE products ADD COLUMN hack TEXT;")
        assert is_valid is False
        assert "ALTER" in reason

    def test_block_truncate(self):
        is_valid, reason = validate_sql("TRUNCATE TABLE products;")
        assert is_valid is False
        assert "TRUNCATE" in reason

    def test_block_multiple_statements(self):
        is_valid, reason = validate_sql("SELECT 1; DROP TABLE products;")
        assert is_valid is False

    def test_block_empty_query(self):
        is_valid, reason = validate_sql("")
        assert is_valid is False

    def test_block_none_like_query(self):
        is_valid, reason = validate_sql("   ")
        assert is_valid is False


class TestSQLExecution:
    """Test SQL execution with read-only enforcement."""

    def test_execute_valid_select(self):
        df, sql = execute_sql("SELECT COUNT(*) as cnt FROM products;")
        assert len(df) == 1
        assert df.iloc[0]["cnt"] == 5

    def test_execute_returns_dataframe(self):
        df, sql = execute_sql("SELECT product_name FROM products LIMIT 2;")
        assert len(df) == 2
        assert "product_name" in df.columns

    def test_execute_blocks_delete(self):
        with pytest.raises(SQLValidationError):
            execute_sql("DELETE FROM products;")

    def test_execute_blocks_drop(self):
        with pytest.raises(SQLValidationError):
            execute_sql("DROP TABLE sales;")

    def test_auto_adds_limit(self):
        df, sql = execute_sql("SELECT * FROM sales;")
        assert "LIMIT" in sql.upper()
