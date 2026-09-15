# 데이터 파이프라인

> 챕터 데이터가 외부 사이트 → 로컬 JSON → API 응답으로 흘러가는 과정.

## 파이프라인 흐름

```
[외부 소스]                    [수집]                  [저장]                 [API]
─────────                  ─────────              ───────────           ────────────
북토끼 (23.ondobook.net)  ─┐
                             │
뉴토끼 (toki31.com)        ─┼─→  pipeline.py collect  ─→  /opt/ai_data/  ─→  FastAPI
                             │       (source별 분기)        flaresolverr/       (3ms)
                             │                              novels/{소설명}/
                             │   ─────────                    ├── meta.json
                             │   (rate limiter:               ├── {wr_id}.json
                             │    8분 + ±2분)  
                             │                              └── SQLite DB (ebooklib.db)
                             │                                   - novels table
                             │                                   - chapters index table
                             │                                   - reading_progress table
                             │
                             └──→  Vercel ISR (CDN 0ms)
```

## 1. 파이프라인 시작

### Admin 페이지 (권장)
- URL: `https://miniebook.vercel.app/admin`
- 비밀번호 입력 + URL 붙여넣기
- 자동 분기: **소스 레지스트리(`sources.json`)의 domains로 URL 매칭** → source/ID 추출
  - 23.ondobook.net → bookto31, toki31.com/newtoki31.com → toki31, 그 외 등록 도메인
- 제목 자동 추출 → 큐 등록 → 루프 시작 (루프는 소스 무관, 모든 소스 수집)

### CLI
```bash
# 전체 체인 (신규 소설)
python3 scripts/pipeline.py all 25575 "오늘만 사는 기사"

# 무한 루프 (다중 소스 — 모든 소스 수집)
python3 scripts/pipeline.py loop

# 단계별
python3 scripts/pipeline.py discover 25575 "오늘만 사는 기사" --source bookto31
python3 scripts/pipeline.py discover 58455 "아포칼립스의 고인물" --source toki31
python3 scripts/pipeline.py collect --limit 1
python3 scripts/pipeline.py enrich "오늘만 사는 기사"
python3 scripts/pipeline.py index
python3 scripts/pipeline.py revalidate "오늘만 사는 기사"
```

## 2. 파이프라인 단계

### Step 0: 소스 레지스트리 (`sources.json`)

`apps/backend/sources.json`에 소스를 등록 — 코드 수정 없이 추가/도메인 변경 가능:

```json
{
  "bookto31": { "domains": ["23.ondobook.net"], "base_url": "https://23.ondobook.net",
                "collector": "bookto31", "discover": "gnuboard", "speed_hint_sec": 300 },
  "toki31":   { "domains": ["toki31.com", "newtoki31.com"], "base_url": "https://toki31.com",
                "collector": "toki31", "discover": "toki31_episodes", "speed_hint_sec": 5 }
}
```

- `domains`: URL 매칭 + **미러 후보**, `base_url`: 크롤링 주소, `collector`: 수집기 키,
  `discover`: 발견 전략(gnuboard/toki31_episodes/...), `speed_hint_sec`: 수집 딜레이/ETA 기준
- **도메인 변경은 대부분 자동 처리** — 리다이렉트 최종 URL 감지/페일오버 시 `base_url`·`domains`를
  `lib/domain_router.py`가 자동 갱신. **이전 URL은 폐기**(새 호스트만 유지)
- ⚠️ 사이트 도메인이 바뀌면 **wr_id 체계도 달라질 수 있음** (예: bookto31→ondobook). 기존 소설의
  `meta.main_wr_id`는 discover 실행 시 소스에서 자동 재발견됨

### Step 1: discover (소스별 전략 분기)

`run_discover`가 `get_discover(source)`로 전략 라우팅:
- **gnuboard**(bookto31 계열): 작품 메인 GNUBOARD5 spage 순회 → wr_id+chapter 추출
- **toki31_episodes**: 에피소드 목록(화수→episode_id) 페이지네이션 → 큐 등록
- `--dry-run` 모드로 제목만 추출 가능

### Step 2: collect (source별 분기)

큐 아이템의 `source` 필드에 따라 collector 자동 선택:

| source | collector | 방법 | 속도 (speed_hint) |
|--------|-----------|------|------|
| `bookto31` | `_collect_bookto31()` | FlareSolverr + HTML 파싱 | 5~8분/챕터 (300초) |
| `toki31` | `_collect_newtoki()` | Playwright + AES-GCM 복호화 | **~18초/챕터 (5초)** |

