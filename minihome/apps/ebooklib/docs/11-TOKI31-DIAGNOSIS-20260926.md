# toki31 수집 불능 — 2026-09-26 진단 보고서

> **상태**: 조사·분석 완료. 개선안 ①~⑤은 **미착수(승인 대기)**, ④은 폐기.
> **관련 문서**: `docs/08-TOKI31-ANALYSIS.md` (이전 재분석) · `docs/10-TOKI31-PROXY-IMPLEMENTATION.md` (프록시 구현)
> **외부 검증 원장**: `/home/opc/research_report.md` (31 citations, verify PASS)

## 1. 한 줄 결론

toki31 수집 불능은 **(a) 죽은 `base_url`, (b) Playwright `Accept-Encoding: zstd` + `route.fulfill` 조합 버그,
(c) discover 단계의 미러 페일오버 부재** — 세 겹의 병목이 겹친 결과이며, **미러 도메인 하나 추가로는 해결되지 않는다.**

## 2. 현황 스냅샷 (2026-09-26)

| 항목 | 값 |
|---|---|
| 실행 중 loop | PID 3593, **2026-09-23 기동** → 09-25 생성된 `lib/official_feed.py` **미적용** (피드 갱신·점검 감지·미러 자동등록 OFF) |
| `sources.json` base_url | `https://newtoki31.com` (**접속 불가**) |
| 수집 E2E | `EBOOK_TOK31_MIN_HEADERS=0`일 때만 성공 (본문 7,173자 복호화). **기본값(1)이면 실패** |
| 검증 베이스라인 | pytest **172 passed** · ruff 합 **46** (pipeline 42 / main 2 / tests 4) · mypy **21 errors** |

## 3. 도메인 상태 (로컬 실측 + 공식 공지)

| 도메인 | 직접 접속 | DataImpulse(KR) | 출처 | 판정 |
|---|---|---|---|---|
| `newtoki31.com` | connection refused | refused | **1차 출처 부재** | 출처 미확인 + 접속 불가 → 폐기 후보 |
| `toki31.com` | refused | refused | 공식 공지 = 신버전 | 점검 상태와 일치 |
| `sbxh9.com` | **200** | **200** | 공식 공지 = 신버전 | **유일한 검증 완료 미러** (목록 100행·회차 200·`/api/novel-content` ok=true) |
| `newtoki1.org` | `/` 200, `/novel/*` **403** | 403 | 공식 공지 = **구버전 롤백** | **미추적(사용자 결정)** — 신버전 파서 미호환 |

**공식 공지 원문** (`t.me/toki1234/5`, 2026-09-23, 직접 fetch 확인):

> newtoki1.org 구버전만 롤백 서버로 복구되었으며, sbxh9.com toki31.com 신버전 및 모든 서버 정상화까지
> 로그인은 제한되고 업로드가 중단됩니다. 100% 정상화 복구 시간은 현재로썬 미정입니다.

## 4. 원인 (b) — zstd / route.fulfill

### 4.1 A/B 실험 결과

| 조건 | 결과 |
|---|---|
| `MINIMAL_REQUEST_HEADERS`(zstd 포함) + JS route 캐시 | **실패** (JS 청크 깨짐 → `/api/novel-content` 호출 없음 → 25s 타임아웃) |
| 동일 헤더에서 `zstd`만 제거 | **성공** |
| `Accept-Encoding` 헤더 자체 미지정 | **성공** |
| zstd 헤더 + JS route **미사용** | **성공** |

→ 청크 깨짐이 아니라 **zstd + `route.fetch()`/`fulfill()` 상호작용**이 원인.

### 4.2 메커니즘 (공식 이슈 기반)

