#!/usr/bin/env python3
# Status: production
# Path: systemd:devforge-news-api.service
"""DevForge News Read API — Vercel(표시 전용)용 읽기 전용 HTTP API.

Neon DB 없이 로컬 devforge_app DB(news_articles)를 직접 조회해 JSON으로 제공.
Vercel Next.js가 이 API를 fetch해서 화면에 표시한다 (처리는 전부 devforge에서).

Usage:
  python3 news_api.py              # 127.0.0.1:8091 (Caddy /news/* 뒤)
  python3 news_api.py --port 8091

Endpoints (Caddy가 /news/* 접두사를 제거하므로 내부 경로 기준):
  GET /health
  GET /dates                       — 수집일(KST) 목록 (내림차순)
  GET /articles?date=YYYY-MM-DD    — 해당 수집일 기사 목록
  GET /articles/<id>               — 기사 상세
  GET /articles/<id>/related       — 같은 dedup 그룹의 관련 기사
  GET /stats                       — 대시보드 통계
  GET /sources                     — 소스별 집계

전부 GET + 읽기 전용. stdlib(http.server)만 사용 → 별도 패키지 의존성 없음.
응답은 20초 인메모리 캐시로 DB/서브프로세스 부하를 줄인다.
"""

import json
import re
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict

_SCRIPTS = "/opt/projects/server/scripts"
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from lib.db import psql_json, esc_sql

HOST = "127.0.0.1"
PORT = 8091
CACHE_TTL_SEC = 20.0

# 요약/관련목록 등 화면에 필요한 컬럼 (embedding/metadata 제외 → payload 절감)
LIST_COLUMNS = (
    "id, title, title_ko, source, language, category, "
    "summary_ko, highlights_ko, pipeline_state, "
    "published_at, collected_at, url, relevance_score, dedup_group_id, summary"
)
DETAIL_COLUMNS = (
    "id, title, title_ko, source, language, category, "
    "summary_ko, highlights_ko, pipeline_state, "
    "published_at, collected_at, url, relevance_score, "
    "concept_ids, dedup_group_id, full_text, summary"
)

# ── 경량 인메모리 TTL 캐시 ──────────────────────────────────────────
_cache: Dict[str, tuple[float, Any]] = {}


def _cached(key: str, ttl: float = CACHE_TTL_SEC) -> Any:
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    return None


def _store(key: str, value: Any) -> Any:
    _cache[key] = (time.time(), value)
    if len(_cache) > 256:  # 방어: 무한 성장 방지
        now = time.time()
        for k in [k for k, (ts, _) in _cache.items() if now - ts > CACHE_TTL_SEC * 3]:
            _cache.pop(k, None)
    return value


def _rows(sql: str) -> list:
    return psql_json(sql)


def _send_json(handler: BaseHTTPRequestHandler, payload: Any, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "public, max-age=15")
    handler.end_headers()
    handler.wfile.write(body)


def _send_error(handler: BaseHTTPRequestHandler, status: int, msg: str) -> None:
    _send_json(handler, {"error": msg}, status)


# ── 라우트 구현 ─────────────────────────────────────────────────────


