#!/usr/bin/env python3
# Status: production
# Path: ebooklib/apps/backend/lib/dataimpulse_monitor.py
"""DataImpulse 공식 API 클라이언트 — 트래픽 실측 비교.

DataImpulse Gateway API (https://gw.dataimpulse.com:777) 사용:
- GET /api/stats: 기본 통계 (total_traffic, traffic_used, traffic_left, used_threads)
- GET /api/stats_with_history: 일별 히스토리 포함

Playwright 스크래핑 완전 대체: 60초 → <1초, 10화 제한 → 매 화 호출 가능.

인증: DataImpulse Gateway API는 Basic Auth(user/pass)를 사용한다.
시크릿은 Azure Key Vault에 저장하고 `kv-fetch-env.py`가 환경변수로 주입한다
(SSOT: /opt/projects/server/docs/handover-secrets-kv.md §12/§13).

Key Vault 시크릿 → 환경변수 매핑 (하이픈→밑줄):
    DATAIMPULSE-API-KEY   → DATAIMPULSE_API_KEY   (API/프록시 login)
    DATAIMPULSE-LOGIN     → DATAIMPULSE_LOGIN
    DATAIMPULSE-PASS      → DATAIMPULSE_PASS
    DATAIMPULSE-PROXY-KEY → DATAIMPULSE_PROXY_KEY (user:pass@host:port 결합형)
    DATAIMPULSE-HOST/PORT → DATAIMPULSE_HOST/PORT

자격증명 우선순위:
1. DATAIMPULSE_PROXY_KEY (결합형, KV)
2. DATAIMPULSE_API_KEY / DATAIMPULSE_LOGIN / DATAIMPULSE_USER (개별 env, KV)
3. .env.local (로컬 개발용 템플릿, git 미포함)

서버 하드코딩 금지 — 시크릿 값은 코드에 두지 않는다.
"""

import logging
import os
import time
from pathlib import Path
from typing import Optional

import requests
import urllib3

from lib.bucket_meter import (
    DEFAULT_API_POINTS_PATH,
    ApiPoint,
    append_api_snapshots,
    prune_api_snapshots,
)
from lib.traffic_guard import summary as get_traffic_summary

# SSL 검증 비활성화 (자체 서명 인증서 대응)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

API_BASE = "https://gw.dataimpulse.com:777"
STATS_ENDPOINT = "/api/stats"
STATS_HISTORY_ENDPOINT = "/api/stats_with_history"

# 상태 파일: API 응답 캐시 및 비교 이력
STATE_FILE = Path('/opt/ai_data/flaresolverr/ebook_watcher/dataimpulse_api_state.json')


def _parse_proxy_key(value: str) -> tuple[str, str]:
    """결합형 프록시 키 'user:pass@host:port' → (user, pass)."""
    if "@" in value:
        cred = value.rsplit("@", 1)[0]
        if ":" in cred:
            user, pw = cred.split(":", 1)
            return user, pw
    return "", ""


def _load_env_local() -> dict:
    """로컬 개발용 .env.local 파싱 (템플릿; 실제 값은 KV 주입)."""
    env: dict = {}
    env_path = Path(__file__).parent.parent / ".env.local"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip()
    return env


def _load_proxy_credentials() -> tuple[str, str]:
    """DataImpulse API/프록시 자격증명 로드 (Basic Auth user, pass).

    우선순위:
    1. 환경변수 — kv-fetch-env.py가 Key Vault에서 주입 (운영/컨테이너)
    2. .env.local — 로컬 개발 템플릿 (git 미포함)
    """
    local = _load_env_local()

    def _env(name: str) -> str:
        return os.getenv(name, "") or local.get(name, "")

    # 1. 결합형 키 (user:pass@host:port)
    combined = _env("DATAIMPULSE_PROXY_KEY")
    if combined and "@" in combined:
        user, passwd = _parse_proxy_key(combined)
        if user and passwd:
            return user, passwd

    # 2. 개별 키 — API-KEY(login) > LOGIN > USER
    user = _env("DATAIMPULSE_API_KEY") or _env("DATAIMPULSE_LOGIN") or _env("DATAIMPULSE_USER")
    passwd = _env("DATAIMPULSE_PASS")

    if not user or not passwd:
        logger.warning(
            "DataImpulse 자격증명 없음 — 환경변수(DATAIMPULSE_API_KEY/DATAIMPULSE_PASS) "
            "또는 .env.local 확인"
        )

    return user, passwd


