import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import re
import html
import base64
import requests
from pathlib import Path
from urllib.parse import quote_plus, urljoin
from html.parser import HTMLParser

from cyclon_engine import load_cyclon_products, search_cyclon


# ============================================================
# PAGE SETTINGS
# ============================================================

st.set_page_config(
    page_title="CYCLON Lubricants Standard Finder",
    page_icon="🔎",
    layout="wide",
)

st.markdown("""
<style>
.stApp, .stApp * {
    direction: ltr;
}

h1, h2, h3, p, div[data-testid="stCaptionContainer"],
label[data-testid="stWidgetLabel"] p {
    direction: ltr;
    text-align: left;
}

input {
    direction: ltr !important;
    text-align: left !important;
}

div.stButton,
div.stDownloadButton,
div[data-testid="stButton"],
div[data-testid="stDataFrame"],
div[data-testid="stTable"] {
    direction: ltr;
    text-align: initial;
}

@media (max-width: 700px) {
    /* Mobile keeps the same visual structure as desktop, only scaled to the screen. */
    .oil-table-wrap {
        overflow-x:auto;
        -webkit-overflow-scrolling:touch;
    }
    table.oil-table {
        min-width:920px;
        font-size:14px;
    }
    .oil-table th, .oil-table td { padding:9px !important; }
    .oil-table img { max-width:92px !important; max-height:105px !important; object-fit:contain !important; }
}

div[data-testid="stFormSubmitButton"] button {
    background:#062b66 !important;
    border:2px solid #ffd400 !important;
    color:#ffd400 !important;
    font-weight:900 !important;
    border-radius:15px !important;
    box-shadow:0 6px 16px rgba(6,31,61,.18) !important;
}
div[data-testid="stFormSubmitButton"] button:hover {
    background:#ffd400 !important;
    border-color:#062b66 !important;
    color:#062b66 !important;
}
/* Hide the entire Streamlit Cloud toolbar/header chrome. */
[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stToolbarActions"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"],
[data-testid="stConnectionStatus"],
[data-testid="stDeployButton"],
#MainMenu,
header[data-testid="stHeader"],
.stDeployButton,
.stAppDeployButton,
[data-testid="manage_app_button"],
iframe[title="managed-hosted-app-badge"],
.viewerBadge,
[class*="viewerBadge"] {
    display:none !important;
    visibility:hidden !important;
    height:0 !important;
    min-height:0 !important;
    width:0 !important;
    min-width:0 !important;
    padding:0 !important;
    margin:0 !important;
    border:0 !important;
}

/* Remove the blank top strip left behind by Streamlit's hidden header. */
.stAppViewContainer > .main,
[data-testid="stAppViewContainer"] > .main {
    padding-top:0 !important;
    margin-top:0 !important;
}
</style>
""", unsafe_allow_html=True)

# Custom Share button. Streamlit's own toolbar stays hidden.
components.html(
    r"""
    <style>
      html,body{margin:0;padding:0;background:transparent;overflow:hidden;font-family:Arial,sans-serif}
      #shareBtn{
        position:fixed;top:8px;right:12px;z-index:2147483647;
        height:38px;padding:0 15px;border-radius:19px;
        border:1px solid #ffd400;
        background:#ffd400;color:#062b66;font-weight:700;font-size:14px;
        cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,.16);
      }
      #shareBtn:hover{background:#ffe04d;color:#062b66;border-color:#ffe04d}
      #msg{display:none;position:fixed;top:50px;right:12px;background:#fff;color:#062b66;
           border:1px solid #ddd;border-radius:8px;padding:7px 10px;font-size:12px;box-shadow:0 2px 8px rgba(0,0,0,.12)}
    </style>
    <button id="shareBtn" title="Share">↗ Share</button><div id="msg">Link copied</div>
    <script>
      const btn=document.getElementById('shareBtn');
      const msg=document.getElementById('msg');
      function appUrl(){
        try { return window.parent.location.href; } catch(e) {}
        return document.referrer || window.location.href;
      }
      btn.addEventListener('click', async () => {
        const data={title:'CYCLON Lubricants Standard Finder', text:'CYCLON Lubricants Standard Finder', url:appUrl()};
        try {
          if (navigator.share) { await navigator.share(data); return; }
          await navigator.clipboard.writeText(data.url);
          msg.style.display='block'; setTimeout(()=>msg.style.display='none',1600);
        } catch(e) {
          try { await navigator.clipboard.writeText(data.url); msg.style.display='block'; setTimeout(()=>msg.style.display='none',1600); } catch(_) {}
        }
      });
    </script>
    """,
    height=0,
    width=0,
)


