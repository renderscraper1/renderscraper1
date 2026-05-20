import os
from decimal import Decimal
from typing import List, Dict, Any, Tuple

import psycopg2
from psycopg2.extras import execute_values

# Verifica que exista el archivo schema.sql en la misma carpeta
schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
try:
    SCHEMA_SQL = open(schema_path, encoding='utf-8').read()
except FileNotFoundError:
    print("⚠️ ADVERTENCIA: No se encontró schema.sql. Se asume que las tablas ya existen.")
    SCHEMA_SQL = ""


def connect_db():
    url = os.getenv('DATABASE_URL')
    if not url:
        raise RuntimeError('Falta DATABASE_URL. Asegurate de tenerla en GitHub Secrets o en tu .env local.')
    return psycopg2.connect(
        url,
        sslmode="require"
    )


def ensure_schema(conn):
    if not SCHEMA_SQL:
        return
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
    conn.commit()


def _rows_to_map(rows):
    out = {}
    for row in rows:
        ean = str(row[0]).strip()
        # Ahora solo extraemos precio y stock (list_price fue eliminado)
        out[ean] = {
            'price': row[1],
            'stock': row[2]
        }
    return out


def _normalize_row(r: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(r)
    out['store_slug'] = str(out.get('store_slug', '')).strip()
    out['ean'] = str(out.get('ean', '')).strip()
    return out


def _dedupe_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    dedup: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for r in rows:
        nr = _normalize_row(r)
        store_slug = nr.get('store_slug', '')
        ean = nr.get('ean', '')
        if not store_slug or not ean:
            continue
        dedup[(store_slug, ean)] = nr
    return list(dedup.values())


def fetch_existing_current(conn, store_slug: str, eans: List[str]):
    if not eans:
        return {}
    
    eans = [str(e).strip() for e in eans if str(e).strip()]
    if not eans:
        return {}

    with conn.cursor() as cur:
        cur.execute(
            '''
            SELECT ean, price, stock
            FROM current_products
            WHERE store_slug = %s AND ean = ANY(%s)
            ''',
            (store_slug, eans),
        )
        return _rows_to_map(cur.fetchall())


def upsert_current_and_history(conn, rows: List[Dict[str, Any]]):
    if not rows:
        return {'current_upserted': 0, 'history_inserted': 0}

    rows = _dedupe_rows(rows)
    if not rows:
        return {'current_upserted': 0, 'history_inserted': 0}

    store_slug = rows[0]['store_slug']
    eans = [str(r['ean']).strip() for r in rows if str(r.get('ean', '')).strip()]
    existing = fetch_existing_current(conn, store_slug, eans)

    catalog_values = []
    current_values = []
    history_values = []

    def _to_decimal(val):
        if val is None or val == '':
            return None
        try:
            return Decimal(str(val))
        except (ValueError, TypeError, Exception):
            return None

    for r in rows:
        ean = str(r.get('ean', '')).strip()
        if not ean:
            continue

        # 1. Alimentamos el catálogo unificado (sin stock ni precio)
        catalog_values.append((
            ean,
            r.get('product_name'),
            r.get('brand')
        ))

        new_price = _to_decimal(r.get('price'))
        new_stock = r.get('stock')

        # 2. Alimentamos la tabla de estados actuales
        current_values.append((
            r['store_slug'],
            ean,
            r.get('cat1'),
            r.get('cat2'),
            r.get('cat3'),
            new_price,
            new_stock
        ))

        # 3. Lógica del historial: Solo si hay cambios y si hay stock = 1
        prev = existing.get(ean)
        if prev is not None:
            prev_price_dec = _to_decimal(prev['price'])
            
            if prev_price_dec != new_price and new_stock == 1:
                history_values.append((
                    r['store_slug'],
                    ean,
                    prev_price_dec,
                    new_price
                ))

    # Transacción SQL segura
    with conn:
        with conn.cursor() as cur:
            if catalog_values:
                execute_values(
                    cur,
                    '''
                    INSERT INTO catalogo_unificado (ean, product_name, brand)
                    VALUES %s
                    ON CONFLICT (ean) DO NOTHING
                    ''',
                    catalog_values,
                    page_size=500,
                )

            if current_values:
                execute_values(
                    cur,
                    '''
                    INSERT INTO current_products
                    (store_slug, ean, cat1, cat2, cat3, price, stock)
                    VALUES %s
                    ON CONFLICT (store_slug, ean) DO UPDATE SET
                        cat1 = EXCLUDED.cat1,
                        cat2 = EXCLUDED.cat2,
                        cat3 = EXCLUDED.cat3,
                        price = EXCLUDED.price,
                        stock = EXCLUDED.stock,
                        updated_at = NOW()
                    ''',
                    current_values,
                    page_size=500,
                )

            if history_values:
                execute_values(
                    cur,
                    '''
                    INSERT INTO price_history
                    (store_slug, ean, previous_price, new_price)
                    VALUES %s
                    ''',
                    history_values,
                    page_size=500,
                )

    return {
        'current_upserted': len(current_values),
        'history_inserted': len(history_values)
    }
