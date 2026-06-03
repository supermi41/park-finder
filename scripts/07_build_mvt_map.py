#!/usr/bin/env python3
"""
Stage 7 — Build MapLibre + PMTiles version of the map.
Outputs: map-mvt.html (lightweight HTML using vector tiles)
Same feature set as map.html but loads from PMTiles instead of inline GeoJSON.
"""

import json
from pathlib import Path
from collections import Counter
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parent.parent
SEOUL = ROOT / "data" / "seoul"
PUB = ROOT / "public"
OUT_HTML = ROOT / "map-mvt.html"

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

    # Build HTML
    html = HTML_TEMPLATE
    repl = {
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
    }
    for k, v in repl.items():
        html = html.replace(k, v)

    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"✅ {OUT_HTML.name}  ({OUT_HTML.stat().st_size // 1024} KB)")


HTML_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>핀파인더 · 서울 (Vector Tiles)</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css">
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
  .tab { padding:6px 14px; border:none; background:#f0f0f3; border-radius:8px;
         font-size:13px; cursor:pointer; color:#666; font-weight:500; }
  .tab.primary { background:#0071e3; color:#fff; font-weight:600; }

  .layout { display:flex; height:calc(100vh - 48px); width:100vw; }
  .sidebar { width: 250px; background:#fff; border-right:1px solid #e5e5ea;
             overflow-y:auto; padding:14px; flex-shrink:0; }
  .map-wrap { flex:1; position:relative; min-width:0; }
  #map { width:100%; height:100%; }

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
  .filter-row .count { margin-left:auto; color:#86868b; font-size:11px; font-weight:500; }
  .toggle-all { font-size:11px; color:#0071e3; cursor:pointer; user-select:none; font-weight:500; }

  .loading { position:absolute; inset:0; display:flex; align-items:center;
             justify-content:center; background:rgba(255,255,255,0.85); z-index:1000;
             font-size:13px; color:#444; flex-direction:column; gap:10px; }
  .loading .spinner { width:32px; height:32px; border:3px solid #e5e5ea;
                      border-top-color:#0071e3; border-radius:50%; animation:spin 0.8s linear infinite; }
  @keyframes spin { to { transform:rotate(360deg); } }

  .maplibregl-popup-content {
    font-size:12px; line-height:1.5; min-width:240px;
    border-radius:8px; padding:14px;
  }
</style>
</head>
<body>
<header>
  <div class="brand">
    <span style="font-size:18px;">📍</span>
    <h1>핀파인더 · 서울시 (벡터타일)</h1>
    <span class="sub">공원지정 필지 · 출처 V-World</span>
  </div>
  <div style="display:flex;gap:8px;">
    <button class="tab primary" onclick="window.location.href='map.html'">📋 목록 버전</button>
  </div>
</header>

<div class="layout">
  <aside class="sidebar">
    <div class="stat-card">
      <div class="big">__PCT__%</div>
      <div class="label">서울 __TOTAL__건 중 사유지 __PRIVATE__건</div>
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

    <h2>오버레이</h2>
    <label class="filter-row">
      <input type="checkbox" id="show-parks" checked>
      <span class="chip" style="background:#a8dadc;"></span>
      <span>공원/녹지 폴리곤</span>
    </label>
    <label class="filter-row">
      <input type="checkbox" id="show-parcels" checked>
      <span class="chip" style="background:linear-gradient(90deg,#e63946,#f4a261);"></span>
      <span>필지</span>
    </label>
  </aside>

  <div class="map-wrap">
    <div id="map"></div>
    <div id="loading" class="loading">
      <div class="spinner"></div>
      <div id="loading-text">지도 로딩...</div>
    </div>
  </div>
</div>

<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<script src="https://unpkg.com/pmtiles@3.0.7/dist/pmtiles.js"></script>
<script>
const COLORS = __COLORS__;
const ORDER = __OWNER_ORDER__;
const PARK_CATS = __PARK_CATS__;
const PARK_COLORS = __PARK_COLORS__;
const JIMOK_GROUPS = __JIMOK_GROUPS__;
const JIMOK_GROUP_COLORS = __JIMOK_GROUP_COLORS__;
const STATS = __STATS__;
const PYEONG = 3.3058;

const state = {
  activeOwners: new Set(ORDER),
  activeParkTypes: new Set(PARK_CATS),
  activeJimokGroups: new Set(Object.keys(JIMOK_GROUPS)),
  activeSggs: new Set(),
  showParks: true, showParcels: true,
};
function activeJimokSet() {
  const s = new Set();
  for (const g of state.activeJimokGroups) (JIMOK_GROUPS[g]||[]).forEach(j => s.add(j));
  return s;
}

// Register pmtiles protocol
const protocol = new pmtiles.Protocol();
maplibregl.addProtocol('pmtiles', protocol.tile);

// Detect deployment vs local (R2 URL or relative)
const PARCELS_URL = window.PARCELS_PMTILES_URL || 'tiles/parcels.pmtiles';
const PARKS_URL = window.PARKS_PMTILES_URL || 'tiles/parks.pmtiles';

const map = new maplibregl.Map({
  container: 'map',
  style: {
    version: 8,
    sources: {
      osm: {
        type: 'raster',
        tiles: ['https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png'],
        tileSize: 256,
        attribution: '© OSM © CartoDB'
      },
      parks: { type: 'vector', url: 'pmtiles://' + PARKS_URL },
      parcels: { type: 'vector', url: 'pmtiles://' + PARCELS_URL }
    },
    layers: [
      { id: 'base', type: 'raster', source: 'osm' }
    ]
  },
  center: [126.98, 37.55],
  zoom: 11,
  maxZoom: 18,
  minZoom: 8
});
map.addControl(new maplibregl.NavigationControl(), 'top-left');

// Filter expressions
function ownerFilter() {
  const owners = Array.from(state.activeOwners);
  if (owners.length === 0) return ['==', ['get', 'owner_type'], '__none__'];
  return ['in', ['get', 'owner_type'], ['literal', owners]];
}
function jimokFilter() {
  const js = Array.from(activeJimokSet());
  if (js.length === 0) return ['==', ['get', 'jimok'], '__none__'];
  return ['in', ['get', 'jimok'], ['literal', js]];
}
function sggFilter() {
  const ss = Array.from(state.activeSggs);
  if (ss.length === 0) return ['==', ['get', 'sgg_nm'], '__none__'];
  return ['in', ['get', 'sgg_nm'], ['literal', ss]];
}
function parkCatFilter() {
  const ps = Array.from(state.activeParkTypes);
  if (ps.length === 0) return ['==', ['get', 'park_cat'], '__none__'];
  return ['in', ['get', 'park_cat'], ['literal', ps]];
}

function combinedParcelFilter() {
  return ['all', ownerFilter(), jimokFilter(), sggFilter()];
}

// Color expression — match owner_type
function parcelColorExpr() {
  const expr = ['match', ['get', 'owner_type']];
  for (const [k, v] of Object.entries(COLORS)) {
    if (k === '?') continue;
    expr.push(k, v);
  }
  expr.push('#888');
  return expr;
}
function parkColorExpr() {
  const expr = ['match', ['get', 'park_cat']];
  for (const [k, v] of Object.entries(PARK_COLORS)) {
    expr.push(k, v);
  }
  expr.push('#cccccc');
  return expr;
}

map.on('load', () => {
  // Add parks layer
  map.addLayer({
    id: 'parks-fill',
    source: 'parks',
    'source-layer': 'parks',
    type: 'fill',
    paint: {
      'fill-color': parkColorExpr(),
      'fill-opacity': 0.25,
      'fill-outline-color': '#2a9d8f',
    },
    filter: parkCatFilter(),
  });
  // Parks outline
  map.addLayer({
    id: 'parks-outline',
    source: 'parks',
    'source-layer': 'parks',
    type: 'line',
    paint: {
      'line-color': '#2a9d8f',
      'line-width': 0.5,
    },
    filter: parkCatFilter(),
  });
  // Parcels fill
  map.addLayer({
    id: 'parcels-fill',
    source: 'parcels',
    'source-layer': 'parcels',
    type: 'fill',
    paint: {
      'fill-color': parcelColorExpr(),
      'fill-opacity': 0.55,
      'fill-outline-color': '#222',
    },
    filter: combinedParcelFilter(),
  });

  // Click handler for parcels
  map.on('click', 'parcels-fill', (e) => {
    if (!e.features || !e.features[0]) return;
    const p = e.features[0].properties;
    new maplibregl.Popup({ maxWidth: '320px' })
      .setLngLat(e.lngLat)
      .setHTML(buildPopup(p))
      .addTo(map);
  });
  map.on('mouseenter', 'parcels-fill', () => { map.getCanvas().style.cursor = 'pointer'; });
  map.on('mouseleave', 'parcels-fill', () => { map.getCanvas().style.cursor = ''; });

  document.getElementById('loading').style.display = 'none';
});

function buildCleanAddr(p) {
  const jimok = (p.jimok || '').trim();
  let jibun = (p.jibun || '').trim();
  if (jimok && jibun.endsWith(jimok) && /\\d$/.test(jibun.slice(0, -jimok.length))) {
    jibun = jibun.slice(0, -jimok.length);
  }
  return `${p.sido_nm||''} ${p.sgg_nm||''} ${p.emd_nm||''} ${jibun}`.replace(/\\s+/g,' ').trim();
}

function buildPopup(p) {
  const m2 = parseFloat(p.parea)||parseFloat(p.area_m2)||0;
  const py = m2/PYEONG;
  const pricePerM = parseFloat(p.price_per_m2)||0;
  const pricePerPy = pricePerM*PYEONG;
  const addr = buildCleanAddr(p).replace(/'/g,'');
  return `
    <b>${p.sgg_nm || ''} ${p.emd_nm || ''} ${p.jibun || ''}</b><br>
    ${p.matched_park_name ? `📍 <b>${p.matched_park_name}</b> <small style="color:#888;">(${p.matched_park_type||''} · 겹침 ${p.match_overlap_pct||'?'}%)</small><br>` : ''}
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
  const clean = addr.replace(/\\s*PNU[: ].*$/i,'').trim();
  navigator.clipboard.writeText(clean).catch(()=>{});
  alert('주소 복사됨:\\n' + clean + '\\n\\niros.go.kr "소재지번검색" 탭에서 붙여넣기');
  window.open('http://www.iros.go.kr/index.jsp', '_blank');
}
function jumpEum(pnu) {
  window.open(`https://www.eum.go.kr/web/am/amMain.jsp?pnu=${pnu}`, '_blank');
}
function copyAddr(addr) {
  navigator.clipboard.writeText(addr).then(()=> alert('주소 복사됨:\\n' + addr));
}

function updateFilters() {
  if (!map.getLayer('parcels-fill')) return;
  map.setFilter('parcels-fill', combinedParcelFilter());
  map.setFilter('parks-fill', parkCatFilter());
  map.setFilter('parks-outline', parkCatFilter());
}

// Sidebar UI ===
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
    updateFilters();
  });
});
document.getElementById('toggle-all').addEventListener('click', () => {
  const allOn = ORDER.every(o => state.activeOwners.has(o));
  if (allOn) { state.activeOwners.clear(); filterPanel.querySelectorAll('input').forEach(cb => cb.checked = false); }
  else { state.activeOwners = new Set(ORDER); filterPanel.querySelectorAll('input').forEach(cb => cb.checked = true); }
  updateFilters();
});
document.getElementById('only-private').addEventListener('click', () => {
  state.activeOwners = new Set(["개인","법인"]);
  filterPanel.querySelectorAll('input').forEach(cb => {
    cb.checked = state.activeOwners.has(cb.dataset.owner);
  });
  updateFilters();
});

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
    updateFilters();
  });
});
document.getElementById('sgg-all').addEventListener('click', () => {
  const allOn = sggKeys.every(s => state.activeSggs.has(s));
  if (allOn) { state.activeSggs.clear(); sggPanel.querySelectorAll('input').forEach(cb => cb.checked = false); }
  else { state.activeSggs = new Set(sggKeys); sggPanel.querySelectorAll('input').forEach(cb => cb.checked = true); }
  updateFilters();
});

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
    updateFilters();
  });
});

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
    updateFilters();
  });
});
document.getElementById('jimok-all').addEventListener('click', () => {
  const keys = Object.keys(JIMOK_GROUPS);
  const allOn = keys.every(k => state.activeJimokGroups.has(k));
  if (allOn) { state.activeJimokGroups.clear(); jimokPanel.querySelectorAll('input').forEach(cb => cb.checked = false); }
  else { state.activeJimokGroups = new Set(keys); jimokPanel.querySelectorAll('input').forEach(cb => cb.checked = true); }
  updateFilters();
});
document.getElementById('jimok-natural').addEventListener('click', () => {
  state.activeJimokGroups = new Set(["자연/녹지","공원/잡종"]);
  jimokPanel.querySelectorAll('input').forEach(cb => {
    cb.checked = state.activeJimokGroups.has(cb.dataset.jimokGroup);
  });
  updateFilters();
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
</script>
</body>
</html>"""


if __name__ == "__main__":
    main()