# ============================================================
# SESSION STATE
# ============================================================

if "search_results" not in st.session_state:
    st.session_state.search_results = []

if "last_standard" not in st.session_state:
    st.session_state.last_standard = ""

if "standard_input" not in st.session_state:
    st.session_state.standard_input = ""




# ============================================================
# OFFICIAL CYCLON IMAGE LOADER
# ============================================================

@st.cache_data(ttl=86400, show_spinner=False)
def cyclon_asset(url):
    """Fetch an official CYCLON image on the Streamlit server and embed it."""
    if not url:
        return ""
    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://www.cyclon-lpc.com/",
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            },
            timeout=20,
        )
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").split(";")[0].strip()
        if not content_type.startswith("image/"):
            return ""
        encoded = base64.b64encode(response.content).decode("ascii")
        return f"data:{content_type};base64,{encoded}"
    except Exception:
        return ""



# ============================================================
# CYCLON PRIMARY PRODUCT-PACKAGE IMAGE RESOLVER
# ============================================================

class _CyclonPageImageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "img":
            return
        a = dict(attrs)
        src = (
            a.get("src")
            or a.get("data-src")
            or a.get("data-lazy-src")
            or a.get("data-original")
            or ""
        )
        if not src:
            return

        width = clean_text(a.get("width"))
        height = clean_text(a.get("height"))
        self.images.append({
            "src": src,
            "alt": clean_text(a.get("alt")),
            "title": clean_text(a.get("title")),
            "class": clean_text(a.get("class")),
            "width": width,
            "height": height,
        })


def _cyclon_img_tokens(value):
    value = html.unescape(clean_text(value)).upper()
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"[^A-Z0-9]+", " ", value)
    stop = {
        "CYCLON", "LPC", "IMAGE", "IMG", "PRODUCT", "OIL",
        "MOTOR", "ENGINE", "LUBRICANT", "LOGO", "ICON",
        "PASSENGER", "CARS", "CAR", "LIGHT", "DUTY",
    }
    return [x for x in value.split() if x and x not in stop]


def _cyclon_reject_non_product_image(img):
    text = " ".join([
        img.get("src", ""),
        img.get("alt", ""),
        img.get("title", ""),
        img.get("class", ""),
    ]).lower()

    # Explicitly reject page/category artwork and vehicle icons.
    blocked = [
        "logo", "icon", "passenger", "truck", "tractor", "vehicle",
        "category", "banner", "slider", "hero", "mega-menu",
        "technology", "network", "customer-support", "quality",
        "engineered-to-perform", "product-range", "agri",
    ]
    if any(x in text for x in blocked):
        return True

    # Tiny declared images are almost certainly icons, not the product pack.
    try:
        w = int(re.sub(r"\D", "", img.get("width", "")) or "0")
        h = int(re.sub(r"\D", "", img.get("height", "")) or "0")
        if w and h and (w < 180 or h < 180):
            return True
    except Exception:
        pass

    return False


@st.cache_data(ttl=86400, show_spinner=False)
def cyclon_primary_product_image(product_page_url, product_name):
    """
    Resolve ONLY the main package/bottle/can image from the specific official
    CYCLON product page. Page icons (cars, trucks, tractors, categories) are
    rejected even though they occur on the same product page.
    """
    if not product_page_url or not product_name:
        return ""

    try:
        r = requests.get(
            product_page_url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://www.cyclon-lpc.com/",
                "Accept": "text/html,application/xhtml+xml",
            },
            timeout=15,
        )
        r.raise_for_status()

        parser = _CyclonPageImageParser()
        parser.feed(r.text)

        p_tokens = set(_cyclon_img_tokens(product_name))
        candidates = []

        for pos, img in enumerate(parser.images):
            full = urljoin(product_page_url, img["src"])

            if "wp-content/uploads/" not in full:
                continue
            if _cyclon_reject_non_product_image(img):
                continue

            descriptor = " ".join([
                img.get("src", ""),
                img.get("alt", ""),
                img.get("title", ""),
            ])
            d_tokens = set(_cyclon_img_tokens(descriptor))
            common = p_tokens & d_tokens

            # Product image should share meaningful product-name information.
            name_score = sum(len(x) for x in common if len(x) >= 2)
            distinctive = any(len(x) >= 3 for x in common)

            # Strongly favor images that look like package assets by filename.
            low = full.lower()
            package_bonus = 0
            if any(x in low for x in ["1l", "4l", "5l", "20l", "60l", "208l", "package", "pack"]):
                package_bonus += 5

            if not distinctive and name_score < 4:
                continue

            # Earlier substantial matching images on CYCLON product pages are
            # typically the main product pack; icons are rejected above.
            score = name_score + package_bonus - (pos * 0.01)
            candidates.append((score, full))

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            return candidates[0][1]

    except Exception:
        pass

    # Never substitute a random image from the page.
    return ""



