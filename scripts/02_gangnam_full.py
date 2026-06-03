#!/usr/bin/env python3
"""
Stage 2 — 강남구 full pipeline:
1) Get all 도시계획(공간시설) polygons in 강남구
2) For each park polygon, find parcels (필지) inside (true spatial join)
3) Query ownership for each unique parcel PNU
4) Save matched private-owned parcels as GeoJSON
"""

import csv
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from shapely.geometry import shape, Polygon, mapping
from shapely.ops import unary_union
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
KEY = os.environ.get("VWORLD_API_KEY")
DOMAIN = "localhost:3000"

if not KEY or KEY.startswith("your-"):
    sys.exit("❌ VWORLD_API_KEY not set")

OUT = ROOT / "data" / "seoul" / "gangnam"
OUT.mkdir(parents=True, exist_ok=True)

# 강남구 bbox (loose)
GANGNAM_BBOX = (127.000, 37.460, 127.130, 37.545)
SPACE_LAYER = "lt_c_upisuq153"
PARCEL_LAYER = "lt_c_landinfobasemap"

DATA_URL = "https://api.vworld.kr/req/data"
POSS_URL = "https://api.vworld.kr/ned/data/getPossessionAttr"

SESSION = requests.Session()


def fetch_features(layer, bbox, attr_filter=None, max_pages=20):
    """Fetch all features in bbox (paginated)."""
    minx, miny, maxx, maxy = bbox
    geom = f"BOX({minx},{miny},{maxx},{maxy})"
    all_feats = []
    page = 1
    while page <= max_pages:
        params = {
            "key": KEY, "domain": DOMAIN,
            "service": "data", "request": "GetFeature",
            "data": layer, "geomFilter": geom,
            "size": 1000, "page": page,
            "format": "json", "crs": "EPSG:4326",
            "geometry": "true", "attribute": "true",
        }
        if attr_filter:
            params["attrFilter"] = attr_filter
        r = SESSION.get(DATA_URL, params=params, timeout=60)
        j = r.json()
        if j.get("response", {}).get("status") != "OK":
            err = j.get("response", {}).get("error", {}).get("text", "?")
            print(f"   ⚠️ page {page}: {err[:80]}")
            break
        feats = j["response"]["result"]["featureCollection"]["features"]
        all_feats.extend(feats)
        rec = j["response"]["record"]
        total = int(rec.get("total", 0))
        print(f"   page {page}: +{len(feats)} (total in bbox: {total})")
        if len(feats) < 1000 or len(all_feats) >= total:
            break
        page += 1
        time.sleep(0.1)
    return all_feats


def fetch_possession(pnu):
    params = {"key": KEY, "domain": DOMAIN, "pnu": pnu, "format": "json", "numOfRows": 5, "pageNo": 1}
    try:
        r = SESSION.get(POSS_URL, params=params, timeout=15)
        j = r.json()
        poss = j.get("possessions") or {}
        fields = poss.get("field", [])
        return fields
    except Exception as e:
        return []