1. `set_extra_http_headers`는 컨텍스트의 **모든 요청**에 전달 → `route.fetch()`까지 침투 (공식 문서).
2. `APIRequestContext.body()/text()`는 **zstd를 압축 해제하지 않음** (gzip/br은 함) — [playwright#37032](https://github.com/microsoft/playwright/issues/37032).
3. `route.fulfill({response})`는 **content-encoding 헤더를 실은 채 처리된 body**를 전송 — [playwright#39292](https://github.com/microsoft/playwright/issues/39292) (→ #39351).
4. 결과: 브라우저가 디코딩 불가한 JS 청크 수신 → 번들 미로드 → 수집 API 호출 자체가 안 일어남.

### 4.3 미확인 (정직하게)

- "zstd JS를 fulfill로 재서빙하면 깨진다"는 **단건 공식 이슈 없음** (공식 저장소 `zstd` 검색 8건). 원인은 위 두 이슈 **조합 + 로컬 A/B**로 구성한 결론.
- 공식 문서에 `Accept-Encoding` 재정의 **경고는 없음** → "문서가 그렇게 권한다"는 근거는 성립하지 않음.

## 5. 원인 (a)(c) — base_url 고착 / discover 페일오버 부재

### 5.1 URL 제출 경로에서 base 갱신이 끊긴 지점

```
POST /pipeline/start {url}
  └─ parse_url()                    routers/pipeline.py:67  → /novel/(\d+) = toki31
  └─ parse 실패 시에만               routers/pipeline.py:667
       detect_and_register_source() lib/domain_router.py:185
         └─ 호스트가 이미 domains에 있으면 no-op (203~205) → set_base 미발동
```

- `sbxh9.com`은 이미 등록 → `parse_url`이 **성공** → `detect` 호출 자체가 안 됨.
- 설령 호출돼도 **no-op** → `add_source_domain(set_base=True)`의 base 갱신이 발동 안 함.
- 결과: **"제출 URL을 분석해 쓰는" 기능은 있으나, 그 URL이 base가 되는 연결이 끊겨 있음.**

### 5.2 discover vs collect 불균형

| 단계 | 미러 페일오버 |
|---|---|
| `discover_toki31()` (`scripts/pipeline.py:602`) | **없음** (단건 `goto`) |
| `fetch_chapter_content_full()` (`lib/toki31_playwright.py:877`) | **있음** (`candidate_bases()` 순회) |

미러가 있어도 **발견 단계에서 막히면 끝**.

### 5.3 헬스체크 오탐

`scripts/pipeline.py:337`의 toki31 헬스체크는 **DNS 조회만** 수행 → `newtoki31.com`이 죽어도
`status.json.domain_health.toki31 = ok`로 남아 base가 고착됨.

## 6. 미검증 항목 (신뢰도)

### 웹(외부 출처)

| # | 항목 | 상태 | 비고 |
|---|---|---|---|
| W1 | 구버전/신버전 안내 채널 (`t.me/s/newtoki_url/31`) | **부분 재확인** | 해당 페이지는 빈 셸만 렌더 → 직접 재현 실패. 동일 내용은 `t.me/toki1234/5`로 직접 확인 |
| W2 | `newtoki31.com`의 공식 출처 | **확인불가** | 공식 채널·검색 어디에도 미등장. "무효"가 아니라 "출처 미확인" |
| W3 | zstd+fulfill 단건 이슈 | **없음** | #37032+#39292 조합 + 로컬 A/B로 구성 (두 이슈 원문은 직접 확인) |
| W4 | "discover 페일오버 우선"이 일반 권고 | **표준 없음** | APT `apt-transport-mirror`·OpenShift는 "다중 미러 + 자동 페일오버"까지만 지지 |
| W5 | 리서치 보고서 원문 신뢰도 | **자각 표기** | 에이전트가 문구 재구성 `[unverified]` 표기 → GitHub/공식문서는 직접 재확인 |

### 로컬(우리 환경)

| # | 항목 | 비고 |
|---|---|---|
| L1 | 기본 설정으로 수집 성공 | E2E 통과는 `EBOOK_TOK31_MIN_HEADERS=0`에서만 관측 → **수정 전에는 통과 못 함** |
| L2 | zstd가 유일한 병목인지 | A/B로 JS 체크만 확인, 추출기 전 영역 배제 아님 |
| L3 | `ebook-watcher` 재시동 후 동작 | 피드 갱신·미러 등록·점검 스킵 **코드상 의도이나 미실험** |
| L4 | 로그 격리 부수 소실 | 03:05~03:32 사용자 서비스 로그 복구 불가 |

## 7. 본 세션 선행 조치 (완료)

| 조치 | 검증 |
|---|---|
| `jobs.json`의 `novel:58667` 잔재 → `POST /api/pipeline/reset` 초기화 | `jobs.json={}`, 유령 `job:58667` 제거, 작품 `동생이_천재였다` 226/226 유지 |
| query-string 비밀번호 → 본문(JSON) 방식 (`ResetRequest`) | 본문 `{"ok":true}` · query 전송 시 **HTTP 422** · 프런트 reset 버튼 복구 |
| access log 비밀번호 마스킹 (`_RedactSecretsFilter`) | `password=***` 확인, `journalctl -g 'password=[0-9]'` 0건 |
| 평문 비밀번호 journal 파일 격리·삭제 | `/var/log`, `~/.bash_history`, FlareSolverr 로그 0건 |
| 회귀 검증 | pytest 172 / ruff 46 / mypy 21 — 베이스라인 동일 |

## 8. 개선안 (승인 대기)

| # | 내용 | 판정 |
|---|---|---|
| ① | `lib/toki31_playwright.py` `MINIMAL_REQUEST_HEADERS`에서 **`zstd` 제거** (또는 `Accept-Encoding` 미지정) | **우선** — 수집기 자체 복구 |
| ② | `discover_toki31()`에 `candidate_bases()` **미러 루프** 추가 | 유효 — 미러를 실질적으로 작동시키는 핵심 |
| ③ | **제출 URL 호스트를 base로 갱신** (단순 sbxh9 승격 대신 자동화) | 유효 — `base_url: newtoki31.com` 죽은 상태 해소 |
| ④ | `newtoki1.org` 폴백 추가 | **폐기** — 403 + 구버전. 추적하지 않음(사용자 결정) |
| ⑤ | `ebook-watcher` 재시동 | 피드 갱신·점검 감지·미러 자동등록 활성화 (실험 필요) |

## 9. 관련 파일

| 파일 | 관련 위치 |
|---|---|
| `apps/backend/sources.json` | toki31 `base_url` / `domains` |
| `apps/backend/routers/pipeline.py` | `parse_url` 67 · `start_pipeline` 649 · detect 호출 667 · `ResetRequest` 613 · `pipeline_reset` 797 |
| `apps/backend/lib/domain_router.py` | `classify_source_by_url` 157 · `detect_and_register_source` 185 · no-op 203~205 |
| `apps/backend/lib/sources.py` | `add_source_domain` 199 (`set_base`) |
| `apps/backend/lib/toki31_playwright.py` | `MINIMAL_REQUEST_HEADERS` · `_block_unnecessary` · `candidate_bases` 877 · `_MIN_HEADERS_ENV` |
| `apps/backend/lib/official_feed.py` | 피드 파싱·maintenance·`DOMAIN_HINTS` (loop 미적용) |
| `scripts/pipeline.py` | `_check_domain_health_once` 330(DNS-only) · `discover_toki31` 602 · `_refresh_official_feed` 54/2686 · maintenance skip 2751 |
| `apps/backend/main.py` | `_RedactSecretsFilter` |

## 10. 외부 출처

- https://playwright.dev/docs/api/class-browsercontext (extra HTTP headers 범위)
- https://github.com/microsoft/playwright/issues/37032 (zstd 미해제)
- https://github.com/microsoft/playwright/issues/39292 (fulfill 헤더/본문 불일치)
- https://developer.chrome.com/blog/new-in-chrome-123 (Chrome 123 zstd 지원)
- https://t.me/toki1234/5 (2026-09-23 점검·롤백 공지)
- https://man.archlinux.org/man/apt-transport-mirror.1.en (미러리스트 자동 페일오버)
- 전체 원장: `/home/opc/research_report.md` (31 citations)