# ============================================================
# CYCLON VISUAL DESIGN
# ============================================================
st.markdown("""
<style>
:root {
    --cyclon-navy:#061f3d;
    --cyclon-navy2:#0a3159;
    --cyclon-yellow:#ffd400;
    --cyclon-bg:#eef4f8;
    --cyclon-text:#092443;
}
.stApp {
    background:
      radial-gradient(circle at 85% 0%, rgba(255,212,0,.12), transparent 24rem),
      linear-gradient(180deg,#061f3d 0 250px,#eef4f8 250px 100%);
    color:var(--cyclon-text);
}
[data-testid="stHeader"] { background:transparent; }
.block-container {
    max-width:1420px;
    padding-top:1.25rem;
    padding-bottom:3rem;
}
.cyclon-hero {
    min-height:205px;
    border-radius:0 0 28px 28px;
    padding:34px 42px;
    margin:-20px -18px 24px;
    position:sticky;
    top:0;
    z-index:999;
    overflow:hidden;
    background:
      radial-gradient(ellipse at 72% 52%, rgba(255,212,0,.32), transparent 9%),
      radial-gradient(ellipse at 70% 55%, rgba(23,95,151,.55), transparent 32%),
      linear-gradient(115deg,#03172d 0%,#082d52 58%,#041a33 100%);
    box-shadow:0 16px 40px rgba(3,24,46,.25);
}
.cyclon-hero:after {
    content:"";
    position:absolute;
    width:560px;height:120px;
    right:-80px;bottom:12px;
    border-top:12px solid rgba(255,212,0,.9);
    border-radius:50%;
    transform:rotate(-10deg);
    filter:drop-shadow(0 0 12px rgba(255,212,0,.25));
}
.cyclon-logo-text {
    color:var(--cyclon-yellow);
    font-size:58px;
    font-weight:900;
    letter-spacing:-4px;
    line-height:.9;
}
.cyclon-tag {
    color:white;
    font-size:13px;
    letter-spacing:2.2px;
    margin-top:8px;
}
.cyclon-hero-title {
    color:white;
    font-size:30px;
    font-weight:800;
    margin-top:28px;
    max-width:580px;
}
.cyclon-hero-title b { color:var(--cyclon-yellow); }
.cyclon-card {
    background:rgba(255,255,255,.98);
    border:1px solid rgba(9,49,89,.08);
    border-radius:24px;
    padding:22px 26px 10px;
    box-shadow:0 12px 35px rgba(8,42,73,.10);
    margin-bottom:12px;
}
div[data-testid="stForm"] {
    background:white;
    border:1px solid rgba(9,49,89,.08);
    border-radius:24px;
    padding:20px 24px 10px;
    box-shadow:0 12px 35px rgba(8,42,73,.11);
}
div[data-testid="stTextInput"] input {
    border-radius:16px;
    min-height:52px;
    border:1px solid #d5e0ea;
    font-size:17px;
}
div[data-testid="stFormSubmitButton"] button {
    min-height:50px;
    border-radius:15px;
    background:var(--cyclon-navy) !important;
    color:var(--cyclon-yellow) !important;
    border:2px solid var(--cyclon-yellow) !important;
    font-weight:900;
    font-size:17px;
    letter-spacing:.3px;
    box-shadow:0 6px 16px rgba(6,31,61,.18);
}
div[data-testid="stFormSubmitButton"] button:hover {
    background:var(--cyclon-yellow) !important;
    color:var(--cyclon-navy) !important;
    border:2px solid var(--cyclon-navy) !important;
}
h1,h2,h3 { color:#092443; }
.oil-table-wrap {
    border-radius:20px !important;
    box-shadow:0 10px 28px rgba(8,42,73,.10);
    background:white;
}
table.oil-table {
    border-collapse:separate !important;
    border-spacing:0 !important;
}
.oil-table th {
    background:#e7eef4 !important;
    color:#092443 !important;
    border-color:#dbe4ec !important;
}
.oil-table td {
    background:white;
    border-color:#e7edf2 !important;
}
.oil-table tr:hover td { background:#f8fbfd; }
.oil-table img {
    max-width:92px !important;
    max-height:105px !important;
}
.oil-table a {
    color:#0b5eaa;
    text-decoration:none !important;
}
.cyclon-footer {
    margin:32px -18px -48px;
    padding:24px 34px;
    border-radius:22px 22px 0 0;
    background:#061f3d;
    color:#d9e5ef;
    display:flex;
    justify-content:space-between;
    gap:20px;
    flex-wrap:wrap;
    font-size:12px;
    letter-spacing:1.4px;
}
.cyclon-footer strong { color:#ffd400; font-size:25px; }
@media(max-width:700px){
  .block-container{padding-left:.7rem;padding-right:.7rem;max-width:1420px}
  .cyclon-hero{padding:34px 28px;min-height:205px;margin:-12px -.25rem 24px;border-radius:0 0 28px 28px}
  .cyclon-logo-text{font-size:58px}
  .cyclon-hero-title{font-size:30px}
  div[data-testid="stForm"]{padding:20px 18px 10px}
  div[data-testid="stTextInput"] input{font-size:17px;min-height:52px}
  div[data-testid="stFormSubmitButton"] button{font-size:17px;min-height:50px}
}
</style>
<div class="cyclon-hero">
  <div class="cyclon-logo-text">cyclon</div>
  <div class="cyclon-tag">LUBRICANTS FOR A MOVING WORLD</div>
  <div class="cyclon-hero-title">DRIVE PERFORMANCE<br><b>EVERY DAY</b></div>
</div>
""", unsafe_allow_html=True)


