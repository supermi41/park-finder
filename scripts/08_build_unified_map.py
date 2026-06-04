#!/usr/bin/env python3
"""
Stage 8 — Unified map builder.
Produces map.html: MapLibre + PMTiles map + right-side list panel.
- Map: vector tiles (fast, small initial download)
- List: lazy-loaded parcels.json on first 목록 tab click
- Filters: apply to both map (setFilter) and list (re-render)
- Excel: SheetJS download
- Modals: 사용법 + 매칭 기준
- Jump buttons: 등기부 / 토지이용 / 주소복사
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUB = ROOT / "public"
OUT_HTML = ROOT / "map.html"
# Also write index.html for static hosts that default to index.html
OUT_INDEX = ROOT / "index.html"

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


def main():
    stats = json.loads((PUB / "stats.json").read_text())
    total = stats.get("total_parcels", 0)
    private_total = stats.get("private_total", 0)
    pct = stats.get("private_pct", 0)

    html = HTML
    for k, v in {
        "__TOTAL__": f"{total:,}",
        "__PRIVATE__": f"{private_total:,}",
        "__PCT__": str(pct),
        "__OWNER_ORDER__": json.dumps(OWNER_ORDER, ensure_ascii=False),
        "__COLORS__": json.dumps(COLORS, ensure_ascii=False),
        "__PARK_CATS__": json.dumps(PARK_CATS, ensure_ascii=False),
        "__PARK_COLORS__": json.dumps(PARK_COLORS, ensure_ascii=False),
        "__JIMOK_GROUPS__": json.dumps(JIMOK_GROUPS, ensure_ascii=False),
        "__JIMOK_GROUP_COLORS__": json.dumps(JIMOK_GROUP_COLORS, ensure_ascii=False),
        "__STATS__": json.dumps(stats, ensure_ascii=False),
    }.items():
        html = html.replace(k, v)

    OUT_HTML.write_text(html, encoding="utf-8")
    OUT_INDEX.write_text(html, encoding="utf-8")
    print(f"✅ {OUT_HTML.name} / {OUT_INDEX.name}  ({OUT_HTML.stat().st_size // 1024} KB)")


HTML = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>핀파인더 · 전국 공원지정 사유지</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css">
<link rel="manifest" href="manifest.json">
<meta name="theme-color" content="#1d1d1f">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="핀파인더">
<link rel="apple-touch-icon" href="icon-192.png">
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
       text-transform:uppercase; letter-spacing:0.5px; display:flex; align-items:center; gap:8px; }
  .filter-row { display:flex; align-items:center; gap:8px; padding:4px;
                font-size:13px; cursor:pointer; user-select:none; border-radius:5px; }
  .filter-row:hover { background:#f6f6f8; }
  .chip { width:12px; height:12px; border-radius:3px; flex-shrink:0; }
  .filter-row .count { margin-left:auto; color:#86868b; font-size:11px; font-weight:500; }
  .toggle-all { font-size:11px; color:#0071e3; cursor:pointer; user-select:none; font-weight:500; }
  .sido-block { border-bottom:1px solid #f0f0f3; }
  .sido-head { display:flex; align-items:center; gap:6px; padding:6px 4px; cursor:pointer;
               user-select:none; font-size:12px; font-weight:600; color:#1d1d1f; }
  .sido-head:hover { background:#f6f6f8; }
  .sido-head .caret { font-size:9px; color:#888; transition:transform 0.15s; }
  .sido-head.collapsed .caret { transform:rotate(-90deg); }
  .sido-head input[type=checkbox] { margin:0; }
  .sido-head .count { margin-left:auto; color:#86868b; font-size:10.5px; font-weight:500; }
  .sido-body { padding-left:18px; }
  .sido-body.collapsed { display:none; }
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
  .icon-btn { padding:6px 10px; background:#f0f0f3; color:#333;
              border:none; border-radius:6px; font-size:12px; cursor:pointer; font-weight:500; }
  .icon-btn.primary { background:#0071e3; color:#fff; }
  .icon-btn:hover { filter:brightness(0.96); }
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
                    font-weight:700; font-size:12px; padding:8px 10px; color:#1d1d1f; cursor:pointer; }
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
  .maplibregl-popup-content {
    font-size:12px; line-height:1.5; min-width:240px; border-radius:8px; padding:14px;
  }
  .modal-bg { display:none; position:fixed; inset:0; background:rgba(0,0,0,0.5); z-index:5000;
              align-items:center; justify-content:center; }
  .modal-box { background:#fff; width:560px; max-width:92vw; max-height:85vh; overflow:auto;
               border-radius:14px; box-shadow:0 20px 60px rgba(0,0,0,0.3); }
  .modal-head { display:flex; justify-content:space-between; align-items:center;
                padding:18px 22px; border-bottom:1px solid #e5e5ea; }
  .modal-head h2 { margin:0; font-size:16px; font-weight:700; text-transform:none; letter-spacing:0; }
  .modal-body { padding:22px; font-size:13px; line-height:1.65; color:#333; }
  .modal-close { border:none; background:transparent; font-size:20px; cursor:pointer; color:#888; }
  .hamburger { display:none; background:transparent; border:none; padding:6px 8px; font-size:18px;
               cursor:pointer; color:#1d1d1f; margin-right:8px; }
  .sidebar-backdrop { display:none; position:fixed; inset:48px 0 0 0; background:rgba(0,0,0,0.4); z-index:999; }
  .sidebar-backdrop.open { display:block; }
  /* Mobile (≤768px) */
  @media (max-width: 768px) {
    .hamburger { display:inline-block; }
    .brand h1 { font-size:14px; }
    .brand .sub { display:none; }
    header { padding:8px 12px; }
    .tab { padding:5px 10px; font-size:12px; }
    .sidebar {
      position:fixed; left:-280px; top:48px; bottom:0; width:260px; z-index:1000;
      transition:left 0.22s ease; box-shadow:2px 0 14px rgba(0,0,0,0.15);
    }
    .sidebar.open { left:0; }
    .main-wrap { width:100%; }
    .right-panel { position:fixed; inset:48px 0 0 0; width:100%; z-index:998; }
    .right-panel.open { display:flex; }
    .right-panel.expanded { inset:48px 0 0 0; }
    .map-wrap.hidden { display:none; }
    .pcard .head { font-size:14px; }
    .pcard .meta { font-size:12.5px; }
    .filter-row { padding:8px 4px; font-size:14px; }
    .filter-row input[type=checkbox] { transform:scale(1.2); }
    .icon-btn { padding:8px 12px; font-size:13px; }
    .toolbar input { padding:9px 10px; font-size:14px; }
    .modal-box { width:96vw; max-height:90vh; border-radius:10px; }
    .modal-head { padding:14px 16px; }
    .modal-body { padding:16px; font-size:13px; }
    /* Stat card lighter on small screens */
    .stat-card .big { font-size:24px; }
    /* Map controls (top-right) bigger touch */
    .maplibregl-ctrl-group button { width:36px; height:36px; }
  }
</style>
</head>
<body>
<header>
  <div class="brand">
    <button type="button" class="hamburger" id="hamburger-btn" aria-label="필터 메뉴">☰</button>
    <span style="font-size:18px;">📍</span>
    <h1>핀파인더 · 전국</h1>
    <span class="sub">공원지정 필지 · 출처 V-World</span>
  </div>
  <div style="display:flex;gap:8px;align-items:center;">
    <button type="button" id="open-howto" class="tab" style="background:#f0fbf2;color:#2f8a3a;font-weight:600;">💡 사용법</button>
    <button type="button" id="open-methodology" class="tab" style="background:#f4f4f9;color:#0071e3;font-weight:600;">📋 매칭 기준</button>
    <div class="tabs">
      <button type="button" class="tab active" data-view="map">지도</button>
      <button type="button" class="tab" data-view="list">목록 (__TOTAL__)</button>
    </div>
  </div>
</header>

<!-- Methodology modal -->
<div class="modal-bg" id="methodology-overlay">
  <div class="modal-box">
    <div class="modal-head"><h2>📋 매칭 기준 · 데이터 출처</h2>
      <button type="button" class="modal-close" id="close-methodology">✕</button></div>
    <div class="modal-body" id="methodology-body"></div>
  </div>
</div>
<div class="modal-bg" id="howto-overlay">
  <div class="modal-box">
    <div class="modal-head"><h2>💡 사용법 · 목적별 필터 가이드</h2>
      <button type="button" class="modal-close" id="close-howto">✕</button></div>
    <div class="modal-body">
      <div style="background:#fef9e7;padding:14px;border-radius:8px;border:1px solid #f6d860;margin-bottom:20px;font-size:12.5px;">
        🎯 도시계획상 공원이지만 소유주가 개인/법인인 필지 (장기미집행 사유지) 매핑
      </div>
      <h3 style="margin:0 0 8px 0;">🔍 추천 흐름</h3>
      <ol style="margin:0 0 16px 18px;padding:0;">
        <li>자치구 선택 + 도로/시설·공공/기타 끄기</li>
        <li>소유 구분 [사유지만]</li>
        <li>[목록] 탭 → 평수 또는 공시지가 정렬</li>
        <li>행 클릭 → 지도로 점프</li>
        <li>[Excel] 다운로드해서 엑셀 분석</li>
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

<div class="sidebar-backdrop" id="sidebar-backdrop"></div>
<div class="layout">
  <aside class="sidebar" id="sidebar">
    <div class="stat-card">
      <div class="big">__PCT__%</div>
      <div class="label">전국 __TOTAL__건 중 사유지 __PRIVATE__건</div>
    </div>
    <button type="button" id="preset-litigation" style="width:100%;padding:10px;margin-bottom:14px;background:linear-gradient(135deg,#0071e3,#0058b3);color:#fff;border:none;border-radius:10px;font-size:13px;cursor:pointer;font-weight:700;box-shadow:0 2px 8px rgba(0,113,227,0.25);">
      🎯 수용청구 후보 (원클릭)
      <div style="font-size:10.5px;font-weight:500;opacity:0.9;margin-top:3px;">사유지 · 자연/녹지·공원 · 대 제외</div>
    </button>
    <h2>소유 구분
      <span class="toggle-all" id="toggle-all" style="margin-left:auto;">전체</span>
      <span class="toggle-all" id="only-private">사유지만</span></h2>
    <div id="owner-filters"></div>
    <h2>자치구 (시·도 클릭하여 펼침)
      <span class="toggle-all" id="sgg-all" style="margin-left:auto;">전체</span>
      <span class="toggle-all" id="sgg-none" style="margin-left:4px;">해제</span></h2>
    <div id="sgg-filters" style="max-height:260px;overflow-y:auto;border:1px solid #e5e5ea;border-radius:6px;padding:4px 6px;"></div>
    <h2>공원 시설 유형</h2>
    <div id="park-type-filters"></div>

    <h2>
      결정일 / 일몰
      <span class="toggle-all" id="sunset-reset" style="margin-left:auto;">초기화</span>
    </h2>
    <div style="padding:4px;">
      <div style="display:flex;justify-content:space-between;font-size:11px;color:#666;margin-bottom:4px;">
        <span>결정 후</span>
        <span><b id="years-label" style="color:#e63946;">0년+</b></span>
      </div>
      <input type="range" id="years-slider" min="0" max="30" step="1" value="0" style="width:100%;">
      <div style="font-size:10.5px;color:#888;margin-top:6px;display:flex;justify-content:space-between;">
        <span>전체</span>
        <span>10년+</span>
        <span style="color:#e63946;font-weight:600;">20년+ (일몰)</span>
        <span>30년+</span>
      </div>
      <label class="filter-row" style="margin-top:8px;">
        <input type="checkbox" id="include-unknown-date" checked>
        <span style="font-size:12px;">결정일 미상도 포함</span>
      </label>
    </div>
    <h2>지목 그룹
      <span class="toggle-all" id="jimok-all" style="margin-left:auto;">전체</span>
      <span class="toggle-all" id="jimok-natural">자연만</span></h2>
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
        <div id="loading-text">지도 로딩...</div>
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
        <span id="row-count" style="font-size:11px;color:#86868b;"></span>
        <button type="button" id="showAllBtn" style="display:none;padding:4px 10px;background:#1d1d1f;color:#fff;border:none;border-radius:5px;font-size:11px;cursor:pointer;font-weight:600;">전체보기</button>
      </div>
      <div class="compact-list" id="compact-list">
        <div id="listLoading" style="padding:30px;text-align:center;color:#888;font-size:12px;display:none;">
          <div class="spinner" style="margin:0 auto 10px;"></div>
          목록 데이터 로딩 중 (38MB)...
        </div>
      </div>
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
            <button type="button" id="loadMoreBtn" style="padding:8px 20px;background:#0071e3;color:#fff;border:none;border-radius:6px;font-size:13px;cursor:pointer;font-weight:600;">더 보기</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>

<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<script src="https://unpkg.com/pmtiles@3.0.7/dist/pmtiles.js"></script>
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
const PAGE_SIZE = 2000;

const state = {
  activeOwners: new Set(ORDER),
  activeParkTypes: new Set(PARK_CATS),
  activeJimokGroups: new Set(Object.keys(JIMOK_GROUPS)),
  activeSggs: new Set(),
  showParks: true, showParcels: true,
  expanded: false, sortKey: null, sortDir: 1, displayedRows: PAGE_SIZE,
  minYearsSince: 0, includeUnknownDate: true,
};
function activeJimokSet() {
  const s = new Set();
  for (const g of state.activeJimokGroups) (JIMOK_GROUPS[g]||[]).forEach(j => s.add(j));
  return s;
}

// Lazy parcels storage for list view
let PARCELS_LIST = null;
let lastRows = [];
const collapsedGroups = new Set();

// PMTiles
const protocol = new pmtiles.Protocol();
maplibregl.addProtocol('pmtiles', protocol.tile);
// PMTiles host: localhost → local files; prod → GitHub Pages (Range supported, no 50MB cap).
const IS_LOCAL = ['localhost','127.0.0.1','0.0.0.0'].includes(location.hostname);
const PMTILES_BASE = IS_LOCAL ? 'tiles' : 'https://supermi41.github.io/park-finder/tiles';
const PARCELS_URL = window.PARCELS_PMTILES_URL || `${PMTILES_BASE}/parcels.pmtiles`;
const PARKS_URL = window.PARKS_PMTILES_URL || `${PMTILES_BASE}/parks.pmtiles`;

const BASEMAPS = {
  light:    { name:'라이트',  tiles:['https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png'], attr:'© CartoDB' },
  osm:      { name:'OSM',    tiles:['https://a.tile.openstreetmap.org/{z}/{x}/{y}.png'], attr:'© OSM' },
  dark:     { name:'다크',    tiles:['https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png'], attr:'© CartoDB' },
  satellite:{ name:'위성',    tiles:['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'], attr:'© Esri' },
  voyager:  { name:'보이저',  tiles:['https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png'], attr:'© CartoDB' },
};
let currentBasemap = 'light';

const map = new maplibregl.Map({
  container: 'map',
  style: {
    version: 8,
    sources: {
      osm: { type:'raster', tiles: BASEMAPS.light.tiles, tileSize:256, attribution: BASEMAPS.light.attr },
      parks: { type:'vector', url:'pmtiles://' + PARKS_URL },
      parcels: { type:'vector', url:'pmtiles://' + PARCELS_URL }
    },
    layers: [{ id:'base', type:'raster', source:'osm' }]
  },
  center:[126.98, 37.55], zoom:11, maxZoom:18, minZoom:8
});

function switchBasemap(key) {
  if (key === currentBasemap) return;
  const cfg = BASEMAPS[key];
  const src = map.getSource('osm');
  if (src && src.setTiles) {
    src.setTiles(cfg.tiles);
    currentBasemap = key;
  }
}

const basemapPicker = document.getElementById('basemap-picker');
Object.entries(BASEMAPS).forEach(([key, cfg]) => {
  const div = document.createElement('label');
  div.className = 'filter-row';
  div.innerHTML = `
    <input type="radio" name="basemap" value="${key}" ${key===currentBasemap?'checked':''}>
    <span>${cfg.name}</span>
  `;
  div.querySelector('input').addEventListener('change', () => switchBasemap(key));
  basemapPicker.appendChild(div);
});
map.addControl(new maplibregl.NavigationControl(), 'top-left');

function ownerFilter() {
  const a = Array.from(state.activeOwners);
  return a.length === 0 ? ['==', ['get','owner_type'], '__none__'] : ['in', ['get','owner_type'], ['literal', a]];
}
function jimokFilterExpr() {
  const a = Array.from(activeJimokSet());
  return a.length === 0 ? ['==', ['get','jimok'], '__none__'] : ['in', ['get','jimok'], ['literal', a]];
}
function sggFilter() {
  const active = Array.from(state.activeSggs);
  if (active.length === 0) return ['==', ['get','sgg_nm'], '__none__'];
  // Group active composite keys by sido: avoid concat in filter (some MapLibre versions buggy)
  const bySido = {};
  for (const k of active) {
    const idx = k.indexOf(' ');
    if (idx < 0) continue;
    const sido = k.substring(0, idx);
    const sgg = k.substring(idx + 1);
    (bySido[sido] = bySido[sido] || []).push(sgg);
  }
  const clauses = Object.entries(bySido).map(([sido, sggs]) =>
    ['all', ['==', ['get','sido_nm'], sido], ['in', ['get','sgg_nm'], ['literal', sggs]]]
  );
  if (clauses.length === 0) return ['==', ['get','sgg_nm'], '__none__'];
  if (clauses.length === 1) return clauses[0];
  return ['any', ...clauses];
}
function parkCatFilter() {
  const a = Array.from(state.activeParkTypes);
  return a.length === 0 ? ['==', ['get','park_cat'], '__none__'] : ['in', ['get','park_cat'], ['literal', a]];
}
function dateFilter() {
  if (state.minYearsSince === 0) return ['==', 0, 0]; // always true
  const currentYear = (new Date()).getFullYear();
  const cutoff = currentYear - state.minYearsSince;
  if (state.includeUnknownDate) {
    return ['any',
      ['==', ['get', 'park_decision_year'], 0],
      ['all',
        ['>', ['get', 'park_decision_year'], 0],
        ['<=', ['get', 'park_decision_year'], cutoff]
      ]
    ];
  }
  return ['all',
    ['>', ['get', 'park_decision_year'], 0],
    ['<=', ['get', 'park_decision_year'], cutoff]
  ];
}
function combinedParcelFilter() {
  return ['all', ownerFilter(), jimokFilterExpr(), sggFilter(), dateFilter()];
}
function parcelColorExpr() {
  const e = ['match', ['get','owner_type']];
  for (const [k,v] of Object.entries(COLORS)) { if (k==='?') continue; e.push(k,v); }
  e.push('#888'); return e;
}
function parkColorExpr() {
  const e = ['match', ['get','park_cat']];
  for (const [k,v] of Object.entries(PARK_COLORS)) e.push(k,v);
  e.push('#cccccc'); return e;
}

map.on('load', async () => {
  // Districts (자치구 경계) — small GeoJSON, load directly
  try {
    const d = await (await fetch('public/districts.json')).json();
    map.addSource('districts', { type:'geojson', data:d });
    map.addLayer({ id:'districts-line', source:'districts', type:'line',
      paint:{ 'line-color':'#1d3557', 'line-width':1.2, 'line-dasharray':[3,2] } });
  } catch(e) { console.warn('districts load failed:', e); }

  map.addLayer({ id:'parks-fill', source:'parks', 'source-layer':'parks', type:'fill',
    paint:{ 'fill-color': parkColorExpr(), 'fill-opacity':0.25, 'fill-outline-color':'#2a9d8f' },
    filter: parkCatFilter() });
  map.addLayer({ id:'parks-outline', source:'parks', 'source-layer':'parks', type:'line',
    paint:{ 'line-color':'#2a9d8f', 'line-width':0.5 }, filter: parkCatFilter() });
  // v10: parcels-fill with color-by-owner, NO sgg/jimok filter (only 'has pnu')
  map.addLayer({ id:'parcels-fill', source:'parcels', 'source-layer':'parcels', type:'fill',
    paint:{ 'fill-color': parcelColorExpr(), 'fill-opacity':0.55, 'fill-outline-color':'#222' },
    filter: ['has', 'pnu'] });

  map.on('click', 'parcels-fill', (e) => {
    if (!e.features || !e.features[0]) return;
    const p = e.features[0].properties;
    new maplibregl.Popup({ maxWidth:'320px' })
      .setLngLat(e.lngLat).setHTML(buildPopup(p)).addTo(map);
  });
  map.on('mouseenter','parcels-fill',()=>{ map.getCanvas().style.cursor='pointer'; });
  map.on('mouseleave','parcels-fill',()=>{ map.getCanvas().style.cursor=''; });

  document.getElementById('loading').style.display = 'none';
});

function buildCleanAddr(p) {
  const jimok = (p.jimok || '').trim();
  let jibun = (p.jibun || '').trim();
  if (jimok && jibun.endsWith(jimok) && /\d$/.test(jibun.slice(0, -jimok.length))) {
    jibun = jibun.slice(0, -jimok.length);
  }
  return `${p.sido_nm||''} ${p.sgg_nm||''} ${p.emd_nm||''} ${jibun}`.replace(/\s+/g,' ').trim();
}
function rnFull(p){ if (!p.rn_nm) return ''; return `${p.rn_nm} ${p.bld_mnnm||''}`.trim(); }

function buildPopup(p) {
  const m2 = parseFloat(p.parea)||parseFloat(p.area_m2)||0;
  const py = m2/PYEONG;
  const pricePerM = parseFloat(p.price_per_m2)||0;
  const pricePerPy = pricePerM*PYEONG;
  const addr = buildCleanAddr(p).replace(/'/g,'');
  const decYear = parseInt(p.park_decision_year||0, 10);
  const now = (new Date()).getFullYear();
  let sunsetLine = '';
  if (decYear > 0) {
    const elapsed = now - decYear;
    const sunsetIn = 20 - elapsed;
    if (sunsetIn <= 0) sunsetLine = `<span style="color:#e63946;font-weight:600;">⚠️ 일몰 대상 (${decYear}년 결정, ${elapsed}년 경과)</span><br>`;
    else if (sunsetIn <= 5) sunsetLine = `<span style="color:#f4a261;font-weight:600;">🟡 일몰 ${sunsetIn}년 남음 (${decYear}년 결정)</span><br>`;
    else sunsetLine = `<small style="color:#888;">${decYear}년 결정 · 일몰까지 ${sunsetIn}년</small><br>`;
  }
  return `
    <b>${p.sgg_nm || ''} ${p.emd_nm || ''} ${p.jibun || ''}</b><br>
    ${p.matched_park_name ? `📍 <b>${p.matched_park_name}</b> <small style="color:#888;">(${p.matched_park_type||''} · 겹침 ${p.match_overlap_pct||'?'}%)</small><br>` : ''}
    ${sunsetLine}
    소유: <b style="color:${COLORS[p.owner_type] || '#000'}">${p.owner_type || '?'}</b>
      <small>(${p.owner_subtype || ''})</small><br>
    지목: ${p.jimok || '?'}<br>
    면적: ${m2 ? Math.round(m2).toLocaleString() : '?'} ㎡ (${py ? Math.round(py).toLocaleString() : '?'} 평)<br>
    공시지가: ${pricePerM ? pricePerM.toLocaleString() : '?'} 원/㎡
      (${pricePerPy ? Math.round(pricePerPy).toLocaleString() : '?'} 원/평)<br>
    <small style="color:#888;">PNU: ${p.pnu}</small>
    <div style="margin-top:10px;padding-top:10px;border-top:1px solid #eee;display:flex;gap:4px;flex-wrap:wrap;">
      <button onclick="jumpIros('${p.pnu}','${addr}')" style="flex:1;min-width:80px;padding:5px 8px;background:#0071e3;color:#fff;border:none;border-radius:5px;font-size:11px;cursor:pointer;font-weight:600;">📜 등기부</button>
      <button onclick="jumpEum('${p.pnu}')" style="flex:1;min-width:80px;padding:5px 8px;background:#2f8a3a;color:#fff;border:none;border-radius:5px;font-size:11px;cursor:pointer;font-weight:600;">🗺 토지이용</button>
      <button onclick="copyAddr('${addr}')" style="flex:1;min-width:80px;padding:5px 8px;background:#f4f4f9;color:#333;border:1px solid #d0d0d5;border-radius:5px;font-size:11px;cursor:pointer;">📋 복사</button>
    </div>
  `;
}

function jumpIros(pnu, addr) {
  const clean = addr.replace(/\s*PNU[: ].*$/i,'').trim();
  navigator.clipboard.writeText(clean).catch(()=>{});
  alert('주소 복사됨:\n' + clean + '\n\niros.go.kr "소재지번검색" 탭에서 붙여넣기');
  window.open('http://www.iros.go.kr/index.jsp', '_blank');
}
function jumpEum(pnu) { window.open(`https://www.eum.go.kr/web/am/amMain.jsp?pnu=${pnu}`, '_blank'); }
function copyAddr(addr) { navigator.clipboard.writeText(addr).then(()=> alert('주소 복사됨:\n' + addr)); }

function updateMapFilters() {
  if (!map.getLayer('parcels-fill')) return;
  map.setFilter('parcels-fill', combinedParcelFilter());
  map.setFilter('parks-fill', parkCatFilter());
  map.setFilter('parks-outline', parkCatFilter());
}

// ---- List handling (lazy) ----
const compactEl = document.getElementById('compact-list');
const tbody = document.querySelector('#table tbody');
const searchEl = document.getElementById('search');
const rowCount = document.getElementById('row-count');
const listLoading = document.getElementById('listLoading');

async function ensureParcelsLoaded() {
  if (PARCELS_LIST) return;
  listLoading.style.display = 'block';
  compactEl.style.opacity = '0.5';
  try {
    // Try manifest-based chunked load first; fall back to single file
    let chunks = null;
    try {
      const m = await fetch('public/parcels-manifest.json');
      if (m.ok) chunks = (await m.json()).chunks;
    } catch(_) {}
    if (chunks && chunks.length) {
      const results = await Promise.all(chunks.map(name =>
        fetch('public/' + name).then(r => r.json())
      ));
      PARCELS_LIST = [];
      for (const r of results) PARCELS_LIST.push(...r.features.map(f => f.properties));
    } else {
      const j = await (await fetch('public/parcels.json')).json();
      PARCELS_LIST = j.features.map(f => f.properties);
    }
  } catch(e) {
    alert('parcels 로드 실패: ' + e.message);
    PARCELS_LIST = [];
  }
  listLoading.style.display = 'none';
  compactEl.style.opacity = '1';
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
  if (!PARCELS_LIST) {
    rowCount.textContent = '로딩 대기';
    return;
  }
  const q = searchEl.value.trim().toLowerCase();
  const jset = activeJimokSet();
  const cutoffYear = (new Date()).getFullYear() - state.minYearsSince;
  let rows = PARCELS_LIST.filter(p => {
    const sggKey = `${p.sido_nm||''} ${p.sgg_nm||''}`;
    if (!(state.activeOwners.has(p.owner_type) && jset.has(p.jimok) && state.activeSggs.has(sggKey))) return false;
    if (state.minYearsSince > 0) {
      const py = p.park_decision_year || 0;
      if (py === 0) return state.includeUnknownDate;
      if (py > cutoffYear) return false;
    }
    return true;
  });
  if (q) rows = rows.filter(p =>
    (p.emd_nm||'').toLowerCase().includes(q) ||
    (p.jibun||'').toLowerCase().includes(q) ||
    (p.jimok||'').toLowerCase().includes(q) ||
    (p.rn_nm||'').toLowerCase().includes(q) ||
    (p.sgg_nm||'').toLowerCase().includes(q));
  if (state.sortKey) {
    rows.sort((a,b) => {
      let av,bv;
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
    if (state.displayedRows < PAGE_SIZE) state.displayedRows = PAGE_SIZE;
    const cap = Math.min(rows.length, state.displayedRows);
    rowCount.textContent = `${rows.length.toLocaleString()}건 ${cap < rows.length ? '(상위 '+cap.toLocaleString()+')' : '(전체)'}`;
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
        ? `<div style="font-size:11.5px;color:#2a9d8f;margin-bottom:3px;">📍 <b>${p.matched_park_name}</b> <small style="color:#888;">${p.match_overlap_pct||'?'}%</small></div>` : '';
      const addr = buildCleanAddr(p).replace(/'/g,'');
      const jumpBtns = `<div style="margin-top:6px;display:flex;gap:4px;">
        <button onclick="event.stopPropagation();jumpIros('${p.pnu}','${addr}')" style="padding:3px 8px;background:#0071e3;color:#fff;border:none;border-radius:4px;font-size:10.5px;cursor:pointer;font-weight:600;">📜 등기부</button>
        <button onclick="event.stopPropagation();jumpEum('${p.pnu}')" style="padding:3px 8px;background:#2f8a3a;color:#fff;border:none;border-radius:4px;font-size:10.5px;cursor:pointer;font-weight:600;">🗺 토지이용</button>
        <button onclick="event.stopPropagation();copyAddr('${addr}')" style="padding:3px 8px;background:#f4f4f9;color:#333;border:1px solid #d0d0d5;border-radius:4px;font-size:10.5px;cursor:pointer;">📋</button>
      </div>`;
      html += `<div class="pcard" data-pnu="${p.pnu}"><div class="num">${idx}</div><div class="body">
        <div class="head">${p.emd_nm||''} ${p.jibun||''}
          <span class="pill" style="background:${COLORS[p.owner_type]||'#888'}">${p.owner_type||'?'}</span></div>
        <div class="addr">${p.sido_nm||''} ${p.sgg_nm||''}</div>
        ${parkLine}
        <div class="meta">지목 <b>${p.jimok||'-'}</b> · 면적 <b>${m2?Math.round(m2).toLocaleString():'-'} ㎡</b> (${py?Math.round(py).toLocaleString():'-'} 평)<br>
        공시지가 <b>${pricePerM?pricePerM.toLocaleString():'-'} 원/㎡</b></div>
        ${jumpBtns}</div></div>`;
    }
    html += '</div>';
  }
  compactEl.innerHTML = html;
  compactEl.querySelectorAll('.pcard').forEach(el => el.addEventListener('click', () => focusParcel(el.dataset.pnu)));
  compactEl.querySelectorAll('.group-header').forEach(el => el.addEventListener('click', () => toggleGroup(el.dataset.group)));
}

function renderTable(rows) {
  const groups = groupByDistrict(rows);
  let html = '', idx = 0;
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
        ? `<span style="color:#2a9d8f;font-weight:600;">${p.matched_park_name}</span> <small style="color:#888;">${p.match_overlap_pct||'?'}%</small>` : '-';
      const addr = buildCleanAddr(p).replace(/'/g,'');
      const jumpCell = `<button onclick="event.stopPropagation();jumpIros('${p.pnu}','${addr}')" title="등기부" style="padding:2px 6px;background:#0071e3;color:#fff;border:none;border-radius:4px;font-size:10px;cursor:pointer;margin-right:2px;">📜</button><button onclick="event.stopPropagation();jumpEum('${p.pnu}')" title="토지이용" style="padding:2px 6px;background:#2f8a3a;color:#fff;border:none;border-radius:4px;font-size:10px;cursor:pointer;margin-right:2px;">🗺</button><button onclick="event.stopPropagation();copyAddr('${addr}')" title="복사" style="padding:2px 6px;background:#f4f4f9;color:#333;border:1px solid #d0d0d5;border-radius:4px;font-size:10px;cursor:pointer;">📋</button>`;
      const areaCell = m2 ? `${Math.round(m2).toLocaleString()} ㎡<br><small style="color:#888;">${Math.round(py).toLocaleString()} 평</small>` : '-';
      const priceCell = pricePerM ? `${pricePerM.toLocaleString()} 원/㎡<br><small style="color:#888;">${Math.round(pricePerPy).toLocaleString()} 원/평</small>` : '-';
      html += `<tr data-pnu="${p.pnu}"><td>${idx}</td><td>${p.emd_nm||''} ${p.jibun||''}</td><td>${parkCell}</td><td>${rnFull(p)||'-'}</td><td>${p.jimok||'-'}</td><td class="right">${areaCell}</td><td class="right">${priceCell}</td><td><span class="pill" style="background:${COLORS[p.owner_type]||'#888'}">${p.owner_type||'?'}</span></td><td>${p.owner_subtype||''}</td><td>${jumpCell}</td></tr>`;
    }
  }
  tbody.innerHTML = html;
  tbody.querySelectorAll('tr[data-pnu]').forEach(tr => tr.addEventListener('click', () => focusParcel(tr.dataset.pnu)));
  tbody.querySelectorAll('tr.group-row').forEach(tr => tr.addEventListener('click', () => toggleGroup(tr.dataset.group)));
}

function focusParcel(pnu) {
  if (!PARCELS_LIST) return;
  const p = PARCELS_LIST.find(x => x.pnu === pnu);
  if (!p) return;
  if (state.expanded) {
    state.expanded = false;
    document.getElementById('right-panel').classList.remove('expanded');
    document.querySelector('.map-wrap').classList.remove('hidden');
    document.getElementById('expand-btn').textContent = '⇱ 확장';
    setTimeout(() => map.resize(), 50);
  }
  // We don't have parcel geometry centroid in list data — open popup at sgg center or use search
  // Best effort: zoom into the sgg, user can click
  alert(`${buildCleanAddr(p)}\n\n지도 클릭으로 더 자세히`);
}

// ---- Tabs / sidebar / events ----
const mapWrap = document.querySelector('.map-wrap');
const rightPanel = document.getElementById('right-panel');
document.querySelectorAll('.tab[data-view]').forEach(t => {
  t.addEventListener('click', async () => {
    document.querySelectorAll('.tab[data-view]').forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    const v = t.dataset.view;
    if (v === 'map') {
      rightPanel.classList.remove('open','expanded');
      mapWrap.classList.remove('hidden');
      state.expanded = false;
    } else {
      rightPanel.classList.add('open');
      await ensureParcelsLoaded();
      renderList();
    }
    setTimeout(() => map.resize(), 100);
  });
});
document.getElementById('expand-btn').addEventListener('click', () => {
  state.expanded = !state.expanded;
  if (state.expanded) {
    rightPanel.classList.add('expanded'); mapWrap.classList.add('hidden');
    document.getElementById('expand-btn').textContent = '⇲ 축소';
  } else {
    rightPanel.classList.remove('expanded'); mapWrap.classList.remove('hidden');
    document.getElementById('expand-btn').textContent = '⇱ 확장';
    setTimeout(() => map.resize(), 100);
  }
  renderList();
});
document.getElementById('loadMoreBtn').addEventListener('click', () => {
  state.displayedRows += PAGE_SIZE; renderList();
});
document.getElementById('showAllBtn').addEventListener('click', () => {
  if (!confirm(`전체 ${lastRows.length.toLocaleString()}건 한 번에 렌더링합니다. 계속할까요?`)) return;
  state.displayedRows = lastRows.length; renderList();
});

// Owner filters
const ownerPanel = document.getElementById('owner-filters');
ORDER.forEach(ot => {
  const count = STATS.owner_counts[ot] || 0;
  if (count === 0) return;
  const div = document.createElement('label');
  div.className = 'filter-row';
  div.innerHTML = `
    <input type="checkbox" checked data-owner="${ot}">
    <span class="chip" style="background:${COLORS[ot] || '#888'}"></span>
    <span>${ot}</span>
    <span class="count">${count.toLocaleString()}</span>`;
  ownerPanel.appendChild(div);
});
ownerPanel.querySelectorAll('input').forEach(cb => {
  cb.addEventListener('change', () => {
    const ot = cb.dataset.owner;
    if (cb.checked) state.activeOwners.add(ot); else state.activeOwners.delete(ot);
    updateMapFilters(); renderList();
  });
});
document.getElementById('toggle-all').addEventListener('click', () => {
  const allOn = ORDER.every(o => state.activeOwners.has(o));
  if (allOn) { state.activeOwners.clear(); ownerPanel.querySelectorAll('input').forEach(cb => cb.checked = false); }
  else { state.activeOwners = new Set(ORDER); ownerPanel.querySelectorAll('input').forEach(cb => cb.checked = true); }
  updateMapFilters(); renderList();
});
document.getElementById('only-private').addEventListener('click', () => {
  state.activeOwners = new Set(["개인","법인"]);
  ownerPanel.querySelectorAll('input').forEach(cb => cb.checked = state.activeOwners.has(cb.dataset.owner));
  updateMapFilters(); renderList();
});

// 수용청구 후보 프리셋: 사유지 + 자연/녹지·공원/잡종 (대·도로·공공 제외)
document.getElementById('preset-litigation').addEventListener('click', () => {
  // Owners → 사유지만
  state.activeOwners = new Set(["개인","법인"]);
  ownerPanel.querySelectorAll('input').forEach(cb => cb.checked = state.activeOwners.has(cb.dataset.owner));
  // Jimok → 자연/녹지 + 공원/잡종만
  state.activeJimokGroups = new Set(["자연/녹지","공원/잡종"]);
  jimokPanel.querySelectorAll('input').forEach(cb => cb.checked = state.activeJimokGroups.has(cb.dataset.jimokGroup));
  // Park type → 공원 + 녹지 + 유원지 (광장 제외 — 도로 위)
  state.activeParkTypes = new Set(["공원","녹지","유원지"]);
  ptPanel.querySelectorAll('input').forEach(cb => cb.checked = state.activeParkTypes.has(cb.dataset.cat));
  updateMapFilters(); renderList();
  alert('🎯 수용청구 후보 필터 적용\\n\\n• 사유지 (개인+법인)\\n• 지목: 자연/녹지·공원/잡종 (대·도로 제외)\\n• 공원·녹지·유원지 (광장 제외)\\n\\n[목록] 탭 → 면적·공시지가 정렬해서 큰 케이스부터 검토.\\n등기부 점프로 소유자 확인.');
});

// SGG — sido-grouped accordion. composite key = "{sido} {sgg}"
const sggPanel = document.getElementById('sgg-filters');
const SGG_BY_SIDO = STATS.sgg_by_sido || {};
const SIDO_PRIORITY = [
  '서울특별시','경기도','인천광역시',
  '부산광역시','대구광역시','대전광역시','광주광역시','울산광역시','세종특별자치시',
  '강원특별자치도','강원도',
  '충청북도','충청남도',
  '전북특별자치도','전라북도','전라남도',
  '경상북도','경상남도',
  '제주특별자치도',
];
const sidoOrder = Object.keys(SGG_BY_SIDO).sort((a, b) => {
  const ai = SIDO_PRIORITY.indexOf(a);
  const bi = SIDO_PRIORITY.indexOf(b);
  if (ai === -1 && bi === -1) return a.localeCompare(b, 'ko');
  if (ai === -1) return 1;
  if (bi === -1) return -1;
  return ai - bi;
});
const allSggKeys = [];
sidoOrder.forEach(sido => {
  Object.keys(SGG_BY_SIDO[sido]).sort().forEach(sgg => {
    allSggKeys.push(`${sido} ${sgg}`);
  });
});
state.activeSggs = new Set(allSggKeys);

sidoOrder.forEach(sido => {
  const sggMap = SGG_BY_SIDO[sido];
  const sggNames = Object.keys(sggMap).sort();
  const totTot = sggNames.reduce((s,n) => s + sggMap[n].tot, 0);
  const totPriv = sggNames.reduce((s,n) => s + sggMap[n].priv, 0);
  const block = document.createElement('div');
  block.className = 'sido-block';
  block.innerHTML = `
    <div class="sido-head collapsed" data-sido="${sido}">
      <span class="caret">▼</span>
      <input type="checkbox" checked data-sido-check="${sido}" onclick="event.stopPropagation()">
      <span>${sido}</span>
      <span class="count">${totPriv.toLocaleString()}/${totTot.toLocaleString()}</span>
    </div>
    <div class="sido-body collapsed">
      ${sggNames.map(sgg => {
        const key = `${sido} ${sgg}`;
        const c = sggMap[sgg];
        return `<label class="filter-row"><input type="checkbox" checked data-sgg-key="${key}"><span style="flex:1;font-size:12px;">${sgg}</span><span class="count">${c.priv}/${c.tot}</span></label>`;
      }).join('')}
    </div>`;
  sggPanel.appendChild(block);
});

// Toggle accordion + sido master checkbox
sggPanel.querySelectorAll('.sido-head').forEach(head => {
  head.addEventListener('click', () => {
    head.classList.toggle('collapsed');
    head.nextElementSibling.classList.toggle('collapsed');
  });
});
sggPanel.querySelectorAll('input[data-sido-check]').forEach(cb => {
  cb.addEventListener('change', () => {
    const sido = cb.dataset.sidoCheck;
    const body = cb.closest('.sido-head').nextElementSibling;
    body.querySelectorAll('input[data-sgg-key]').forEach(child => {
      child.checked = cb.checked;
      const k = child.dataset.sggKey;
      if (cb.checked) state.activeSggs.add(k); else state.activeSggs.delete(k);
    });
    updateMapFilters(); renderList();
  });
});
sggPanel.querySelectorAll('input[data-sgg-key]').forEach(cb => {
  cb.addEventListener('change', () => {
    const k = cb.dataset.sggKey;
    if (cb.checked) state.activeSggs.add(k); else state.activeSggs.delete(k);
    // sync parent sido checkbox
    const head = cb.closest('.sido-body').previousElementSibling;
    const all = cb.closest('.sido-body').querySelectorAll('input[data-sgg-key]');
    const checked = Array.from(all).filter(x => x.checked).length;
    head.querySelector('input[data-sido-check]').checked = checked === all.length;
    head.querySelector('input[data-sido-check]').indeterminate = checked > 0 && checked < all.length;
    updateMapFilters(); renderList();
  });
});
document.getElementById('sgg-all').addEventListener('click', () => {
  state.activeSggs = new Set(allSggKeys);
  sggPanel.querySelectorAll('input').forEach(cb => { cb.checked = true; cb.indeterminate = false; });
  updateMapFilters(); renderList();
});
document.getElementById('sgg-none').addEventListener('click', () => {
  state.activeSggs.clear();
  sggPanel.querySelectorAll('input').forEach(cb => { cb.checked = false; cb.indeterminate = false; });
  updateMapFilters(); renderList();
});
// Safety: re-apply filter after map style is ready (in case activeSggs was empty when 'load' fired)
function applyFiltersWhenReady() {
  if (map.getLayer && map.getLayer('parcels-fill')) { updateMapFilters(); }
  else { setTimeout(applyFiltersWhenReady, 200); }
}
applyFiltersWhenReady();

// Park type
const ptPanel = document.getElementById('park-type-filters');
PARK_CATS.forEach(c => {
  const count = STATS.park_type_counts[c] || 0;
  if (count === 0) return;
  const div = document.createElement('label');
  div.className = 'filter-row';
  div.innerHTML = `<input type="checkbox" checked data-cat="${c}"><span class="chip" style="background:${PARK_COLORS[c]||'#ccc'}"></span><span>${c}</span><span class="count">${count.toLocaleString()}</span>`;
  ptPanel.appendChild(div);
});
ptPanel.querySelectorAll('input').forEach(cb => {
  cb.addEventListener('change', () => {
    const c = cb.dataset.cat;
    if (cb.checked) state.activeParkTypes.add(c); else state.activeParkTypes.delete(c);
    updateMapFilters();
  });
});

// Jimok
const jimokPanel = document.getElementById('jimok-filters');
Object.entries(JIMOK_GROUPS).forEach(([group, codes]) => {
  const count = codes.reduce((s, j) => s + (STATS.jimok_counts[j] || 0), 0);
  if (count === 0) return;
  const div = document.createElement('label');
  div.className = 'filter-row';
  div.innerHTML = `<input type="checkbox" checked data-jimok-group="${group}"><span class="chip" style="background:${JIMOK_GROUP_COLORS[group]||'#888'}"></span><span>${group}</span><span class="count">${count.toLocaleString()}</span>`;
  jimokPanel.appendChild(div);
});
jimokPanel.querySelectorAll('input').forEach(cb => {
  cb.addEventListener('change', () => {
    const g = cb.dataset.jimokGroup;
    if (cb.checked) state.activeJimokGroups.add(g); else state.activeJimokGroups.delete(g);
    updateMapFilters(); renderList();
  });
});
document.getElementById('jimok-all').addEventListener('click', () => {
  const keys = Object.keys(JIMOK_GROUPS);
  const allOn = keys.every(k => state.activeJimokGroups.has(k));
  if (allOn) { state.activeJimokGroups.clear(); jimokPanel.querySelectorAll('input').forEach(cb => cb.checked = false); }
  else { state.activeJimokGroups = new Set(keys); jimokPanel.querySelectorAll('input').forEach(cb => cb.checked = true); }
  updateMapFilters(); renderList();
});
document.getElementById('jimok-natural').addEventListener('click', () => {
  state.activeJimokGroups = new Set(["자연/녹지","공원/잡종"]);
  jimokPanel.querySelectorAll('input').forEach(cb => cb.checked = state.activeJimokGroups.has(cb.dataset.jimokGroup));
  updateMapFilters(); renderList();
});

// Overlay toggles
// 일몰 슬라이더 + 미상 포함 토글
const yearsSlider = document.getElementById('years-slider');
const yearsLabel = document.getElementById('years-label');
yearsSlider.addEventListener('input', e => {
  state.minYearsSince = parseInt(e.target.value, 10) || 0;
  if (state.minYearsSince === 0) {
    yearsLabel.textContent = '0년+'; yearsLabel.style.color = '#666';
  } else if (state.minYearsSince >= 20) {
    yearsLabel.textContent = state.minYearsSince + '년+ ⚠️일몰';
    yearsLabel.style.color = '#e63946';
  } else {
    yearsLabel.textContent = state.minYearsSince + '년+';
    yearsLabel.style.color = '#e63946';
  }
  updateMapFilters(); renderList();
});
document.getElementById('include-unknown-date').addEventListener('change', e => {
  state.includeUnknownDate = e.target.checked;
  updateMapFilters(); renderList();
});
document.getElementById('sunset-reset').addEventListener('click', () => {
  state.minYearsSince = 0;
  state.includeUnknownDate = true;
  yearsSlider.value = 0;
  yearsLabel.textContent = '0년+'; yearsLabel.style.color = '#666';
  document.getElementById('include-unknown-date').checked = true;
  updateMapFilters(); renderList();
});

document.getElementById('show-districts').addEventListener('change', e => {
  if (map.getLayer('districts-line')) {
    map.setLayoutProperty('districts-line', 'visibility', e.target.checked ? 'visible' : 'none');
  }
});
document.getElementById('show-parks').addEventListener('change', e => {
  state.showParks = e.target.checked;
  ['parks-fill','parks-outline'].forEach(id => {
    if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', state.showParks ? 'visible' : 'none');
  });
});
document.getElementById('show-parcels').addEventListener('change', e => {
  state.showParcels = e.target.checked;
  if (map.getLayer('parcels-fill')) {
    map.setLayoutProperty('parcels-fill', 'visibility', state.showParcels ? 'visible' : 'none');
  }
});

// Search + sort
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

// Methodology + how-to
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
      <li>겹침 임계값 <b>50%</b></li>
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

// Mobile hamburger toggle
const sidebar = document.getElementById('sidebar');
const sidebarBackdrop = document.getElementById('sidebar-backdrop');
function toggleSidebar(open) {
  const willOpen = open ?? !sidebar.classList.contains('open');
  sidebar.classList.toggle('open', willOpen);
  sidebarBackdrop.classList.toggle('open', willOpen);
}
document.getElementById('hamburger-btn').addEventListener('click', () => toggleSidebar());
sidebarBackdrop.addEventListener('click', () => toggleSidebar(false));
// auto-close sidebar after filter change on mobile
sidebar.addEventListener('change', () => {
  if (window.innerWidth <= 768) toggleSidebar(false);
});

// PWA service worker — with auto-reload on update
const APP_VERSION = 'v5-sido-accordion-2026-06-04';
if ('serviceWorker' in navigator) {
  window.addEventListener('load', async () => {
    try {
      const reg = await navigator.serviceWorker.register('sw.js');
      // Force check for new SW every page load
      reg.update().catch(()=>{});
      // When a new SW takes control, force a one-time reload to pick up new HTML
      let refreshing = false;
      navigator.serviceWorker.addEventListener('controllerchange', () => {
        if (refreshing) return;
        refreshing = true;
        window.location.reload();
      });
    } catch(_) {}
  });
}
// One-time eviction for users stuck on stale cache (very old SW)
try {
  const seen = localStorage.getItem('app_version');
  if (seen !== APP_VERSION) {
    localStorage.setItem('app_version', APP_VERSION);
    if ('caches' in window) {
      caches.keys().then(keys => Promise.all(keys.map(k => caches.delete(k))));
    }
  }
} catch(_) {}

// Excel / CSV download
function buildRowsForExport() {
  return lastRows.map((p, i) => {
    const m2 = parseFloat(p.parea)||parseFloat(p.area_m2)||0;
    const py = m2/PYEONG;
    const pricePerM = parseFloat(p.price_per_m2)||0;
    const pricePerPy = pricePerM*PYEONG;
    return {
      순번: i+1, 시도: p.sido_nm||'', 자치구: p.sgg_nm||'', 동: p.emd_nm||'', 지번: p.jibun||'',
      도로명주소: rnFull(p), 지목: p.jimok||'',
      "면적(㎡)": Math.round(m2*10)/10, "면적(평)": Math.round(py*10)/10,
      "공시지가(원/㎡)": pricePerM, "공시지가(원/평)": Math.round(pricePerPy),
      소유구분: p.owner_type||'', 세부: p.owner_subtype||'',
      매칭공원: p.matched_park_name||'', "겹침(%)": p.match_overlap_pct||'',
    };
  });
}
function downloadXlsx() {
  if (!lastRows.length) { alert('내보낼 데이터가 없습니다 (목록을 먼저 열어주세요)'); return; }
  if (typeof XLSX === 'undefined') { alert('Excel 라이브러리 로딩 중...'); return; }
  const rows = buildRowsForExport();
  const headers = Object.keys(rows[0]);
  const aoa = [headers, ...rows.map(r => headers.map(h => r[h]))];
  const ws = XLSX.utils.aoa_to_sheet(aoa);
  ws['!cols'] = [{wch:6},{wch:10},{wch:10},{wch:12},{wch:12},{wch:28},{wch:8},{wch:12},{wch:10},{wch:14},{wch:14},{wch:10},{wch:10},{wch:20},{wch:8}];
  const fmtArea = '#,##0.0', fmtPrice = '#,##0';
  for (let r = 2; r <= aoa.length; r++) {
    ['H','I'].forEach(col => { const c=ws[`${col}${r}`]; if (c) { c.t='n'; c.z=fmtArea; }});
    ['J','K'].forEach(col => { const c=ws[`${col}${r}`]; if (c) { c.t='n'; c.z=fmtPrice; }});
    const a = ws[`A${r}`]; if (a) a.t='n';
    const ov = ws[`O${r}`]; if (ov) { ov.t='n'; ov.z='0.0'; }
  }
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, '서울 사유지');
  XLSX.writeFile(wb, `seoul-park-parcels-${new Date().toISOString().slice(0,10)}.xlsx`);
}
function downloadCsv() {
  if (!lastRows.length) { alert('내보낼 데이터가 없습니다'); return; }
  const rows = buildRowsForExport();
  const headers = Object.keys(rows[0]);
  const lines = ["﻿" + headers.join(",")];
  rows.forEach(r => {
    lines.push(headers.map(h => {
      const v = r[h]; const s = (v??'').toString().replace(/"/g,'""');
      return /[,"\n]/.test(s) ? `"${s}"` : s;
    }).join(","));
  });
  const blob = new Blob([lines.join("\n")], {type:"text/csv"});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `seoul-park-parcels-${new Date().toISOString().slice(0,10)}.csv`;
  a.click();
}
</script>
</body>
</html>"""


if __name__ == "__main__":
    main()
