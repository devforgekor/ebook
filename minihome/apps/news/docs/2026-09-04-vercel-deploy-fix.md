# Vercel 배포 전환 및 코드 정리 패치 (2026-09-04)

> **갱신 (2026-09-09)**: 이후 아키텍처를 "devforge에서 처리, Vercel은 표시 전용"으로
> 확정. Vercel 코드 배포는 `.github/workflows/deploy.yml`(GitHub Actions, `web/**`
> push 시 Vercel API 배포)로 전환하여, collector의 `_trigger_vercel_deploy()`(CLI 배포)
> 단계는 제거됨.
>
> **추가 갱신 (2026-09-09, 당일 2차)**: **Neon DB를 완전히 제거.** devforge 로컬 DB가
> 단일 SSOT가 되고, Vercel은 devforge News Read API(`/news/*`, news_api.py)를 fetch해
> 표시만 한다. 상세: `2026-09-09-no-neon-architecture.md` 참고.

## 문제 상황

`https://mini-news.vercel.app/articles` 접속 시 `404 This page could not be found` 오류 발생.
브라우저 창에 "전자책 라이브러리" 타이틀이 노출되고 뉴스 기사가 전혀 표시되지 않았음.

## 원인 분석

### 1. Vercel Git 통합으로 잘못된 코드 배포

Vercel 'news' 프로젝트(`mini-news.vercel.app`)는 GitHub 리포지토리 `Minipark-KOR/news`와 Git 통합 연결되어 있었음.
`rootDirectory`가 `.`(루트)로 설정되어 있어 Git push 시 리포지토리 루트에서 빌드가 실행됨.

**Production 배포의 실제 빌드 로그**:
```
> frontend@0.1.0 build
Route (app)
├ ƒ /novel/[id]           ← 전자책(ebooklib) 라우트
├ ƒ /novel/[id]/chapter/[wr_id]
```

- `package name: frontend` → `apps/ebook/frontend`의 package.json
- `novel/[id]` 라우트 → ebooklib(전자책 라이브러리) 앱
- `workspace sync` 과정에서 ebooklib 파일이 리포지토리에 포함되어 엉뚱한 코드가 배포됨

**Preview 배포(CLI)는 정상**:
```
> web@0.1.0 build
Route (app)
├ ƒ /articles
├ ƒ /articles/[id]
```
- Preview 배포는 CLI로 `web/` 디렉토리에서 직접 실행했기 때문에 올바른 뉴스 앱이 배포됨

### 2. `collector.py` 코드 중복

`/opt/workspace/minihome/apps/news/collector.py` 파일에 다음과 같은 함수들이 중복 정의되어 있었음:

| 함수 | 1번째 정의 (라인) | 2번째 정의 (라인) | 문제 |
|------|-------------------|-------------------|------|
| `_trigger_summary_retry()` | 228 | 300 (dead code) | 의도: _verify_deployment 내부에서 실행되다가 분리된 흔적 |
| `_git_push()` | 290 (deprecated stub) | 322 (실제 구현) | git push 로직이 2개, 첫 번째는 미사용 |
| `_verify_deployment()` | 296 | — | 300번 라인에 dead code(string) 포함 |
| `_check_and_alert_critical_failures()` | 250 (standalone) | 863 (class method) | 동일 로직이 2개, standalone은 미사용 |

원인: 이전 리팩터 과정에서 함수를 분리/이동했으나 기존 정의를 제거하지 않음.
Python은 나중에 정의된 함수가 이전 정의를 덮어쓰므로, `_git_push()`의 실제 구현(322번째 정의)만 실행됨.

### 3. `summary_retry.py` Import 에러

`from collector import _sync_to_neon` 구문이 `ImportError` 발생:
- Python은 `collector`를 **모듈**(`collector.py`)이 아닌 **패키지**(`collector/` 디렉토리)로 먼저 인식
- `collector/__init__.py`가 빈 파일이므로 `_sync_to_neon` 심볼을 찾을 수 없음
- collector.py(모듈)와 collector/(패키지)의 이름 충돌

### 4. `articles/page.tsx` SQL 쿼리에서 `pipeline_state` 누락

`/articles` 페이지의 SQL SELECT 문에 `pipeline_state` 컬럼이 없어서,
`ArticlesClient.tsx`가 `pipeline_state === "needs_summary"` 조건을 판별할 수 없었음.