> **루프는 다중 소스 처리**: 모든 소스의 큐 항목을 순서대로 수집. 소스별 페이싱은
> `speed_hint_sec` 기반 내부 적응형 딜레이(fast: 5초, slow: 300~600초)가 담당.
> toki31은 유동 IP(DataImpulse KR 회전)라 IP 차단 무력화 → 고속 수집 가능.

**toki31 에피소드 매핑**: toki31의 episode_id는 bookto31 wr_id와 **다른 체계**.
- 사전에 toki31 에피소드 맵(화수→episode_id)을 수집해야 함 (e.g. `/novel/{id}` 페이지 + "이전 회차 더 보기" 페이징)
- 큐 항목: `wr_id = toki31 episode_id`, `novel_ref = toki31 novel_id`, `chapter = 화수`
- 저장 파일명은 `{toki31 episode_id}.json` — 기존 bookto31 파일과 혼재되지만 chapter 번호 정렬로 정상 표시

**bookto31 수집기**:
```python
# services/bookto31.py 사용
html = fetch_chapter(wr_id)            # FlareSolverr → Cloudflare 우회
body = parse_chapter_body(html)        # GNUBOARD5 본문 추출
chapter_num = _extract_chapter_from_html(html) # "<title>제목 - 839화</title>" 패턴
```

> **중복 본문 방지 (collect 저장 전)**: 같은 본문이 다른 화수로 저장되는 것을 차단
> - **동일 본문 해시 검출**: `_saved_content_hash_index()`로 같은 내용이 이미 다른 chapter 번호로
>   저장돼 있으면 → 저장 생략 + `duplicates.json` 기록 + 큐에서 제거
> - **챕터 번호 보정**: 본문 표기("N화")가 기대 chapter와 다르고 충돌이 없으면 저장 단계에서 본문 표기 우선
>   (소스 wr_id→화수 매핑 오프바이원 대응)
> - **소스 무관 dedup**: `_load_saved_chapters()`가 chapter 번호 기준으로 저장 여부 확인
>   (bookto31/toki31/ondobook wr_id 체계가 달라도 동일 화수는 재다운로드 안 함)

**newtoki 수집기**:
```python
# lib/toki31_playwright.py 사용
result = await fetch_chapter_content_full(novel_id, episode_id)
# Playwright 브라우저가 ad/ack 처리 → API 응답 인터셉트 → AES-GCM 복호화
# (venv에 playwright + cryptography 필요)
```

> **toki31 프록시/트래픽 (2026-09-12)**:
> - 프록시: **DataImpulse 주력**(`__cr.kr` 한국 IP 회전) + MaskProxy 폴백 (`_PROXY_PRIORITY`)
> - 회차당 실측 **~0.9~1.6MB** (toki31이 JS/wasm을 매 챕터 재다운로드 — anti-bot, 캐시 불가)
> - 회차 상한: 콜드 2.5MB / 웜 2.0MB (정상 챕터 차단 방지용 안전장치)
> - 브라우저 재사용(싱글턴) + 리소스 차단(media/CSS/이미지)으로 절약
> - `ad_guard_bg.wasm`은 콘텐츠 추출 필수(차단 불가) — 상세: [10-TOKI31-PROXY-IMPLEMENTATION.md](10-TOKI31-PROXY-IMPLEMENTATION.md)

### Step 3: enrich
- namu.wiki에서 작가/표지/장르/설명/연재상태 수집
- `namu_attempted` 플래그로 **1회만** 시도 (중복 방지)
- 표지 이미지 검증: 5KB 이상, 200×200px 이상, og:image만 사용

### 표지 수집 (SSOT 우선)
표지의 진실 원천은 **소스 사이트**다. `scripts/fetch_cover.py`가 순차 시도한다:
1. **toki31**: Playwright(유료 프록시)로 `/novel/{main_wr_id}` 로드 → `.nd-thumb img`(alt=제목) 표지
2. **bookto31/ondobook**: FlareSolverr로 `bbs/board.php` 로드 → `imgspeedtoki` CDN → `og:image` → 본문 첫 이미지
3. **namu.wiki**: 보조 백업

- 웹 이미지 검색 폴백은 신뢰도 문제로 **미사용** (엉뚱한 이미지 방지)
- `run_enrich`에서 namu/소스가 표지를 못 주면 표지 미존재 시 소스 기반으로 재시도
- `python3 scripts/fetch_cover.py <novel_id> [--force]` / `--all`

### Step 4: index
- SQLite `chapters` 테이블에 인덱스 저장 (wr_id, chapter, title, content_length, source, url, collected_at)
- API 성능 최적화: 데이터.py에서 SQLite 조회 + TTL 캐시 (소설 목록 5분, 챕터 상세 10분)

