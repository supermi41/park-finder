#!/usr/bin/env python3
"""
Stage 5 — Build Seoul-wide interactive map.

Output:
  ./map.html                 (UI shell, ~50KB)
  ./public/parks.json        (simplified park polygons)
  ./public/parcels.json      (simplified parcels with owner info)
  ./public/districts.json    (자치구 boundaries)
  ./public/stats.json        (precomputed stats)

The HTML uses fetch() to lazy-load the data files, so the file itself stays small.
"""

import json
from pathlib import Path
from collections import Counter

from shapely.geometry import shape, mapping

ROOT = Path(__file__).resolve().parent.parent
SEOUL = ROOT / "data" / "korea"
PUB = ROOT / "public"
PUB.mkdir(exist_ok=True)
OUT_HTML = ROOT / "map.html"

PYEONG = 3.3058
OWNER_ORDER = ["개인", "법인", "시 도유지", "군유지", "국유지",
               "종교단체", "종중", "기타단체", "외국인 외국공공기관", "일본인 창씨명등"]
COLORS = {
    "개인": "#e63946", "법인": "#f4a261", "국유지": "#264653",
    "시 도유지": "#2a9d8f", "군유지": "#588157", "종교단체": "#9b5de5",
    "종중": "#b6ad90", "기타단체": "#6c757d", "외국인 외국공공기관": "#000000",
    "일본인 창씨명등": "#d62828", "?": "#aaaaaa",
}
PARK_CATS = ["공원", "녹지", "광장", "유원지"]
PARK_COLORS = {"공원": "#a8dadc", "녹지": "#b7e4c7", "광장": "#fee08b", "유원지": "#cbb9ff"}
JIMOK_GROUPS = {
    "자연/녹지": ["임야", "전", "답", "유지", "구거", "하천", "제방"],
    "공원/잡종": ["공원", "잡종지"],
    "건물용지": ["대"],
    "도로/시설": ["도로", "주차장", "철도용지", "수도용지"],
    "공공/기타": ["종교용지", "학교용지"],
}
JIMOK_GROUP_COLORS = {"자연/녹지":"#588157","공원/잡종":"#2a9d8f","건물용지":"#e63946",
                      "도로/시설":"#6c757d","공공/기타":"#9b5de5"}


def simplify_features(features, tolerance):
    """Simplify geometry with Douglas-Peucker. tolerance in degrees (~111km/deg)."""
    out = []
    skipped = 0
    for f in features:
        try:
            g = shape(f["geometry"])
            if not g.is_valid:
                g = g.buffer(0)
            simp = g.simplify(tolerance, preserve_topology=True)
            if simp.is_empty:
                simp = g  # fallback
            f["geometry"] = mapping(simp)
            out.append(f)
        except Exception:
            skipped += 1
    if skipped:
        print(f"  simplify skipped {skipped}")
    return out


def main():
    print("📦 Loading raw data...")
    parks_raw = json.loads((SEOUL / "korea_parks.geojson").read_text())["features"]
    parcels_raw = json.loads((SEOUL / "korea_park_parcels_all.geojson").read_text())["features"]
    districts_raw = json.loads((SEOUL / "korea_districts.geojson").read_text())["features"]
    print(f"  parks: {len(parks_raw)}, parcels: {len(parcels_raw)}, districts: {len(districts_raw)}")

    # Categorize parks + extract decision date from ntfc_sn
    import re
    NTFC_RE = re.compile(r'\d{5}NTC(\d{8})')
    for pf in parks_raw:
        lcl = pf["properties"].get("lcl_nam", "")
        cat = "기타"
        for c in PARK_CATS:
            if c in lcl:
                cat = c; break
        pf["properties"]["park_cat"] = cat
        ntfc = pf["properties"].get("ntfc_sn", "") or ""
        m = NTFC_RE.match(ntfc)
        ntfc_date = ""; ntfc_year = 0
        if m:
            ymd = m.group(1)
            yy = int(ymd[:4])
            if 1950 <= yy <= 2030:
                ntfc_date = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}"
                ntfc_year = yy
        pf["properties"]["ntfc_date"] = ntfc_date
        pf["properties"]["ntfc_year"] = ntfc_year

    # Filter parks to only those with valid geometry; trim properties
    print("✂️  Simplifying parks (tolerance ~3m)...")
    parks_keep = []
    for pf in parks_raw:
        props = pf["properties"]
        slim = {
            "dgm_nm": props.get("dgm_nm", ""),
            "lcl_nam": props.get("lcl_nam", ""),
            "park_cat": props.get("park_cat", "기타"),
            "ntfc_date": props.get("ntfc_date", ""),
            "ntfc_year": props.get("ntfc_year", 0),
        }
        parks_keep.append({"type": "Feature", "geometry": pf["geometry"], "properties": slim})
    parks_keep = simplify_features(parks_keep, tolerance=0.00003)
    print(f"  kept {len(parks_keep)} parks")

    # Compute per-park matched count
    print("🔗 Computing matched parcel counts per park...")
    pname_count = Counter()
    for f in parcels_raw:
        pname_count[f["properties"].get("matched_park_name", "")] += 1
    for pf in parks_keep:
        n = pname_count.get(pf["properties"]["dgm_nm"], 0)
        pf["properties"]["matched_count"] = n

    # Build map from park name → ntfc_year for parcel lookup
    park_year_map = {pf["properties"]["dgm_nm"]: pf["properties"].get("ntfc_year", 0)
                     for pf in parks_raw if pf["properties"].get("dgm_nm")}

    # Simplify parcels — keep small but tag properties
    print("✂️  Simplifying parcels (tolerance ~1m)...")
    parcels_keep = []
    for f in parcels_raw:
        p = f["properties"]
        pyear = park_year_map.get(p.get("matched_park_name", ""), 0)
        slim = {
            "park_decision_year": pyear,
            "pnu": p.get("pnu", ""),
            "sido_nm": p.get("sido_nm", ""),
            "sgg_nm": p.get("sgg_nm", ""),
            "emd_nm": p.get("emd_nm", ""),
            "jibun": p.get("jibun", ""),
            "jimok": p.get("jimok", ""),
            "parea": p.get("parea", ""),
            "rn_nm": p.get("rn_nm", ""),
            "bld_mnnm": p.get("bld_mnnm", ""),
            "owner_type": p.get("owner_type", "?"),
            "owner_subtype": p.get("owner_subtype", ""),
            "area_m2": p.get("area_m2", ""),
            "price_per_m2": p.get("price_per_m2", ""),
            "matched_park_name": p.get("matched_park_name", ""),
            "matched_park_type": p.get("matched_park_type", ""),
            "match_overlap_pct": p.get("match_overlap_pct", 0),
        }
        parcels_keep.append({"type": "Feature", "geometry": f["geometry"], "properties": slim})
    parcels_keep = simplify_features(parcels_keep, tolerance=0.00001)
    print(f"  kept {len(parcels_keep)} parcels")

    # Slim districts (just boundary + name)
    districts_keep = []
    for d in districts_raw:
        p = d["properties"]
        slim = {
            "sig_cd": p.get("sig_cd") or p.get("sigungu_cd") or "",
            "sig_nm": (p.get("sig_kor_nm") or p.get("sig_nm")
                       or p.get("sigungu_nm") or "?"),
        }
        districts_keep.append({"type": "Feature", "geometry": d["geometry"], "properties": slim})
    districts_keep = simplify_features(districts_keep, tolerance=0.0001)

    # Stats
    print("📊 Computing stats...")
    owner_counts = Counter()
    jimok_counts = Counter()
    sgg_counts = Counter()
    sgg_private = Counter()
    park_type_counts = Counter()
    for f in parcels_keep:
        p = f["properties"]
        ot = p.get("owner_type", "?")
        owner_counts[ot] += 1
        jimok_counts[p.get("jimok", "?")] += 1
        sgg = p.get("sgg_nm", "?")
        sgg_counts[sgg] += 1
        if ot in ("개인", "법인"):
            sgg_private[sgg] += 1
    for pf in parks_keep:
        park_type_counts[pf["properties"]["park_cat"]] += 1

    total = sum(owner_counts.values())
    private_total = owner_counts.get("개인", 0) + owner_counts.get("법인", 0)

    stats = {
        "total_parcels": total,
        "private_total": private_total,
        "private_pct": round(private_total / total * 100, 1) if total else 0,
        "owner_counts": dict(owner_counts),
        "jimok_counts": dict(jimok_counts),
        "park_type_counts": dict(park_type_counts),
        "sgg_counts": dict(sgg_counts),
        "sgg_private": dict(sgg_private),
    }

    # Write data files
    print("💾 Writing data files...")
    (PUB / "parks.json").write_text(json.dumps(
        {"type": "FeatureCollection", "features": parks_keep}, ensure_ascii=False))
    (PUB / "parcels.json").write_text(json.dumps(
        {"type": "FeatureCollection", "features": parcels_keep}, ensure_ascii=False))
    (PUB / "districts.json").write_text(json.dumps(
        {"type": "FeatureCollection", "features": districts_keep}, ensure_ascii=False))
    (PUB / "stats.json").write_text(json.dumps(stats, ensure_ascii=False))

    for name in ["parks", "parcels", "districts", "stats"]:
        size = (PUB / f"{name}.json").stat().st_size
        print(f"  public/{name}.json: {size//1024:,} KB")

    # Build HTML shell
    print("🎨 Building map.html...")
    html = HTML_TEMPLATE
    html = html.replace("__TOTAL__", f"{total:,}")
    html = html.replace("__PRIVATE__", f"{private_total:,}")
    html = html.replace("__PCT__", str(stats["private_pct"]))
    html = html.replace("__OWNER_ORDER__", json.dumps(OWNER_ORDER, ensure_ascii=False))
    html = html.replace("__COLORS__", json.dumps(COLORS, ensure_ascii=False))
    html = html.replace("__PARK_CATS__", json.dumps(PARK_CATS, ensure_ascii=False))
    html = html.replace("__PARK_COLORS__", json.dumps(PARK_COLORS, ensure_ascii=False))
    html = html.replace("__JIMOK_GROUPS__", json.dumps(JIMOK_GROUPS, ensure_ascii=False))
    html = html.replace("__JIMOK_GROUP_COLORS__", json.dumps(JIMOK_GROUP_COLORS, ensure_ascii=False))
    html = html.replace("__STATS__", json.dumps(stats, ensure_ascii=False))

    OUT_HTML.write_text(html, encoding="utf-8")
    size_kb = OUT_HTML.stat().st_size // 1024
    print(f"  map.html: {size_kb} KB")

    print(f"\n✅ Done. Serve from {ROOT}")


