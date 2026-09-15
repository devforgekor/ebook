# 조치 요약: 성인(adult) 카테고리 추가 및 "방 빼!" 이동

## 1. 디렉토리 구조 변경
- `/opt/ai_data/flaresolverr/adult/` 디렉토리 생성
- 기존 웹툰 폴더 `/opt/ai_data/flaresolverr/webtoons/방_빼!` 를 `/opt/ai_data/flaresolverr/adult/방_빼!` 로 이동

## 2. 메타데이터 업데이트
- `/opt/ai_data/flaresolverr/adult/방_빼!/meta.json` 의 `media_type` 필드를 `"webtoon"` → `"adult"` 로 변경

## 3. 데이터베이스 동기화
- SQLite DB(`/opt/ai_data/flaresolverr/ebooklib.db`) の `novels` 테이블에서 `id='방_빼!'` 의 `media_type` 를 `"adult"` 로 업데이트

## 4. 백엔드 경로 설정 (`lib/paths.py`)
- `MEDIA_DIRS` 사전에 `"adult": LIBRARY_ROOT / "adult"` 추가
- `MEDIA_TYPES` 튜플에 자동 반영
- `normalize_media_type`, `media_dir`, `find_novel_dir`, `find_novel_dir_with_type`, `iter_media_dirs`, `iter_novel_dirs`, `ensure_media_dirs` 등이 자동으로 adult를 처리

## 5. 프론트엔드 타입 및 UI 업데이트
- `/opt/workspace/ebooklib/apps/frontend/lib/api.ts`
  - `export type MediaType` 에 `"adult"` 추가
- `/opt/workspace/ebooklib/apps/frontend/app/LibraryClient.tsx`
  - `MEDIA_TYPE_LABEL`에 `"adult": "성인"` 추가
  - `TABS` 배열에 `{ value: "adult", label: "성인" }` 추가

## 6. 검증
- **백엔드 API**: `/api/novels` 에서 `"방_빼!"` 의 `media_type` 가 `"adult"` 로 반환됨
- **표지 이미지**: `/opt/ai_data/flaresolverr/covers/방_빼!.png` 존재 및 `/api/covers/방_빼!.png` 로 정상 제공 (Content-Type: image/png)
- **챕터 목록**: `/api/novels/방_빼!/chapters` 로 10화 정상 조회
- **EPUB 생성**: `services.epub.build_epub('방_빼!')` 로 約4.8MB EPUB 생성 성공 (표지 포함)
- **프론트엔드 탭**: 라이브러리 화면에서 "성인" 탭 선택 시 "방 빼!" 가 표시됨 (필터링 로직 동일)

## 7. 결과
- "방 빼!" 는 이제 성인 카테고리에 소속되어 있으며, 기존 웹툰 카테고리에서 제거됨.
- 모든 관련 로직이 개정되어 시스템이 일관되게 동작함.
