#!/bin/bash
# Stage 14 — full rebuild + deploy pipeline.
# Run after scripts/13_korea_crawl_region.py has refreshed checkpoints + aggregated.
# Picks up the current korea_park_parcels_all.geojson and pushes through:
#   11 (parcels.json, stats.json) → sgg_full patch → 09 split → tippecanoe → 08 HTML
#   → git commit + push → cloudflare pages deploy
#
# Idempotent. Safe to run anytime.

set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

PY="$HOME/.local/python/bin/python3"
TIPPECANOE="$HOME/.local/bin/tippecanoe"
GH="$HOME/.local/bin/gh"
NPX="/usr/local/bin/npx"
TOKEN_FILE="$HOME/.cf-api-token"

log() { echo "[$(date +%H:%M:%S)] $*"; }

log "📦 Stage 11: rebuild parcels.json + stats.json from korea_park_parcels_all.geojson"
"$PY" scripts/11_build_korea_map.py >/dev/null 2>&1 || {
  log "❌ stage 11 failed"; exit 1
}

log "🏷  Patch sgg_full into parcels.json"
"$PY" - <<'PY'
import json
from pathlib import Path
p = Path('public/parcels.json')
d = json.loads(p.read_text())
for f in d['features']:
    pr = f['properties']
    pr['sgg_full'] = f"{pr.get('sido_nm','')} {pr.get('sgg_nm','')}"
p.write_text(json.dumps(d, ensure_ascii=False))
print(f"  patched {len(d['features'])} features")
PY

log "🏷  Patch sgg_by_sido + composite sgg keys into stats.json"
"$PY" - <<'PY'
import json
from collections import Counter, defaultdict
from pathlib import Path
PUB = Path('public')
manifest = json.loads((PUB/'parcels-manifest.json').read_text()) if (PUB/'parcels-manifest.json').exists() else None
# Recompute stats with sgg_by_sido using the rebuilt parcels.json
d = json.loads((PUB/'parcels.json').read_text())
owner_counts = Counter(); jimok_counts = Counter()
sgg_counts = Counter(); sgg_private = Counter()
sgg_by_sido = defaultdict(lambda: defaultdict(lambda: {"tot":0,"priv":0}))
for f in d['features']:
    p = f['properties']
    sido = p.get('sido_nm','?'); sgg = p.get('sgg_nm','?')
    ot = p.get('owner_type','?')
    owner_counts[ot] += 1
    jimok_counts[p.get('jimok','?')] += 1
    key = f'{sido} {sgg}'
    sgg_counts[key] += 1
    sgg_by_sido[sido][sgg]['tot'] += 1
    if ot in ('개인','법인'):
        sgg_private[key] += 1
        sgg_by_sido[sido][sgg]['priv'] += 1
total = sum(owner_counts.values())
priv = owner_counts.get('개인',0)+owner_counts.get('법인',0)
old = json.loads((PUB/'stats.json').read_text()) if (PUB/'stats.json').exists() else {}
stats = {
  'total_parcels': total, 'private_total': priv,
  'private_pct': round(priv/total*100,1) if total else 0,
  'owner_counts': dict(owner_counts), 'jimok_counts': dict(jimok_counts),
  'park_type_counts': old.get('park_type_counts', {}),
  'sgg_counts': dict(sgg_counts), 'sgg_private': dict(sgg_private),
  'sgg_by_sido': {s: dict(m) for s,m in sgg_by_sido.items()},
}
(PUB/'stats.json').write_text(json.dumps(stats, ensure_ascii=False))
print(f"  stats: {total} total, {priv} private")
PY

log "✂️  Stage 09: split parcels.json into 10 chunks"
"$PY" scripts/09_split_parcels.py >/dev/null

log "🗺  Tippecanoe: regenerate PMTiles"
"$TIPPECANOE" -o tiles/parcels.pmtiles --layer=parcels \
  --maximum-zoom=16 --minimum-zoom=10 \
  --drop-densest-as-needed --force \
  --no-feature-limit --no-tile-size-limit \
  public/parcels.json 2>&1 | tail -3

log "🗺  Tippecanoe: regenerate parks.pmtiles"
"$TIPPECANOE" -o tiles/parks.pmtiles --layer=parks \
  --maximum-zoom=16 --minimum-zoom=9 \
  --drop-densest-as-needed --force \
  --no-feature-limit --no-tile-size-limit \
  public/parks.json 2>&1 | tail -3

log "📄 Stage 08: rebuild index.html"
"$PY" scripts/08_build_unified_map.py >/dev/null

log "📦 Stage dist sync"
cp index.html dist/index.html
cp sw.js dist/sw.js
cp public/stats.json dist/public/stats.json
cp public/districts.json dist/public/districts.json
cp public/parcels-manifest.json dist/public/parcels-manifest.json
for i in 1 2 3 4 5 6 7 8 9 10; do
  cp "public/parcels-${i}.json" "dist/public/parcels-${i}.json"
done

log "📜 Git commit + push"
# Stage data files individually to avoid huge geojson sources
git add tiles/parcels.pmtiles tiles/parks.pmtiles \
        public/stats.json public/parcels-manifest.json \
        scripts/13_korea_crawl_region.py scripts/14_rebuild_and_deploy.sh \
        index.html map.html sw.js 2>/dev/null || true
if ! git diff --cached --quiet; then
  TS=$(date +%Y-%m-%d_%H%M)
  git -c commit.gpgsign=false commit -m "auto-rebuild $TS" >/dev/null
  git push origin main 2>&1 | tail -1
else
  log "  no changes to commit"
fi

log "☁️  Cloudflare Pages deploy"
export CLOUDFLARE_API_TOKEN="$(tr -d '\n ' < "$TOKEN_FILE")"
rm -rf .wrangler
"$NPX" --yes wrangler@4 pages deploy dist --project-name=park-finder --branch=main --commit-dirty=true 2>&1 | tail -2

log "✅ rebuild + deploy done"
