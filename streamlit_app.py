import streamlit as st
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
    page_title="CYCLON Oil Standard Finder",
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
    .oil-table-wrap {
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
    }
    table.oil-table {
        min-width: 980px;
        font-size: 12px;
    }
    .oil-table th,
    .oil-table td {
        padding: 6px !important;
    }
    .oil-table img {
        max-width: 65px !important;
        max-height: 75px !important;
    }
}

div[data-testid="stFormSubmitButton"] button {
    background:#d71920 !important;
    border-color:#d71920 !important;
    color:white !important;
    font-weight:700 !important;
}
div[data-testid="stFormSubmitButton"] button:hover {
    background:#b51218 !important;
    border-color:#b51218 !important;
    color:white !important;
}
</style>
""", unsafe_allow_html=True)



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
    position:relative;
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
    background:var(--cyclon-yellow);
    color:#061f3d;
    border:0;
    font-weight:800;
    font-size:17px;
}
div[data-testid="stFormSubmitButton"] button:hover {
    background:#ffe047;
    color:#061f3d;
    border:0;
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
  .block-container{padding-left:.7rem;padding-right:.7rem}
  .cyclon-hero{padding:28px 24px;min-height:190px;margin-top:-12px}
  .cyclon-logo-text{font-size:48px}
  .cyclon-hero-title{font-size:24px}
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

import base64

_logo_file = Path(__file__).with_name("cyclon_logo.png")
_logo_b64 = base64.b64encode(_logo_file.read_bytes()).decode("ascii")
st.markdown(
    '<img src="data:image/png;base64,' + _logo_b64 + '" alt="CYCLON" '
    'style="width:230px; height:auto; margin-bottom:14px;">',
    unsafe_allow_html=True,
)

st.markdown(
    '<h1 style="font-size: 30px; margin-bottom: 0.5rem;">🔎 CYCLON Oil Standard Finder</h1>',
    unsafe_allow_html=True,
)

st.write("Search CYCLON automotive oils by vehicle manufacturer specification, viscosity, or SKU.")

st.caption("Examples: VW509, BMWLL04, 5W30, OPP005, JM26508")

st.caption(
    "Searches the local CYCLON catalog by specification, viscosity, or exact SKU/article number."
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


def build_results(standard):
    products = get_cyclon_products()

    if _is_viscosity_query(standard):
        matches = search_cyclon_by_viscosity(products, standard)
    else:
        sku_matches = search_cyclon_by_sku(products, standard)
        if sku_matches:
            matches = sku_matches
        else:
            matches = search_cyclon(products, standard)

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
        .oil-table-wrap { overflow-x:auto; width:100%; }
        table.oil-table { width:100%; border-collapse:collapse; font-size:14px; }
        .oil-table th,.oil-table td {
            border:1px solid #e6e6e6;
            padding:9px;
            vertical-align:middle;
            text-align:left;
        }
        .oil-table th {
            font-weight:700;
            background:rgba(128,128,128,0.08);
            position:sticky;
            top:0;
        }
        .oil-table img {
            max-width:80px;
            max-height:90px;
            object-fit:contain;
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
            parts.append(
                '<td><img src="'
                + html.escape(image_src, quote=True)
                + '" loading="lazy"></td>'
            )
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
        "Enter specification, viscosity, or SKU",
        key="standard_input",
        placeholder="Example: VW504, 5W30, OPP005 or JM26508",
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
    standard = st.session_state.standard_input.strip()

    if not standard:
        st.warning("Please enter a specification, viscosity, or SKU.")
    else:
        with st.spinner("Searching the CYCLON catalog..."):
            results = build_results(standard)

        st.session_state.search_results = results
        st.session_state.last_standard = standard


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
</div>
""", unsafe_allow_html=True)
