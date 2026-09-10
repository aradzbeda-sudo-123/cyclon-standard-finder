import streamlit as st
import pandas as pd
import re
import html
import base64
import requests
from pathlib import Path
from urllib.parse import quote_plus

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

if "ferromat_display_filter" not in st.session_state:
    st.session_state.ferromat_display_filter = "FERROMAT_ONLY"


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
# HEADER
# ============================================================

CYCLON_LOGO_URL = "https://www.cyclon-lpc.com/wp-content/uploads/2022/04/Group-16404.svg"
_logo_src = cyclon_asset(CYCLON_LOGO_URL) or CYCLON_LOGO_URL
st.markdown(
    '<img src="' + html.escape(_logo_src, quote=True) + '" alt="CYCLON" '
    'style="width:150px; height:auto; margin-bottom:14px;">',
    unsafe_allow_html=True,
)

st.markdown(
    '<h1 style="font-size: 30px; margin-bottom: 0.5rem;">🔎 CYCLON Oil Standard Finder</h1>',
    unsafe_allow_html=True,
)

st.write("Search CYCLON automotive oils by vehicle manufacturer specification.")

st.caption("Examples: VW509, VW504, MB22951, BMWLL04, PorscheC30")

st.caption(
    "Searches the local CYCLON catalog and automatically matches equivalent standard formats."
)


# ============================================================
# HELPERS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
FERROMAT_FILE = BASE_DIR / "oils.xlsx"


def clean_text(value):
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(x).strip() for x in value if str(x).strip())
    return str(value).strip()


def _ref_key(value):
    return re.sub(r"[^A-Z0-9]+", "", clean_text(value).upper())


def _split_master_refs(value):
    text = clean_text(value)
    if not text:
        return []
    refs = []
    for part in re.split(r"\s*/\s*|\s*\|\s*|\s*;\s*|\s*,\s*", text):
        key = _ref_key(part)
        if key and key not in refs:
            refs.append(key)
    return refs


def _supplier_refs_from_result(value):
    """
    Extract CYCLON article numbers from SKU / Size.
    Example:
      3707 – 5 l | 8972 – 1 l | 3715 – 4 l
    """
    text = clean_text(value)
    if not text:
        return []

    refs = []
    for chunk in re.split(r"\s*\|\s*|\s*;\s*|\s*,\s*", text):
        chunk = chunk.strip()
        if not chunk:
            continue

        m = re.match(r"^\s*([A-Za-z0-9][A-Za-z0-9._/-]*)", chunk)
        if not m:
            continue

        token = m.group(1)

        for part in token.split("/"):
            key = _ref_key(part)
            if key and key not in refs:
                refs.append(key)

    return refs


@st.cache_data(show_spinner=False)
def load_ferromat_lookup():
    """
    Exact mapping only:
      BRAND = CYCLON
      + exact SUPPLIER_REF

    No mapping is inferred from an oil standard or product name.
    """
    lookup = {}

    if not FERROMAT_FILE.exists():
        return lookup

    try:
        frame = pd.read_excel(FERROMAT_FILE, dtype=str).fillna("")
    except Exception:
        return lookup

    required = {"SKU_FERROMAT", "BRAND", "SUPPLIER_REF"}
    if not required.issubset(frame.columns):
        return lookup

    frame = frame[
        frame["BRAND"].astype(str).str.strip().str.upper().eq("CYCLON")
    ].copy()

    for _, item in frame.iterrows():
        ferromat_sku = clean_text(item.get("SKU_FERROMAT"))
        if not ferromat_sku:
            continue

        for supplier_ref in _split_master_refs(item.get("SUPPLIER_REF")):
            lookup.setdefault(supplier_ref, [])
            if ferromat_sku not in lookup[supplier_ref]:
                lookup[supplier_ref].append(ferromat_sku)

    return lookup


