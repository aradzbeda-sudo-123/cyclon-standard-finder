import streamlit as st
import pandas as pd
import json
import re
import html
from pathlib import Path
from urllib.parse import quote_plus

BASE_DIR = Path(__file__).resolve().parent
CACHE_FILE = BASE_DIR / "cyclon_catalog_cache.json"
FERROMAT_FILE = BASE_DIR / "oils.xlsx"

st.set_page_config(page_title="CYCLON Oil Standard Finder", page_icon="🔎", layout="wide")

st.markdown("""
<style>
.stApp, .stApp * { direction:ltr; }
h1,h2,h3,p,div[data-testid="stCaptionContainer"],label[data-testid="stWidgetLabel"] p {
  direction:ltr; text-align:left;
}
input { direction:ltr !important; text-align:left !important; }
.cyclon-logo { max-width:230px; height:auto; margin:0 0 12px 0; display:block; }
.oil-table-wrap { overflow-x:auto; -webkit-overflow-scrolling:touch; }
table.oil-table { width:100%; border-collapse:collapse; font-size:14px; }
.oil-table th { background:#f1f3f5; font-weight:700; }
.oil-table th,.oil-table td { border:1px solid #ddd; padding:8px; vertical-align:middle; text-align:left; }
.oil-table img { max-width:90px; max-height:100px; object-fit:contain; }
@media(max-width:700px){
 table.oil-table{min-width:980px;font-size:12px}
 .oil-table th,.oil-table td{padding:6px}
 .oil-table img{max-width:65px;max-height:75px}
}
</style>
""", unsafe_allow_html=True)

# Official CYCLON site logo displayed from the brand website.
st.markdown(
    '<img class="cyclon-logo" src="https://www.cyclon-lpc.com/wp-content/uploads/2021/03/logo.png" alt="CYCLON">',
    unsafe_allow_html=True,
)

st.title("🔎 CYCLON Oil Standard Finder")
st.write("Search CYCLON automotive oils by vehicle manufacturer specification.")
st.caption("Examples: VW504, VW507, MB22951, BMWLL04, PorscheC30")

def txt(v):
    if v is None: return ""
    if isinstance(v, list):
        return ", ".join(str(x).strip() for x in v if str(x).strip())
    return str(v).strip()

def norm(v):
    return re.sub(r"[^A-Z0-9]+", "", txt(v).upper())

def query_variants(q):
    n = norm(q)
    vals = {n}
    # Manufacturer-standard shorthand used by the original multi-brand app:
    # VW504 -> VW50400, VW509 -> VW50900, etc.
    m = re.fullmatch(r"VW(\d{3})", n)
    if m: vals.add("VW" + m.group(1) + "00")
    return vals

@st.cache_data(show_spinner=False)
def load_products():
    data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    return data.get("products", [])

@st.cache_data(show_spinner=False)
def load_ferromat():
    if not FERROMAT_FILE.exists():
        return {}
    d = pd.read_excel(FERROMAT_FILE, dtype=str).fillna("")
    lookup = {}
    for _, r in d.iterrows():
        if txt(r.get("BRAND")).upper() != "CYCLON":
            continue
        ref = norm(r.get("SUPPLIER_REF"))
        sku = txt(r.get("SKU_FERROMAT"))
        if ref and sku:
            lookup.setdefault(ref, [])
            if sku not in lookup[ref]: lookup[ref].append(sku)
    return lookup

def product_code(item):
    return txt(item.get("sku_size") or item.get("code") or item.get("sku"))

def image_url(item):
    return txt(item.get("image") or item.get("image_url") or item.get("Image"))

def product_url(item):
    return txt(item.get("url") or item.get("product_url") or item.get("Product Page"))

def tds_url(item):
    return txt(item.get("tds") or item.get("tds_url") or item.get("TDS"))

def product_name(item):
    return txt(item.get("name") or item.get("product") or item.get("Product"))

def search_products(q, products):
    variants = query_variants(q)
    rows = []
    seen = set()
    for item in products:
        candidates = []
        for field in ("standards", "search_keys", "specifications", "approvals"):
            v = item.get(field, [])
            candidates.extend(v if isinstance(v, list) else [v])
        keys = {norm(x) for x in candidates if txt(x)}
        matched = any(any(v == k or v in k for k in keys) for v in variants)
        if not matched:
            continue
        key = (product_name(item).upper(), product_code(item).upper())
        if key in seen: continue
        seen.add(key)
        rows.append(item)
    return rows

def ferromat_skus(item, lookup):
    code = product_code(item)
    candidates = [code]
    candidates += re.findall(r"[A-Za-z0-9._/-]+", code)
    found = []
    for c in candidates:
        k = norm(c)
        for sku in lookup.get(k, []):
            if sku not in found: found.append(sku)
    return found

def render_table(items, lookup):
    parts = ['<div class="oil-table-wrap"><table class="oil-table"><thead><tr>',
             '<th>Image</th><th>Manufacturer</th><th>Product</th><th>SKU / Size</th>',
             '<th>Viscosity</th><th>Standards</th><th>TDS</th><th>Product Page</th>',
             '</tr></thead><tbody>']
    for item in items:
        img = image_url(item)
        img_html = ('<img src="'+html.escape(img, quote=True)+'" alt="product">') if img else ""
        skus = ferromat_skus(item, lookup)
        sku_html = html.escape(product_code(item))
        if skus:
            links = []
            for sku in skus:
                u = "https://www.ferromat.co.il/?s=" + quote_plus(sku)
                links.append('<a target="_blank" href="'+html.escape(u,quote=True)+'">'+html.escape(sku)+'</a>')
            sku_html += " (FERROMAT: " + " | ".join(links) + ")"
        standards = txt(item.get("standards"))
        tds = tds_url(item)
        page = product_url(item)
        parts += [
            "<tr>",
            "<td>"+img_html+"</td>",
            "<td>CYCLON</td>",
            "<td>"+html.escape(product_name(item))+"</td>",
            "<td>"+sku_html+"</td>",
            "<td>"+html.escape(txt(item.get("viscosity")))+"</td>",
            "<td>"+html.escape(standards)+"</td>",
            '<td>'+('<a target="_blank" href="'+html.escape(tds,quote=True)+'">View TDS</a>' if tds else "")+'</td>',
            '<td>'+('<a target="_blank" href="'+html.escape(page,quote=True)+'">View Product</a>' if page else "")+'</td>',
            "</tr>"
        ]
    parts.append("</tbody></table></div>")
    st.markdown("".join(parts), unsafe_allow_html=True)

products = load_products()
ferromat = load_ferromat()

q = st.text_input("Enter oil specification", placeholder="Example: VW504")
if st.button("🔎 Search", use_container_width=True):
    if not q.strip():
        st.warning("Please enter an oil specification.")
        st.session_state["cyclon_results"] = []
        st.session_state["cyclon_last"] = ""
    else:
        st.session_state["cyclon_results"] = search_products(q, products)
        st.session_state["cyclon_last"] = q.strip()

results = st.session_state.get("cyclon_results", [])
last = st.session_state.get("cyclon_last", "")

if last:
    if results:
        st.markdown(f"### CYCLON Results ({len(results)})")
        render_table(results, ferromat)
    else:
        st.info(f"No CYCLON products were found for specification {last}.")
