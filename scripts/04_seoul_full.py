#!/usr/bin/env python3
"""
Stage 4 — Seoul-wide pipeline (all 25 자치구). v2: STRtree spatial index,
cached bounds, hoisted bbox, unbuffered output, per-district checkpoints.

Pipeline:
1) Fetch Seoul 자치구 polygons (cached → skip if seoul_districts.geojson exists)
2) Fetch all park polygons within Seoul bbox (cached → skip if seoul_parks.geojson exists)
3) Per district: parcels fetch → STRtree spatial join (>=50%) → checkpoint
4) Query ownership for all unique matched parcels
5) Save combined seoul_park_parcels_all.geojson
"""

import json
import os
import sys
import time
from pathlib import Path
from functools import partial

import requests
from dotenv import load_dotenv
from shapely.geometry import shape
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
KEY = os.environ.get("VWORLD_API_KEY")
DOMAIN = "localhost:3000"

if not KEY or KEY.startswith("your-"):
    sys.exit("❌ VWORLD_API_KEY not set")

OUT = ROOT / "data" / "seoul"
OUT.mkdir(parents=True, exist_ok=True)
DISTRICTS_DIR = OUT / "districts"
DISTRICTS_DIR.mkdir(exist_ok=True)

SEOUL_BBOX = (126.760, 37.420, 127.190, 37.705)
ADMIN_LAYER_CANDIDATES = ["lt_c_adsigg_info", "lt_c_adsigg", "lt_c_adsigg2025", "lt_c_admsection"]
SPACE_LAYER = "lt_c_upisuq153"
PARCEL_LAYER = "lt_c_landinfobasemap"
OVERLAP_THRESHOLD = 0.50

DATA_URL = "https://api.vworld.kr/req/data"
POSS_URL = "https://api.vworld.kr/ned/data/getPossessionAttr"

# Force-flushed print
log = partial(print, flush=True)

SESSION = requests.Session()


def fetch_features(layer, bbox, attr_filter=None, max_pages=200):
    minx, miny, maxx, maxy = bbox
    geom = f"BOX({minx},{miny},{maxx},{maxy})"
    all_feats, page = [], 1
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
        try:
            r = SESSION.get(DATA_URL, params=params, timeout=60)
            j = r.json()
        except Exception as e:
            log(f"   ⚠️ page {page}: {e}")
            break
        if j.get("response", {}).get("status") != "OK":
            err = j.get("response", {}).get("error", {}).get("text", "?")
            log(f"   ⚠️ page {page}: {err[:100]}")
            break
        feats = j["response"]["result"]["featureCollection"]["features"]
        all_feats.extend(feats)
        rec = j["response"]["record"]
        total = int(rec.get("total", 0))
        if page % 5 == 0 or len(feats) < 1000:
            log(f"   page {page}: +{len(feats)} (running {len(all_feats)}/{total})")
        if len(feats) < 1000 or len(all_feats) >= total:
            break
        page += 1
        time.sleep(0.05)
    return all_feats


def fetch_possession(pnu):
    params = {"key": KEY, "domain": DOMAIN, "pnu": pnu, "format": "json", "numOfRows": 5, "pageNo": 1}
    try:
        r = SESSION.get(POSS_URL, params=params, timeout=15)
        j = r.json()
        poss = j.get("possessions") or {}
        return poss.get("field", [])
    except Exception:
        return []


def find_admin_layer():
    for cand in ADMIN_LAYER_CANDIDATES:
        try:
            r = SESSION.get(DATA_URL, params={
                "key": KEY, "domain": DOMAIN, "service": "data", "request": "GetFeature",
                "data": cand, "geomFilter": "BOX(126.97,37.55,127.00,37.58)",
                "size": 1, "format": "json", "crs": "EPSG:4326"
            }, timeout=30)
            j = r.json()
            if j.get("response", {}).get("status") == "OK":
                return cand
        except Exception:
            continue
    return None


