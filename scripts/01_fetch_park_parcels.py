#!/usr/bin/env python3
"""
Stage 1 — Gangnam-gu pilot:
1) Fetch 도시계획(공간시설) features (parks/녹지) in a bbox
2) Filter for 공원 / 녹지
3) For each polygon, find intersecting parcels (PNUs)
4) Query getPossessionAttr for each PNU
5) Save GeoJSON + summary CSV
"""

import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

KEY = os.environ.get("VWORLD_API_KEY")
if not KEY or KEY == "your-vworld-key-here":
    sys.exit("❌ VWORLD_API_KEY not set in .env")

DOMAIN = "localhost:3000"
DATA_DIR = ROOT / "data" / "samples"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Pilot bbox: a small slice of Gangnam (역삼동/대치동 area)
PILOT_BBOX = "127.040,37.495,127.075,37.515"  # minX,minY,maxX,maxY (EPSG:4326)
SPACE_FACILITY_LAYER = "lt_c_upisuq153"   # 도시계획(공간시설) — parks, 녹지, 광장
PARCEL_LAYER = "lt_c_landinfobasemap"     # 필지 base map (PNU)

VWORLD_DATA = "https://api.vworld.kr/req/data"
NED_POSS = "https://api.vworld.kr/ned/data/getPossessionAttr"


def fetch_data_features(layer, bbox, size=1000, page=1):
    params = {
        "key": KEY,
        "domain": DOMAIN,
        "service": "data",
        "request": "GetFeature",
        "data": layer,
        "geomFilter": f"BOX({bbox})",
        "size": size,
        "page": page,
        "format": "json",
        "crs": "EPSG:4326",
        "geometry": "true",
        "attribute": "true",
    }
    r = requests.get(VWORLD_DATA, params=params, timeout=30)
    j = r.json()
    if j.get("response", {}).get("status") != "OK":
        print("  ⚠️", j.get("response", {}).get("error", {}).get("text", "?")[:200])
        return [], 0
    fc = j["response"]["result"]["featureCollection"]
    total = int(j["response"]["record"]["total"])
    return fc.get("features", []), total


def fetch_possession(pnu):
    params = {
        "key": KEY,
        "domain": DOMAIN,
        "pnu": pnu,
        "format": "json",
        "numOfRows": 5,
        "pageNo": 1,
    }
    r = requests.get(NED_POSS, params=params, timeout=15)
    j = r.json()
    poss = j.get("possessions") or j.get("response") or {}
    fields = poss.get("field", [])
    return fields


def main():
    print(f"📍 Pilot bbox: {PILOT_BBOX}")
    print(f"🔑 Key: {KEY[:8]}... (domain={DOMAIN})\n")

    # 1) 공간시설 (parks/녹지)
    print(f"1️⃣  Fetching {SPACE_FACILITY_LAYER} (도시계획 공간시설)...")
    space_feats, total = fetch_data_features(SPACE_FACILITY_LAYER, PILOT_BBOX, size=1000)
    print(f"   total in bbox: {total}, fetched: {len(space_feats)}")

    # Filter for 공원/녹지 only
    park_feats = []
    type_counts = {}
    for f in space_feats:
        p = f.get("properties", {})
        lcl = p.get("lcl_nam") or p.get("lclas_cl") or ""
        type_counts[lcl] = type_counts.get(lcl, 0) + 1
        if any(k in lcl for k in ["공원", "녹지", "유원지", "광장"]):
            park_feats.append(f)
    print(f"   facility types: {type_counts}")
    print(f"   filtered 공원/녹지/유원지/광장: {len(park_feats)}\n")

    # Save raw space facilities GeoJSON
    fc_out = {"type": "FeatureCollection", "features": park_feats}
    (DATA_DIR / "01_space_facilities.geojson").write_text(
        json.dumps(fc_out, ensure_ascii=False, indent=2)
    )
    print(f"   💾 saved {DATA_DIR}/01_space_facilities.geojson")

    if not park_feats:
        print("⚠️ no park polygons — try wider bbox")
        return

    # 2) Parcels (필지) in same bbox
    print(f"\n2️⃣  Fetching {PARCEL_LAYER} (필지 PNU)...")
    parcel_feats, parcel_total = fetch_data_features(PARCEL_LAYER, PILOT_BBOX, size=1000)
    print(f"   parcels in bbox: {parcel_total}, fetched: {len(parcel_feats)}")

    # Build PNU -> parcel feature map
    pnu_to_parcel = {}
    for f in parcel_feats:
        pnu = f.get("properties", {}).get("pnu")
        if pnu:
            pnu_to_parcel[pnu] = f

    # 3) Filter parcels intersecting park polygons (simple bbox-overlap for now)
    # For pilot, take first 30 parcels (rate limit care)
    sample_pnus = list(pnu_to_parcel.keys())[:30]
    print(f"\n3️⃣  Sampling {len(sample_pnus)} parcels for ownership lookup")

    # 4) Query ownership
    results = []
    for i, pnu in enumerate(sample_pnus, 1):
        fields = fetch_possession(pnu)
        if fields:
            row = fields[0]  # first owner record per parcel
            results.append({
                "pnu": pnu,
                "addr": row.get("ldCodeNm"),
                "jibun": row.get("mnnmSlno"),
                "jimok": row.get("lndcgrCodeNm"),
                "area_m2": row.get("lndpclAr"),
                "price_per_m2": row.get("pblntfPclnd"),
                "owner_type": row.get("posesnSeCodeNm"),   # 개인/법인/...
                "owner_subtype": row.get("nationInsttSeCodeNm"),
                "resdnc": row.get("resdncSeCodeNm"),
            })
        if i % 5 == 0:
            print(f"   {i}/{len(sample_pnus)} done")
        time.sleep(0.1)  # gentle rate limit

    # Save CSV
    import csv
    csv_path = DATA_DIR / "02_ownership_sample.csv"
    if results:
        keys = list(results[0].keys())
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(results)
        print(f"\n   💾 saved {csv_path}")

    # Summary
    owner_counts = {}
    for r in results:
        ot = r.get("owner_type") or "?"
        owner_counts[ot] = owner_counts.get(ot, 0) + 1
    print(f"\n📊 Owner type distribution (sample of {len(results)}):")
    for k, v in sorted(owner_counts.items(), key=lambda x: -x[1]):
        print(f"   {k:10s} {v}")


if __name__ == "__main__":
    main()