def _load_api_state() -> dict:
    """API 상태 파일 로드."""
    if STATE_FILE.exists():
        try:
            import json
            return json.loads(STATE_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {
        "last_check": 0,
        "last_api_data": None,
        "comparisons": []
    }


def _save_api_state(state: dict) -> None:
    """API 상태 파일 저장."""
    try:
        import json
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE.with_suffix(f'.tmp.{os.getpid()}')
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(tmp, STATE_FILE)
    except Exception as e:
        logger.warning(f"DataImpulse API 상태 저장 실패: {e}")


def _today_str() -> str:
    """오늘 날짜 문자열 (UTC)."""
    from datetime import datetime
    return datetime.utcnow().strftime('%Y-%m-%d')


_USAGE_HEADER_HINTS = ("usage", "proxy", "quota", "rate", "traffic", "requests")


def _extract_usage_headers(headers) -> dict:
    """DataImpulse 게이트웨이 응답에서 사용량/프록시 관련 헤더만 추출.

    [WHY] §10-3 분석: X-Proxy-Usage 등 게이트웨이 헤더로 과금 힌트를 얻는다.
    인증/쿠키 등 민감 헤더는 힌트 불일치로 자연 제외된다.
    """
    out: dict = {}
    for key, value in (headers or {}).items():
        low = str(key).lower()
        if any(hint in low for hint in _USAGE_HEADER_HINTS):
            out[str(key)] = str(value)[:200]
    return out


def _log_usage_headers(headers: dict) -> None:
    if headers:
        logger.info(f"DataImpulse 사용량 헤더: {headers}")


def fetch_stats() -> Optional[dict]:
    """기본 통계 조회 (/api/stats)."""
    user, passwd = _load_proxy_credentials()
    if not user or not passwd:
        logger.warning("DataImpulse 크레덴셜 없음")
        return None
    
    url = f"{API_BASE}{STATS_ENDPOINT}"
    try:
        resp = requests.get(url, auth=(user, passwd), timeout=10, verify=False)
        if resp.status_code == 200:
            _log_usage_headers(_extract_usage_headers(resp.headers))
            return resp.json()
        else:
            logger.warning(f"DataImpulse API 오류: {resp.status_code} - {resp.text}")
    except Exception as e:
        logger.warning(f"DataImpulse API 호출 실패: {e}")
    return None


def fetch_stats_with_history() -> Optional[dict]:
    """히스토리 포함 통계 조회 (/api/stats_with_history)."""
    user, passwd = _load_proxy_credentials()
    if not user or not passwd:
        logger.warning("DataImpulse 크레덴셜 없음")
        return None
    
    url = f"{API_BASE}{STATS_HISTORY_ENDPOINT}"
    try:
        resp = requests.get(url, auth=(user, passwd), timeout=10, verify=False)
        if resp.status_code == 200:
            _log_usage_headers(_extract_usage_headers(resp.headers))
            return resp.json()
        else:
            logger.warning(f"DataImpulse API 오류: {resp.status_code} - {resp.text}")
    except Exception as e:
        logger.warning(f"DataImpulse API 호출 실패: {e}")
    return None


def get_today_usage(api_data: dict) -> Optional[dict]:
    """API 응답에서 오늘 데이터 추출."""
    if not api_data or 'traffic_history' not in api_data:
        return None
    
    today = _today_str()
    for entry in api_data['traffic_history']:
        if entry.get('group_date', '').startswith(today):
            return {
                'date': today,
                'inbound_mb': round(entry.get('inbound_traffic', 0) / 1024 / 1024, 2),
                'outgoing_mb': round(entry.get('outgoing_traffic', 0) / 1024 / 1024, 2),
                'total_mb': round(entry.get('total_traffic', 0) / 1024 / 1024, 2),
                'requests': entry.get('requests_count', 0),
                'errors': entry.get('errors', 0),
                'raw': entry
            }
    return None


def compare_with_traffic_guard(api_today: dict) -> dict:
    """traffic_guard 실측과 API 실측 비교."""
    tg = get_traffic_summary()
    
    api_mb = api_today['total_mb']
    tg_mb = tg['used_mb']
    diff_mb = api_mb - tg_mb
    diff_pct = (diff_mb / api_mb * 100) if api_mb > 0 else 0
    
    result = {
        "timestamp": time.time(),
        "date": api_today['date'],
        "api_mb": api_mb,
        "tg_mb": tg_mb,
        "diff_mb": round(diff_mb, 2),
        "diff_pct": round(diff_pct, 1),
        "tg_chapters": tg['chapters'],
        "api_requests": api_today['requests'],
        "api_inbound_mb": api_today['inbound_mb'],
        "api_outgoing_mb": api_today['outgoing_mb'],
    }
    
    # 로깅
    logger.info(
        f"📊 DataImpulse API 비교: "
        f"API={api_mb:.2f}MB (in:{api_today['inbound_mb']:.2f} out:{api_today['outgoing_mb']:.2f}) | "
        f"TG={tg_mb:.2f}MB | "
        f"차이={diff_mb:+.2f}MB ({diff_pct:+.1f}%) | "
        f"TG챕터={tg['chapters']} API요청={api_today['requests']}"
    )
    
    if abs(diff_pct) > 20:
        logger.warning(
            f"⚠️ TG-API 격차 큼 ({diff_pct:+.1f}%) — "
            f"TG가 API 대비 {'과소' if diff_mb > 0 else '과대'} 측정 중"
        )
    
    return result


def _maybe_calibrate_daily(api_data: dict, bucket_ratio: "Optional[float]" = None) -> None:
    """보정계수를 '가장 최근 완료된 수집일' 총량 기준으로 1일 1회 갱신.

    [WHY] DataImpulse API 카운터는 단구간(수십 화)에서 비단조·청크 갱신이라
    per-chapter/per-window 비율이 0.55~0.75로 흔들린다. 또한 수집은 매일 하지
    않으므로 '어제' 고정이 아니라, 마지막으로 수집이 있었던 날(prev_day)의
    총량을 기준으로 삼는다. 같은 날짜에 대해 중복 갱신하지 않는다.
    """
    from lib.traffic_guard import _update_calibration_factor_ewma, get_prev_day

    prev = get_prev_day() or {}
    day = prev.get('date')
    if not day:
        logger.info("보정계수 갱신 대기: 완료된 수집일(prev_day) 없음")
        return

    state = _load_api_state()
    if state.get('calibration_last_day') == day:
        return  # 이 수집일은 이미 보정함

    # ① 버킷 중앙값 r (완결·웜) 우선 — 단구간 노이즈에 강함(호출자가 전달)
    ratio = bucket_ratio
    ratio_source = "bucket_median" if bucket_ratio is not None else None

    # ② 폴백: 전일 총량비 (prev_day)
    if ratio is None:
        api_day_mb = None
        for entry in (api_data.get('traffic_history') or []):
            if entry.get('group_date', '').startswith(day):
                api_day_mb = entry.get('total_traffic', 0) / 1024 / 1024
                break
        tg_day_mb = prev.get('bytes', 0) / 1024 / 1024
        if api_day_mb and tg_day_mb > 0:
            ratio = api_day_mb / tg_day_mb
            ratio_source = "prev_day"

    if ratio is not None:
        _update_calibration_factor_ewma(ratio)
        state['calibration_last_day'] = day
        _save_api_state(state)
        logger.info(f"보정계수 갱신(수집일 {day}, {ratio_source}): r={ratio:.3f}")
    else:
        logger.info(
            f"보정계수 갱신 대기: 수집일 {day} 데이터 불충분 "
            f"(api_history/tg_bytes={prev.get('bytes')})"
        )


def check_dataimpulse_sync() -> dict:
    """동기 버전 — 파이프라인에서 직접 호출.
    
    Returns:
        dict: success, api_data, comparison, message
    """
    # 히스토리 포함 조회 (오늘 데이터 필터링용)
    api_data = fetch_stats_with_history()
    
    if not api_data:
        return {"success": False, "message": "API 조회 실패"}
    
    api_today = get_today_usage(api_data)
    if not api_today:
        return {"success": False, "message": "오늘 데이터 없음"}
    
    comparison = compare_with_traffic_guard(api_today)

    # [WHY] 원시 스냅샷 보존(plan §14.2): 수집 시간대 버킷 r 역산을 위해 append-only 보관.
    #       comparisons(-100 롤링)는 파생이라 원시가 아니므로 별도 파일에 남긴다. fail-open.
    try:
        append_api_snapshots(
            DEFAULT_API_POINTS_PATH,
            [
                ApiPoint(
                    ts=time.time(),
                    date=str(api_today["date"]),
                    mb=float(api_today["total_mb"]),
                )
            ],
        )
        prune_api_snapshots(DEFAULT_API_POINTS_PATH)
    except Exception as e:
        logger.debug(f"원시 스냅샷 기록 실패(무시): {e}")

    # 버닝레이트 입력: 사용량 스냅샷(5분 throttle, 24h 링)
    try:
        from lib.traffic_guard import record_usage_sample

        record_usage_sample()
    except Exception as e:
        logger.debug(f"사용량 스냅샷 기록 실패(무시): {e}")

    # 버킷: 팩트 계산+영속(1회), 소비 급증 안전망, 기준선 시딩
    bucket_facts = []
    bucket_ratio = None
    try:
        from lib.bucket_meter import (
            DEFAULT_BUCKET_SIZE,
            bucket_ratio_median_from_facts,
            compute_config_hash,
            kb_per_chapter,
            latest_tg_warm_fact,
            record_bucket_facts,
            tg_baseline_stats_from_facts,
        )
        from lib.traffic_guard import (
            get_bucket_baseline,
            seed_bucket_baseline,
            update_bucket_anomaly,
        )

        flags = {
            "launch_tuning": os.getenv("EBOOK_TOK31_LAUNCH_TUNING", "1"),
            "min_headers": os.getenv("EBOOK_TOK31_MIN_HEADERS", "1"),
            "cdp_block": os.getenv("EBOOK_TOK31_CDP_BLOCK", "0"),
            "bucket_size": str(DEFAULT_BUCKET_SIZE),
        }
        bucket_facts = record_bucket_facts(config_hash=compute_config_hash(flags))
        bucket_ratio = bucket_ratio_median_from_facts(bucket_facts)

        # 초기 기준선은 과거 완결·웜(TG) 버킷에서 1회 시딩(콜드는 제외됨)
        if get_bucket_baseline() is None:
            stats = tg_baseline_stats_from_facts(bucket_facts)
            if stats:
                seed_bucket_baseline(
                    stats["kb_per_chapter_median"], stats["kb_per_chapter_stdev"]
                )

        fact = latest_tg_warm_fact(bucket_facts)
        if fact is not None:
            res = update_bucket_anomaly(
                kb_per_chapter(fact), event_id=fact.get("event_id")
            )
            if res.get("stop"):
                logger.critical("🚨 버킷 소비 급증 5연속 — 파이프라인 중지 플래그 설정됨")
    except Exception as e:
        logger.debug(f"버킷 안전망 평가 실패(무시): {e}")

    # P6 정합: 일별 확정 API ↔ 버킷 롤업 정산(콜드/경계/미귀속 gap 가시화)
    reconcile_result = None
    try:
        from lib.bucket_meter import daily_reconcile
        from lib.traffic_guard import get_prev_day

        history = api_data.get('traffic_history') or []
        day = (get_prev_day() or {}).get('date')
        if not day and history:
            day = str(history[-1].get('group_date', ''))[:10]
        if day:
            reconcile_result = daily_reconcile(bucket_facts, history, day)
            logger.info(
                f"P6 정합({day}): API={reconcile_result['api_billed_mb']}MB "
                f"rollup={reconcile_result['rollup_api_mb']}MB "
                f"gap={reconcile_result['gap_mb']}MB TG={reconcile_result['tg_mb']}MB "
                f"r={reconcile_result['r_day']}"
            )
    except Exception as e:
        logger.debug(f"P6 정합 실패(무시): {e}")

    # 보정계수: 버킷 중앙값 r(전달) 우선, 없으면 전일 총량 (1일 1회)
    try:
        _maybe_calibrate_daily(api_data, bucket_ratio=bucket_ratio)
    except Exception as e:
        logger.debug(f"일일 보정계수 갱신 실패: {e}")

    # 상태 저장
    state = _load_api_state()
    state["last_check"] = time.time()
    state["last_api_data"] = api_today
    state.setdefault("comparisons", []).append(comparison)
    # 최근 100개만 유지
    state["comparisons"] = state["comparisons"][-100:]
    # [WHY] API 오늘값은 청크 갱신으로 하향 튐 → 일중 최대값(단조 봉투) 유지.
    # 소비처: traffic_guard.api_daily_used_mb (한도 판정 과소추정 방지)
    today_mb = float(api_today.get("total_mb") or 0)
    if state.get("api_today_date") != api_today.get("date"):
        state["api_today_date"] = api_today.get("date")
        state["api_today_max_mb"] = today_mb
    else:
        state["api_today_max_mb"] = max(
            float(state.get("api_today_max_mb") or 0), today_mb
        )
    # P6/P5: 확정 API 일별 총량 히스토리(최근 90일) + 최근 정합 결과
    hist = state.setdefault("api_history", {})
    for entry in (api_data.get("traffic_history") or []):
        gd = str(entry.get("group_date", ""))[:10]
        if gd:
            hist[gd] = round(float(entry.get("total_traffic", 0) or 0) / (1024 * 1024), 3)
    if len(hist) > 90:
        for key in sorted(hist)[:-90]:
            hist.pop(key, None)
    if reconcile_result is not None:
        state["last_reconcile"] = reconcile_result
    _save_api_state(state)
    
    return {
        "success": True,
        "api_data": api_today,
        "comparison": comparison,
        "message": f"API={api_today['total_mb']:.2f}MB TG={comparison['tg_mb']:.2f}MB diff={comparison['diff_pct']:+.1f}%"
    }


# 하위 호환: 기존 함수명 유지
def check_dataimpulse_usage(cdp_url: str = "http://127.0.0.1:9222") -> dict:
    """기존 인터페이스 호환 — Playwright 제거, API로 대체."""
    return check_dataimpulse_sync()


def _log_comparison(result: dict):
    """기존 호환 — 비교 로깅은 compare_with_traffic_guard에서 수행."""
    pass


def _log_fallback_status(result: dict):
    """기존 호환 — fallback 로깅."""
    pass


if __name__ == "__main__":
    # 직접 실행 테스트
    import logging
    logging.basicConfig(level=logging.INFO)
    
    print("=== DataImpulse API 테스트 ===")
    result = check_dataimpulse_sync()
    print(f"Success: {result['success']}")
    print(f"Message: {result['message']}")
    if result.get('api_data'):
        print(f"API Today: {result['api_data']}")
    if result.get('comparison'):
        print(f"Comparison: {result['comparison']}")