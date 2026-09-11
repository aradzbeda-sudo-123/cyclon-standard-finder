import json
import re
from pathlib import Path

CATALOG_FILE = Path(__file__).with_name("cyclon_catalog.json")


def normalize(value):
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def load_cyclon_products():
    with open(CATALOG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def product_search_keys(product):
    keys = set()

    for value in product.get("search_keys", []) or []:
        key = normalize(value)
        if key:
            keys.add(key)

    for standard in product.get("standards", []) or []:
        s = str(standard).upper()
        n = normalize(s)

        if n:
            keys.add(n)

        if "VW" in s:
            for num in re.findall(r"\b(5\d{2})[\s.\-]*00\b", s):
                keys.add("VW" + num)

        if "MB" in s:
            for match in re.findall(r"\b229[\s.\-]*(\d+)\b", s):
                keys.add("MB229" + match)

        if "BMW" in s and "LONGLIFE" in s:
            m = re.search(r"LONGLIFE[\s\-]*(\d+)", s)
            if m:
                value = m.group(1)
                if len(value) == 1:
                    value = value.zfill(2)
                keys.add("BMWLL" + value)

    return keys


def search_cyclon(products, standard):
    query = normalize(standard)
    if not query:
        return []

    results = []
    for product in products:
        if query in product_search_keys(product):
            results.append(product)
    return results