def step1_districts():
    """Fetch or load cached 자치구."""
    cache = OUT / "seoul_districts.geojson"
    if cache.exists():
        log(f"1️⃣  Using cached {cache.name}")
        return json.loads(cache.read_text())["features"]
    log("1️⃣  Fetching 자치구 (admin boundaries)...")
    admin_layer = find_admin_layer()
    if not admin_layer:
        log("⚠️ no admin layer found")
        return []
    log(f"   using layer: {admin_layer}")
    admin_feats = fetch_features(admin_layer, SEOUL_BBOX, max_pages=5)
    seoul = []
    by_cd = {}
    for f in admin_feats:
        p = f["properties"]
        sig_cd = p.get("sig_cd") or p.get("sigungu_cd") or p.get("adm_cd") or ""
        sig_nm = p.get("sig_kor_nm") or p.get("sig_nm") or p.get("sigungu_nm") or p.get("adm_nm") or ""
        if sig_cd.startswith("11") and ("구" in sig_nm or sig_cd[2:5] not in ["000", ""]):
            if sig_cd and sig_cd not in by_cd:
                by_cd[sig_cd] = f
    seoul = list(by_cd.values())
    log(f"   found {len(seoul)} districts")
    cache.write_text(json.dumps({"type":"FeatureCollection","features":seoul}, ensure_ascii=False))
    return seoul


def step2_parks():
    """Fetch or load cached parks."""
    cache = OUT / "seoul_parks.geojson"
    if cache.exists():
        log(f"2️⃣  Using cached {cache.name}")
        return json.loads(cache.read_text())["features"]
    log("2️⃣  Fetching all park polygons in Seoul...")
    space_feats = fetch_features(SPACE_LAYER, SEOUL_BBOX, max_pages=50)
    log(f"   total fetched: {len(space_feats)}")
    parks = [f for f in space_feats
             if any(k in (f["properties"].get("lcl_nam","")) for k in ["공원","녹지","유원지","광장"])]
    log(f"   park-like: {len(parks)}")
    cache.write_text(json.dumps({"type":"FeatureCollection","features":parks}, ensure_ascii=False))
    return parks