# ============================================================
# HEADER
# ============================================================

st.markdown(
    '<h1 style="font-size: 30px; margin-bottom: 0.5rem;">🔎 CYCLON Lubricants Standard Finder</h1>',
    unsafe_allow_html=True,
)



# ============================================================
# HELPERS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent


def clean_text(value):
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(x).strip() for x in value if str(x).strip())
    return str(value).strip()


def _viscosity_key(value):
    """
    Normalizes viscosity so these are equivalent:
    5W30, 5W-30, 5 W 30, SAE 5W-30
    """
    text = clean_text(value).upper()
    text = re.sub(r"\bSAE\b", "", text)
    return re.sub(r"[^A-Z0-9]", "", text)


def _is_viscosity_query(value):
    return bool(re.fullmatch(r"\d{1,3}W\d{1,3}", _viscosity_key(value)))


def search_cyclon_by_viscosity(products, viscosity):
    query = _viscosity_key(viscosity)
    if not query:
        return []

    matches = []
    for product in products:
        if _viscosity_key(product.get("viscosity")) == query:
            matches.append(product)
    return matches



def _sku_key(value):
    """Normalize SKU/article number: ignore spaces, dashes and punctuation."""
    return re.sub(r"[^A-Z0-9]+", "", clean_text(value).upper())


def _product_sku_keys(product):
    keys = set()

    for field in ("code", "parent_code", "legacy_code"):
        key = _sku_key(product.get(field))
        if key:
            keys.add(key)

    for row in product.get("sku_rows") or []:
        key = _sku_key(row.get("sku"))
        if key:
            keys.add(key)

    # sku_size may contain several SKU + package rows separated by |.
    sku_size = clean_text(product.get("sku_size"))
    if sku_size:
        for chunk in re.split(r"\s*\|\s*|\s*;\s*", sku_size):
            # take the leading article number before size text
            m = re.match(r"^\s*([A-Za-z0-9._/-]+)", chunk)
            if m:
                key = _sku_key(m.group(1))
                if key:
                    keys.add(key)

    return keys


