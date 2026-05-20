# config_farmaonline.py
BASE_URL = "https://www.farmaciasdelpueblo.com.ar"
CATEGORY_TREE_URL = f"{BASE_URL}/api/catalog_system/pub/category/tree/2"

PAGE_SIZE  = 50
MAX_ITEMS  = 2000

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/json, text/plain, */*",
    "Referer": BASE_URL,
    "Origin": BASE_URL,
    "Connection": "keep-alive"
}

def build_products_request(category, from_idx, to_idx):
    # Si 'path_ids' existe la usamos; si no, caemos al id suelto
    filtro = category.get("path_ids", str(category["id"]))

    url  = f"{BASE_URL}/api/catalog_system/pub/products/search"
    params = {
        "fq":   f"C:{filtro}",          # ←  'C:3/4'
        "_from": from_idx,
        "_to":   to_idx,
    }
    return url, params

def extract_fields_for_csv(prod):
    return {
        "productId":        prod.get("productId"),
        "productName":      prod.get("productName"),
        "brand":            prod.get("brand"),
        "categoryId":       prod.get("categoryId"),
        "productReference": prod.get("productReference"),
        "productTitle":     prod.get("productTitle"),
        "releaseDate":      prod.get("releaseDate")
    }
