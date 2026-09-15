# Neon DB 제거 — devforge 단일 저장소 + News Read API (2026-09-09)

## 결정
- **Neon DB 사용 중단.** 반복되는 동기화/표시 오류 원인을 제거.
- 아키텍처 확정: **devforge가 수집·처리·DB의 단일 SSOT**, **Vercel은 표시 전용**.
  Vercel은 devforge가 공개하는 **News Read API**를 fetch해 화면에 표시한다
  (ebook 백엔드와 동일한 분리 패턴).

## 새 데이터 흐름
```
devforge (SSOT)
  collector.py ──▶ 로컬 devforge_app DB (news_articles)
                     ▲
  summary_retry.py ──┘ (요약 재시도 → 로컬만 갱신)

  news_api.py (읽기 전용, 127.0.0.1:8091)
      └─ Caddy: https://devforge.152-69-229-246.nip.io/news/* ──▶ 공개

Vercel (표시 전용, mini-news.vercel.app)
  /articles, /articles/[id]  → devforge News Read API fetch (no-store)
  /api/stats, /api/sources   → devforge API 프록시
```
제거된 것:
- `_sync_to_neon()`, `_prune_neon()` (collector)
- collector/summary_retry의 Vercel ISR revalidation
- web Neon `lib/db.ts`(pg pool) 및 `/api/articles`, `/api/articles/[id]/related`, `/api/revalidate` 라우트
- collector의 Vercel CLI deploy (이미 GH Actions로 전환)

## News Read API (news_api.py)
- stdlib `http.server` 전용 (패키지 의존성 없음), `127.0.0.1:8091`
- 시스템 서비스: `devforge-news-api.service` (user, Restart=on-failure)
- Caddy 서버블록에 `handle_path /news/* → 127.0.0.1:8091`
- 엔드포인트 (Caddy가 `/news` 접두사 제거):
  - `GET /health`
  - `GET /dates` — 수집일(KST)
  - `GET /articles?date=YYYY-MM-DD`
  - `GET /articles/<id>`
  - `GET /articles/<id>/related`
  - `GET /stats`
  - `GET /sources`
- 20초 인메모리 TTL 캐시로 DB 부하 완화. 전부 읽기 전용.

## 운영 Notes
- **가용성 의존**: devforge가 내려가면 사이트 데이터도 멈춤 (Neon 제거의 트레이드오프).
  사이트는 빈 배열/에러 폴백 표시.
- Vercel 배포: `.github/workflows/deploy.yml` (web/** push 시 자동) — devforge에서 CLI 배포 없음.
- 남은 정리(수동): Vercel 대시보드의 `DATABASE_URL`(Neon) 등 환경변수 제거 가능.
- 로컬 `secrets.env`의 `NEON_DATABASE_URL`은 더 이상 사용되지 않음(무해, 제거 가능).
- devforge-news.service 유닛에서 `VERCEL_REVALIDATE_URL` 제거됨.

## 검증
- `curl https://devforge.152-69-229-246.nip.io/news/{health,dates,articles?date=...,stats,sources}` 정상
- collector 실수행: Neon/revalidation 참조 없이 완료 + `Heartbeat recorded (news_collector)`
- web `tsc --noEmit` / `next build` 통과 (Neon 라우트/의존 제거 확인)
