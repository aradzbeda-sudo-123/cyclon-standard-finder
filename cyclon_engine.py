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
    # Fixed local index of the CURRENT 47-product CYCLON Passenger Cars & Light Duty catalogue.
    # This avoids crawling six category pages on every app start.
    return [
        'https://www.cyclon-lpc.com/cyclon_new_product/bw-fe/',
        'https://www.cyclon-lpc.com/cyclon_new_product/dxs-c3/',
        'https://www.cyclon-lpc.com/cyclon_new_product/fd-fe/',
        'https://www.cyclon-lpc.com/cyclon_new_product/j-fe/',
        'https://www.cyclon-lpc.com/cyclon_new_product/m-fe/',
        'https://www.cyclon-lpc.com/cyclon_new_product/psa-c2/',
        'https://www.cyclon-lpc.com/cyclon_new_product/psa-ll/',
        'https://www.cyclon-lpc.com/cyclon_new_product/racing/',
        'https://www.cyclon-lpc.com/cyclon_new_product/rnl-c4/',
        'https://www.cyclon-lpc.com/cyclon_new_product/rnl-fe/',
        'https://www.cyclon-lpc.com/cyclon_new_product/stl-ll/',
        'https://www.cyclon-lpc.com/cyclon_new_product/t-fe/',
        'https://www.cyclon-lpc.com/cyclon_new_product/tdi-c3/',
        'https://www.cyclon-lpc.com/cyclon_new_product/ultra/',
        'https://www.cyclon-lpc.com/cyclon_new_product/ultra-2/',
        'https://www.cyclon-lpc.com/cyclon_new_product/ultra-3/',
        'https://www.cyclon-lpc.com/cyclon_new_product/ultra-s-2/',
        'https://www.cyclon-lpc.com/cyclon_new_product/ultra-s-3/',
        'https://www.cyclon-lpc.com/cyclon_new_product/ultra-s/',
        'https://www.cyclon-lpc.com/cyclon_new_product/v-fe/',
        'https://www.cyclon-lpc.com/cyclon_new_product/v1-ll/',
        'https://www.cyclon-lpc.com/cyclon_new_product/v1-ll-2/',
        'https://www.cyclon-lpc.com/cyclon_new_product/dxs-c3-2/',
        'https://www.cyclon-lpc.com/cyclon_new_product/fd-a5-b5/',
        'https://www.cyclon-lpc.com/cyclon_new_product/psa-c2-2/',
        'https://www.cyclon-lpc.com/cyclon_new_product/tdi-c3-2/',
        'https://www.cyclon-lpc.com/cyclon_new_product/v1-ll-3/',
        'https://www.cyclon-lpc.com/cyclon_new_product/v1-ll-4/',
        'https://www.cyclon-lpc.com/cyclon_new_product/r2-dxs/',
        'https://www.cyclon-lpc.com/cyclon_new_product/r2-ultra/',
        'https://www.cyclon-lpc.com/cyclon_new_product/r2-ultra-s/',
        'https://www.cyclon-lpc.com/cyclon_new_product/r2-v1/',
        'https://www.cyclon-lpc.com/cyclon_new_product/r2-x-100/',
        'https://www.cyclon-lpc.com/cyclon_new_product/prm/',
        'https://www.cyclon-lpc.com/cyclon_new_product/prm-2/',
        'https://www.cyclon-lpc.com/cyclon_new_product/spr-a3-b4/',
        'https://www.cyclon-lpc.com/cyclon_new_product/spr-a3-b4-2/',
        'https://www.cyclon-lpc.com/cyclon_new_product/spr-a3-b4-3/',
        'https://www.cyclon-lpc.com/cyclon_new_product/x-100/',
        'https://www.cyclon-lpc.com/cyclon_new_product/x-100-2/',
        'https://www.cyclon-lpc.com/cyclon_new_product/x-100-3/',
        'https://www.cyclon-lpc.com/cyclon_new_product/x-100-4/',
        'https://www.cyclon-lpc.com/cyclon_new_product/x-200/',
        'https://www.cyclon-lpc.com/cyclon_new_product/x-200-2/',
        'https://www.cyclon-lpc.com/cyclon_new_product/x-200-3/',
        'https://www.cyclon-lpc.com/cyclon_new_product/x-300/',
        'https://www.cyclon-lpc.com/cyclon_new_product/x-300-2/'
    ]

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

def _best_image(soup, product_name=""):
    """
    Return only an image that looks like the actual product packshot.
    If we cannot identify a product image confidently, return blank rather
    than showing a car/banner/site graphic.
    """
    name_tokens = {
        x.lower() for x in re.findall(r"[A-Za-z0-9]+", product_name or "")
        if len(x) >= 2 and x.lower() not in {"cyclon", "motor", "oil"}
    }
    candidates = []
    banned = (
        "engineered", "banner", "slider", "hero", "matching", "discover",
        "vehicle", "car-", "automotive", "footer", "header", "logo", "icon",
        "shine", "social", "certificate", "iso-", "tribon"
    )
    for img in soup.find_all("img"):
        src = img.get("data-src") or img.get("data-lazy-src") or img.get("src") or ""
        alt = (img.get("alt") or "").strip()
        if not src:
            continue
        src = urljoin(BASE, src)
        low = src.lower()
        alt_low = alt.lower()
        if any(x in low or x in alt_low for x in banned):
            continue
        if "wp-content/uploads" not in low:
            continue

        alt_tokens = set(re.findall(r"[a-z0-9]+", alt_low))
        overlap = len(name_tokens & alt_tokens)
        filename = low.rsplit("/", 1)[-1]
        filename_tokens = set(re.findall(r"[a-z0-9]+", filename))
        file_overlap = len(name_tokens & filename_tokens)

        # A real CYCLON product packshot normally carries the product name/code
        # in its ALT text or filename. Require that evidence.
        score = overlap * 20 + file_overlap * 10
        if any(x in filename for x in ("1lt", "4lt", "5lt", "20lt", "208", "pack", "bottle")):
            score += 8
        if low.endswith((".png", ".webp")):
            score += 3
        if score > 0:
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
        "image": _best_image(soup, name),
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
    COMPLETE CYCLON dataset used by this app:
      1) bundled legacy CYCLON catalogue (keeps MAGMA and all prior products);
      2) current 47-product Passenger Cars & Light Duty catalogue
         (EVO / PRO / ECO / MAX).

    The current pages are read only once per Streamlit process because the
    app caches this function's result. Repeated searches are local/fast.
    """
    legacy = _old_catalog()
    try:
        current = _live_catalog()
    except Exception:
        current = []

    # Never throw MAGMA away. Start with every bundled legacy record.
    combined = list(legacy)

    # Add every current product. Do not replace MAGMA: new and legacy product
    # families intentionally coexist in the search catalogue.
    seen_urls = {str(x.get("url", "")).rstrip("/").lower() for x in combined}
    for item in current:
        u = str(item.get("url", "")).rstrip("/").lower()
        if u and u in seen_urls:
            continue
        combined.append(item)
        if u:
            seen_urls.add(u)

    return combined

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