### Step 5: revalidate
- Vercel ISR 캐시 갱신 (해당 소설 페이지만)
- `VERCEL_REVALIDATE_URL` + `VERCEL_REVALIDATE_TOKEN` 필요

## 3. 데이터 저장 (JSON 스키마 + SQLite 인덱스)

### meta.json
- 각 소설의 `/opt/ai_data/flaresolverr/novels/{소설명}/meta.json` 파일에 저장 (제목, 저자, 출판사, 설명, 장르, 상태, 표지 URL 등)
- 동시에 SQLite `novels` 테이블에도 동기화 (id, title, author, source, media_type, meta_json)

### {wr_id}.json (챕터)
- 챕터 본문은 여전히 `/opt/ai_data/flaresolverr/novels/{소설명}/{wr_id}.json` 파일로 저장
- wr_id는 파일명, source는 bookto31 또는 toki31 등
- 내용: wr_id, chapter, title, content_length, content, url, collected_at, source

### SQLite 인덱스 (ebooklib.db)
- `novels` 테이블: 소설 메타데이터 (id, title, author, source, media_type, meta_json)
- `chapters` 테이블: 챕터 인덱스 (wr_id, novel_id, chapter, title, content_length, source, url, collected_at)
- `reading_progress` 테이블: 사용자 별 읽기 진행상황 (소설_id, chapter, timestamp)
- 인덱스: `idx_chapters_novel_id`, `idx_chapters_wr_id`, `idx_novels_source`

## 4. 데이터 읽기 (API)

```python
def get_novel_list():
    # SQLite에서 novels 테이블 조회 + TTL 캐시 5분
    ...

def get_novel_detail(novel_id):
    # SQLite에서 단일 소설 조회 + TTL 캐시
    ...

def get_chapter_list(novel_id, page=1, limit=20):
    # SQLite에서 chapters 테이블에서 novel_id 조건, chapter 순서 정렬, limit/offset 적용 + TTL 캐시 10분
    ...

def get_chapter_detail(wr_id):
    # SQLite에서 챕터 메타 조회 + 실제 본문은 {wr_id}.json 파일에서 직접 읽기
    ...
```

## 5. 데이터 흐름 (한 챕터 기준)

```
1. 파이프라인 collect 단계 (devforge)
   └─→ source별 collector → JSON 저장
   └─→ index 재구축 → revalidate 호출
        ↓

2. Vercel ISR (CDN)
   └─→ 해당 소설 페이지 백그라운드 재생성
   └─→ 사용자는 항상 CDN 캐시 (0ms)
        ↓

3. 사용자가 회차 클릭
   └─→ GET /novel/{id}/chapter/{wr_id} (ISR)
   └─→ devforge 직접: /api/chapters/{wr_id} (3ms)
```

## 6. 데이터 무결성

- **챕터 번호 추출 우선순위** (`lib/storage.py::_extract_chapter_num`):
  1. 큐/collect 단계에서 전달된 chapter 번호
  2. HTML `<title>`에서 `"제목 - N화"` 패턴 (`_extract_chapter_from_html`)
  3. 본문 첫 줄 `^(\d+)(?:화|편|장)` — 실패 시 본문 어디서든 같은 패턴
- **추출 실패 시**: **wr_id로 폴백하지 않고 `chapter: null`**로 저장 (2026-09-09부터).
  - 이전 버그: `chapter = wr_id` 폴백 → chapter/title이 "5784625화"로 오염 → "1화→2화" 탐색 파괴
- **정렬**: 이전/다음 화, 회차 목록은 **chapter 번호 기준** 정렬 (wr_id 아님). wr_id는 파일명/식별자로만 사용.
- **빈 챕터**: 100자 미만 본문은 수집 실패로 간주, 3회 재시도 → 실패 시 DLQ(failed.json) 기록

## 7. 큐 데이터 구조

```json
{
  "wr_id": 7240583,
  "episode_id": 7240583,
  "novel_title": "게임 속 바바리안으로 살아남기",
  "chapter": 934,
  "source": "toki31",
  "novel_ref": "20",
  "priority": 1,
  "added_at": "2026-09-09T...",
  "attempts": 0,
  "last_error": null
}
```

- `wr_id`: 저장 파일명/식별자 (toki31이면 episode_id, bookto31이면 GNUBOARD wr_id)
- `episode_id`: toki31 fetch용 (bookto31 wr_id와 다름)
- `novel_ref`: toki31 novel_id (`/novel/{novel_id}`) — bookto31에는 없음
```

## 다음 문서
- [02-BOT-BYPASS.md](02-BOT-BYPASS.md) - 봇 우회 전략
- [03-EPUB-GENERATION.md](03-EPUB-GENERATION.md) - EPUB 생성