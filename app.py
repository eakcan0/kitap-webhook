# app.py
from flask import Flask, request, jsonify
import os, time, csv, io, requests, unicodedata, re

app = Flask(__name__)
SHEET_CSV_URL = os.getenv("SHEET_CSV_URL")
CACHE_TTL = int(os.getenv("CACHE_TTL", "60"))  # saniye

_cache = {"ts": 0, "rows": []}

def _norm_tr(s: str) -> str:
    if not s: return ""
    s = s.strip()
    tr_map = str.maketrans("ıİşŞçÇğĞöÖüÜ", "iiSSccggoouu")
    s = s.translate(tr_map).lower()
    s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s

def _load_rows():
    now = time.time()
    if _cache["rows"] and now - _cache["ts"] < CACHE_TTL:
        return _cache["rows"]
    r = requests.get(SHEET_CSV_URL, timeout=8)
    r.raise_for_status()
    rdr = csv.DictReader(io.StringIO(r.text))
    rows = []
    for row in rdr:
        title = (row.get("Title") or "").strip()
        price = row.get("Price_TRY")
        stock_note = (row.get("StockNote") or "").strip()
        sku = (row.get("SKU") or "").strip()
        kws = (row.get("Keywords") or "").strip()
        rows.append({
            "title": title,
            "norm": _norm_tr(title),
            "price": float(price) if (price is not None and str(price).strip() != "") else None,
            "stock_note": stock_note,
            "sku": sku,
            "kw_norms": [_norm_tr(k) for k in kws.split(",") if k.strip()]
        })
    _cache.update({"ts": now, "rows": rows})
    return rows

def _find(query):
    q = _norm_tr(query)
    if not q: return None
    rows = _load_rows()
    # Tam eşleşme
    for r in rows:
        if r["norm"] == q:
            return r
    # Keywords tam eşleşme
    for r in rows:
        if q in r["kw_norms"]:
            return r
    # Kısmi eşleşme (başlıkta)
    cands = [r for r in rows if q in r["norm"]]
    if cands:
        cands.sort(key=lambda x: len(x["norm"]))
        return cands[0]
    return None

@app.route("/", methods=["GET"])
def health():
    return "ok", 200

@app.route("/check-book", methods=["POST"])
def check_book():
    data = request.get_json(force=True) or {}
    query = (data.get("query") or "").strip()
    row = _find(query)
    if not row or row["price"] is None:
        return jsonify({"found": False}), 200

    title = row["title"]
    price = int(row["price"]) if row["price"].is_integer() else row["price"]
    if row["stock_note"]:
        message = f"'{title}' {row['stock_note']}. Fiyatı {price} TL."
    else:
        message = f"'{title}' ürün stoklarımızda mevcuttur. Fiyatı {price} TL."
    return jsonify({
        "found": True,
        "title": title,
        "price": price,
        "stock_note": row["stock_note"],
        "sku": row["sku"],
        "message": message
    }), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
