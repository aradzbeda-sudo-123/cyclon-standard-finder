import json
import re
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

CATALOG = Path(__file__).resolve().parent / "cyclon_catalog.json"
BASE = "https://www.cyclon-lpc.com"
CATEGORY = BASE + "/cyclon_new_product_cat/passenger-light-duty/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CYCLON-Standard-Finder/1.0)",
    "Accept-Language": "en-US,en;q=0.9",
}

def _norm(v):
    return re.sub(r"[^A-Z0-9]+", "", str(v or "").upper())

def _variants(q):
    n = _norm(q)
    v = {n}
    m = re.fullmatch(r"VW(\d{3})", n)
    if m:
        v.add("VW" + m.group(1) + "00")
    m = re.fullmatch(r"VW(\d{3})00", n)
    if m:
        v.add("VW" + m.group(1))
    if n.startswith("BMWLONGLIFE"):
        v.add(n.replace("BMWLONGLIFE", "BMWLL", 1))
    if n.startswith("BMWLL"):
        v.add(n.replace("BMWLL", "BMWLONGLIFE", 1))
    return {x for x in v if x}

def _old_catalog():
    try:
        return json.loads(CATALOG.read_text(encoding="utf-8"))
    except Exception:
        return []

def _get(url, timeout=25):
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r

