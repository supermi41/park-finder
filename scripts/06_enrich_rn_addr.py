#!/usr/bin/env python3
"""
Stage 6 — Fill in missing 도로명주소 via V-World reverse geocoder.

For each parcel without rn_nm, take polygon centroid and query
https://api.vworld.kr/req/address?service=address&request=getAddress&type=road
to get the road-name address. Save in-place to seoul_park_parcels_all.geojson,
checkpoint progress every 500 parcels.
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

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
KEY = os.environ.get("VWORLD_API_KEY")
DOMAIN = "localhost:3000"

if not KEY or KEY.startswith("your-"):
    sys.exit("❌ VWORLD_API_KEY not set")

SEOUL = ROOT / "data" / "seoul"
INPUT = SEOUL / "seoul_park_parcels_all.geojson"
CHECKPOINT = SEOUL / "rn_addr_cache.json"

ADDR_URL = "https://api.vworld.kr/req/address"
log = partial(print, flush=True)

SESSION = requests.Session()


def get_road_address(lon, lat):
    # type=road → 도로명 우선. NOT_FOUND이면 None (그 좌표는 도로명주소 없음)
    params = {
        "service": "address", "request": "getAddress",
        "version": "2.0", "crs": "epsg:4326",
        "type": "road",
        "point": f"{lon},{lat}",
        "format": "json", "errorformat": "json",
        "key": KEY, "domain": DOMAIN,
    }
    try:
        r = SESSION.get(ADDR_URL, params=params, timeout=15)
        j = r.json()
        if j.get("response", {}).get("status") != "OK":
            return None
        results = j["response"].get("result", [])
        if not results:
            return None
        r0 = results[0]
        structure = r0.get("structure", {})
        return {
            "rn_nm": structure.get("level4L", ""),       # 도로명
            "rn_full": r0.get("text", ""),               # 전체 도로명주소
            "bld_mnnm": structure.get("level5", ""),     # 건물 본번
            "bld_slno": structure.get("detail", ""),     # 부번/상세
        }
    except Exception:
        return None


def main():
    log(f"📦 Loading {INPUT.name}...")
    data = json.loads(INPUT.read_text())
    feats = data["features"]
    log(f"   {len(feats)} parcels total")

    # Resume cache
    cache = {}
    if CHECKPOINT.exists():
        cache = json.loads(CHECKPOINT.read_text())
        log(f"   resume cache: {len(cache)} entries")

    # Targets: parcels that don't have rn_nm
    targets = []
    for f in feats:
        p = f["properties"]
        rn = p.get("rn_nm", "").strip()
        if not rn:
            pnu = p.get("pnu")
            if pnu and pnu not in cache:
                targets.append(f)

    log(f"   missing rn_nm + not cached: {len(targets)}")
    if not targets:
        log("✅ nothing to do")
        return

    # Process
    t0 = time.time()
    done = 0
    for i, f in enumerate(targets, 1):
        pnu = f["properties"]["pnu"]
        try:
            g = shape(f["geometry"])
            c = g.centroid
            lon, lat = c.x, c.y
        except Exception:
            cache[pnu] = {}
            continue
        addr = get_road_address(lon, lat)
        cache[pnu] = addr or {}
        done += 1
        time.sleep(0.04)

        if i % 500 == 0:
            elapsed = time.time() - t0
            rate = i / elapsed
            eta = (len(targets) - i) / rate
            log(f"   {i}/{len(targets)} rate={rate:.1f}/s eta={eta/60:.1f}min")
            CHECKPOINT.write_text(json.dumps(cache, ensure_ascii=False))
    CHECKPOINT.write_text(json.dumps(cache, ensure_ascii=False))
    log(f"\n✅ queried {done} parcels  ({time.time()-t0:.0f}s)")

    # Merge cache into features
    log("\n🔀 Merging back into features...")
    filled = 0
    for f in feats:
        pnu = f["properties"].get("pnu")
        if not pnu: continue
        if pnu in cache and cache[pnu]:
            entry = cache[pnu]
            if entry.get("rn_nm") and not f["properties"].get("rn_nm"):
                f["properties"]["rn_nm"] = entry.get("rn_nm", "")
                f["properties"]["bld_mnnm"] = entry.get("bld_mnnm", "")
                f["properties"]["bld_slno"] = entry.get("bld_slno", "")
                f["properties"]["rn_full"] = entry.get("rn_full", "")
                filled += 1
    log(f"   filled rn_nm for: {filled} parcels")

    # Save back
    INPUT.write_text(json.dumps(data, ensure_ascii=False))
    log(f"   💾 {INPUT.name} updated")


if __name__ == "__main__":
    main()
