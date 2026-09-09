import json, re
from pathlib import Path

CATALOG = Path(__file__).resolve().parent / "cyclon_catalog.json"

def _norm(v):
    return re.sub(r"[^A-Z0-9]+", "", str(v or "").upper())

def _variants(q):
    n=_norm(q); v={n}
    m=re.fullmatch(r"VW(\d{3})", n)
    if m: v.add("VW"+m.group(1)+"00")
    m=re.fullmatch(r"VW(\d{3})00", n)
    if m: v.add("VW"+m.group(1))
    if n.startswith("BMWLONGLIFE"): v.add(n.replace("BMWLONGLIFE","BMWLL",1))
    if n.startswith("BMWLL"): v.add(n.replace("BMWLL","BMWLONGLIFE",1))
    return v

def load_cyclon_products():
    return json.loads(CATALOG.read_text(encoding="utf-8"))

def search_cyclon(products, standard):
    qv=_variants(standard)
    result=[]
    for p in products:
        keys=set()
        for field in ("search_keys","standards"):
            vals=p.get(field,[])
            if not isinstance(vals,list): vals=[vals]
            keys.update(_norm(x) for x in vals if x)
        if qv & keys:
            result.append(p)
    return result
