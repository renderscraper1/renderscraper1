-- Usamos IF NOT EXISTS para que solo las cree si faltan, sin borrar los datos existentes.

CREATE TABLE IF NOT EXISTS catalogo_unificado (
    ean TEXT PRIMARY KEY,
    product_name TEXT,
    brand TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS current_products (
    store_slug TEXT NOT NULL,
    ean TEXT NOT NULL REFERENCES catalogo_unificado(ean),
    cat1 TEXT,
    cat2 TEXT,
    cat3 TEXT,
    price NUMERIC,
    stock INTEGER,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (store_slug, ean)
);

CREATE TABLE IF NOT EXISTS price_history (
    id BIGSERIAL PRIMARY KEY,
    store_slug TEXT NOT NULL,
    ean TEXT NOT NULL REFERENCES catalogo_unificado(ean),
    previous_price NUMERIC,
    new_price NUMERIC,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_current_products_ean ON current_products (ean);
CREATE INDEX IF NOT EXISTS idx_price_history_ean ON price_history (ean);

CREATE OR REPLACE VIEW vista_descarga_productos AS
SELECT 
    c.ean, 
    c.product_name, 
    c.brand, 
    p.cat1, 
    p.cat2, 
    p.cat3, 
    p.price, 
    p.updated_at AS fecha_scrapeo, 
    p.store_slug AS plataforma
FROM catalogo_unificado c
JOIN current_products p ON c.ean = p.ean
WHERE p.stock = 1;