def ferromat_links_for_product(sku_size):
    lookup = load_ferromat_lookup()
    found = []
    seen = set()

    for supplier_ref in _supplier_refs_from_result(sku_size):
        for ferromat_sku in lookup.get(supplier_ref, []):
            if ferromat_sku in seen:
                continue

            seen.add(ferromat_sku)
            found.append({
                "sku": ferromat_sku,
                # oils.xlsx does not contain FERROMAT URLs.
                # This opens FERROMAT's own exact-SKU search and is navigation only.
                "url": "https://www.ferromat.co.il/?s=" + quote_plus(ferromat_sku),
                "supplier_ref": supplier_ref,
            })

    return found


@st.cache_resource(show_spinner=False)
def get_cyclon_products():
    return load_cyclon_products()


def build_results(standard):
    products = get_cyclon_products()
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
        row["FERROMAT Links"] = ferromat_links_for_product(row["SKU / Size"])
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

    Matching FERROMAT SKUs are appended inside SKU / Size.
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

        image_url = clean_text(row.get("Image"))
        if image_url:
            image_src = cyclon_asset(image_url) or image_url
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
        links = row.get("FERROMAT Links", []) or []
        ferromat_display = []

        for item in links:
            sku = clean_text(item.get("sku"))
            url = clean_text(item.get("url"))
            if not sku:
                continue

            if url:
                ferromat_display.append(
                    '<a target="_blank" href="'
                    + html.escape(url, quote=True)
                    + '">'
                    + html.escape(sku)
                    + "</a>"
                )
            else:
                ferromat_display.append(html.escape(sku))

        if ferromat_display:
            if sku_html:
                sku_html += " "
            sku_html += "(FERROMAT " + " | ".join(ferromat_display) + ")"

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
        "Enter oil specification",
        key="standard_input",
        placeholder="Example: VW504",
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
        st.warning("Please enter an oil specification.")
    else:
        with st.spinner("Searching the CYCLON catalog..."):
            results = build_results(standard)

        st.session_state.search_results = results
        st.session_state.last_standard = standard
        st.session_state.ferromat_display_filter = "FERROMAT_ONLY"


# ============================================================
# SHOW RESULTS
# ============================================================

results = st.session_state.search_results

if results:
    df = pd.DataFrame(results)

    st.markdown("### Product Display")

    ferromat_mask = df["FERROMAT Links"].apply(
        lambda value: bool(value)
        if isinstance(value, (list, tuple, set, dict))
        else bool(clean_text(value))
    )

    ferromat_count = int(ferromat_mask.sum())

    filter_col_all, filter_col_ferromat = st.columns(2)

    with filter_col_all:
        all_selected = st.session_state.ferromat_display_filter == "ALL"
        if st.button(
            f"All matching products\n\n{len(df)}",
            key="ferromat_filter_all",
            use_container_width=True,
            type="primary" if all_selected else "secondary",
        ):
            st.session_state.ferromat_display_filter = "ALL"
            st.rerun()

    with filter_col_ferromat:
        ferromat_selected = (
            st.session_state.ferromat_display_filter == "FERROMAT_ONLY"
        )
        if st.button(
            f"FERROMAT products only\n\n{ferromat_count}",
            key="ferromat_filter_only",
            use_container_width=True,
            type="primary" if ferromat_selected else "secondary",
        ):
            st.session_state.ferromat_display_filter = "FERROMAT_ONLY"
            st.rerun()

    if st.session_state.ferromat_display_filter == "FERROMAT_ONLY":
        df = df.loc[ferromat_mask].copy()

    st.markdown(
        f"### CYCLON Results ({len(df)})"
    )

    if df.empty:
        st.info(
            "CYCLON products matching this specification were found, but none has an exact FERROMAT mapping. "
            "Click 'All matching products' to view them all."
        )
    else:
        render_results_table(df)

elif st.session_state.last_standard:
    st.info(
        f"No CYCLON products were found for specification {st.session_state.last_standard}."
    )
