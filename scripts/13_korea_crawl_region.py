#!/usr/bin/env python3
"""
Stage 13 — Region-filtered Korea crawler for cron use.

Selects districts whose sig_cd matches the requested 시·도 codes, deletes their
old checkpoints, re-crawls + spatial-joins + ownership-queries them, then
aggregates ALL existing checkpoints (target + untouched) into
korea_park_parcels_all.geojson so downstream stages always see complete data.

Usage:
  python 13_korea_crawl_region.py --sidos 서울특별시 경기도 인천광역시 ...

Sig_cd prefix → 시·도:
  11: 서울특별시   26: 부산광역시   27: 대구광역시   28: 인천광역시
  29: 광주광역시   30: 대전광역시   31: 울산광역시   36: 세종특별자치시
  41: 경기도       42: 강원특별자치도/강원도
  43: 충청북도     44: 충청남도
  45: 전북특별자치도/전라북도   46: 전라남도
  47: 경상북도     48: 경상남도   50: 제주특별자치도

Checkpoints are always saved as {name}_{sig_cd}.geojson (collision-free vs older
{name}.geojson scheme — both formats are read on aggregation).
"""

import argparse
import json
import os
import sys
import time
from functools import partial
from pathlib import Path

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

OUT = ROOT / "data" / "korea"
DISTRICTS_DIR = OUT / "districts"
DISTRICTS_DIR.mkdir(exist_ok=True, parents=True)

OVERLAP_THRESHOLD = 0.50
PARCEL_LAYER = "lt_c_landinfobasemap"
DATA_URL = "https://api.vworld.kr/req/data"
POSS_URL = "https://api.vworld.kr/ned/data/getPossessionAttr"

SIDO_PREFIX = {
    "서울특별시": "11", "부산광역시": "26", "대구광역시": "27", "인천광역시": "28",
    "광주광역시": "29", "대전광역시": "30", "울산광역시": "31", "세종특별자치시": "36",
    "경기도": "41",
    "강원특별자치도": "42", "강원도": "42",
    "충청북도": "43", "충청남도": "44",
    "전북특별자치도": "45", "전라북도": "45", "전라남도": "46",
    "경상북도": "47", "경상남도": "48", "제주특별자치도": "50",
}

log = partial(print, flush=True)
SESSION = requests.Session()


def fetch_features(layer, bbox, max_pages=100):
    minx, miny, maxx, maxy = bbox
    geom = f"BOX({minx},{miny},{maxx},{maxy})"
    out, page = [], 1
    while page <= max_pages:
        params = {
            "key": KEY, "domain": DOMAIN,
            "service": "data", "request": "GetFeature",
            "data": layer, "geomFilter": geom,
            "size": 1000, "page": page,
            "format": "json", "crs": "EPSG:4326",
            "geometry": "true", "attribute": "true",
        }
        try:
            r = SESSION.get(DATA_URL, params=params, timeout=60)
            j = r.json()
        except Exception as e:
            log(f"   ⚠️ {e}"); break
        if j.get("response", {}).get("status") != "OK":
            err = j.get("response", {}).get("error", {}).get("text", "?")
            log(f"   ⚠️ page {page}: {err[:80]}"); break
        feats = j["response"]["result"]["featureCollection"]["features"]
        out.extend(feats)
        total = int(j["response"]["record"].get("total", 0))
        if page % 10 == 0 or len(feats) < 1000:
            log(f"   page {page}: {len(out)}/{total}")
        if len(feats) < 1000 or len(out) >= total:
            break
        page += 1
        time.sleep(0.05)
    return out