def search_cyclon_by_sku(products, value):
    query = _sku_key(value)
    if not query:
        return []

    matches = []
    for product in products:
        if query in _product_sku_keys(product):
            matches.append(product)
    return matches


@st.cache_resource(show_spinner=False)
def get_cyclon_products():
    return load_cyclon_products()



def _smart_query_parts(value):
    """
    One search box for specification / viscosity / SKU / combinations.
    Example: 10w30sq -> viscosity 10W30 + remaining term SQ.
    """
    compact = re.sub(r"[^A-Z0-9]+", "", clean_text(value).upper())

    m = re.search(r"\d{1,3}W\d{1,3}", compact)
    viscosity = m.group(0) if m else ""

    remainder = compact
    if viscosity:
        remainder = remainder.replace(viscosity, "", 1)

    return viscosity, remainder


def _cyclon_free_text_match(product, term):
    term = re.sub(r"[^A-Z0-9]+", "", clean_text(term).upper())
    if not term:
        return True

    fields = [
        product.get("name"),
        product.get("product"),
        product.get("code"),
        product.get("parent_code"),
        product.get("legacy_code"),
        product.get("sku_size"),
        product.get("standards"),
    ]

    for sku_row in product.get("sku_rows") or []:
        fields.extend([sku_row.get("sku"), sku_row.get("size")])

    haystack = re.sub(
        r"[^A-Z0-9]+",
        "",
        " ".join(clean_text(x).upper() for x in fields if x),
    )
    return term in haystack


def build_results(query):
    products = get_cyclon_products()
    viscosity, remainder = _smart_query_parts(query)

    matches = list(products)

    if viscosity:
        matches = search_cyclon_by_viscosity(matches, viscosity)

    if remainder:
        matches = [item for item in matches if _cyclon_free_text_match(item, remainder)]

    # No viscosity detected: keep the original standard search as fallback.
    if not viscosity and remainder:
        direct = [item for item in products if _cyclon_free_text_match(item, remainder)]
        if direct:
            matches = direct
        else:
            matches = search_cyclon(products, query)

    rows = []
    seen = set()

    for item in matches:
        row = {
            "Image": clean_text(item.get("image")),
            "Manufacturer": "CYCLON",
            "Product": clean_text(item.get("name") or item.get("product")),
            "SKU / Size": clean_text(item.get("sku_size") or item.get("code") or item.get("parent_code")),
            "Viscosity": clean_text(item.get("viscosity")),
            "Standards": clean_text(item.get("standards")),
            "TDS": clean_text(item.get("tds")),
            "Product Page": clean_text(item.get("url")),
        }

        key = (
            row["Product"].upper(),
            row["SKU / Size"].upper(),
            row["Viscosity"].upper(),
        )
        if key in seen:
            continue

        seen.add(key)
        rows.append(row)

    rows.sort(
        key=lambda x: (
            x["Product"].upper(),
            x["Viscosity"].upper(),
            x["SKU / Size"].upper(),
        )
    )
    return rows


