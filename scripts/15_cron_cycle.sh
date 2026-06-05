#!/bin/bash
# Stage 15 — single cron cycle. Picks one of "cycle1" / "cycle2" and runs:
#   crawl target sidos (refresh checkpoints) → aggregate → full rebuild + deploy
#
# Usage: 15_cron_cycle.sh cycle1     # 수도권 + 광역시 (화 02:00)
#        15_cron_cycle.sh cycle2     # 도 단위 (금 02:00)

set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

CYCLE="${1:-}"
PY="$HOME/.local/python/bin/python3"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/cron_${CYCLE}_$(date +%Y-%m-%d).log"

# Redirect everything to log + stderr
exec > >(tee -a "$LOG") 2>&1

echo "════════════════════════════════════════════════════════════════"
echo "  park-finder cron — $CYCLE — $(date)"
echo "════════════════════════════════════════════════════════════════"

case "$CYCLE" in
  cycle1)
    # 수도권 + 광역시 — V-World가 세종을 충남/충북으로 라벨링하므로 세종은 cycle2에 포함
    SIDOS=(서울특별시 경기도 인천광역시 부산광역시 대구광역시 대전광역시 광주광역시 울산광역시)
    ;;
  cycle2)
    # 도 단위 + 세종(충남/충북에 머지되는 영역 포함)
    SIDOS=(세종특별자치시 강원특별자치도 충청북도 충청남도 전북특별자치도 전라남도 경상북도 경상남도 제주특별자치도)
    ;;
  *)
    echo "❌ unknown cycle: $CYCLE (expected cycle1 or cycle2)"; exit 1
    ;;
esac

echo "📍 Target 시·도: ${SIDOS[*]}"
echo

# Crawl + aggregate (force-delete target checkpoints to get fresh data)
"$PY" scripts/13_korea_crawl_region.py --sidos "${SIDOS[@]}" --force

# Rebuild + deploy pipeline
bash scripts/14_rebuild_and_deploy.sh

echo
echo "════════════════════════════════════════════════════════════════"
echo "  ✅ $CYCLE complete — $(date)"
echo "════════════════════════════════════════════════════════════════"
