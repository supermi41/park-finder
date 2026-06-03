# 핸드오프 — `scripts/04_seoul_full.py` 재실행 전 패치 필요

작성: 2026-06-03 (다른 Claude Code 세션에서 진단)

## 현재 상태

- **이전 실행 프로세스 PID 86162 강제 종료됨** (2시간 7분간 돌고도 자치구 0개 완료)
- 살아남은 산출물 (재사용 OK):
  - `data/seoul/seoul_districts.geojson` (1.5MB) — Step 1 결과
  - `data/seoul/seoul_parks.geojson` (26MB) — Step 2 결과
- `data/seoul/districts/` — 비어있음 (Step 3 미시작)
- 로그 `/tmp/seoul-run.log` — 0바이트 (출력 버퍼링 때문에 진행 상황 안 보였음)

## 진단된 병목

`sample(1)`로 스택 추적한 결과, 핫패스가 `shapely .bounds → GEOS_init_r/finish_r`.

문제 부위 (lines 209–231):
```python
for pf in parcel_feats:                        # 자치구당 수만 필지
    pg = shape(pf["geometry"])
    for park_g, park_f in park_polys:          # 서울 전체 공원 ~수천개
        pgb = pg.bounds; gb = park_g.bounds    # ← 매 반복 GEOS 핸들 생성
        if pgb[2] < gb[0] or ...: continue
        if not pg.intersects(park_g): continue
        inter = pg.intersection(park_g)
        ...
```

- `pg.bounds`가 park 루프마다 재계산
- `park_g.bounds`가 필지마다 재계산
- `STRtree` 167행에서 만들어놓고도 **안 씀** → brute-force O(필지 × 공원)
- `print()` flush 없어서 진행 상황 안 보임

## 필요한 패치 (5개)

1. **`STRtree.query(pg)` 도입** — 후보 공원만 골라서 inner loop 짧게
2. **`park_bounds_arr` 사전 계산** — 공원 polygon 만들 때 bounds도 같이 캐싱
3. **`pg.bounds` hoist** — inner loop 밖으로
4. **버퍼링 해제** — `python3 -u` 또는 `print(..., flush=True)`
5. **체크포인트** — 자치구 끝날 때마다 `data/seoul/districts/{name}.geojson` 저장 (재개 가능 + 진행 가시화)

## 재실행 방법

Step 1, 2 산출물 살아있으니, 스크립트가 캐시 재사용하도록 패치하거나, 그게 귀찮으면 그냥 통째로 다시 돌려도 됨 (앞 2단계는 1–2분이라 부담 없음).

```bash
cd ~/DJ_HQ2/Project/02_Park-private-land
nohup python3 -u scripts/04_seoul_full.py > /tmp/seoul-run.log 2>&1 &
echo $! > /tmp/seoul-run.pid
tail -f /tmp/seoul-run.log    # 진행 상황 실시간 확인
```

## 참고

- 작업 dir: `~/DJ_HQ2/Project/02_Park-private-land/`
- 사용자 Python: `~/.local/python/bin/python3` (Xcode CLT 없음, brew 없음)
- API key: `.env` 안의 `VWORLD_API_KEY` (VWorld OpenAPI)
