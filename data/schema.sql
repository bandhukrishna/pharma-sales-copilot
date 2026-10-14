CREATE TABLE products (
    product_id       INTEGER PRIMARY KEY,
    product_name     TEXT NOT NULL,
    brand            TEXT NOT NULL,
    therapeutic_area TEXT NOT NULL,
    launch_date      TEXT NOT NULL,   -- YYYY-MM-DD
    net_price_inr    REAL NOT NULL    -- net price per unit
);
CREATE TABLE sales (
    sale_month    TEXT NOT NULL,      -- first day of month, YYYY-MM-DD
    product_id    INTEGER NOT NULL REFERENCES products(product_id),
    region        TEXT NOT NULL,      -- North / South / East / West
    units         INTEGER NOT NULL,
    net_sales_inr REAL NOT NULL,
    PRIMARY KEY (sale_month, product_id, region)
);