def fetch_possession(pnu):
    params = {"key": KEY, "domain": DOMAIN, "pnu": pnu, "format": "json",
              "numOfRows": 5, "pageNo": 1}
    try:
        r = SESSION.get(POSS_URL, params=params, timeout=15)
        return (r.json().get("possessions") or {}).get("field", [])
    except Exception:
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sidos", nargs="+", required=True, help="Target 시·도 names")
    ap.add_argument("--force", action="store_true", help="Delete existing checkpoints first")
    args = ap.parse_args()

    target_prefixes = set()
    for s in args.sidos:
        if s not in SIDO_PREFIX:
            sys.exit(f"❌ unknown sido: {s}")
        target_prefixes.add(SIDO_PREFIX[s])
    log(f"🎯 Target 시·도: {', '.join(args.sidos)} (prefixes={sorted(target_prefixes)})")

    # Load admin districts
    admin_path = OUT / "korea_districts.geojson"
    if not admin_path.exists():
        sys.exit(f"❌ missing {admin_path}")
    admin = json.loads(admin_path.read_text())["features"]
    target_districts = []
    for f in admin:
        p = f["properties"]
        cd = p.get("sig_cd") or p.get("sigungu_cd") or ""
        nm = p.get("sig_kor_nm") or p.get("sig_nm") or p.get("sigungu_nm") or "?"
        if cd[:2] in target_prefixes:
            target_districts.append((nm, cd, f))
    log(f"   {len(target_districts)} target districts\n")

    # Force-delete existing checkpoints for target districts
    if args.force:
        n = 0
        for nm, cd, _ in target_districts:
            for cand in [DISTRICTS_DIR/f"{nm}_{cd}.geojson", DISTRICTS_DIR/f"{nm}.geojson"]:
                if cand.exists():
                    cand.unlink()
                    n += 1
        log(f"🗑️  deleted {n} stale checkpoints\n")

    # Load parks + build STRtree
    log("🌳 Building STRtree for parks...")
    parks_raw = json.loads((OUT/"korea_parks.geojson").read_text())["features"]
    park_geoms, park_props, park_bounds = [], [], []
    for f in parks_raw:
        try:
            g = shape(f["geometry"])
            if not g.is_valid: g = g.buffer(0)
            park_geoms.append(g); park_props.append(f["properties"])
            park_bounds.append(g.bounds)
        except Exception:
            continue
    park_tree = STRtree(park_geoms)
    log(f"   {len(park_geoms)} parks indexed\n")

    # Crawl each target district
    log(f"3️⃣  Processing {len(target_districts)} districts...\n")
    for di, (nm, cd, feat) in enumerate(target_districts, 1):
        ckpt = DISTRICTS_DIR / f"{nm}_{cd}.geojson"
        if ckpt.exists():
            log(f"[{di}/{len(target_districts)}] {nm}({cd}) — cached")
            continue
        try:
            g = shape(feat["geometry"])
            if not g.is_valid: g = g.buffer(0)
            bbox = g.bounds
        except Exception as e:
            log(f"[{di}/{len(target_districts)}] {nm}({cd}) — bbox fail: {e}")
            continue

        log(f"\n[{di}/{len(target_districts)}] {nm}({cd}) bbox={bbox}")
        t0 = time.time()
        parcels = fetch_features(PARCEL_LAYER, bbox, max_pages=100)
        log(f"   parcels: {len(parcels)} ({time.time()-t0:.1f}s)")

        n_matched = 0
        district_matched = []
        t1 = time.time()
        for pf in parcels:
            pnu = pf["properties"].get("pnu")
            if not pnu: continue
            try:
                pg = shape(pf["geometry"])
                if not pg.is_valid: pg = pg.buffer(0)
            except Exception:
                continue
            pg_bounds = pg.bounds; pg_area = pg.area
            cand_idx = park_tree.query(pg)
            best_overlap = 0.0; best_idx = -1
            for idx in cand_idx:
                gb = park_bounds[idx]
                if pg_bounds[2] < gb[0] or pg_bounds[0] > gb[2] \
                   or pg_bounds[3] < gb[1] or pg_bounds[1] > gb[3]:
                    continue
                park_g = park_geoms[idx]
                if not pg.intersects(park_g): continue
                inter = pg.intersection(park_g)
                ov = inter.area / pg_area
                if ov > best_overlap: best_overlap = ov; best_idx = idx
            if best_overlap >= OVERLAP_THRESHOLD and best_idx >= 0:
                pp = park_props[best_idx]
                pf["properties"]["matched_park_name"] = pp.get("dgm_nm","")
                pf["properties"]["matched_park_type"] = pp.get("lcl_nam","")
                pf["properties"]["match_overlap_pct"] = round(best_overlap*100, 1)
                district_matched.append(pf)
                n_matched += 1
        log(f"   matched: {n_matched}  spatial: {time.time()-t1:.1f}s")
        ckpt.write_text(json.dumps(
            {"type":"FeatureCollection","features":district_matched}, ensure_ascii=False))

    # Smart merge: keep existing enriched parcels from non-target sidos,
    # replace target-sido parcels with freshly crawled checkpoints (no owner yet).
    log("\n🔀 Merging: keep existing non-target + replace target sidos from checkpoints")
    out_path = OUT / "korea_park_parcels_all.geojson"
    existing = []
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text())["features"]
        except Exception as e:
            log(f"   ⚠️ failed to load existing: {e}")
    log(f"   existing: {len(existing)} parcels")

    # Keep only non-target sido parcels from existing (they retain owner_type)
    kept = []
    for f in existing:
        pnu = f["properties"].get("pnu", "")
        # sig_cd is first 5 of pnu; sido prefix is first 2
        if pnu[:2] not in target_prefixes:
            kept.append(f)
    log(f"   kept (non-target): {len(kept)}")

    # Add fresh target-sido parcels from checkpoints
    fresh = []
    fresh_by_pnu = {}
    for nm, cd, _ in target_districts:
        ckpt = DISTRICTS_DIR / f"{nm}_{cd}.geojson"
        if not ckpt.exists(): continue
        try:
            for f in json.loads(ckpt.read_text())["features"]:
                pnu = f["properties"].get("pnu")
                if pnu and pnu not in fresh_by_pnu:
                    fresh_by_pnu[pnu] = f
                    fresh.append(f)
        except Exception as e:
            log(f"   ⚠️ {ckpt.name}: {e}")
    log(f"   fresh (target): {len(fresh)} from {len(target_districts)} districts")

    # Owner query only for fresh parcels (they have no owner_type yet)
    log(f"\n4️⃣  Owner query: {len(fresh)} target-sido parcels")
    t0 = time.time()
    for i, f in enumerate(fresh, 1):
        pnu = f["properties"]["pnu"]
        fields = fetch_possession(pnu)
        if fields:
            row = fields[0]
            f["properties"]["owner_type"] = row.get("posesnSeCodeNm", "")
            f["properties"]["owner_subtype"] = row.get("nationInsttSeCodeNm", "")
            f["properties"]["area_m2"] = row.get("lndpclAr", "")
            f["properties"]["price_per_m2"] = row.get("pblntfPclnd", "")
        if i % 100 == 0:
            elapsed = time.time() - t0
            rate = i/elapsed if elapsed>0 else 0
            eta = (len(fresh) - i)/rate if rate>0 else 0
            log(f"   {i}/{len(fresh)}  rate={rate:.1f}/s  eta={eta/60:.1f}min")
        time.sleep(0.03)
    enriched_fresh = [f for f in fresh if f["properties"].get("owner_type")]
    log(f"✅ enriched fresh: {len(enriched_fresh)} / {len(fresh)}")

    merged = kept + enriched_fresh
    log(f"\n📦 merged total: {len(merged)} = {len(kept)} kept + {len(enriched_fresh)} fresh")

    out_path.write_text(json.dumps(
        {"type":"FeatureCollection","features":merged}, ensure_ascii=False))
    log(f"💾 {out_path.name} ({out_path.stat().st_size//1024//1024} MB)")


if __name__ == "__main__":
    main()