def main():
    print(f"📍 강남구 bbox: {GANGNAM_BBOX}")
    print(f"🔑 key: {KEY[:8]}...\n")

    # 1) Park polygons in 강남구
    print("1️⃣  Fetching 도시계획 공간시설 (lt_c_upisuq153)...")
    space_feats = fetch_features(SPACE_LAYER, GANGNAM_BBOX)
    print(f"   total fetched: {len(space_feats)}")

    # Filter park-like + only 강남구
    park_feats = []
    for f in space_feats:
        p = f["properties"]
        lcl = p.get("lcl_nam", "")
        sig = p.get("sig_nam", "")  # 시군구 코드 fragment
        # 강남구 sig code: 11680. sig_nam in this layer is "11" only -- so cross-check via geometry
        if any(k in lcl for k in ["공원", "녹지", "유원지", "광장"]):
            park_feats.append(f)
    print(f"   filtered 공원/녹지/유원지/광장: {len(park_feats)}")

    # Build shapely polygons
    park_polys = []
    for f in park_feats:
        geom = f.get("geometry")
        if not geom:
            continue
        try:
            g = shape(geom)
            if not g.is_valid:
                g = g.buffer(0)
            park_polys.append((g, f))
        except Exception:
            continue
    print(f"   valid polygons: {len(park_polys)}")

    # Save park polygons
    park_fc = {"type": "FeatureCollection", "features": [pf for _, pf in park_polys]}
    (OUT / "parks.geojson").write_text(json.dumps(park_fc, ensure_ascii=False))
    print(f"   💾 parks.geojson")

    # 2) Parcels in same bbox (paginated)
    print("\n2️⃣  Fetching 필지 (lt_c_landinfobasemap)...")
    parcel_feats = fetch_features(PARCEL_LAYER, GANGNAM_BBOX, max_pages=80)
    print(f"   total parcels fetched: {len(parcel_feats)}")

    # 3) Spatial join: parcels intersecting any park polygon (>=50%)
    OVERLAP_THRESHOLD = 0.50
    print(f"\n3️⃣  Spatial join (overlap >= {int(OVERLAP_THRESHOLD*100)}%)...")
    # Per-polygon intersection so we can attach the matched park's name
    inside_parcels = []
    seen_pnu = set()
    # Build R-tree-like quick lookup by bbox for efficiency
    for f in parcel_feats:
        pnu = f.get("properties", {}).get("pnu")
        if not pnu or pnu in seen_pnu:
            continue
        geom = f.get("geometry")
        if not geom:
            continue
        try:
            pg = shape(geom)
            if not pg.is_valid:
                pg = pg.buffer(0)
            best_park = None
            best_overlap = 0.0
            for park_g, park_f in park_polys:
                if not pg.intersects(park_g):
                    continue
                inter = pg.intersection(park_g)
                ov = inter.area / pg.area
                if ov > best_overlap:
                    best_overlap = ov
                    best_park = park_f
            if best_overlap >= OVERLAP_THRESHOLD and best_park is not None:
                pp = best_park["properties"]
                f["properties"]["matched_park_name"] = pp.get("dgm_nm", "")
                f["properties"]["matched_park_type"] = pp.get("lcl_nam", "")
                f["properties"]["match_overlap_pct"] = round(best_overlap * 100, 1)
                seen_pnu.add(pnu)
                inside_parcels.append(f)
        except Exception:
            continue

    print(f"   parcels matched (>= {int(OVERLAP_THRESHOLD*100)}% overlap): {len(inside_parcels)}")

    # Restrict to 강남구 administrative area by sgg_nm
    inside_parcels = [
        f for f in inside_parcels
        if (f.get("properties", {}).get("sgg_nm") or "") == "강남구"
    ]
    print(f"   filtered to 강남구: {len(inside_parcels)}")

    # 4) Query ownership for each
    print(f"\n4️⃣  Querying ownership for {len(inside_parcels)} parcels...")
    enriched = []
    for i, f in enumerate(inside_parcels, 1):
        pnu = f["properties"]["pnu"]
        fields = fetch_possession(pnu)
        if fields:
            row = fields[0]
            f["properties"]["owner_type"] = row.get("posesnSeCodeNm", "")
            f["properties"]["owner_subtype"] = row.get("nationInsttSeCodeNm", "")
            f["properties"]["area_m2"] = row.get("lndpclAr", "")
            f["properties"]["price_per_m2"] = row.get("pblntfPclnd", "")
            enriched.append(f)
        if i % 20 == 0:
            print(f"   {i}/{len(inside_parcels)} done")
        time.sleep(0.05)

    # 5) Filter private (개인/법인) and save
    private_only = [
        f for f in enriched
        if f["properties"].get("owner_type") in ["개인", "법인"]
    ]
    print(f"\n5️⃣  Private (개인+법인) parcels: {len(private_only)}")

    # Save GeoJSON
    full_fc = {"type": "FeatureCollection", "features": enriched}
    (OUT / "park_parcels_all.geojson").write_text(json.dumps(full_fc, ensure_ascii=False))
    priv_fc = {"type": "FeatureCollection", "features": private_only}
    (OUT / "park_parcels_private.geojson").write_text(json.dumps(priv_fc, ensure_ascii=False))

    # Summary CSV
    counts = {}
    for f in enriched:
        ot = f["properties"].get("owner_type") or "?"
        counts[ot] = counts.get(ot, 0) + 1
    print("\n📊 Owner type distribution:")
    for k, v in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"   {k:12s} {v}")

    # Write csv summary
    if enriched:
        keys = ["pnu", "sgg_nm", "emd_nm", "jibun", "jimok", "area_m2",
                "price_per_m2", "owner_type", "owner_subtype"]
        with open(OUT / "summary.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(keys)
            for feat in enriched:
                p = feat["properties"]
                w.writerow([p.get(k, "") for k in keys])

    print(f"\n💾 All output in: {OUT}")


if __name__ == "__main__":
    main()