def _route_health(handler: BaseHTTPRequestHandler) -> None:
    cnt = psql_json("SELECT COUNT(*) AS n FROM news_articles WHERE title != 'Test Article'")
    _send_json(handler, {
        "ok": True,
        "total": int(cnt[0]["n"]) if cnt else 0,
        "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })


def _route_dates(handler: BaseHTTPRequestHandler) -> None:
    cached = _cached("dates")
    if cached is not None:
        return _send_json(handler, cached)
    rows = _rows(
        "SELECT DISTINCT to_char(DATE(collected_at AT TIME ZONE 'Asia/Seoul'), 'YYYY-MM-DD') AS date "
        "FROM news_articles WHERE title != 'Test Article' ORDER BY date DESC"
    )
    _send_json(handler, _store("dates", rows))


def _route_articles_by_date(handler: BaseHTTPRequestHandler, query: Dict[str, str]) -> None:
    date = (query.get("date") or "").strip()
    if not date:  # 날짜 미지정 → 최신 날짜 기본값
        latest = _rows(
            "SELECT to_char(MAX(DATE(collected_at AT TIME ZONE 'Asia/Seoul')),'YYYY-MM-DD') AS d "
            "FROM news_articles WHERE title != 'Test Article'"
        )
        date = (latest[0].get("d") if latest else "") or ""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        return _send_error(handler, 400, "date is required as YYYY-MM-DD")
    key = f"articles:{date}"
    cached = _cached(key)
    if cached is not None:
        return _send_json(handler, cached)
    rows = _rows(
        f"SELECT {LIST_COLUMNS} FROM news_articles "
        f"WHERE title != 'Test Article' "
        f"AND to_char(DATE(collected_at AT TIME ZONE 'Asia/Seoul'), 'YYYY-MM-DD') = '{esc_sql(date)}' "
        f"ORDER BY published_at DESC NULLS LAST"
    )
    _send_json(handler, _store(key, rows))


def _route_article_detail(handler: BaseHTTPRequestHandler, article_id: int) -> None:
    key = f"article:{article_id}"
    cached = _cached(key)
    if cached is not None:
        if cached is None:
            return _send_error(handler, 404, "not found")
        return _send_json(handler, cached)
    rows = _rows(f"SELECT {DETAIL_COLUMNS} FROM news_articles WHERE id = {article_id}")
    if not rows:
        _store(key, None)
        return _send_error(handler, 404, "not found")
    _send_json(handler, _store(key, rows[0]))


def _route_related(handler: BaseHTTPRequestHandler, article_id: int) -> None:
    key = f"related:{article_id}"
    cached = _cached(key)
    if cached is not None:
        return _send_json(handler, cached)
    rows = _rows(
        "SELECT id, title, title_ko, source, relevance_score, published_at "
        "FROM news_articles "
        "WHERE dedup_group_id = (SELECT dedup_group_id FROM news_articles WHERE id = "
        f"{article_id}) AND id != {article_id} "
        "ORDER BY published_at DESC NULLS LAST LIMIT 5"
    )
    _send_json(handler, _store(key, {"articles": rows}))


def _route_stats(handler: BaseHTTPRequestHandler) -> None:
    cached = _cached("stats")
    if cached is not None:
        return _send_json(handler, cached)
    where = "WHERE title != 'Test Article'"
    total = _rows(f"SELECT COUNT(*) AS n FROM news_articles {where}")
    by_category = _rows(
        f"SELECT category, COUNT(*) AS count FROM news_articles {where} GROUP BY category ORDER BY count DESC"
    )
    by_language = _rows(
        f"SELECT language, COUNT(*) AS count FROM news_articles {where} GROUP BY language ORDER BY count DESC"
    )
    by_source = _rows(
        f"SELECT source, COUNT(*) AS count FROM news_articles {where} GROUP BY source ORDER BY count DESC LIMIT 10"
    )
    recent = _rows(
        "SELECT to_char(DATE(collected_at AT TIME ZONE 'Asia/Seoul'), 'YYYY-MM-DD') AS date, "
        "COUNT(*) AS count FROM news_articles WHERE title != 'Test Article' "
        "GROUP BY 1 ORDER BY date DESC LIMIT 7"
    )
    payload = {
        "total": int(total[0]["n"]) if total else 0,
        "byCategory": by_category,
        "byLanguage": by_language,
        "bySource": by_source,
        "recent": recent,
    }
    _send_json(handler, _store("stats", payload))


def _route_sources(handler: BaseHTTPRequestHandler) -> None:
    cached = _cached("sources")
    if cached is not None:
        return _send_json(handler, cached)
    rows = _rows(
        "SELECT source, language, category, COUNT(*) AS article_count, "
        "MAX(collected_at) AS last_collected "
        "FROM news_articles WHERE title != 'Test Article' "
        "GROUP BY source, language, category ORDER BY article_count DESC"
    )
    _send_json(handler, _store("sources", {"sources": rows}))


# ── HTTP Handler ────────────────────────────────────────────────────


class NewsHandler(BaseHTTPRequestHandler):
    server_version = "NewsReadAPI/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[news-api] {self.address_string()} {fmt % args}\n")

    def do_GET(self):  # noqa: N802
        try:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            query = dict(urllib.parse.parse_qsl(parsed.query))

            if path == "/health":
                return _route_health(self)

            if path == "/dates":
                return _route_dates(self)

            if path == "/articles":
                return _route_articles_by_date(self, query)

            if path == "/stats":
                return _route_stats(self)

            if path == "/sources":
                return _route_sources(self)

            # /articles/<id> 및 /articles/<id>/related
            m = re.fullmatch(r"/articles/(\d+)(/related)?", path)
            if m:
                article_id = int(m.group(1))
                if m.group(2):
                    return _route_related(self, article_id)
                return _route_article_detail(self, article_id)

            return _send_error(self, 404, "unknown path")
        except BrokenPipeError:
            pass
        except Exception as e:  # noqa: BLE001
            try:
                _send_error(self, 500, f"internal error: {e}")
            except Exception:
                pass


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="DevForge News Read API")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--host", default=HOST)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), NewsHandler)
    print(f"[news-api] listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