def _product_links():
    links = []
    seen = set()
    for page in range(1, 7):
        url = CATEGORY if page == 1 else f"{CATEGORY}page/{page}/"
        soup = BeautifulSoup(_get(url).text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = urljoin(BASE, a["href"])
            if "/cyclon_new_product/" not in href:
                continue
            href = href.split("#", 1)[0].split("?", 1)[0]
            if href not in seen:
                seen.add(href)
                links.append(href)
    return links

def _section_text(soup, heading):
    target = None
    for tag in soup.find_all(["h2", "h3", "h4", "strong", "div", "span", "p"]):
        if tag.get_text(" ", strip=True).lower() == heading.lower():
            target = tag
            break
    if not target:
        return ""
    chunks = []
    for node in target.find_all_next():
        if node is target:
            continue
        if node.name in ("h2", "h3", "h4") and chunks:
            break
        txt = node.get_text(" ", strip=True)
        if txt and txt.lower() not in (heading.lower(), "show more"):
            chunks.append(txt)
        if len(" ".join(chunks)) > 2500:
            break
    # de-duplicate repeated nested text
    result = []
    for x in chunks:
        if x not in result:
            result.append(x)
    return " | ".join(result)

def _best_image(soup):
    candidates = []
    for img in soup.find_all("img"):
        src = img.get("data-src") or img.get("data-lazy-src") or img.get("src") or ""
        if not src:
            continue
        src = urljoin(BASE, src)
        alt = (img.get("alt") or "").lower()
        score = 0
        low = src.lower()
        if "logo" in low or "icon" in low:
            continue
        if "wp-content/uploads" in low:
            score += 2
        if any(k in alt for k in ("cyclon", "evo", "pro", "eco", "max")):
            score += 3
        if any(k in low for k in ("evo", "pro", "eco", "max", "product")):
            score += 2
        candidates.append((score, src))
    return max(candidates, default=(0, ""))[1]

def _pdf_link(soup):
    for a in soup.find_all("a", href=True):
        href = urljoin(BASE, a["href"])
        text = a.get_text(" ", strip=True).upper()
        if href.lower().endswith(".pdf") and ("TDS" in text or "TECHNICAL" in text):
            return href
    # Prefer a PDF whose filename looks like a technical sheet; avoid catalogues.
    for a in soup.find_all("a", href=True):
        href = urljoin(BASE, a["href"])
        low = href.lower()
        if low.endswith(".pdf") and "catalog" not in low and "matching" not in low:
            return href
    return ""

def _parse_product(url, old_by_parent):
    soup = BeautifulSoup(_get(url).text, "html.parser")
    full = soup.get_text("\n", strip=True)
    lines = [x.strip() for x in full.splitlines() if x.strip()]

    # Name/range/grade from the current page.
    name = ""
    h1 = soup.find("h1")
    if h1:
        h1txt = h1.get_text(" ", strip=True)
        if h1txt.lower() != "cyclon":
            name = h1txt

    # Current pages often render "Cyclon", then range/name, then grade.
    parent_m = re.search(r"Parent Code:\s*([A-Z0-9-]+)", full, re.I)
    parent = parent_m.group(1).upper() if parent_m else ""

    repl_m = re.search(r"Replaces\s+(.+?)\s+([A-Z]{1,3}\d{3,})\b", full, re.I)
    replaced_name = repl_m.group(1).strip() if repl_m else ""
    legacy_parent = repl_m.group(2).upper() if repl_m else ""

    grade = ""
    for line in lines:
        if re.fullmatch(r"(?:0W|5W|10W|15W|20W)[- ]?\d{1,2}|\d{1,2}", line, re.I):
            grade = line.replace(" ", "")
            break

    # Find a current product title in meta/OG first.
    for key in ("og:title", "twitter:title"):
        tag = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
        if tag and tag.get("content"):
            title = tag["content"].split("–")[0].split("|")[0].strip()
            if title and title.lower() not in ("cyclon", "cyclon lpc"):
                name = title
                break

    # Reconstruct from visible text if meta title is generic.
    range_name = ""
    for line in lines:
        if re.match(r"^(EVO|PRO|ECO|MAX)\b", line, re.I):
            range_name = line
            break
    if range_name:
        name = range_name
    if not name:
        name = replaced_name or url.rstrip("/").split("/")[-1].replace("-", " ").upper()

    specs = _section_text(soup, "Specifications")
    if not specs:
        # Search between Specifications and Packaging in plain text.
        m = re.search(r"Specifications\s+(.*?)(?:Packaging|TDS|Product Catalogue)", full, re.I | re.S)
        specs = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""

    packaging = _section_text(soup, "Packaging")
    if not packaging:
        m = re.search(r"Packaging\s+(.*?)(?:TDS|Product Catalogue|Similar Products)", full, re.I | re.S)
        packaging = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""

    old = old_by_parent.get(legacy_parent, {})
    old_sku = old.get("sku_size", "") if old else ""

    sku_parts = []
    if parent:
        sku_parts.append("Parent " + parent)
    if packaging:
        # keep compact; page may contain nested repeated text
        pack = packaging.split("| Similar", 1)[0].strip(" |")
        if pack:
            sku_parts.append(pack)
    if old_sku:
        sku_parts.append("Legacy " + old_sku)

    standards = [x.strip() for x in re.split(r"\s*\|\s*|,\s*", specs) if x.strip()]
    search_keys = [_norm(x) for x in standards if _norm(x)]

    return {
        "brand": "CYCLON",
        "name": name,
        "viscosity": grade,
        "standards": standards,
        "search_keys": search_keys,
        "legacy_code": legacy_parent,
        "parent_code": parent,
        "packaging": packaging,
        "sku_rows": old.get("sku_rows", []) if old else [],
        "sku_size": " | ".join(sku_parts),
        "image": _best_image(soup),
        "tds": _pdf_link(soup),
        "url": url,
        "_page_text": full,
    }

def _live_catalog():
    old = _old_catalog()
    old_by_parent = {}
    for p in old:
        for key in (p.get("parent_code"), p.get("legacy_code")):
            if key:
                old_by_parent[_norm(key)] = p

    products = []
    for url in _product_links():
        try:
            products.append(_parse_product(url, old_by_parent))
        except Exception:
            continue
    return products

def load_cyclon_products():
    """
    Load CYCLON's CURRENT Passenger Cars & Light Duty catalogue.
    If the CYCLON site is temporarily unavailable, fall back to the bundled
    catalogue so the app still works.
    """
    try:
        current = _live_catalog()
        if len(current) >= 40:
            return current
    except Exception:
        pass
    return _old_catalog()

def search_cyclon(products, standard):
    qv = _variants(standard)
    result = []
    for p in products:
        hay = set()
        for field in ("search_keys", "standards"):
            vals = p.get(field, [])
            if not isinstance(vals, list):
                vals = [vals]
            hay.update(_norm(x) for x in vals if x)

        # Current CYCLON pages are also searched as normalized full text,
        # which catches combined forms such as VW 504.00/507.00.
        page_norm = _norm(p.get("_page_text", ""))
        matched = bool(qv & hay) or any(q and q in page_norm for q in qv)
        if matched:
            result.append(p)
    return result