```sql
-- BEFORE
SELECT id, title, title_ko, ..., summary_ko, highlights_ko
--                                       ↑ pipeline_state 없음

-- AFTER
SELECT id, title, title_ko, ..., summary_ko, highlights_ko, pipeline_state
--                                                            ↑ 추가됨
```

이로 인해 요약이 없는 기사들은 `"요약 생성 중..."` 메시지조차 표시되지 않고 제목만 보임.

## 수정 사항

### 1. Vercel 프로젝트 설정 변경

```
실행: vercel git disconnect
이전: Git 통합 활성화 (GitHub push → 자동 배포)
이후: Git 통합 해제 (CLI로만 배포)
```

- Vercel 'news' 프로젝트의 Git 통합을 해제하여 GitHub push가 자동 배포를 트리거하지 않도록 변경
- 배포 방식: `vercel deploy --prod --yes --cwd web/` (CLI 명령어)

### 2. 새 배포 함수 `_trigger_vercel_deploy()` 추가

**파일**: `collector.py` (250-280번째 라인)

```python
def _trigger_vercel_deploy() -> bool:
    """Deploy news web app to Vercel production via CLI (no git push)."""
    ...
    result = subprocess.run(
        ["vercel", "deploy", "--prod", "--yes", "--cwd", str(web_dir)],
        capture_output=True, text=True, timeout=120
    )
```

**변경 사항**:
- `_git_push()` (git add → commit → push → Vercel 자동배포 의존) → **제거**
- `_trigger_vercel_deploy()` (직접 `vercel deploy --prod --cwd web/` 실행) → **신규 추가**
- 수집 완료 후 deploy 호출 추가 (ISR revalidation 직후)

### 3. 중복 함수 제거

**파일**: `collector.py`

제거된 함수들:
- `_check_and_alert_critical_failures(self)` standalone (250번째 라인) → **제거**, class method (863번째 라인) 유지
- `_git_push()` deprecated stub (290번째 라인) → **제거**
- `_verify_deployment()` (296번째 라인, 내부 dead code 포함) → **제거**
- `_git_push()` 실제 구현 (322번째 라인) → **제거** (`_trigger_vercel_deploy()`로 대체)

### 4. `articles/page.tsx` SQL 쿼리 수정

**파일**: `web/src/app/articles/page.tsx`

```sql
-- BEFORE (43-44번째 라인)
SELECT id, title, title_ko, source, language, category,
       summary_ko, highlights_ko,

-- AFTER (수정)
SELECT id, title, title_ko, source, language, category,
       summary_ko, highlights_ko, pipeline_state,
```

`pipeline_state` 컬럼을 SELECT에 추가하여 `ArticlesClient.tsx`가 요약 상태를 정확히 판별 가능하도록 수정.

### 5. `summary_retry.py` Import 방식 변경

**파일**: `summary_retry.py`

```python
# BEFORE (26번째 라인)
from collector import _sync_to_neon  # ImportError: collector/ 패키지와 충돌

# AFTER
import importlib.util
_collector_spec = importlib.util.spec_from_file_location(
    "_collector_mod", os.path.join(_NEWS, "collector.py"))
_collector_mod = importlib.util.module_from_spec(_collector_spec)
_collector_spec.loader.exec_module(_collector_mod)
_sync_to_neon = _collector_mod._sync_to_neon
```

- `collector` 모듈(패키지 아님)을 `importlib.util.spec_from_file_location`으로 직접 로드
- `collector/` 패키지와의 이름 충돌 회피

### 6. `summary_retry` 실행

```
실행: python3 summary_retry.py --loops 3
결과: 10개 기사 요약 생성 완료, 11개는 본문 부족으로 summary_failed 처리
```

- `collector.py`의 `_check_missing_summaries()`가 `pipeline_state = 'needs_summary'`로 마킹한 기사들 처리
- `summary_retry.py`가 `translate_to_korean()` API를 호출하여 요약 생성
- 본문이 없거나 100자 미만인 기사는 `pipeline_state = 'summary_failed'`로 마킹

## 현재 동작 방식

```
수집 완료 (collector.py)
  → NeonDB 동기화 (_sync_to_neon)
  → ISR 캐시 재검증 (_trigger_vercel_revalidation)
  → Vercel CLI 배포 (_trigger_vercel_deploy)  ← 신규
  → summary_retry 트리거 (systemd)
```

## 확인 결과

```
https://mini-news.vercel.app/articles
- 기사: 27개
- 요약 표시: 27개
- HTTP 200 정상 응답
- 브라우저 타이틀: "Mini News"
```