def main():
    log(f"📍 Seoul bbox: {SEOUL_BBOX}\n")

    seoul_districts = step1_districts()
    park_feats = step2_parks()

    # Build STRtree once
    log("\n🌳 Building spatial index (STRtree) for parks...")
    park_geoms = []
    park_props = []
    park_bounds = []  # precomputed bounds tuples
    for f in park_feats:
        try:
            g = shape(f["geometry"])
            if not g.is_valid: g = g.buffer(0)
            park_geoms.append(g)
            park_props.append(f["properties"])
            park_bounds.append(g.bounds)
        except Exception:
            continue
    park_tree = STRtree(park_geoms)
    log(f"   indexed {len(park_geoms)} park polygons\n")

    # Build district jobs (per-district bbox + bounding polygon for admin filter)
    log("📋 Building district job list...")
    district_jobs = []
    if seoul_districts:
        for d in seoul_districts:
            try:
                g = shape(d["geometry"])
                if not g.is_valid: g = g.buffer(0)
                minx, miny, maxx, maxy = g.bounds
                p = d["properties"]
                name = (p.get("sig_kor_nm") or p.get("sig_nm")
                        or p.get("sigungu_nm") or p.get("adm_nm") or "?")
                cd = p.get("sig_cd") or p.get("sigungu_cd") or ""
                district_jobs.append((name, cd, (minx,miny,maxx,maxy)))
            except Exception:
                continue
    else:
        log("   fallback: 5x5 grid of Seoul bbox")
        for i in range(5):
            for j in range(5):
                lx = 126.760 + (127.190-126.760) * i/5
                rx = 126.760 + (127.190-126.760) * (i+1)/5
                ly = 37.420 + (37.705-37.420) * j/5
                ry = 37.420 + (37.705-37.420) * (j+1)/5
                district_jobs.append((f"tile_{i}_{j}", "", (lx,ly,rx,ry)))
    log(f"   {len(district_jobs)} districts to process\n")

    # Stage 3: per-district parcel fetch + STRtree-accelerated spatial join
    log(f"3️⃣  Processing {len(district_jobs)} districts (STRtree spatial join)...\n")
    all_matched = {}

    for di, (name, cd, bbox) in enumerate(district_jobs, 1):
        ckpt = DISTRICTS_DIR / f"{name}.geojson"
        if ckpt.exists():
            cached = json.loads(ckpt.read_text())["features"]
            log(f"[{di}/{len(district_jobs)}] {name} — cached ({len(cached)}건)")
            for f in cached:
                pnu = f["properties"].get("pnu")
                if pnu: all_matched[pnu] = f
            continue

        log(f"[{di}/{len(district_jobs)}] {name} (cd={cd}) bbox={bbox}")
        t0 = time.time()
        parcel_feats = fetch_features(PARCEL_LAYER, bbox, max_pages=100)
        log(f"   parcels fetched: {len(parcel_feats)} ({time.time()-t0:.1f}s)")
        n_matched = 0
        district_matched = []
        t1 = time.time()
        for pf in parcel_feats:
            pnu = pf["properties"].get("pnu")
            if not pnu or pnu in all_matched:
                continue
            try:
                pg = shape(pf["geometry"])
                if not pg.is_valid: pg = pg.buffer(0)
            except Exception:
                continue
            pg_bounds = pg.bounds              # PATCH 3: hoist
            pg_area = pg.area
            # PATCH 1: STRtree spatial query
            cand_idx = park_tree.query(pg)
            best_overlap = 0.0
            best_idx = -1
            for idx in cand_idx:
                gb = park_bounds[idx]           # PATCH 2: cached bounds
                if pg_bounds[2] < gb[0] or pg_bounds[0] > gb[2] \
                   or pg_bounds[3] < gb[1] or pg_bounds[1] > gb[3]:
                    continue
                park_g = park_geoms[idx]
                if not pg.intersects(park_g):
                    continue
                inter = pg.intersection(park_g)
                ov = inter.area / pg_area
                if ov > best_overlap:
                    best_overlap = ov; best_idx = idx
            if best_overlap >= OVERLAP_THRESHOLD and best_idx >= 0:
                pp = park_props[best_idx]
                pf["properties"]["matched_park_name"] = pp.get("dgm_nm","")
                pf["properties"]["matched_park_type"] = pp.get("lcl_nam","")
                pf["properties"]["match_overlap_pct"] = round(best_overlap*100, 1)
                all_matched[pnu] = pf
                district_matched.append(pf)
                n_matched += 1
        log(f"   matched: {n_matched}  spatial: {time.time()-t1:.1f}s  cumulative: {len(all_matched)}")
        # PATCH 5: checkpoint
        ckpt.write_text(json.dumps(
            {"type":"FeatureCollection","features":district_matched}, ensure_ascii=False))
        log(f"   💾 checkpoint: {ckpt.name}")

    log(f"\n✅ total matched parcels: {len(all_matched)}")
    (OUT / "_pre_ownership.geojson").write_text(
        json.dumps({"type":"FeatureCollection","features":list(all_matched.values())}, ensure_ascii=False))

    # Stage 4: ownership query
    log(f"\n4️⃣  Querying ownership for {len(all_matched)} parcels...")
    matched_list = list(all_matched.values())
    enriched = []
    t0 = time.time()
    for i, f in enumerate(matched_list, 1):
        # If already enriched from cache, skip
        if f["properties"].get("owner_type"):
            enriched.append(f)
            continue
        pnu = f["properties"]["pnu"]
        fields = fetch_possession(pnu)
        if fields:
            row = fields[0]
            f["properties"]["owner_type"] = row.get("posesnSeCodeNm","")
            f["properties"]["owner_subtype"] = row.get("nationInsttSeCodeNm","")
            f["properties"]["area_m2"] = row.get("lndpclAr","")
            f["properties"]["price_per_m2"] = row.get("pblntfPclnd","")
            enriched.append(f)
        if i % 100 == 0:
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed > 0 else 0
            eta = (len(matched_list) - i) / rate if rate > 0 else 0
            log(f"   {i}/{len(matched_list)} done  rate={rate:.1f}/s  eta={eta/60:.1f}min")
        time.sleep(0.03)
    log(f"\n✅ enriched: {len(enriched)}")

    # Stage 5: save
    out_fc = {"type":"FeatureCollection","features":enriched}
    (OUT / "seoul_park_parcels_all.geojson").write_text(json.dumps(out_fc, ensure_ascii=False))
    log(f"💾 seoul_park_parcels_all.geojson  ({len(enriched)} features)")

    counts = {}
    for f in enriched:
        ot = f["properties"].get("owner_type") or "?"
        counts[ot] = counts.get(ot, 0) + 1
    log("\n📊 Owner type distribution:")
    for k, v in sorted(counts.items(), key=lambda x: -x[1]):
        log(f"   {k:14s} {v:6d}")
    private = sum(v for k,v in counts.items() if k in ["개인","법인"])
    log(f"\n  Private (개인+법인): {private}  ({round(private/len(enriched)*100,1)}%)" if enriched else "")
    log(f"\n💾 Output in: {OUT}")


if __name__ == "__main__":
    main()