def render_results_table(df):
    """
    Preserve the original table structure:
    Image, Manufacturer, Product, SKU / Size, Viscosity,
    Standards, TDS, Product Page.

    """
    columns = [
        "Image",
        "Manufacturer",
        "Product",
        "SKU / Size",
        "Viscosity",
        "Standards",
        "TDS",
        "Product Page",
    ]

    parts = [
        """
        <style>
        .oil-table-wrap { overflow:visible; width:100%; }
        table.oil-table { width:100%; border-collapse:collapse; font-size:14px; }
        .oil-table th,.oil-table td {
            border:1px solid #e6e6e6;
            padding:9px;
            vertical-align:middle;
            text-align:left;
            overflow:visible;
        }
        .oil-table th {
            font-weight:700;
            background:rgba(128,128,128,0.08);
            position:sticky;
            top:0;
        }
        .oil-table .product-image-link {
            display:inline-block;
            position:relative;
            cursor:pointer;
        }
        .oil-table .product-image-link img {
            max-width:80px;
            max-height:90px;
            object-fit:contain;
            transition:transform .18s ease, box-shadow .18s ease;
            transform-origin:center center;
            position:relative;
            z-index:1;
        }
        @media (hover:hover) and (pointer:fine) {
            .oil-table .product-image-link:hover img {
                transform:scale(2.15);
                z-index:1000;
                background:#fff;
                box-shadow:0 10px 30px rgba(6,31,61,.28);
                border-radius:8px;
            }
            .oil-table td:has(.product-image-link:hover) {
                position:relative;
                z-index:1001;
            }
        }
        .oil-table a {
            text-decoration:underline;
            font-weight:600;
        }
        </style>
        <div class="oil-table-wrap">
        <table class="oil-table">
        <thead><tr>
        """
    ]

    for column in columns:
        parts.append("<th>" + html.escape(column) + "</th>")

    parts.append("</tr></thead><tbody>")

    for _, row in df.iterrows():
        parts.append("<tr>")

        product_page_url = clean_text(row.get("Product Page"))
        product_name = clean_text(row.get("Product"))

        product_image_url = cyclon_primary_product_image(
            product_page_url,
            product_name,
        )

        if product_image_url:
            image_src = cyclon_asset(product_image_url) or product_image_url
            image_html = (
                '<img src="' + html.escape(image_src, quote=True) + '" '
                'loading="lazy" alt="' + html.escape(product_name, quote=True) + '">'
            )
            if product_page_url:
                image_html = (
                    '<a class="product-image-link" target="_blank" rel="noopener noreferrer" href="'
                    + html.escape(product_page_url, quote=True)
                    + '" title="Open CYCLON product page">'
                    + image_html
                    + '</a>'
                )
            parts.append('<td>' + image_html + '</td>')
        else:
            parts.append("<td></td>")

        parts.append(
            "<td>" + html.escape(clean_text(row.get("Manufacturer"))) + "</td>"
        )
        parts.append(
            "<td>" + html.escape(clean_text(row.get("Product"))) + "</td>"
        )

        sku_html = html.escape(clean_text(row.get("SKU / Size")))
        parts.append("<td>" + sku_html + "</td>")

        for column in ["Viscosity", "Standards"]:
            parts.append(
                "<td>" + html.escape(clean_text(row.get(column))) + "</td>"
            )

        tds = clean_text(row.get("TDS"))
        if tds:
            parts.append(
                '<td><a target="_blank" href="'
                + html.escape(tds, quote=True)
                + '">View TDS</a></td>'
            )
        else:
            parts.append("<td></td>")

        product_page = clean_text(row.get("Product Page"))
        if product_page:
            parts.append(
                '<td><a target="_blank" href="'
                + html.escape(product_page, quote=True)
                + '">View Product</a></td>'
            )
        else:
            parts.append("<td></td>")

        parts.append("</tr>")

    parts.append("</tbody></table></div>")

    st.markdown("".join(parts), unsafe_allow_html=True)


# ============================================================
# SEARCH FORM
# ============================================================

with st.form("search_form", clear_on_submit=False):
    st.text_input(
        "Search",
        key="standard_input",
        placeholder="Examples: VW509, BMWLL04, 5W30, OPP005, JM26508",
        label_visibility="collapsed",
    )


    submitted = st.form_submit_button(
        "🔎 Search",
        type="primary",
        use_container_width=True,
    )


# ============================================================
# RUN SEARCH
# ============================================================

if submitted:
    query = st.session_state.standard_input.strip()

    if not query:
        st.warning("Please enter a search value.")
    else:
        with st.spinner("Searching the CYCLON catalog..."):
            results = build_results(query)

        st.session_state.search_results = results
        st.session_state.last_standard = query


# ============================================================
# SHOW RESULTS
# ============================================================

results = st.session_state.search_results

if results:
    df = pd.DataFrame(results)

    st.markdown(
        f"### CYCLON Results ({len(df)})"
    )

    render_results_table(df)

elif st.session_state.last_standard:
    st.info(
        f"No CYCLON products were found for {st.session_state.last_standard}."
    )

st.markdown("""
<div class="cyclon-footer">
  <div><strong>cyclon</strong><br>LUBRICANTS FOR A MOVING WORLD</div>
  <div>QUALITY &nbsp; | &nbsp; TECHNOLOGY &nbsp; | &nbsp; PERFORMANCE</div>
  <div>A CLEANER · BRIGHTER TOMORROW</div>
  <div style="margin-top:18px;font-size:12px;opacity:0.72;letter-spacing:0.2px;">All Rights Reserved © Arad Zbeda</div>
</div>
""", unsafe_allow_html=True)
