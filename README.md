# 핀파인더 (Park Finder)

> 도시계획상 공원으로 지정되어 있지만 소유주가 개인/법인인 필지(=장기미집행 도시공원의 사유지)를 찾고 시각화하는 도구.

**🌐 Live**: https://park-finder.pages.dev
**📊 데이터 기준**: 서울특별시 25개 자치구 · 46,001 필지 매칭 · 사유지 17,399건 (37.8%)

---

## 🎯 왜 만들었나

장기미집행 도시계획시설(공원)이 도시 전역에 산재해 있다. 소유주가 개인·법인인 채로 정부가 공원 지정만 해두고 보상·수용은 하지 않은 토지가 다수.

이 사유지 보유자는 법적으로 다음이 가능하다:
- **부당이득반환청구** — 정부가 점유·사용 중인 토지에 대해 지대 청구 (대법원 판례 다수)
- **매수청구권** (도시공원 및 녹지 등에 관한 법률 §16) — 10년 이상 미집행 시 지자체 매수 검토 의무

핀파인더는 이런 토지를 한눈에 찾고, 필터링하고, 등기부등본 발급까지 한 번에 점프할 수 있게 한다.

---

## 🛠 데이터 출처

전부 [국토교통부 V-World](https://www.vworld.kr) 공공 API:

| 데이터 | V-World 레이어 |
|---|---|
| 도시계획 공간시설(공원/녹지/광장) | `lt_c_upisuq153` |
| 필지 정보 (PNU·주소·지목·면적) | `lt_c_landinfobasemap` |
| 소유 구분 (개인·법인·국공유) | `/ned/data/getPossessionAttr` |
| 도로명주소 | `/req/address` (reverse geocoder) |
| 자치구 경계 | `lt_c_adsigg` |

---

## 🔬 매칭 방법론

1. 자치구별로 도시계획 공원/녹지/광장/유원지 폴리곤 수집
2. 같은 자치구에서 모든 필지(PNU) 수집
3. **공간 조인**: 필지가 공원 폴리곤과 **50% 이상 겹치면** 매칭
4. 매칭된 PNU별로 `getPossessionAttr` 호출 → 소유 구분(개인/법인/국공유) 획득
5. 단순화 + JSON/PMTiles 변환

겹침 임계값 50%는 노이즈(폴리곤 가장자리에 살짝 걸치는 케이스)를 걸러내기 위함. 압구정 한양아파트 같이 28% 겹침은 제외된다.

---

## 🖱 사용법

### 🎯 수용청구 후보 (원클릭)
좌측 사이드바 상단의 파란 버튼. 클릭하면:
- 사유지(개인+법인)만
- 자연/녹지 + 공원/잡종 지목만 (건물용지·도로·공공 제외)
- 공원·녹지·유원지 (광장 제외)
→ "정부가 실제 공원으로 점유 중인 사유지" 조건 자동 적용

### 필터
- 소유 구분 (개인/법인/시도유지/군유지/국유지 등 9종)
- 자치구 (25개)
- 공원 시설 유형 (공원/녹지/광장/유원지)
- 지목 그룹 (자연/녹지·공원/잡종·건물용지·도로/시설·공공/기타)

### 목록 (우측 패널)
- 카드 뷰 / 확장 테이블 전환
- 동·지번 검색
- 면적·공시지가 정렬
- Excel·CSV 다운로드 (천 단위 콤마 자동 포매팅)

### 점프 버튼 (각 필지)
- 📜 **등기부** — 주소 클립보드 복사 + iros.go.kr 열림
- 🗺 **토지이용** — eum.go.kr 토지이용규제정보 (무료)
- 📋 **복사** — 깨끗한 주소만 클립보드

---

## 💻 기술 스택

| 영역 | 기술 |
|---|---|
| 데이터 수집 | Python + V-World API + Shapely (STRtree) |
| 공간 처리 | tippecanoe (GeoJSON → PMTiles 벡터타일) |
| 지도 | MapLibre GL JS + PMTiles |
| 목록/Excel | Vanilla JS + SheetJS |
| 호스팅 | Cloudflare Pages (HTML/JSON) + jsDelivr (PMTiles) |
| 배포 | wrangler pages deploy |

---

## 🚀 로컬 실행

```bash
# 1. clone + venv
git clone https://github.com/supermi41/park-finder.git
cd park-finder
python3 -m venv venv
source venv/bin/activate
pip install requests python-dotenv shapely

# 2. V-World API 키 (https://www.vworld.kr)
cp .env.example .env
nano .env   # VWORLD_API_KEY 채움

# 3. 데이터 수집 (서울 기준 ~2시간)
python3 scripts/04_seoul_full.py
python3 scripts/05_build_seoul_map.py
python3 scripts/09_split_parcels.py

# 4. tippecanoe (PMTiles 빌드)
# tippecanoe는 felt/tippecanoe 소스 빌드 필요
tippecanoe -o tiles/parcels.pmtiles --layer=parcels \
  --maximum-zoom=16 --minimum-zoom=10 \
  --drop-densest-as-needed --force public/parcels.json

# 5. 통합 HTML 빌드
python3 scripts/08_build_unified_map.py

# 6. Range 지원 로컬 서버 (PMTiles 필수)
python3 scripts/range_server.py 3001
# → http://localhost:3001/map.html
```

---

## 📁 디렉터리 구조

```
park-finder/
├── scripts/
│   ├── 04_seoul_full.py       # 서울 25개 구 데이터 수집
│   ├── 05_build_seoul_map.py  # 기존 Leaflet 빌더 (참고용)
│   ├── 06_enrich_rn_addr.py   # 도로명주소 보강
│   ├── 07_build_mvt_map.py    # 초기 MVT 빌더 (참고용)
│   ├── 08_build_unified_map.py  # ★ 현재 메인 빌더
│   ├── 09_split_parcels.py    # Cloudflare 25MB 한도용 분할
│   └── range_server.py        # 로컬 PMTiles 테스트용
├── public/                    # 정적 데이터 (배포 대상)
│   ├── parcels-1/2/3.json    # 필지 데이터 청크 (~12MB × 3)
│   ├── parcels-manifest.json
│   ├── parks.json             # 공원 폴리곤
│   ├── districts.json         # 자치구 경계
│   └── stats.json             # 사전계산 통계
├── tiles/                     # PMTiles (jsDelivr 호스팅)
│   ├── parcels.pmtiles        # 18MB, 줌 10-16
│   └── parks.pmtiles          # 3.6MB, 줌 9-16
├── map.html / index.html      # 메인 페이지
└── dist/                      # Pages 배포용 (build 시 생성)
```

---

## ⚠️ 한계 / 주의

- **도로명주소 누락 多**: V-World reverse geocoder가 공원 내부 좌표에 도로명주소를 반환하지 않음 (자연 상태 토지는 도로 없음). 임야·전·답이 많은 우리 데이터 특성상 도로명주소가 채워진 비율은 약 1.3%.
- **소유자 본인 식별 불가**: 개인정보보호로 소유주 이름·연락처는 제공되지 않음. 구분(개인/법인/국공유 등)만 확인 가능. 본인 이름까지 필요하면 등기부등본을 발급해야 함 (1통 ₩700).
- **공원 지정 ≠ 실제 사용**: 도시계획상 지정이라도 실제로는 미집행 상태일 수 있음. 지목으로 실제 토지 사용 용도를 교차 확인 권장.
- **압구정 케이스 (50% 임계값)**: 50% 이하 겹침은 제외. 진짜 알박기 케이스 중 일부 누락 가능. 이는 의도적인 트레이드오프.

---

## 📜 License

MIT License — `LICENSE` 파일 참조.

데이터는 [국토교통부 V-World](https://www.vworld.kr) 공공데이터를 가공한 결과물.

---

## 🙏 Credits

- **데이터**: 국토교통부 V-World 디지털트윈국토 (Public Domain)
- **PMTiles**: [protomaps/PMTiles](https://github.com/protomaps/PMTiles)
- **tippecanoe**: [felt/tippecanoe](https://github.com/felt/tippecanoe)
- **MapLibre GL JS**: [MapLibre](https://maplibre.org/)
- **SheetJS**: [SheetJS Community Edition](https://sheetjs.com/)
- **Made with**: Python · TypeScript · 🤖 Claude Code