HTML_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>핀파인더 · 서울시 공원지정 사유지</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
  * { box-sizing: border-box; }
  body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Segoe UI",sans-serif;
         color:#1d1d1f; background:#f6f6f8; overflow:hidden; }
  header { display:flex; align-items:center; justify-content:space-between;
           padding:10px 18px; background:#fff; border-bottom:1px solid #e5e5ea;
           height:48px; flex-shrink:0; }
  header .brand { display:flex; gap:10px; align-items:center; }
  header h1 { margin:0; font-size:15px; font-weight:700; }
  header .sub { font-size:11px; color:#86868b; margin-left:8px; }
  .tabs { display:flex; gap:4px; }
  .tab { padding:6px 14px; border:none; background:#f0f0f3; border-radius:8px;
         font-size:13px; cursor:pointer; color:#666; font-weight:500; }
  .tab.active { background:#1d1d1f; color:#fff; }

  .layout { display:flex; height:calc(100vh - 48px); width:100vw; }
  .sidebar { width: 250px; background:#fff; border-right:1px solid #e5e5ea;
             overflow-y:auto; padding:14px; flex-shrink:0; }
  .main-wrap { flex:1; display:flex; min-width:0; }
  .map-wrap { flex:1; position:relative; min-width:0; }
  #map { width:100%; height:100%; }
  .right-panel { width: 420px; background:#fff; border-left:1px solid #e5e5ea;
                 display:none; flex-direction:column; flex-shrink:0; }
  .right-panel.open { display:flex; }
  .right-panel.expanded { width:100%; flex:1; }
  .map-wrap.hidden { display:none; }

  .stat-card { background:linear-gradient(135deg,#fff5f5,#fde8e8); padding:13px;
               border-radius:10px; border:1px solid #fad1d1; margin-bottom:14px; }
  .stat-card .big { font-size:28px; font-weight:700; color:#e63946; line-height:1; }
  .stat-card .label { font-size:11px; color:#666; margin-top:6px; }

  h2 { font-size:11px; font-weight:600; color:#86868b; margin:14px 0 6px 0;
       text-transform:uppercase; letter-spacing:0.5px; display:flex;
       align-items:center; gap:8px; }
  .filter-row { display:flex; align-items:center; gap:8px; padding:4px 4px;
                font-size:13px; cursor:pointer; user-select:none; border-radius:5px; }
  .filter-row:hover { background:#f6f6f8; }
  .chip { width:12px; height:12px; border-radius:3px; flex-shrink:0; }
  .chip.dashed { background:transparent !important; border:1.5px dashed #999; }
  .filter-row .count { margin-left:auto; color:#86868b; font-size:11px; font-weight:500; }
  .toggle-all { font-size:11px; color:#0071e3; cursor:pointer; user-select:none; font-weight:500; }

  .loading { position:absolute; inset:0; display:flex; align-items:center;
             justify-content:center; background:rgba(255,255,255,0.85); z-index:1000;
             font-size:13px; color:#444; flex-direction:column; gap:10px; }
  .loading .spinner { width:32px; height:32px; border:3px solid #e5e5ea;
                      border-top-color:#0071e3; border-radius:50%; animation:spin 0.8s linear infinite; }
  @keyframes spin { to { transform:rotate(360deg); } }

  .toolbar { padding:10px 12px; background:#fafafc; border-bottom:1px solid #e5e5ea;
             display:flex; gap:8px; align-items:center; flex-shrink:0; }
  .toolbar input { flex:1; padding:6px 10px; font-size:13px; border:1px solid #d0d0d5;
                   border-radius:6px; outline:none; }
  .toolbar input:focus { border-color:#0071e3; }
  .toolbar .icon-btn { padding:6px 10px; background:#f0f0f3; color:#333;
                       border:none; border-radius:6px; font-size:12px; cursor:pointer;
                       font-weight:500; }
  .toolbar .icon-btn:hover { background:#e6e6ea; }
  .toolbar .icon-btn.primary { background:#0071e3; color:#fff; }
  .toolbar .info { font-size:11px; color:#86868b; }

  .compact-list { flex:1; overflow:auto; }
  .group-header { position:sticky; top:0; z-index:5;
                  background:linear-gradient(180deg,#fff,#f8f8fc);
                  padding:10px 14px 8px; border-bottom:1px solid #e5e5ea;
                  font-size:12px; font-weight:700; color:#1d1d1f;
                  display:flex; align-items:center; gap:8px; cursor:pointer; user-select:none; }
  .group-header .caret { font-size:10px; color:#888; transition:transform 0.15s; }
  .group-header.collapsed .caret { transform:rotate(-90deg); }
  .group-header .count { margin-left:auto; font-size:11px; color:#86868b; font-weight:500; }
  .group-body.collapsed { display:none; }
  .pcard { padding:10px 14px; border-bottom:1px solid #f0f0f3; cursor:pointer;
           display:flex; gap:10px; align-items:flex-start; }
  .pcard:hover { background:#fafafd; }
  .pcard .num { font-size:11px; color:#999; font-weight:600; min-width:36px; text-align:right; }
  .pcard .body { flex:1; min-width:0; }
  .pcard .head { display:flex; align-items:center; gap:6px; font-size:13px;
                 font-weight:600; margin-bottom:3px; flex-wrap:wrap; }
  .pcard .addr { font-size:11px; color:#86868b; margin-bottom:3px; }
  .pcard .meta { font-size:11.5px; color:#666; line-height:1.45; }
  .pcard .meta b { color:#333; font-weight:500; }
  .pill { display:inline-block; padding:1px 7px; border-radius:9px;
          font-size:10px; font-weight:600; color:#fff; }
  tr.group-row td { background:linear-gradient(180deg,#f0f5fa,#e7eef5);
                    font-weight:700; font-size:12px; padding:8px 10px;
                    color:#1d1d1f; cursor:pointer; }
  tr.group-row td .count { float:right; color:#666; font-weight:500; }
  .expanded-table { display:none; flex:1; min-height:0; }
  .right-panel.expanded .compact-list { display:none; }
  .right-panel.expanded .expanded-table { display:flex; flex-direction:column; }
  #scrollArea { flex:1; min-height:0; overflow:auto; }
  table { border-collapse:collapse; width:100%; font-size:12px; }
  thead { position:sticky; top:0; z-index:5; background:#f8f8fa; }
  th, td { padding:8px 10px; text-align:left; border-bottom:1px solid #ececef;
           white-space:nowrap; overflow:hidden; text-overflow:ellipsis; vertical-align:top; }
  th { font-weight:600; color:#555; font-size:11px; text-transform:uppercase;
       letter-spacing:0.5px; cursor:pointer; user-select:none; }
  th:hover { background:#eef; }
  th.sorted::after { content:'↑'; margin-left:4px; color:#888; }
  th.sorted.desc::after { content:'↓'; }
  tbody tr { cursor:pointer; }
  tbody tr:hover { background:#fafafd; }
  .right { text-align:right; }
  .leaflet-popup-content { font-size:12px; line-height:1.5; min-width:220px; }
  .leaflet-popup-content b { color:#1d1d1f; }
</style>
</head>
<body>
<header>
  <div class="brand">
    <span style="font-size:18px;">📍</span>
    <h1>핀파인더 · 서울시 전체</h1>
    <span class="sub">공원지정 필지 · 출처 V-World</span>
  </div>
  <div style="display:flex;gap:8px;align-items:center;">
    <button id="open-howto" class="tab" style="background:#f0fbf2;color:#2f8a3a;font-weight:600;">💡 사용법</button>
    <button id="open-methodology" class="tab" style="background:#f4f4f9;color:#0071e3;font-weight:600;">📋 매칭 기준</button>
    <div class="tabs">
      <button class="tab active" data-view="map">지도</button>
      <button class="tab" data-view="list">목록 (__TOTAL__)</button>
    </div>
  </div>
</header>

<div id="methodology-overlay" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:5000;align-items:center;justify-content:center;">
  <div style="background:#fff;width:560px;max-width:92vw;max-height:85vh;overflow:auto;border-radius:14px;box-shadow:0 20px 60px rgba(0,0,0,0.3);">
    <div style="display:flex;justify-content:space-between;align-items:center;padding:18px 22px;border-bottom:1px solid #e5e5ea;">
      <h2 style="margin:0;font-size:16px;font-weight:700;color:#1d1d1f;text-transform:none;letter-spacing:0;">📋 매칭 기준 · 데이터 출처</h2>
      <button id="close-methodology" style="border:none;background:transparent;font-size:20px;cursor:pointer;color:#888;">✕</button>
    </div>
    <div id="methodology-body" style="padding:22px;font-size:13px;line-height:1.7;color:#333;"></div>
  </div>
</div>

<div id="howto-overlay" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:5000;align-items:center;justify-content:center;">
  <div style="background:#fff;width:620px;max-width:92vw;max-height:85vh;overflow:auto;border-radius:14px;box-shadow:0 20px 60px rgba(0,0,0,0.3);">
    <div style="display:flex;justify-content:space-between;align-items:center;padding:18px 22px;border-bottom:1px solid #e5e5ea;">
      <h2 style="margin:0;font-size:16px;font-weight:700;color:#1d1d1f;text-transform:none;letter-spacing:0;">💡 사용법 가이드</h2>
      <button id="close-howto" style="border:none;background:transparent;font-size:20px;cursor:pointer;color:#888;">✕</button>
    </div>
    <div style="padding:22px;font-size:13px;line-height:1.65;color:#333;">
      <div style="background:#fef9e7;padding:14px;border-radius:8px;border:1px solid #f6d860;margin-bottom:20px;font-size:12.5px;">
        🎯 핀파인더 = 도시계획상 공원으로 지정되었지만 소유주가 개인/법인인 필지 매핑
      </div>
      <h3 style="margin:0 0 8px 0;">🔍 추천 사용 흐름</h3>
      <ol style="margin:0 0 16px 18px;padding:0;">
        <li>좌측 사이드바에서 자치구 선택 (특정 구만 보기)</li>
        <li>"지목 그룹"에서 도로/시설, 공공/기타 끄기</li>
        <li>"소유 구분"에서 [사유지만] 클릭</li>
        <li>[목록] 탭 → 우측 패널에서 평수·가격 정렬</li>
        <li>행 클릭 → 지도로 점프</li>
        <li>[CSV] 다운로드해서 엑셀 분석</li>
      </ol>
      <h3 style="margin:0 0 8px 0;">📋 지목별 의미</h3>
      <ul style="margin:0 0 16px 18px;padding:0;font-size:12px;">
        <li><b>자연/녹지</b>(임야·전·답): 정통 장기미집행 케이스</li>
        <li><b>공원/잡종</b>: 사실상 공원으로 쓰이는 사유지</li>
        <li><b>건물용지</b>(대): 알박기 케이스</li>
        <li><b>도로/시설</b>: 대부분 국공유, 흥미도 낮음</li>
      </ul>
    </div>
  </div>
</div>

<div class="layout">
  <aside class="sidebar">
    <div class="stat-card">
      <div class="big">__PCT__%</div>
      <div class="label">서울시 전체 __TOTAL__건 중 사유지(개인+법인) __PRIVATE__건</div>
    </div>

    <h2>
      소유 구분
      <span class="toggle-all" id="toggle-all" style="margin-left:auto;">전체</span>
      <span class="toggle-all" id="only-private">사유지만</span>
    </h2>
    <div id="owner-filters"></div>

    <h2>
      자치구
      <span class="toggle-all" id="sgg-all" style="margin-left:auto;">전체</span>
    </h2>
    <div id="sgg-filters" style="max-height:200px;overflow-y:auto;"></div>

    <h2>공원 시설 유형</h2>
    <div id="park-type-filters"></div>

    <h2>
      지목 그룹
      <span class="toggle-all" id="jimok-all" style="margin-left:auto;">전체</span>
      <span class="toggle-all" id="jimok-natural">자연만</span>
    </h2>
    <div id="jimok-filters"></div>

    <h2>배경 지도</h2>
    <div id="basemap-picker"></div>

    <h2>오버레이</h2>
    <label class="filter-row">
      <input type="checkbox" id="show-districts" checked>
      <span class="chip" style="background:transparent;border:1.5px solid #1d3557;"></span>
      <span>자치구 경계</span>
    </label>
    <label class="filter-row">
      <input type="checkbox" id="show-parks" checked>
      <span class="chip" style="background:#a8dadc;"></span>
      <span>공원/녹지 폴리곤</span>
    </label>
    <label class="filter-row">
      <input type="checkbox" id="show-empty-parks">
      <span class="chip dashed"></span>
      <span>매칭 0건 폴리곤</span>
    </label>
    <label class="filter-row">
      <input type="checkbox" id="show-labels">
      <span class="chip" style="background:transparent;border:1px solid #888;"></span>
      <span>공원 이름 라벨 (줌 14+)</span>
    </label>
    <label class="filter-row">
      <input type="checkbox" id="show-parcels" checked>
      <span class="chip" style="background:linear-gradient(90deg,#e63946,#f4a261);"></span>
      <span>필지 표시</span>
    </label>
  </aside>

  <div class="main-wrap">
    <div class="map-wrap">
      <div id="map"></div>
      <div id="loading" class="loading">
        <div class="spinner"></div>
        <div id="loading-text">데이터 로딩 중...</div>
      </div>
    </div>
    <div class="right-panel" id="right-panel">
      <div class="toolbar">
        <input id="search" placeholder="🔍 동·지번·지목 검색...">
        <button type="button" class="icon-btn" id="expand-btn">⇱ 확장</button>
        <span style="width:1px;height:24px;background:#e5e5ea;margin:0 2px;"></span>
        <button type="button" class="icon-btn primary" onclick="downloadXlsx()">⬇ Excel</button>
        <button type="button" class="icon-btn" onclick="downloadCsv()" style="font-size:11px;">CSV</button>
      </div>
      <div class="toolbar" style="background:#fff;padding:6px 14px;justify-content:space-between;">
        <span class="info" id="row-count"></span>
        <button id="showAllBtn" type="button" style="display:none;padding:4px 10px;background:#1d1d1f;color:#fff;border:none;border-radius:5px;font-size:11px;cursor:pointer;font-weight:600;">전체보기</button>
      </div>
      <div class="compact-list" id="compact-list"></div>
      <div class="expanded-table">
        <div id="scrollArea">
          <table id="table">
            <thead>
              <tr>
                <th style="width:50px;">#</th>
                <th data-sort="emd_jibun" style="width:140px;">동·지번</th>
                <th data-sort="matched_park_name" style="width:160px;">매칭 공원</th>
                <th data-sort="rn_full" style="width:180px;">도로명주소</th>
                <th data-sort="jimok" style="width:60px;">지목</th>
                <th data-sort="area_m2" class="right" style="width:130px;">면적</th>
                <th data-sort="price_per_m2" class="right" style="width:160px;">공시지가</th>
                <th data-sort="owner_type" style="width:90px;">소유구분</th>
                <th data-sort="owner_subtype" style="width:80px;">세부</th>
                <th style="width:130px;">점프</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
          <div id="loadMoreWrap" style="display:none;text-align:center;padding:14px;">
            <button id="loadMoreBtn" type="button" style="padding:8px 20px;background:#0071e3;color:#fff;border:none;border-radius:6px;font-size:13px;cursor:pointer;font-weight:600;">더 보기</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.sheetjs.com/xlsx-0.20.3/package/dist/xlsx.full.min.js"></script>
<script>
const COLORS = __COLORS__;
const ORDER = __OWNER_ORDER__;
const PARK_CATS = __PARK_CATS__;
const PARK_COLORS = __PARK_COLORS__;
const JIMOK_GROUPS = __JIMOK_GROUPS__;
const JIMOK_GROUP_COLORS = __JIMOK_GROUP_COLORS__;
const STATS = __STATS__;
const PYEONG = 3.3058;

let PARKS = null, PARCELS = null, DISTRICTS = null;

const state = {
  activeOwners: new Set(ORDER),
  activeParkTypes: new Set(PARK_CATS),
  activeJimokGroups: new Set(Object.keys(JIMOK_GROUPS)),
  activeSggs: new Set(),
  showParks: true, showEmpty: false, showParcels: true, showDistricts: true, showLabels: false,
  sortKey: null, sortDir: 1, expanded: false,
};
function activeJimokSet() {
  const s = new Set();
  for (const g of state.activeJimokGroups) (JIMOK_GROUPS[g]||[]).forEach(j => s.add(j));
  return s;
}

const map = L.map('map', { preferCanvas: true }).setView([37.55, 126.98], 11);
map.createPane('districts'); map.getPane('districts').style.zIndex = 350;
map.createPane('parks');     map.getPane('parks').style.zIndex = 380;
map.createPane('parcels');   map.getPane('parcels').style.zIndex = 410;
map.createPane('labels');    map.getPane('labels').style.zIndex = 650;
map.getPane('labels').style.pointerEvents = 'none';

const BASEMAPS = {
  light: { name:'라이트', url:'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png',
         attribution:'© CartoDB', maxZoom:19 },
  osm: { name:'OSM', url:'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
         attribution:'© OSM', maxZoom:19 },
  dark: { name:'다크', url:'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
         attribution:'© CartoDB', maxZoom:19 },
  satellite: { name:'위성', url:'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
         attribution:'© Esri', maxZoom:19 },
};
let activeBaseLayer = L.tileLayer(BASEMAPS.light.url, BASEMAPS.light).addTo(map);
let currentBaseKey = 'light';
function switchBasemap(key) {
  if (key === currentBaseKey) return;
  map.removeLayer(activeBaseLayer);
  activeBaseLayer = L.tileLayer(BASEMAPS[key].url, BASEMAPS[key]).addTo(map);
  currentBaseKey = key;
}
const basemapPicker = document.getElementById('basemap-picker');
Object.entries(BASEMAPS).forEach(([key, cfg]) => {
  const div = document.createElement('label');
  div.className = 'filter-row';
  div.innerHTML = `
    <input type="radio" name="basemap" value="${key}" ${key===currentBaseKey?'checked':''}>
    <span>${cfg.name}</span>
  `;
  div.querySelector('input').addEventListener('change', () => switchBasemap(key));
  basemapPicker.appendChild(div);
});

// Filters: owner
const filterPanel = document.getElementById('owner-filters');
ORDER.forEach(ot => {
  const count = STATS.owner_counts[ot] || 0;
  if (count === 0) return;
  const div = document.createElement('label');
  div.className = 'filter-row';
  div.innerHTML = `
    <input type="checkbox" checked data-owner="${ot}">
    <span class="chip" style="background:${COLORS[ot] || '#888'}"></span>
    <span>${ot}</span>
    <span class="count">${count.toLocaleString()}</span>
  `;
  filterPanel.appendChild(div);
});
filterPanel.querySelectorAll('input').forEach(cb => {
  cb.addEventListener('change', () => {
    const ot = cb.dataset.owner;
    if (cb.checked) state.activeOwners.add(ot); else state.activeOwners.delete(ot);
    rebuildParcels(); renderList();
  });
});
document.getElementById('toggle-all').addEventListener('click', () => {
  const allOn = ORDER.every(o => state.activeOwners.has(o));
  if (allOn) {
    state.activeOwners.clear();
    filterPanel.querySelectorAll('input').forEach(cb => cb.checked = false);
  } else {
    state.activeOwners = new Set(ORDER);
    filterPanel.querySelectorAll('input').forEach(cb => cb.checked = true);
  }
  rebuildParcels(); renderList();
});
document.getElementById('only-private').addEventListener('click', () => {
  state.activeOwners = new Set(["개인","법인"]);
  filterPanel.querySelectorAll('input').forEach(cb => {
    cb.checked = state.activeOwners.has(cb.dataset.owner);
  });
  rebuildParcels(); renderList();
});

// SGG filter
const sggPanel = document.getElementById('sgg-filters');
const sggKeys = Object.keys(STATS.sgg_counts).sort();
sggKeys.forEach(sgg => {
  state.activeSggs.add(sgg);
  const total = STATS.sgg_counts[sgg];
  const priv = STATS.sgg_private[sgg] || 0;
  const div = document.createElement('label');
  div.className = 'filter-row';
  div.innerHTML = `
    <input type="checkbox" checked data-sgg="${sgg}">
    <span style="flex:1;">${sgg}</span>
    <span class="count">${priv}/${total}</span>
  `;
  sggPanel.appendChild(div);
});
sggPanel.querySelectorAll('input').forEach(cb => {
  cb.addEventListener('change', () => {
    const s = cb.dataset.sgg;
    if (cb.checked) state.activeSggs.add(s); else state.activeSggs.delete(s);
    rebuildParcels(); renderList();
  });
});
document.getElementById('sgg-all').addEventListener('click', () => {
  const allOn = sggKeys.every(s => state.activeSggs.has(s));
  if (allOn) {
    state.activeSggs.clear();
    sggPanel.querySelectorAll('input').forEach(cb => cb.checked = false);
  } else {
    state.activeSggs = new Set(sggKeys);
    sggPanel.querySelectorAll('input').forEach(cb => cb.checked = true);
  }
  rebuildParcels(); renderList();
});

// Park type filter
const ptPanel = document.getElementById('park-type-filters');
PARK_CATS.forEach(c => {
  const count = STATS.park_type_counts[c] || 0;
  if (count === 0) return;
  const div = document.createElement('label');
  div.className = 'filter-row';
  div.innerHTML = `
    <input type="checkbox" checked data-cat="${c}">
    <span class="chip" style="background:${PARK_COLORS[c]||'#ccc'}"></span>
    <span>${c}</span>
    <span class="count">${count.toLocaleString()}</span>
  `;
  ptPanel.appendChild(div);
});
ptPanel.querySelectorAll('input').forEach(cb => {
  cb.addEventListener('change', () => {
    const c = cb.dataset.cat;
    if (cb.checked) state.activeParkTypes.add(c); else state.activeParkTypes.delete(c);
    rebuildParks();
  });
});

// Jimok filter
const jimokPanel = document.getElementById('jimok-filters');
Object.entries(JIMOK_GROUPS).forEach(([group, codes]) => {
  const count = codes.reduce((s, j) => s + (STATS.jimok_counts[j] || 0), 0);
  if (count === 0) return;
  const div = document.createElement('label');
  div.className = 'filter-row';
  div.innerHTML = `
    <input type="checkbox" checked data-jimok-group="${group}">
    <span class="chip" style="background:${JIMOK_GROUP_COLORS[group] || '#888'}"></span>
    <span>${group}</span>
    <span class="count">${count.toLocaleString()}</span>
  `;
  jimokPanel.appendChild(div);
});
jimokPanel.querySelectorAll('input').forEach(cb => {
  cb.addEventListener('change', () => {
    const g = cb.dataset.jimokGroup;
    if (cb.checked) state.activeJimokGroups.add(g); else state.activeJimokGroups.delete(g);
    rebuildParcels(); renderList();
  });
});
document.getElementById('jimok-all').addEventListener('click', () => {
  const keys = Object.keys(JIMOK_GROUPS);
  const allOn = keys.every(k => state.activeJimokGroups.has(k));
  if (allOn) {
    state.activeJimokGroups.clear();
    jimokPanel.querySelectorAll('input').forEach(cb => cb.checked = false);
  } else {
    state.activeJimokGroups = new Set(keys);
    jimokPanel.querySelectorAll('input').forEach(cb => cb.checked = true);
  }
  rebuildParcels(); renderList();
});
document.getElementById('jimok-natural').addEventListener('click', () => {
  state.activeJimokGroups = new Set(["자연/녹지","공원/잡종"]);
  jimokPanel.querySelectorAll('input').forEach(cb => {
    cb.checked = state.activeJimokGroups.has(cb.dataset.jimokGroup);
  });
  rebuildParcels(); renderList();
});

// Methodology + How-to
function openMethodology() {
  const ownerActive = Array.from(state.activeOwners).join(', ');
  const ptActive = Array.from(state.activeParkTypes).join(', ');
  const jiActive = Array.from(state.activeJimokGroups).join(', ');
  const sggActive = Array.from(state.activeSggs).join(', ');
  document.getElementById('methodology-body').innerHTML = `
    <h3 style="margin:0 0 8px 0;">데이터 출처</h3>
    <ul style="margin:0 0 16px 18px;">
      <li>도시계획 공간시설: V-World <code>lt_c_upisuq153</code></li>
      <li>필지: V-World <code>lt_c_landinfobasemap</code></li>
      <li>소유 구분: V-World <code>getPossessionAttr</code></li>
    </ul>
    <h3 style="margin:0 0 8px 0;">공간 매칭 기준</h3>
    <ul style="margin:0 0 16px 18px;">
      <li>겹침 임계값 <b>50%</b> (필지의 50%+가 공원 안)</li>
      <li>대표 매칭: 가장 많이 겹친 공원</li>
    </ul>
    <h3 style="margin:0 0 8px 0;">표시 기준</h3>
    <ul style="margin:0 0 16px 18px;">
      <li>면적: 필지 전체(parea), 평 = ㎡/3.3058</li>
      <li>사유지: 개인 + 법인</li>
    </ul>
    <h3 style="margin:0 0 8px 0;">현재 적용된 필터</h3>
    <ul style="margin:0 0 16px 18px;font-size:11.5px;">
      <li>소유 구분: ${ownerActive}</li>
      <li>자치구: ${sggActive}</li>
      <li>공원 유형: ${ptActive}</li>
      <li>지목 그룹: ${jiActive}</li>
    </ul>
  `;
  document.getElementById('methodology-overlay').style.display = 'flex';
}
document.getElementById('open-methodology').addEventListener('click', openMethodology);
document.getElementById('close-methodology').addEventListener('click', () => {
  document.getElementById('methodology-overlay').style.display = 'none';
});
document.getElementById('methodology-overlay').addEventListener('click', (e) => {
  if (e.target.id === 'methodology-overlay') document.getElementById('methodology-overlay').style.display = 'none';
});
document.getElementById('open-howto').addEventListener('click', () => {
  document.getElementById('howto-overlay').style.display = 'flex';
});
document.getElementById('close-howto').addEventListener('click', () => {
  document.getElementById('howto-overlay').style.display = 'none';
});
document.getElementById('howto-overlay').addEventListener('click', (e) => {
  if (e.target.id === 'howto-overlay') document.getElementById('howto-overlay').style.display = 'none';
});

// Layer instances
let districtsLayer = null, parksMatchedLayer = null, parksEmptyLayer = null, parcelLayer = null;
let labelsLayer = L.layerGroup();
const parcelById = {};

function rebuildLabels() {
  labelsLayer.clearLayers();
  if (!PARKS || !state.showLabels || !state.showParks) return;
  if (map.getZoom() < 14) return;
  const bounds = map.getBounds();
  for (const f of PARKS.features) {
    const p = f.properties;
    if (!p.dgm_nm) continue;
    if (!state.activeParkTypes.has(p.park_cat || '기타')) continue;
    if ((p.matched_count||0) === 0 && !state.showEmpty) continue;
    try {
      const tmp = L.geoJSON(f);
      const c = tmp.getBounds().getCenter();
      if (!bounds.contains(c)) continue;
      L.marker(c, { pane:'labels', interactive:false, icon: L.divIcon({
        className: 'park-label',
        html: `<div style="background:rgba(255,255,255,0.92);padding:2px 6px;border-radius:4px;font-size:10.5px;border:1px solid #d0d0d5;white-space:nowrap;color:#1d1d1f;font-weight:600;box-shadow:0 1px 3px rgba(0,0,0,0.05);">${p.dgm_nm}</div>`,
        iconSize: null, iconAnchor: [50, 8]
      })}).addTo(labelsLayer);
    } catch(e) {}
  }
  labelsLayer.addTo(map);
}
map.on('zoomend moveend', () => {
  if (state.showLabels) rebuildLabels();
});

function rebuildDistricts() {
  if (districtsLayer) map.removeLayer(districtsLayer);
  if (!DISTRICTS || !state.showDistricts) return;
  districtsLayer = L.geoJSON(DISTRICTS, {
    pane: 'districts', interactive: false,
    style: () => ({ color: '#1d3557', weight: 1.5, fillOpacity: 0, dashArray: '4,3' }),
  }).addTo(map);
}
function rebuildParks() {
  if (parksMatchedLayer) map.removeLayer(parksMatchedLayer);
  if (parksEmptyLayer) map.removeLayer(parksEmptyLayer);
  if (!PARKS || !state.showParks) return;
  const matched=[], empty=[];
  for (const f of PARKS.features) {
    if (!state.activeParkTypes.has(f.properties.park_cat || '기타')) continue;
    ((f.properties.matched_count||0) > 0 ? matched : empty).push(f);
  }
  parksMatchedLayer = L.geoJSON({type:'FeatureCollection', features:matched}, {
    pane:'parks', interactive:false,
    style: f => ({ color:'#2a9d8f', weight:0.5,
                   fillColor: PARK_COLORS[f.properties.park_cat] || '#a8dadc',
                   fillOpacity:0.25 }),
  }).addTo(map);
  if (state.showEmpty) {
    parksEmptyLayer = L.geoJSON({type:'FeatureCollection', features:empty}, {
      pane:'parks', interactive:false,
      style: () => ({ color:'#888', weight:0.5, dashArray:'3,2',
                      fillColor:'#999', fillOpacity:0.05 }),
    }).addTo(map);
  }
}
function rebuildParcels() {
  if (parcelLayer) map.removeLayer(parcelLayer);
  Object.keys(parcelById).forEach(k => delete parcelById[k]);
  if (!PARCELS || !state.showParcels) return;
  const jset = activeJimokSet();
  const filtered = PARCELS.features.filter(f =>
    state.activeOwners.has(f.properties.owner_type) &&
    jset.has(f.properties.jimok) &&
    state.activeSggs.has(f.properties.sgg_nm)
  );
  parcelLayer = L.geoJSON({type:'FeatureCollection', features:filtered}, {
    pane:'parcels',
    style: f => {
      const ot = f.properties.owner_type || '?';
      return { color:'#222', weight:0.3, fillColor: COLORS[ot] || '#888', fillOpacity:0.75 };
    },
    onEachFeature: (f, layer) => {
      const p = f.properties;
      parcelById[p.pnu] = layer;
      layer.bindPopup(buildPopup(p));
      // Hover tooltip — quick park name preview
      const tipParts = [`<b>${p.sgg_nm||''} ${p.emd_nm||''} ${p.jibun||''}</b>`];
      if (p.matched_park_name) tipParts.push(`📍 ${p.matched_park_name} <small style="color:#888;">(${p.matched_park_type||''})</small>`);
      tipParts.push(`소유: <b style="color:${COLORS[p.owner_type]||'#000'}">${p.owner_type||'?'}</b>`);
      layer.bindTooltip(tipParts.join('<br>'), {sticky: true, direction: 'top'});
    }
  }).addTo(map);
}
function buildPopup(p) {
  const m2 = parseFloat(p.parea)||parseFloat(p.area_m2)||0;
  const py = m2/PYEONG;
  const pricePerM = parseFloat(p.price_per_m2)||0;
  const pricePerPy = pricePerM*PYEONG;
  const addr = buildCleanAddr(p);
  return `
    <b>${p.sgg_nm || ''} ${p.emd_nm || ''} ${p.jibun || ''}</b><br>
    ${p.matched_park_name ? `📍 <b>${p.matched_park_name}</b> <small style="color:#888;">(${p.matched_park_type||''} · 겹침 ${p.match_overlap_pct||'?'}%)</small><br>` : ''}
    소유: <b style="color:${COLORS[p.owner_type] || '#000'}">${p.owner_type || '?'}</b>
      <small>(${p.owner_subtype || ''})</small><br>
    지목: ${p.jimok || '?'}<br>
    면적: ${m2 ? m2.toLocaleString() : '?'} ㎡ (${py ? Math.round(py).toLocaleString() : '?'} 평)<br>
    공시지가: ${pricePerM ? pricePerM.toLocaleString() : '?'} 원/㎡
      (${pricePerPy ? Math.round(pricePerPy).toLocaleString() : '?'} 원/평)<br>
    ${p.rn_nm ? '도로명: '+p.rn_nm+' '+(p.bld_mnnm||'')+'<br>' : ''}
    <small style="color:#888;">PNU: ${p.pnu}</small>
    <div style="margin-top:10px;padding-top:10px;border-top:1px solid #eee;display:flex;gap:4px;flex-wrap:wrap;">
      <button onclick="jumpIros('${p.pnu}','${addr.replace(/'/g,'')}')" style="flex:1;min-width:80px;padding:5px 8px;background:#0071e3;color:#fff;border:none;border-radius:5px;font-size:11px;cursor:pointer;font-weight:600;">📜 등기부</button>
      <button onclick="jumpEum('${p.pnu}')" style="flex:1;min-width:80px;padding:5px 8px;background:#2f8a3a;color:#fff;border:none;border-radius:5px;font-size:11px;cursor:pointer;font-weight:600;">🗺 토지이용</button>
      <button onclick="copyAddr('${p.pnu}','${addr.replace(/'/g,'')}')" style="flex:1;min-width:80px;padding:5px 8px;background:#f4f4f9;color:#333;border:1px solid #d0d0d5;border-radius:5px;font-size:11px;cursor:pointer;font-weight:500;">📋 주소복사</button>
    </div>
  `;
}

// Strip trailing jimok char(s) from jibun: "산91-1임" → "산91-1", "85-8답" → "85-8"
const JIMOK_SUFFIXES = ["대","답","전","임","도","구","수","잡종지","공원","주차장","철도용지","학교용지","종교용지","수도용지","제방","구거","하천","유지","잡","장","목","과","유","제","원","사","천"];
function cleanJibun(jibun) {
  if (!jibun) return '';
  let s = jibun.trim();
  // Try common jimoks (longer first)
  const tries = ["잡종지","공원","주차장","철도용지","학교용지","종교용지","수도용지","제방","구거","하천","유지","대","답","전","임","도","목","사","장","과","유","제","원","천"];
  for (const j of tries) {
    if (s.endsWith(j) && s.length > j.length) {
      const head = s.slice(0, -j.length);
      // ensure it ends with a digit (avoid stripping "고덕동")
      if (/\\d$/.test(head)) return head;
    }
  }
  return s;
}
function buildCleanAddr(p) {
  const jibun = cleanJibun(p.jibun||'');
  return `${p.sido_nm||''} ${p.sgg_nm||''} ${p.emd_nm||''} ${jibun}`.replace(/\\s+/g,' ').trim();
}

// External link jump helpers
function jumpIros(pnu, addr) {
  // addr param already cleaned upstream, but re-clean as safety
  const clean = addr.replace(/\\s*PNU[: ].*$/i,'').trim();
  navigator.clipboard.writeText(clean).catch(()=>{});
  alert('📋 주소 복사됨:\\n\\n' + clean + '\\n\\n인터넷등기소 새 탭에서:\\n1) "소재지번검색" 탭 클릭 권장\\n2) 시도/시군구/읍면동 따로 입력\\n3) 또는 "간편검색"에서 위 주소 그대로 붙여넣기\\n\\n검색 안 잡히면 "산"이 붙은 임야는 지번을 따로 입력해야 할 수 있어요.');
  window.open('http://www.iros.go.kr/index.jsp', '_blank');
}
function jumpEum(pnu) {
  window.open(`https://www.eum.go.kr/web/am/amMain.jsp?pnu=${pnu}`, '_blank');
}
function copyAddr(pnu, addr) {
  // 깨끗한 주소만 복사 (PNU 안 붙임)
  const clean = addr.replace(/\\s*PNU[: ].*$/i,'').trim();
  navigator.clipboard.writeText(clean).then(()=>{
    alert('📋 주소 복사됨:\\n\\n' + clean);
  }).catch(()=>{ alert('복사 실패'); });
}

document.getElementById('show-districts').addEventListener('change', e => {
  state.showDistricts = e.target.checked; rebuildDistricts();
});
document.getElementById('show-parks').addEventListener('change', e => {
  state.showParks = e.target.checked; rebuildParks();
});
document.getElementById('show-empty-parks').addEventListener('change', e => {
  state.showEmpty = e.target.checked; rebuildParks(); rebuildLabels();
});
document.getElementById('show-labels').addEventListener('change', e => {
  state.showLabels = e.target.checked;
  if (state.showLabels) rebuildLabels();
  else { labelsLayer.clearLayers(); }
});
document.getElementById('show-parcels').addEventListener('change', e => {
  state.showParcels = e.target.checked; rebuildParcels();
});

// Tabs + expand
const mapWrap = document.querySelector('.map-wrap');
const rightPanel = document.getElementById('right-panel');
document.querySelectorAll('.tab').forEach(t => {
  if (!t.dataset.view) return;
  t.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    if (t.dataset.view === 'map') {
      rightPanel.classList.remove('open','expanded');
      mapWrap.classList.remove('hidden');
      state.expanded = false;
    } else {
      rightPanel.classList.add('open');
      renderList();
    }
    setTimeout(() => map.invalidateSize(), 100);
  });
});
document.getElementById('expand-btn').addEventListener('click', () => {
  state.expanded = !state.expanded;
  if (state.expanded) {
    rightPanel.classList.add('expanded');
    mapWrap.classList.add('hidden');
    document.getElementById('expand-btn').textContent = '⇲ 축소';
  } else {
    rightPanel.classList.remove('expanded');
    mapWrap.classList.remove('hidden');
    document.getElementById('expand-btn').textContent = '⇱ 확장';
    setTimeout(() => map.invalidateSize(), 100);
  }
  renderList();
});

// List
const compactEl = document.getElementById('compact-list');
const tbody = document.querySelector('#table tbody');
const searchEl = document.getElementById('search');
const PAGE_SIZE = 2000;
let displayedRows = PAGE_SIZE;
const rowCount = document.getElementById('row-count');
let lastRows = [];
const collapsedGroups = new Set();
function rnFull(p) {
  if (!p.rn_nm) return '';
  return `${p.rn_nm} ${p.bld_mnnm||''}`.trim();
}
function groupByDistrict(rows) {
  const m = new Map();
  for (const r of rows) {
    const key = `${r.sido_nm||'-'} ${r.sgg_nm||'-'}`;
    if (!m.has(key)) m.set(key, []);
    m.get(key).push(r);
  }
  return m;
}
function toggleGroup(k) {
  if (collapsedGroups.has(k)) collapsedGroups.delete(k);
  else collapsedGroups.add(k);
  renderList();
}
function renderList() {
  if (!PARCELS) return;
  const q = searchEl.value.trim().toLowerCase();
  const jset = activeJimokSet();
  let rows = PARCELS.features.map(f => f.properties).filter(p =>
    state.activeOwners.has(p.owner_type) &&
    jset.has(p.jimok) &&
    state.activeSggs.has(p.sgg_nm)
  );
  if (q) rows = rows.filter(p =>
    (p.emd_nm||'').toLowerCase().includes(q) ||
    (p.jibun||'').toLowerCase().includes(q) ||
    (p.jimok||'').toLowerCase().includes(q) ||
    (p.rn_nm||'').toLowerCase().includes(q) ||
    (p.sgg_nm||'').toLowerCase().includes(q));
  if (state.sortKey) {
    rows.sort((a,b) => {
      let av, bv;
      if (state.sortKey === 'emd_jibun') { av=(a.emd_nm||'')+' '+(a.jibun||''); bv=(b.emd_nm||'')+' '+(b.jibun||''); }
      else if (state.sortKey === 'rn_full') { av=rnFull(a); bv=rnFull(b); }
      else { av=a[state.sortKey]||''; bv=b[state.sortKey]||''; }
      const an=parseFloat(av), bn=parseFloat(bv);
      if (!isNaN(an) && !isNaN(bn)) return (an-bn)*state.sortDir;
      return av.toString().localeCompare(bv.toString())*state.sortDir;
    });
  }
  lastRows = rows;
  const showAllBtn = document.getElementById('showAllBtn');
  if (!state.expanded) {
    const cap = Math.min(rows.length, 500);
    rowCount.textContent = `${rows.length.toLocaleString()}건${cap < rows.length ? ' (상위 '+cap+' 표시, 확장하면 전체)' : ''}`;
    showAllBtn.style.display = 'none';
    renderCompact(rows.slice(0, cap));
  } else {
    if (displayedRows < PAGE_SIZE) displayedRows = PAGE_SIZE;
    const cap = Math.min(rows.length, displayedRows);
    rowCount.textContent = `${rows.length.toLocaleString()}건 ${cap < rows.length ? '(상위 '+cap.toLocaleString()+' 표시)' : '(전체)'}`;
    renderTable(rows.slice(0, cap));
    const wrap = document.getElementById('loadMoreWrap');
    if (cap < rows.length) {
      wrap.style.display = 'block';
      document.getElementById('loadMoreBtn').textContent = `더 보기 (다음 ${Math.min(PAGE_SIZE, rows.length-cap).toLocaleString()}건)`;
      showAllBtn.style.display = 'inline-block';
      showAllBtn.textContent = `전체보기 (${rows.length.toLocaleString()}건)`;
    } else {
      wrap.style.display = 'none';
      showAllBtn.style.display = 'none';
    }
  }
}
function renderCompact(rows) {
  const groups = groupByDistrict(rows);
  let html = '', idx = 0;
  for (const [k, items] of groups) {
    const collapsed = collapsedGroups.has(k);
    html += `<div class="group-header${collapsed?' collapsed':''}" data-group="${k}">
      <span class="caret">▼</span><span>${k}</span><span class="count">${items.length.toLocaleString()}건</span></div>
      <div class="group-body${collapsed?' collapsed':''}">`;
    for (const p of items) {
      idx++;
      const m2 = parseFloat(p.parea)||parseFloat(p.area_m2)||0;
      const py = m2/PYEONG;
      const pricePerM = parseFloat(p.price_per_m2)||0;
      const parkLine = p.matched_park_name
        ? `<div style="font-size:11.5px;color:#2a9d8f;margin-bottom:3px;">📍 <b>${p.matched_park_name}</b> <small style="color:#888;">(${p.matched_park_type||''} · ${p.match_overlap_pct||'?'}%)</small></div>`
        : '';
      const addr = buildCleanAddr(p).replace(/'/g,'');
      const jumpButtons = `
        <div style="margin-top:6px;display:flex;gap:4px;">
          <button onclick="event.stopPropagation();jumpIros('${p.pnu}','${addr}')" style="padding:3px 8px;background:#0071e3;color:#fff;border:none;border-radius:4px;font-size:10.5px;cursor:pointer;font-weight:600;">📜 등기부</button>
          <button onclick="event.stopPropagation();jumpEum('${p.pnu}')" style="padding:3px 8px;background:#2f8a3a;color:#fff;border:none;border-radius:4px;font-size:10.5px;cursor:pointer;font-weight:600;">🗺 토지이용</button>
          <button onclick="event.stopPropagation();copyAddr('${p.pnu}','${addr}')" style="padding:3px 8px;background:#f4f4f9;color:#333;border:1px solid #d0d0d5;border-radius:4px;font-size:10.5px;cursor:pointer;">📋</button>
        </div>`;
      html += `<div class="pcard" data-pnu="${p.pnu}"><div class="num">${idx}</div><div class="body">
        <div class="head">${p.emd_nm||''} ${p.jibun||''}
          <span class="pill" style="background:${COLORS[p.owner_type]||'#888'}">${p.owner_type||'?'}</span></div>
        <div class="addr">${p.sido_nm||''} ${p.sgg_nm||''}</div>
        ${parkLine}
        <div class="meta">지목 <b>${p.jimok||'-'}</b> · 면적 <b>${m2?Math.round(m2).toLocaleString():'-'} ㎡</b> (${py?Math.round(py).toLocaleString():'-'} 평)<br>
        공시지가 <b>${pricePerM?pricePerM.toLocaleString():'-'} 원/㎡</b></div>
        ${jumpButtons}</div></div>`;
    }
    html += '</div>';
  }
  compactEl.innerHTML = html;
  compactEl.querySelectorAll('.pcard').forEach(el => el.addEventListener('click', () => focusParcel(el.dataset.pnu)));
  compactEl.querySelectorAll('.group-header').forEach(el => el.addEventListener('click', () => toggleGroup(el.dataset.group)));
}
function renderTable(rows) {
  const groups = groupByDistrict(rows);
  let html = '';
  let idx = 0;
  for (const [k, items] of groups) {
    const collapsed = collapsedGroups.has(k);
    html += `<tr class="group-row" data-group="${k}"><td colspan="10">
      <span style="font-size:10px;color:#888;">${collapsed?'▶':'▼'}</span>
      ${k}<span class="count">${items.length.toLocaleString()}건</span></td></tr>`;
    if (collapsed) continue;
    for (const p of items) {
      idx++;
      const m2 = parseFloat(p.parea)||parseFloat(p.area_m2)||0;
      const py = m2/PYEONG;
      const pricePerM = parseFloat(p.price_per_m2)||0;
      const pricePerPy = pricePerM*PYEONG;
      const parkCell = p.matched_park_name
        ? `<span style="color:#2a9d8f;font-weight:600;">${p.matched_park_name}</span> <small style="color:#888;">${p.match_overlap_pct||'?'}%</small>`
        : '-';
      const addr2 = buildCleanAddr(p).replace(/'/g,'');
      const jumpCell = `<button onclick="event.stopPropagation();jumpIros('${p.pnu}','${addr2}')" title="등기부" style="padding:2px 6px;background:#0071e3;color:#fff;border:none;border-radius:4px;font-size:10px;cursor:pointer;margin-right:2px;">📜</button><button onclick="event.stopPropagation();jumpEum('${p.pnu}')" title="토지이용" style="padding:2px 6px;background:#2f8a3a;color:#fff;border:none;border-radius:4px;font-size:10px;cursor:pointer;margin-right:2px;">🗺</button><button onclick="event.stopPropagation();copyAddr('${p.pnu}','${addr2}')" title="복사" style="padding:2px 6px;background:#f4f4f9;color:#333;border:1px solid #d0d0d5;border-radius:4px;font-size:10px;cursor:pointer;">📋</button>`;
      const areaCell = m2 ? `${Math.round(m2).toLocaleString()} ㎡<br><small style="color:#888;">${Math.round(py).toLocaleString()} 평</small>` : '-';
      const priceCell = pricePerM ? `${pricePerM.toLocaleString()} 원/㎡<br><small style="color:#888;">${Math.round(pricePerPy).toLocaleString()} 원/평</small>` : '-';
      html += `<tr data-pnu="${p.pnu}"><td>${idx}</td><td>${p.emd_nm||''} ${p.jibun||''}</td><td>${parkCell}</td><td>${rnFull(p)||'-'}</td><td>${p.jimok||'-'}</td><td class="right">${areaCell}</td><td class="right">${priceCell}</td><td><span class="pill" style="background:${COLORS[p.owner_type]||'#888'}">${p.owner_type||'?'}</span></td><td>${p.owner_subtype||''}</td><td>${jumpCell}</td></tr>`;
    }
  }
  tbody.innerHTML = html;
  tbody.querySelectorAll('tr[data-pnu]').forEach(tr => tr.addEventListener('click', () => focusParcel(tr.dataset.pnu)));
  tbody.querySelectorAll('tr.group-row').forEach(tr => tr.addEventListener('click', () => toggleGroup(tr.dataset.group)));
}

// 더 보기 버튼
document.getElementById('loadMoreBtn').addEventListener('click', () => {
  displayedRows += PAGE_SIZE;
  renderList();
});
// 전체보기 버튼
document.getElementById('showAllBtn').addEventListener('click', () => {
  if (!confirm(`전체 ${lastRows.length.toLocaleString()}건을 한 번에 렌더링합니다. 행 수가 많으면 잠시 멈춤이 발생할 수 있습니다. 계속할까요?`)) return;
  displayedRows = lastRows.length;
  renderList();
});
function focusParcel(pnu) {
  if (state.expanded) {
    state.expanded = false;
    rightPanel.classList.remove('expanded');
    mapWrap.classList.remove('hidden');
    document.getElementById('expand-btn').textContent = '확장 ⇱';
    setTimeout(() => map.invalidateSize(), 50);
  }
  const layer = parcelById[pnu];
  if (layer) {
    map.fitBounds(layer.getBounds(), {maxZoom: 18, padding:[60,60]});
    layer.openPopup();
  }
}
searchEl.addEventListener('input', renderList);
document.querySelectorAll('th').forEach(th => {
  th.addEventListener('click', () => {
    const k = th.dataset.sort; if (!k) return;
    if (state.sortKey === k) state.sortDir = -state.sortDir;
    else { state.sortKey = k; state.sortDir = 1; }
    document.querySelectorAll('th').forEach(x => x.classList.remove('sorted','desc'));
    th.classList.add('sorted');
    if (state.sortDir === -1) th.classList.add('desc');
    renderList();
  });
});
function buildRows() {
  return lastRows.map((p, i) => {
    const m2 = parseFloat(p.parea)||parseFloat(p.area_m2)||0;
    const py = m2/PYEONG;
    const pricePerM = parseFloat(p.price_per_m2)||0;
    const pricePerPy = pricePerM*PYEONG;
    return {
      순번: i+1,
      시도: p.sido_nm||'',
      자치구: p.sgg_nm||'',
      동: p.emd_nm||'',
      지번: p.jibun||'',
      도로명주소: rnFull(p),
      지목: p.jimok||'',
      "면적(㎡)": Math.round(m2*10)/10,
      "면적(평)": Math.round(py*10)/10,
      "공시지가(원/㎡)": pricePerM,
      "공시지가(원/평)": Math.round(pricePerPy),
      소유구분: p.owner_type||'',
      세부: p.owner_subtype||'',
      매칭공원: p.matched_park_name||'',
      "겹침(%)": p.match_overlap_pct||'',
    };
  });
}

function downloadXlsx() {
  if (typeof XLSX === 'undefined') { alert('Excel 라이브러리 로딩 중...'); return; }
  const rows = buildRows();
  const headers = Object.keys(rows[0] || {순번:1});
  const aoa = [headers, ...rows.map(r => headers.map(h => r[h]))];
  const ws = XLSX.utils.aoa_to_sheet(aoa);
  // Column widths
  ws['!cols'] = [
    {wch:6},{wch:10},{wch:10},{wch:12},{wch:12},{wch:28},{wch:8},
    {wch:12},{wch:10},{wch:14},{wch:14},{wch:10},{wch:10},{wch:20},{wch:8}
  ];
  // Apply number format with thousand separators
  // Column letters: A=순번 ... H=면적㎡ I=면적평 J=공시지가㎡ K=공시지가평
  const fmtArea = '#,##0.0';
  const fmtPrice = '#,##0';
  for (let r = 2; r <= aoa.length; r++) {
    ['H','I'].forEach(col => { const c=ws[`${col}${r}`]; if (c) { c.t='n'; c.z=fmtArea; }});
    ['J','K'].forEach(col => { const c=ws[`${col}${r}`]; if (c) { c.t='n'; c.z=fmtPrice; }});
    const a = ws[`A${r}`]; if (a) { a.t='n'; }
    const ov = ws[`O${r}`]; if (ov) { ov.t='n'; ov.z='0.0'; }
  }
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, '서울 사유지');
  XLSX.writeFile(wb, `seoul-park-parcels-${new Date().toISOString().slice(0,10)}.xlsx`);
}

function downloadCsv() {
  const rows = buildRows();
  const headers = Object.keys(rows[0] || {순번:1});
  const lines = ["\\ufeff" + headers.join(",")];
  rows.forEach(r => {
    lines.push(headers.map(h => {
      const v = r[h];
      const s = (v??'').toString().replace(/"/g,'""');
      return /[,"\\n]/.test(s) ? `"${s}"` : s;
    }).join(","));
  });
  const blob = new Blob([lines.join("\\n")], {type:"text/csv"});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `seoul-park-parcels-${new Date().toISOString().slice(0,10)}.csv`;
  a.click();
}

// Load data
async function loadData() {
  const setText = t => document.getElementById('loading-text').textContent = t;
  try {
    setText('자치구 경계 로딩...');
    DISTRICTS = await (await fetch('public/districts.json')).json();
    rebuildDistricts();

    setText('공원 폴리곤 로딩...');
    PARKS = await (await fetch('public/parks.json')).json();
    rebuildParks();
    rebuildLabels();

    setText('필지 데이터 로딩 (52MB · 잠시만)...');
    PARCELS = await (await fetch('public/parcels.json')).json();
    rebuildParcels();
    renderList();

    document.getElementById('loading').style.display = 'none';
  } catch (e) {
    setText('로드 실패: ' + e.message);
    console.error(e);
  }
}
loadData();
</script>
</body>
</html>"""


if __name__ == "__main__":
    main()
