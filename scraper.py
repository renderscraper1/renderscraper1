import asyncio
import importlib
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

from aiohttp import ClientSession, ClientTimeout, TCPConnector

from db import connect_db, ensure_schema, upsert_current_and_history

# Corrección para caracteres especiales en la consola de Windows
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# Controlamos cuántas peticiones simultáneas hacemos para no saturar
MAX_CONCURRENCY = int(os.getenv('SCRAPER_MAX_CONCURRENCY', '10'))
SEM = asyncio.Semaphore(MAX_CONCURRENCY)


def log(msg, symbol='ℹ️'):
    now = datetime.now().strftime('%H:%M:%S')
    print(f'[{now}] {symbol} {msg}', flush=True)


def clean_text(value):
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def normalizar_ean(ean):
    if ean is None:
        return None
    ean = str(ean).strip().replace(' ', '').replace('-', '')
    return ean or None


def calcular_digito_verificador(ean_sin_dv):
    digits = [int(d) for d in ean_sin_dv]
    if len(ean_sin_dv) == 12:
        suma = sum(d * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits))
        return (10 - (suma % 10)) % 10
    if len(ean_sin_dv) == 7:
        suma = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(digits))
        return (10 - (suma % 10)) % 10
    return None


def es_ean_valido(ean):
    ean = normalizar_ean(ean)
    if not ean or not ean.isdigit():
        return False
    if len(ean) == 13:
        dv = calcular_digito_verificador(ean[:-1])
        return dv is not None and int(ean[-1]) == dv
    return False


def safe_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def get_nested(data, path):
    try:
        for part in path.split('.'):
            if isinstance(data, list) and part.isdigit():
                data = data[int(part)]
            elif isinstance(data, dict):
                data = data.get(part)
            else:
                return None
        return data
    except Exception:
        return None


async def get_category_tree(session, config):
    try:
        async with session.get(config.CATEGORY_TREE_URL) as r:
            if r.status == 200:
                log('Árbol de categorías obtenido.', '🌳')
                return await r.json()
            log(f'HTTP {r.status} al obtener el árbol.', '⚠️')
    except Exception as e:
        log(f'Error obteniendo árbol de categorías: {e}', '⚠️')
    return []


def extract_all_categories(tree, chain=None):
    chain = chain or []
    out = []
    for node in tree or []:
        new_chain = chain + [node['id']]
        out.append({'id': node['id'], 'name': node.get('name', ''), 'path_ids': '/'.join(map(str, new_chain))})
        if node.get('children'):
            out.extend(extract_all_categories(node['children'], new_chain))
    return out


async def fetch_batch(session, config, category, _from, _to):
    url, params = config.build_products_request(category, _from, _to)
    cat_name = category.get('name', 'Desconocida')
    
    async with SEM:
       
        try:
            async with session.get(url, params=params, headers=config.HEADERS) as r:
                if r.status in (200, 206):
                    try:
                        data = await r.json()
                    except Exception:
                        log(f'JSON inválido en {cat_name} [{_from}-{_to}]', '⚠️')
                        return None
                    return data or None
                if r.status in (429, 503):
                    log(f'Saturación {r.status} en {cat_name}. Reintento...', '⏳')
                    await asyncio.sleep(10)
                    return 'RETRY'
                if r.status == 403:
                    log(f'403 en {cat_name}. Pausa larga...', '🚫')
                    await asyncio.sleep(60)
                    return 'RETRY'
                log(f'HTTP {r.status} en {cat_name} [{_from}-{_to}]', '❌')
                return None
        except Exception as e:
            log(f'Error red en {cat_name}: {e}', '🔌')
            return 'RETRY'


def parse_product(product: Dict[str, Any], store_slug: str) -> Optional[Dict[str, Any]]:
    items = product.get('items', [])
    if not items:
        return None

    item = items[0]
    ean = normalizar_ean(item.get('ean'))
    if not es_ean_valido(ean):
        return None

    price = safe_float(get_nested(product, 'items.0.sellers.0.commertialOffer.Price'))
    available_quantity = get_nested(product, 'items.0.sellers.0.commertialOffer.AvailableQuantity')
    
    try:
        stock = 1 if available_quantity is not None and float(available_quantity) > 0 else 0
    except Exception:
        stock = 0

    categories = product.get('categories', [])
    cat_path = max(categories, key=lambda c: c.count('/')).strip('/').split('/') if categories else []

    return {
        'store_slug': store_slug,
        'ean': ean,
        'product_name': clean_text(item.get('nameComplete') or product.get('productName')),
        'brand': clean_text(product.get('brand')),
        'cat1': clean_text(cat_path[0]) if len(cat_path) > 0 else None,
        'cat2': clean_text(cat_path[1]) if len(cat_path) > 1 else None,
        'cat3': clean_text(cat_path[2]) if len(cat_path) > 2 else None,
        'price': price,
        'stock': stock
    }


async def run_store(store_slug: str, module_name: str):
    config = importlib.import_module(module_name)

    conn = connect_db()
    try:
        ensure_schema(conn)
        
        # Memoria temporal para ignorar repetidos en esta ejecución
        seen_eans = set() 

        async with ClientSession(connector=TCPConnector(ssl=False), timeout=ClientTimeout(total=60)) as session:
            log(f'Iniciando extracción para {store_slug}', '🚀')
            tree = await get_category_tree(session, config)
            categories = extract_all_categories(tree)
            log(f'Categorías a escanear: {len(categories)}', '📋')

            for category in categories:
                cat_name = category.get('name', 'Desconocida')
                log(f'Escaneando categoría: {cat_name}', '▶️')
                
                for _from in range(0, config.MAX_ITEMS, config.PAGE_SIZE):
                    _to = _from + config.PAGE_SIZE - 1
                    retries = 3
                    
                    while retries > 0:
                        data = await fetch_batch(session, config, category, _from, _to)
                        
                        if data == 'RETRY':
                            retries -= 1
                            await asyncio.sleep(2)
                            continue
                            
                        if not data:
                            if _from == 0:
                                log(f'Categoría vacía: {cat_name}', '👻')
                            break

                        batch = []
                        for product in data:
                            parsed = parse_product(product, store_slug)
                            if parsed:
                                ean = parsed['ean']
                                # Validamos contra la memoria temporal
                                if ean not in seen_eans:
                                    seen_eans.add(ean)
                                    batch.append(parsed)


                        if batch:
                            result = upsert_current_and_history(conn, batch)
                            log(f"{cat_name} [{_from}-{_to}] -> actuales:{result['current_upserted']} historial:{result['history_inserted']}", '✅')
                        break
                    
                    if not data:
                        break
                        
            log(f'Proceso terminado para {store_slug}', '🏁')
    finally:
        conn.close()


def discover_configs(base_dir: str):
    import pathlib
    files = sorted(pathlib.Path(base_dir).glob('config_*.py'))
    return [(f.stem.replace('config_', ''), f.stem) for f in files]
