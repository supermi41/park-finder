#!/usr/bin/env python3
"""Build interactive HTML map + table for 강남구 park-private-land (v3)."""

import json
from pathlib import Path
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "seoul" / "gangnam"
OUT = ROOT / "map.html"

parks = json.loads((DATA / "parks.geojson").read_text())
parcels = json.loads((DATA / "park_parcels_all.geojson").read_text())

OWNER_ORDER = ["개인", "법인", "시 도유지", "군유지", "국유지",
               "종교단체", "종중", "기타단체", "외국인 외국공공기관"]
COLORS = {
    "개인": "#e63946", "법인": "#f4a261", "국유지": "#264653",
    "시 도유지": "#2a9d8f", "군유지": "#588157", "종교단체": "#9b5de5",
    "종중": "#b6ad90", "기타단체": "#6c757d", "외국인 외국공공기관": "#000000",
}
PARK_CATS = ["공원", "녹지", "광장", "유원지"]
PARK_COLORS = {"공원": "#a8dadc", "녹지": "#b7e4c7", "광장": "#fee08b", "유원지": "#cbb9ff"}

# Jimok grouping (지목 -> category for sidebar filter)
JIMOK_GROUPS = {
    "자연/녹지": ["임야", "전", "답", "유지", "구거", "하천", "제방"],
    "공원/잡종": ["공원", "잡종지"],
    "건물용지": ["대"],
    "도로/시설": ["도로", "주차장", "철도용지", "수도용지"],
    "공공/기타": ["종교용지", "학교용지"],
}
JIMOK_GROUP_COLORS = {"자연/녹지":"#588157","공원/잡종":"#2a9d8f","건물용지":"#e63946",
                      "도로/시설":"#6c757d","공공/기타":"#9b5de5"}

jimok_stats = {}
for f in parcels["features"]:
    j = f["properties"].get("jimok", "?")
    jimok_stats[j] = jimok_stats.get(j, 0) + 1

# Stats
stats = {}
for f in parcels["features"]:
    ot = f["properties"].get("owner_type", "?")
    stats[ot] = stats.get(ot, 0) + 1
total = sum(stats.values())
private_total = sum(v for k, v in stats.items() if k in ["개인", "법인"])
pct = round(private_total / total * 100, 1) if total else 0

# Compute matched parcel count per park polygon (for B improvement)
print("Counting matched parcels per park polygon...")
parcel_geoms = []
for f in parcels["features"]:
    try:
        g = shape(f["geometry"])
        if not g.is_valid: g = g.buffer(0)
        parcel_geoms.append(g)
    except Exception:
        parcel_geoms.append(None)

for pf in parks["features"]:
    try:
        pg = shape(pf["geometry"])
        if not pg.is_valid: pg = pg.buffer(0)
        n = 0
        for gg in parcel_geoms:
            if gg is None: continue
            if pg.intersects(gg):
                inter = pg.intersection(gg)
                if inter.area / gg.area > 0.1:
                    n += 1
        pf["properties"]["matched_count"] = n
        # Categorize into a coarse type
        lcl = pf["properties"].get("lcl_nam", "")
        cat = "기타"
        for c in PARK_CATS:
            if c in lcl:
                cat = c; break
        pf["properties"]["park_cat"] = cat
    except Exception:
        pf["properties"]["matched_count"] = 0
        pf["properties"]["park_cat"] = "기타"

park_type_stats = {}
for pf in parks["features"]:
    c = pf["properties"]["park_cat"]
    park_type_stats[c] = park_type_stats.get(c, 0) + 1

print(f"park_type_stats: {park_type_stats}")
print(f"parks with matched parcels: {sum(1 for pf in parks['features'] if pf['properties']['matched_count']>0)}/{len(parks['features'])}")

html = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>핀파인더 · 강남구 공원지정 사유지</title>
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
  .sidebar { width: 240px; background:#fff; border-right:1px solid #e5e5ea;
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
  .stat-card .big { font-size:30px; font-weight:700; color:#e63946; line-height:1; }
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

  /* Right panel toolbar */
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

  /* Compact list (default) */
  .compact-list { flex:1; overflow:auto; }
  .group-header { position:sticky; top:0; z-index:5;
                  background:linear-gradient(180deg,#fff,#f8f8fc);
                  padding:10px 14px 8px; border-bottom:1px solid #e5e5ea;
                  font-size:12px; font-weight:700; color:#1d1d1f;
                  display:flex; align-items:center; gap:8px; cursor:pointer;
                  user-select:none; }
  .group-header .caret { font-size:10px; color:#888; transition:transform 0.15s; }
  .group-header.collapsed .caret { transform:rotate(-90deg); }
  .group-header .count { margin-left:auto; font-size:11px; color:#86868b;
                         font-weight:500; }
  .group-body.collapsed { display:none; }
  .pcard { padding:10px 14px; border-bottom:1px solid #f0f0f3; cursor:pointer;
           display:flex; gap:10px; align-items:flex-start; }
  .pcard:hover { background:#fafafd; }
  .pcard .num { font-size:11px; color:#999; font-weight:600; min-width:30px;
                text-align:right; }
  .pcard .body { flex:1; min-width:0; }
  .pcard .head { display:flex; align-items:center; gap:6px; font-size:13px;
                 font-weight:600; margin-bottom:3px; flex-wrap:wrap; }
  .pcard .addr { font-size:11px; color:#86868b; margin-bottom:3px; }
  .pcard .meta { font-size:11.5px; color:#666; line-height:1.45; }
  .pcard .meta b { color:#333; font-weight:500; }
  /* Grouped table row */
  tr.group-row td { background:linear-gradient(180deg,#f0f5fa,#e7eef5);
                    font-weight:700; font-size:12px; padding:8px 10px;
                    color:#1d1d1f; cursor:pointer; }
  tr.group-row td .count { float:right; color:#666; font-weight:500; }
  .pill { display:inline-block; padding:1px 7px; border-radius:9px;
          font-size:10px; font-weight:600; color:#fff; }

  /* Expanded table */
  .expanded-table { display:none; flex:1; overflow:auto; }
  .right-panel.expanded .compact-list { display:none; }
  .right-panel.expanded .expanded-table { display:block; }
  table { border-collapse:collapse; width:100%; font-size:12px; }
  thead { position:sticky; top:0; background:#f8f8fa; z-index:2; }
  th, td { padding:8px 10px; text-align:left; border-bottom:1px solid #ececef;
           white-space:nowrap; }
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
    <h1>핀파인더 · 강남구</h1>
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

<!-- Methodology modal -->
<div id="methodology-overlay" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:5000;align-items:center;justify-content:center;">
  <div style="background:#fff;width:560px;max-width:92vw;max-height:85vh;overflow:auto;border-radius:14px;box-shadow:0 20px 60px rgba(0,0,0,0.3);">
    <div style="display:flex;justify-content:space-between;align-items:center;padding:18px 22px;border-bottom:1px solid #e5e5ea;">
      <h2 style="margin:0;font-size:16px;font-weight:700;color:#1d1d1f;text-transform:none;letter-spacing:0;">📋 매칭 기준 · 데이터 출처</h2>
      <button id="close-methodology" style="border:none;background:transparent;font-size:20px;cursor:pointer;color:#888;">✕</button>
    </div>
    <div id="methodology-body" style="padding:22px;font-size:13px;line-height:1.7;color:#333;"></div>
  </div>
</div>

<!-- How-to modal -->
<div id="howto-overlay" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:5000;align-items:center;justify-content:center;">
  <div style="background:#fff;width:620px;max-width:92vw;max-height:85vh;overflow:auto;border-radius:14px;box-shadow:0 20px 60px rgba(0,0,0,0.3);">
    <div style="display:flex;justify-content:space-between;align-items:center;padding:18px 22px;border-bottom:1px solid #e5e5ea;">
      <h2 style="margin:0;font-size:16px;font-weight:700;color:#1d1d1f;text-transform:none;letter-spacing:0;">💡 사용법 · 목적별 필터 가이드</h2>
      <button id="close-howto" style="border:none;background:transparent;font-size:20px;cursor:pointer;color:#888;">✕</button>
    </div>
    <div style="padding:22px;font-size:13px;line-height:1.65;color:#333;">

      <div style="background:#fef9e7;padding:14px;border-radius:8px;border:1px solid #f6d860;margin-bottom:20px;font-size:12.5px;">
        🎯 <b>핀파인더가 보여주는 것</b>: 도시계획상 공원으로 지정되어 있지만 소유주가 개인/법인인 필지 (=장기미집행 도시공원의 사유지).
      </div>

      <h3 style="margin:0 0 8px 0;font-size:13px;">📋 지목별 의미</h3>
      <table style="width:100%;font-size:12px;border-collapse:collapse;margin-bottom:20px;">
        <thead><tr style="background:#f6f6f8;"><th style="text-align:left;padding:8px;">지목 그룹</th><th style="text-align:left;padding:8px;">의미</th></tr></thead>
        <tbody>
          <tr><td style="padding:8px;border-bottom:1px solid #eee;"><b>자연/녹지</b><br><small style="color:#888;">임야·전·답·유지·구거·하천·제방</small></td>
              <td style="padding:8px;border-bottom:1px solid #eee;">원래 자연 상태인 사유지. ⭐ 장기미집행 공원의 정통 케이스</td></tr>
          <tr><td style="padding:8px;border-bottom:1px solid #eee;"><b>공원/잡종</b><br><small style="color:#888;">공원·잡종지</small></td>
              <td style="padding:8px;border-bottom:1px solid #eee;">사실상 공원으로 쓰이고 있지만 소유는 사유. 또는 빈 잡목지대</td></tr>
          <tr><td style="padding:8px;border-bottom:1px solid #eee;"><b>건물용지</b><br><small style="color:#888;">대</small></td>
              <td style="padding:8px;border-bottom:1px solid #eee;">공원 지정인데 건물·집이 지어져 있는 사유지. ⭐ 알박기 케이스</td></tr>
          <tr><td style="padding:8px;border-bottom:1px solid #eee;"><b>도로/시설</b><br><small style="color:#888;">도로·주차장·철도·수도</small></td>
              <td style="padding:8px;border-bottom:1px solid #eee;">대부분 국공유. 사유인 경우는 알박기 도로 (드물고 흥미도 낮음)</td></tr>
          <tr><td style="padding:8px;"><b>공공/기타</b><br><small style="color:#888;">종교용지·학교용지</small></td>
              <td style="padding:8px;">종중·종교단체 소유 별도 이슈</td></tr>
        </tbody>
      </table>

      <h3 style="margin:0 0 8px 0;font-size:13px;">🎯 목적별 추천 필터 조합</h3>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:20px;">
        <div style="background:#f6f9fc;padding:12px;border-radius:8px;border:1px solid #d6e3f0;">
          <b style="color:#0071e3;">A) 보상해서 공원 만들면 되는 땅</b>
          <ul style="margin:6px 0 0 18px;padding:0;font-size:12px;">
            <li>자연/녹지 + 공원/잡종</li>
            <li>사유지(개인+법인)</li>
            <li>비교적 협상 쉬움</li>
          </ul>
        </div>
        <div style="background:#fef5f5;padding:12px;border-radius:8px;border:1px solid #f4d6d6;">
          <b style="color:#e63946;">B) 사회적 이슈 / 알박기</b>
          <ul style="margin:6px 0 0 18px;padding:0;font-size:12px;">
            <li>위 + 건물용지(대)</li>
            <li>사유지(개인+법인)</li>
            <li>가장 시끄러운 케이스</li>
          </ul>
        </div>
        <div style="background:#f6fdf6;padding:12px;border-radius:8px;border:1px solid #c8e6c9;">
          <b style="color:#2f8a3a;">C) 투자·시세 관점</b>
          <ul style="margin:6px 0 0 18px;padding:0;font-size:12px;">
            <li>건물용지(대)만</li>
            <li>법인 위주</li>
            <li>공원 지정 풀리면 가치 ↑</li>
          </ul>
        </div>
        <div style="background:#fef9e7;padding:12px;border-radius:8px;border:1px solid #f6d860;">
          <b style="color:#a17a00;">D) 전체 사유지 보기</b>
          <ul style="margin:6px 0 0 18px;padding:0;font-size:12px;">
            <li>자연/녹지 + 공원/잡종 + 건물용지</li>
            <li>도로·공공만 제외</li>
            <li>전반적 이해</li>
          </ul>
        </div>
      </div>

      <h3 style="margin:0 0 8px 0;font-size:13px;">🔍 추천 사용 흐름</h3>
      <ol style="margin:0 0 0 18px;padding:0;">
        <li><b>좌측 사이드바</b>에서 "도로/시설", "공공/기타" 끄기</li>
        <li><b>소유 구분</b>에서 [사유지만] 클릭 (개인+법인만 남김)</li>
        <li><b>목록 탭</b> 클릭 → 우측 패널 등장</li>
        <li><b>면적(평) 컬럼</b> 클릭해서 큰 순으로 정렬</li>
        <li>큰 평수부터 → 보상 안 된 큰 사유지부터 발견</li>
        <li>행 클릭 → 지도로 점프해서 위치 확인</li>
        <li>CSV 다운로드해서 엑셀 분석</li>
      </ol>

      <div style="margin-top:20px;padding:12px;background:#f4f4f9;border-radius:8px;font-size:12px;color:#666;">
        💡 <b>Tip</b>: [📋 매칭 기준] 버튼을 누르면 지금 적용된 필터와 데이터 출처를 언제든 확인할 수 있어요.
      </div>
    </div>
  </div>
</div>

<div class="layout">
  <aside class="sidebar">
    <div class="stat-card">
      <div class="big">__PCT__%</div>
      <div class="label">전체 __TOTAL__건 중 사유지(개인+법인) __PRIV__건</div>
    </div>

    <h2>
      소유 구분
      <span class="toggle-all" id="toggle-all" style="margin-left:auto;">전체</span>
      <span class="toggle-all" id="only-private">사유지만</span>
    </h2>
    <div id="owner-filters"></div>

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
      <input type="checkbox" id="show-parks" checked>
      <span class="chip" style="background:#a8dadc;"></span>
      <span>공원/녹지 폴리곤</span>
    </label>
    <label class="filter-row">
      <input type="checkbox" id="show-empty-parks">
      <span class="chip dashed"></span>
      <span>매칭 0건 폴리곤 표시</span>
    </label>
    <label class="filter-row">
      <input type="checkbox" id="show-labels">
      <span class="chip" style="background:transparent;border:1px solid #888;"></span>
      <span>공원 이름 라벨</span>
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
    </div>
    <div class="right-panel" id="right-panel">
      <div class="toolbar">
        <input id="search" placeholder="🔍 동·지번·지목 검색...">
        <button class="icon-btn" id="expand-btn">확장 ⇱</button>
        <button class="icon-btn primary" onclick="downloadCsv()">CSV</button>
      </div>
      <div class="toolbar" style="background:#fff;padding:6px 14px;">
        <span class="info" id="row-count"></span>
      </div>
      <div class="compact-list" id="compact-list"></div>
      <div class="expanded-table">
        <table id="table">
          <thead>
            <tr>
              <th style="width:40px;">#</th>
              <th data-sort="emd_jibun">동·지번</th>
              <th data-sort="rn_full">도로명주소</th>
              <th data-sort="jimok">지목</th>
              <th data-sort="area_m2" class="right">면적 (㎡ / 평)</th>
              <th data-sort="price_per_m2" class="right">공시지가 (㎡ / 평)</th>
              <th data-sort="owner_type">소유구분</th>
              <th data-sort="owner_subtype">세부</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>
  </div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const PARKS = __PARKS__;
const PARCELS = __PARCELS__;
const COLORS = __COLORS__;
const ORDER = __ORDER__;
const STATS = __STATS__;
const PARK_CATS = __PARK_CATS__;
const PARK_COLORS = __PARK_COLORS__;
const PARK_TYPE_STATS = __PARK_TYPE_STATS__;
const JIMOK_GROUPS = __JIMOK_GROUPS__;
const JIMOK_GROUP_COLORS = __JIMOK_GROUP_COLORS__;
const JIMOK_STATS = __JIMOK_STATS__;
const PYEONG = 3.3058;

const allJimoks = new Set();
Object.values(JIMOK_GROUPS).forEach(arr => arr.forEach(j => allJimoks.add(j)));
const state = {
  activeOwners: new Set(ORDER),
  activeParkTypes: new Set(PARK_CATS),
  activeJimokGroups: new Set(Object.keys(JIMOK_GROUPS)),
  showParks: true, showEmpty: false, showLabels: false, showParcels: true,
  sortKey: null, sortDir: 1, expanded: false,
};
function activeJimokSet() {
  const set = new Set();
  for (const g of state.activeJimokGroups) {
    (JIMOK_GROUPS[g]||[]).forEach(j => set.add(j));
  }
  return set;
}
function jimokGroupOf(j) {
  for (const [g, arr] of Object.entries(JIMOK_GROUPS)) {
    if (arr.includes(j)) return g;
  }
  return "기타";
}

const map = L.map('map').setView([37.498, 127.058], 14);
map.createPane('parks');     map.getPane('parks').style.zIndex = 380;
map.createPane('parcels');   map.getPane('parcels').style.zIndex = 410;
map.createPane('labels');    map.getPane('labels').style.zIndex = 650;

const BASEMAPS = {
  light: { name:'라이트', url:'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png',
         attribution:'© CartoDB', maxZoom:19 },
  osm: { name:'OSM', url:'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
         attribution:'© OSM', maxZoom:19 },
  dark: { name:'다크', url:'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
         attribution:'© CartoDB', maxZoom:19 },
  satellite: { name:'위성', url:'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
         attribution:'© Esri', maxZoom:19 },
  voyager: { name:'보이저', url:'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png',
         attribution:'© CartoDB', maxZoom:19 },
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

let parksMatchedLayer = null;
let parksEmptyLayer = null;
let labelsLayer = L.layerGroup();

function buildParksLayer() {
  if (parksMatchedLayer) map.removeLayer(parksMatchedLayer);
  if (parksEmptyLayer) map.removeLayer(parksEmptyLayer);

  const matchedFeats = [];
  const emptyFeats = [];
  for (const f of PARKS.features) {
    const cat = f.properties.park_cat || '기타';
    if (!state.activeParkTypes.has(cat)) continue;
    if ((f.properties.matched_count || 0) > 0) matchedFeats.push(f);
    else emptyFeats.push(f);
  }
  parksMatchedLayer = L.geoJSON({type:'FeatureCollection', features:matchedFeats}, {
    pane: 'parks', interactive: false,
    style: f => ({
      color: '#2a9d8f', weight: 1,
      fillColor: PARK_COLORS[f.properties.park_cat] || '#a8dadc',
      fillOpacity: 0.3,
    }),
  });
  parksEmptyLayer = L.geoJSON({type:'FeatureCollection', features:emptyFeats}, {
    pane: 'parks', interactive: false,
    style: () => ({
      color: '#888', weight: 1, dashArray:'4,3',
      fillColor: '#999', fillOpacity: 0.08,
    }),
  });
  if (state.showParks) parksMatchedLayer.addTo(map);
  if (state.showParks && state.showEmpty) parksEmptyLayer.addTo(map);
  rebuildLabels();
}

function rebuildLabels() {
  labelsLayer.clearLayers();
  PARKS.features.forEach(f => {
    const p = f.properties || {};
    const cat = p.park_cat || '기타';
    if (!state.activeParkTypes.has(cat)) return;
    if (!p.dgm_nm) return;
    if ((p.matched_count||0) === 0 && !state.showEmpty) return;
    try {
      const layer = L.geoJSON(f);
      const c = layer.getBounds().getCenter();
      L.marker(c, { pane:'labels', interactive:false, icon: L.divIcon({
        className: 'park-label',
        html: `<div style="background:#fff;padding:2px 6px;border-radius:4px;font-size:10px;border:1px solid #ddd;white-space:nowrap;color:#333;font-weight:500;">${p.dgm_nm} <span style="color:#888;">(${p.matched_count})</span></div>`,
        iconSize:[100,16]
      })}).addTo(labelsLayer);
    } catch(e) {}
  });
  if (state.showLabels) labelsLayer.addTo(map);
}

let parcelLayer = null;
let parcelById = {};
function buildParcelLayer() {
  if (parcelLayer) map.removeLayer(parcelLayer);
  parcelById = {};
  const jset = activeJimokSet();
  const filtered = PARCELS.features.filter(f =>
    state.activeOwners.has(f.properties.owner_type) &&
    jset.has(f.properties.jimok)
  );
  parcelLayer = L.geoJSON({type:'FeatureCollection', features:filtered}, {
    pane: 'parcels',
    style: (f) => {
      const ot = (f.properties || {}).owner_type || '?';
      return { color:'#333', weight:0.5, fillColor: COLORS[ot] || '#888', fillOpacity:0.75 };
    },
    onEachFeature: (f, layer) => {
      const p = f.properties || {};
      parcelById[p.pnu] = layer;
      layer.bindPopup(buildPopup(p));
    }
  });
  if (state.showParcels) parcelLayer.addTo(map);
}
function buildPopup(p) {
  const m2 = parseFloat(p.parea)||parseFloat(p.area_m2)||0;
  const py = m2/PYEONG;
  const pricePerM = parseFloat(p.price_per_m2)||0;
  const pricePerPy = pricePerM*PYEONG;
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
  `;
}
buildParksLayer();
buildParcelLayer();
const bounds = parksMatchedLayer.getBounds();
if (bounds.isValid()) map.fitBounds(bounds, {padding:[20,20]});

// Owner filter
const filterPanel = document.getElementById('owner-filters');
ORDER.forEach(ot => {
  const count = STATS[ot] || 0;
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
    buildParcelLayer(); renderList();
  });
});
document.getElementById('toggle-all').addEventListener('click', () => {
  filterPanel.querySelectorAll('input').forEach(cb => {
    cb.checked = true; state.activeOwners.add(cb.dataset.owner);
  });
  buildParcelLayer(); renderList();
});
document.getElementById('only-private').addEventListener('click', () => {
  state.activeOwners = new Set(["개인","법인"]);
  filterPanel.querySelectorAll('input').forEach(cb => {
    cb.checked = state.activeOwners.has(cb.dataset.owner);
  });
  buildParcelLayer(); renderList();
});

// Jimok group filter
const jimokPanel = document.getElementById('jimok-filters');
Object.entries(JIMOK_GROUPS).forEach(([group, codes]) => {
  const count = codes.reduce((s, j) => s + (JIMOK_STATS[j] || 0), 0);
  if (count === 0) return;
  const div = document.createElement('label');
  div.className = 'filter-row';
  div.innerHTML = `
    <input type="checkbox" checked data-jimok-group="${group}">
    <span class="chip" style="background:${JIMOK_GROUP_COLORS[group] || '#888'}"></span>
    <span>${group}</span>
    <span class="count">${count.toLocaleString()}</span>
  `;
  div.querySelector('span:nth-of-type(2)').setAttribute('title', codes.join(', '));
  jimokPanel.appendChild(div);
});
jimokPanel.querySelectorAll('input').forEach(cb => {
  cb.addEventListener('change', () => {
    const g = cb.dataset.jimokGroup;
    if (cb.checked) state.activeJimokGroups.add(g);
    else state.activeJimokGroups.delete(g);
    buildParcelLayer(); renderList();
  });
});
document.getElementById('jimok-all').addEventListener('click', () => {
  state.activeJimokGroups = new Set(Object.keys(JIMOK_GROUPS));
  jimokPanel.querySelectorAll('input').forEach(cb => { cb.checked = true; });
  buildParcelLayer(); renderList();
});
document.getElementById('jimok-natural').addEventListener('click', () => {
  state.activeJimokGroups = new Set(["자연/녹지","공원/잡종"]);
  jimokPanel.querySelectorAll('input').forEach(cb => {
    cb.checked = state.activeJimokGroups.has(cb.dataset.jimokGroup);
  });
  buildParcelLayer(); renderList();
});

// Methodology modal
function openMethodology() {
  const body = document.getElementById('methodology-body');
  const ownerActive = Array.from(state.activeOwners).join(', ');
  const ptActive = Array.from(state.activeParkTypes).join(', ');
  const jiActive = Array.from(state.activeJimokGroups).join(', ');
  body.innerHTML = `
    <h3 style="margin:0 0 8px 0;font-size:13px;color:#1d1d1f;">데이터 출처</h3>
    <ul style="margin:0 0 18px 16px;padding:0;">
      <li>도시계획 공간시설(공원/녹지/광장/유원지): V-World <code style="background:#f4f4f9;padding:1px 4px;border-radius:3px;font-size:11px;">lt_c_upisuq153</code></li>
      <li>필지 정보(PNU, 주소, 지목, 면적): V-World <code style="background:#f4f4f9;padding:1px 4px;border-radius:3px;font-size:11px;">lt_c_landinfobasemap</code></li>
      <li>소유 구분(개인/법인/국공유): V-World 국가중점데이터 <code style="background:#f4f4f9;padding:1px 4px;border-radius:3px;font-size:11px;">getPossessionAttr</code></li>
    </ul>

    <h3 style="margin:0 0 8px 0;font-size:13px;color:#1d1d1f;">공간 매칭 기준</h3>
    <ul style="margin:0 0 18px 16px;padding:0;">
      <li><b>임계값 50%</b>: 필지의 면적 중 50% 이상이 공원 폴리곤 안에 들어와야 매칭</li>
      <li>한 필지에 여러 공원이 겹치면 가장 많이 겹친 공원이 대표 매칭</li>
      <li>대표 공원명, 시설 유형, 겹침 비율(%)을 팝업에 표시</li>
      <li>이전 10% 기준에서 50%로 상향 → 노이즈 약 18% 감소</li>
    </ul>

    <h3 style="margin:0 0 8px 0;font-size:13px;color:#1d1d1f;">표시 기준</h3>
    <ul style="margin:0 0 18px 16px;padding:0;">
      <li>면적은 <b>전체 필지 면적(parea)</b> 사용. 평 환산은 1평 = 3.3058 ㎡</li>
      <li>공시지가는 ㎡ 단가 기준. 평 단가는 자동 환산</li>
      <li>사유지 정의: 소유구분이 <b>개인 또는 법인</b></li>
      <li>도로명주소는 V-World 데이터에 일부만 존재 (강남구 1,678건 중 약 5%)</li>
    </ul>

    <h3 style="margin:0 0 8px 0;font-size:13px;color:#1d1d1f;">현재 적용된 필터</h3>
    <ul style="margin:0 0 18px 16px;padding:0;">
      <li>소유 구분: ${ownerActive || '(없음)'}</li>
      <li>공원 시설 유형: ${ptActive || '(없음)'}</li>
      <li>지목 그룹: ${jiActive || '(없음)'}</li>
      <li>매칭 0건 폴리곤: ${state.showEmpty ? '표시' : '숨김'}</li>
    </ul>

    <h3 style="margin:0 0 8px 0;font-size:13px;color:#1d1d1f;">한계점</h3>
    <ul style="margin:0 0 18px 16px;padding:0;color:#666;">
      <li>현재 강남구 bbox 기반 → 서초구 일부 폴리곤 포함될 수 있음 (행정경계 정밀 필터 미적용)</li>
      <li>소유자 본인 식별 정보는 개인정보보호로 비공개. 구분(개인/법인/국공유 등) 만 제공</li>
      <li>도시계획 시설 지정은 실제 활용과 다를 수 있음 → 지목으로 실제 토지 용도 확인 필요</li>
    </ul>

    <div style="margin-top:18px;padding:10px;background:#f6f6f8;border-radius:8px;font-size:11px;color:#666;">
      🔁 생성 시각 기준 데이터 · V-World API 응답 그대로 사용
    </div>
  `;
  document.getElementById('methodology-overlay').style.display = 'flex';
}
document.getElementById('open-methodology').addEventListener('click', openMethodology);
document.getElementById('close-methodology').addEventListener('click', () => {
  document.getElementById('methodology-overlay').style.display = 'none';
});
document.getElementById('methodology-overlay').addEventListener('click', (e) => {
  if (e.target.id === 'methodology-overlay') {
    document.getElementById('methodology-overlay').style.display = 'none';
  }
});
// How-to modal
document.getElementById('open-howto').addEventListener('click', () => {
  document.getElementById('howto-overlay').style.display = 'flex';
});
document.getElementById('close-howto').addEventListener('click', () => {
  document.getElementById('howto-overlay').style.display = 'none';
});
document.getElementById('howto-overlay').addEventListener('click', (e) => {
  if (e.target.id === 'howto-overlay') {
    document.getElementById('howto-overlay').style.display = 'none';
  }
});

// Park type filter
const ptPanel = document.getElementById('park-type-filters');
PARK_CATS.forEach(c => {
  const count = PARK_TYPE_STATS[c] || 0;
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
    if (cb.checked) state.activeParkTypes.add(c);
    else state.activeParkTypes.delete(c);
    buildParksLayer();
  });
});

// Overlay toggles
document.getElementById('show-parks').addEventListener('change', e => {
  state.showParks = e.target.checked;
  buildParksLayer();
});
document.getElementById('show-empty-parks').addEventListener('change', e => {
  state.showEmpty = e.target.checked;
  buildParksLayer();
});
document.getElementById('show-labels').addEventListener('change', e => {
  state.showLabels = e.target.checked;
  if (state.showLabels) labelsLayer.addTo(map); else map.removeLayer(labelsLayer);
});
document.getElementById('show-parcels').addEventListener('change', e => {
  state.showParcels = e.target.checked;
  if (state.showParcels) { if (parcelLayer) parcelLayer.addTo(map); }
  else { if (parcelLayer) map.removeLayer(parcelLayer); }
});

// Tab switch — map vs list (right panel)
const mapWrap = document.querySelector('.map-wrap');
const rightPanel = document.getElementById('right-panel');
document.querySelectorAll('.tab').forEach(t => {
  t.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    const v = t.dataset.view;
    if (v === 'map') {
      rightPanel.classList.remove('open', 'expanded');
      mapWrap.classList.remove('hidden');
      state.expanded = false;
    } else {
      rightPanel.classList.add('open');
      renderList();
    }
    setTimeout(() => map.invalidateSize(), 100);
  });
});

// Expand button
document.getElementById('expand-btn').addEventListener('click', () => {
  state.expanded = !state.expanded;
  if (state.expanded) {
    rightPanel.classList.add('expanded');
    mapWrap.classList.add('hidden');
    document.getElementById('expand-btn').textContent = '축소 ⇲';
  } else {
    rightPanel.classList.remove('expanded');
    mapWrap.classList.remove('hidden');
    document.getElementById('expand-btn').textContent = '확장 ⇱';
    setTimeout(() => map.invalidateSize(), 100);
  }
  renderList();
});

// List rendering — both compact and table
const compactEl = document.getElementById('compact-list');
const tbody = document.querySelector('#table tbody');
const searchEl = document.getElementById('search');
const rowCount = document.getElementById('row-count');
let lastRows = [];

function rnFull(p) {
  if (!p.rn_nm) return '';
  return `${p.rn_nm} ${p.bld_mnnm||''}${p.bld_slno?'-'+p.bld_slno:''}`.trim();
}
function fmtNum(v) { return v ? Number(v).toLocaleString() : ''; }

function renderList() {
  const q = searchEl.value.trim().toLowerCase();
  const jset = activeJimokSet();
  let rows = PARCELS.features
    .map(f => f.properties)
    .filter(p => state.activeOwners.has(p.owner_type) && jset.has(p.jimok));
  if (q) rows = rows.filter(p =>
    (p.emd_nm||'').toLowerCase().includes(q) ||
    (p.jibun||'').toLowerCase().includes(q) ||
    (p.jimok||'').toLowerCase().includes(q) ||
    (p.rn_nm||'').toLowerCase().includes(q) ||
    (p.owner_type||'').toLowerCase().includes(q));
  if (state.sortKey) {
    rows.sort((a,b) => {
      let av, bv;
      if (state.sortKey === 'emd_jibun') { av = (a.emd_nm||'') + ' ' + (a.jibun||''); bv = (b.emd_nm||'') + ' ' + (b.jibun||''); }
      else if (state.sortKey === 'rn_full') { av = rnFull(a); bv = rnFull(b); }
      else { av = a[state.sortKey]||''; bv = b[state.sortKey]||''; }
      const an=parseFloat(av), bn=parseFloat(bv);
      if (!isNaN(an) && !isNaN(bn)) return (an-bn)*state.sortDir;
      return av.toString().localeCompare(bv.toString())*state.sortDir;
    });
  }
  lastRows = rows;
  const cap = state.expanded ? rows.length : Math.min(rows.length, 1000);
  rowCount.textContent = `${rows.length.toLocaleString()}건${cap < rows.length ? ' (상위 '+cap+'개 표시, 확장하면 전체 표시)' : ''}`;
  if (!state.expanded) renderCompact(rows.slice(0, cap));
  else renderTable(rows);
}

function groupByDistrict(rows) {
  const groups = new Map();
  for (const r of rows) {
    const key = `${r.sido_nm||'-'} ${r.sgg_nm||'-'}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(r);
  }
  return groups;
}

const collapsedGroups = new Set();

function renderCompact(rows) {
  const groups = groupByDistrict(rows);
  let html = '';
  let globalIdx = 0;
  for (const [groupKey, items] of groups) {
    const collapsed = collapsedGroups.has(groupKey);
    html += `
      <div class="group-header${collapsed?' collapsed':''}" data-group="${groupKey}">
        <span class="caret">▼</span>
        <span>${groupKey}</span>
        <span class="count">${items.length.toLocaleString()}건</span>
      </div>
      <div class="group-body${collapsed?' collapsed':''}" data-group="${groupKey}">
    `;
    for (const p of items) {
      globalIdx++;
      const m2 = parseFloat(p.parea)||parseFloat(p.area_m2)||0;
      const py = m2/PYEONG;
      const pricePerM = parseFloat(p.price_per_m2)||0;
      html += `
        <div class="pcard" data-pnu="${p.pnu}">
          <div class="num">${globalIdx}</div>
          <div class="body">
            <div class="head">${p.emd_nm||''} ${p.jibun||''}
              <span class="pill" style="background:${COLORS[p.owner_type]||'#888'}">${p.owner_type||'?'}</span>
            </div>
            <div class="addr">${p.sido_nm||''} ${p.sgg_nm||''}</div>
            <div class="meta">
              지목 <b>${p.jimok||'-'}</b> · 면적 <b>${m2 ? Math.round(m2).toLocaleString() : '-'} ㎡</b>
              (${py ? Math.round(py).toLocaleString() : '-'} 평)<br>
              공시지가 <b>${pricePerM ? pricePerM.toLocaleString() : '-'} 원/㎡</b>
            </div>
          </div>
        </div>
      `;
    }
    html += `</div>`;
  }
  compactEl.innerHTML = html;
  compactEl.querySelectorAll('.pcard').forEach(el => {
    el.addEventListener('click', () => focusParcel(el.dataset.pnu));
  });
  compactEl.querySelectorAll('.group-header').forEach(el => {
    el.addEventListener('click', () => toggleGroup(el.dataset.group));
  });
}

function toggleGroup(key) {
  if (collapsedGroups.has(key)) collapsedGroups.delete(key);
  else collapsedGroups.add(key);
  renderList();
}

function renderTable(rows) {
  const groups = groupByDistrict(rows);
  let html = '';
  let globalIdx = 0;
  for (const [groupKey, items] of groups) {
    const collapsed = collapsedGroups.has(groupKey);
    html += `<tr class="group-row${collapsed?' collapsed':''}" data-group="${groupKey}">
      <td colspan="8">
        <span style="font-size:10px;color:#888;">${collapsed?'▶':'▼'}</span>
        ${groupKey}
        <span class="count">${items.length.toLocaleString()}건</span>
      </td>
    </tr>`;
    if (collapsed) continue;
    for (const p of items) {
      globalIdx++;
      const m2 = parseFloat(p.parea)||parseFloat(p.area_m2)||0;
      const py = m2/PYEONG;
      const pricePerM = parseFloat(p.price_per_m2)||0;
      const pricePerPy = pricePerM*PYEONG;
      html += `
        <tr data-pnu="${p.pnu}">
          <td>${globalIdx}</td>
          <td>${p.emd_nm||''} ${p.jibun||''}</td>
          <td>${rnFull(p)||'-'}</td>
          <td>${p.jimok||'-'}</td>
          <td class="right">${m2 ? Math.round(m2).toLocaleString() : '-'} / ${py ? Math.round(py).toLocaleString() : '-'}</td>
          <td class="right">${pricePerM ? pricePerM.toLocaleString() : '-'} / ${pricePerPy ? Math.round(pricePerPy).toLocaleString() : '-'}</td>
          <td><span class="pill" style="background:${COLORS[p.owner_type]||'#888'}">${p.owner_type||'?'}</span></td>
          <td>${p.owner_subtype||''}</td>
        </tr>
      `;
    }
  }
  tbody.innerHTML = html;
  tbody.querySelectorAll('tr[data-pnu]').forEach(tr => {
    tr.addEventListener('click', () => focusParcel(tr.dataset.pnu));
  });
  tbody.querySelectorAll('tr.group-row').forEach(tr => {
    tr.addEventListener('click', () => toggleGroup(tr.dataset.group));
  });
  // Hide # column index header text since we now have group rows
}

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
    const k = th.dataset.sort;
    if (!k) return;
    if (state.sortKey === k) state.sortDir = -state.sortDir;
    else { state.sortKey = k; state.sortDir = 1; }
    document.querySelectorAll('th').forEach(x => x.classList.remove('sorted', 'desc'));
    th.classList.add('sorted');
    if (state.sortDir === -1) th.classList.add('desc');
    renderList();
  });
});

function downloadCsv() {
  const headers = ["순번","동","지번","도로명주소","지목","면적(㎡)","면적(평)","공시지가(원/㎡)","공시지가(원/평)","소유구분","세부"];
  const lines = ["\\ufeff" + headers.join(",")];
  lastRows.forEach((p, i) => {
    const m2 = parseFloat(p.area_m2)||0;
    const py = m2/PYEONG;
    const pricePerM = parseFloat(p.price_per_m2)||0;
    const pricePerPy = pricePerM*PYEONG;
    const row = [
      i+1, p.emd_nm||'', p.jibun||'', rnFull(p), p.jimok||'',
      m2.toFixed(1), py.toFixed(1),
      pricePerM, Math.round(pricePerPy),
      p.owner_type||'', p.owner_subtype||'',
    ];
    lines.push(row.map(v => {
      const s = (v??'').toString().replace(/"/g,'""');
      return /[,"\\n]/.test(s) ? `"${s}"` : s;
    }).join(","));
  });
  const blob = new Blob([lines.join("\\n")], {type:"text/csv"});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `gangnam-park-parcels-${new Date().toISOString().slice(0,10)}.csv`;
  a.click();
}

renderList();
</script>
</body>
</html>"""

html = (html
        .replace("__PARKS__", json.dumps(parks, ensure_ascii=False))
        .replace("__PARCELS__", json.dumps(parcels, ensure_ascii=False))
        .replace("__COLORS__", json.dumps(COLORS, ensure_ascii=False))
        .replace("__ORDER__", json.dumps(OWNER_ORDER, ensure_ascii=False))
        .replace("__STATS__", json.dumps(stats, ensure_ascii=False))
        .replace("__PARK_CATS__", json.dumps(PARK_CATS, ensure_ascii=False))
        .replace("__PARK_COLORS__", json.dumps(PARK_COLORS, ensure_ascii=False))
        .replace("__PARK_TYPE_STATS__", json.dumps(park_type_stats, ensure_ascii=False))
        .replace("__JIMOK_GROUPS__", json.dumps(JIMOK_GROUPS, ensure_ascii=False))
        .replace("__JIMOK_GROUP_COLORS__", json.dumps(JIMOK_GROUP_COLORS, ensure_ascii=False))
        .replace("__JIMOK_STATS__", json.dumps(jimok_stats, ensure_ascii=False))
        .replace("__TOTAL__", f"{total:,}")
        .replace("__PRIV__", f"{private_total:,}")
        .replace("__PCT__", str(pct)))

OUT.write_text(html, encoding="utf-8")
print(f"✅ map written: {OUT}  ({OUT.stat().st_size//1024} KB)")
print(f"   total: {total}, private: {private_total} ({pct}%)")
