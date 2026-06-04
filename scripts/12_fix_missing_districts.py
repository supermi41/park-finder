#!/usr/bin/env python3
"""
Stage 12 — Fix 22 districts skipped due to name-collision bug.
Re-fetch districts with checkpoint filename pattern: {sig_cd}_{name}.geojson
Then merge into korea_park_parcels_all.geojson.
"""

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

OUT = ROOT / "data" / "korea"
DISTRICTS_DIR = OUT / "districts"

OVERLAP_THRESHOLD = 0.50
PARCEL_LAYER = "lt_c_landinfobasemap"

DATA_URL = "https://api.vworld.kr/req/data"
POSS_URL = "https://api.vworld.kr/ned/data/getPossessionAttr"

log = partial(print, flush=True)
SESSION = requests.Session()


def fetch_features(layer, bbox, max_pages=200):
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
    log("🔧 누락된 22구 보강\n")

    # Load admin districts
    admin = json.loads((OUT / "korea_districts.geojson").read_text())
    by_name = {}
    for f in admin["features"]:
        p = f["properties"]
        cd = p.get("sig_cd") or p.get("sigungu_cd") or ""
        nm = (p.get("sig_kor_nm") or p.get("sig_nm")
              or p.get("sigungu_nm") or "?")
        by_name.setdefault(nm, []).append((cd, f))

    # Find collisions — first occurrence is already saved as "{name}.geojson"
    # Remaining occurrences are the missing ones
    missing = []
    for nm, lst in by_name.items():
        if len(lst) > 1:
            for cd, feat in lst[1:]:  # skip first
                missing.append((nm, cd, feat))
    log(f"누락 자치구: {len(missing)}개\n")

    # Load park geoms with STRtree
    log("STRtree 빌드...")
    parks_raw = json.loads((OUT / "korea_parks.geojson").read_text())["features"]
    park_geoms = []
    park_props = []
    park_bounds = []
    for f in parks_raw:
        try:
            g = shape(f["geometry"])
            if not g.is_valid:
                g = g.buffer(0)
            park_geoms.append(g)
            park_props.append(f["properties"])
            park_bounds.append(g.bounds)
        except Exception:
            continue
    park_tree = STRtree(park_geoms)
    log(f"  {len(park_geoms)} parks indexed\n")

    # Process each missing district
    all_matched = {}
    for di, (nm, cd, feat) in enumerate(missing, 1):
        # Use sig_cd in checkpoint filename
        ckpt = DISTRICTS_DIR / f"{nm}_{cd}.geojson"
        if ckpt.exists():
            log(f"[{di}/{len(missing)}] {nm}({cd}) — already done")
            cached = json.loads(ckpt.read_text())["features"]
            for f in cached:
                pnu = f["properties"].get("pnu")
                if pnu:
                    all_matched[pnu] = f
            continue

        try:
            g = shape(feat["geometry"])
            if not g.is_valid:
                g = g.buffer(0)
            minx, miny, maxx, maxy = g.bounds
            bbox = (minx, miny, maxx, maxy)
        except Exception as e:
            log(f"[{di}/{len(missing)}] {nm}({cd}) — bbox 실패: {e}")
            continue

        log(f"\n[{di}/{len(missing)}] {nm}({cd}) bbox={bbox}")
        t0 = time.time()
        parcels = fetch_features(PARCEL_LAYER, bbox, max_pages=100)
        log(f"   parcels: {len(parcels)} ({time.time()-t0:.1f}s)")

        n_matched = 0
        district_matched = []
        t1 = time.time()
        for pf in parcels:
            pnu = pf["properties"].get("pnu")
            if not pnu:
                continue
            try:
                pg = shape(pf["geometry"])
                if not pg.is_valid:
                    pg = pg.buffer(0)
            except Exception:
                continue
            pg_bounds = pg.bounds
            pg_area = pg.area
            cand_idx = park_tree.query(pg)
            best_overlap = 0.0
            best_idx = -1
            for idx in cand_idx:
                gb = park_bounds[idx]
                if pg_bounds[2] < gb[0] or pg_bounds[0] > gb[2] \
                   or pg_bounds[3] < gb[1] or pg_bounds[1] > gb[3]:
                    continue
                park_g = park_geoms[idx]
                if not pg.intersects(park_g):
                    continue
                inter = pg.intersection(park_g)
                ov = inter.area / pg_area
                if ov > best_overlap:
                    best_overlap = ov
                    best_idx = idx
            if best_overlap >= OVERLAP_THRESHOLD and best_idx >= 0:
                pp = park_props[best_idx]
                pf["properties"]["matched_park_name"] = pp.get("dgm_nm", "")
                pf["properties"]["matched_park_type"] = pp.get("lcl_nam", "")
                pf["properties"]["match_overlap_pct"] = round(best_overlap * 100, 1)
                all_matched[pnu] = pf
                district_matched.append(pf)
                n_matched += 1
        log(f"   matched: {n_matched}  spatial: {time.time()-t1:.1f}s")
        ckpt.write_text(json.dumps(
            {"type": "FeatureCollection", "features": district_matched},
            ensure_ascii=False))
        log(f"   💾 {ckpt.name}")

    log(f"\n✅ 신규 매칭 필지: {len(all_matched)}")

    # Query ownership
    log(f"\n4️⃣  소유주 조회 ({len(all_matched)}건)")
    matched_list = list(all_matched.values())
    enriched = []
    t0 = time.time()
    for i, f in enumerate(matched_list, 1):
        pnu = f["properties"]["pnu"]
        fields = fetch_possession(pnu)
        if fields:
            row = fields[0]
            f["properties"]["owner_type"] = row.get("posesnSeCodeNm", "")
            f["properties"]["owner_subtype"] = row.get("nationInsttSeCodeNm", "")
            f["properties"]["area_m2"] = row.get("lndpclAr", "")
            f["properties"]["price_per_m2"] = row.get("pblntfPclnd", "")
            enriched.append(f)
        if i % 100 == 0:
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed > 0 else 0
            eta = (len(matched_list) - i) / rate if rate > 0 else 0
            log(f"   {i}/{len(matched_list)}  rate={rate:.1f}/s  eta={eta/60:.1f}min")
        time.sleep(0.03)
    log(f"✅ enriched: {len(enriched)}\n")

    # Merge into existing korea file
    log("🔀 기존 korea_park_parcels_all.geojson에 병합")
    main_path = OUT / "korea_park_parcels_all.geojson"
    main = json.loads(main_path.read_text())
    existing_pnus = {f["properties"].get("pnu") for f in main["features"]}
    added = 0
    for f in enriched:
        pnu = f["properties"].get("pnu")
        if pnu and pnu not in existing_pnus:
            main["features"].append(f)
            added += 1
    log(f"   기존: {len(main['features']) - added}건")
    log(f"   신규: {added}건")
    log(f"   총: {len(main['features'])}건")
    main_path.write_text(json.dumps(main, ensure_ascii=False))
    log(f"💾 {main_path.name} 업데이트 완료")


if __name__ == "__main__":
    main()
