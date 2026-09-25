#!/usr/bin/env python3
# Status: experimental
# Path: ebooklib/apps/backend/lib/traffic_guard.py
"""일일 트래픽 한도 가드 — 프록시 사용량 실측 누적 + 일일 한도 제어.

DataImpulse는 GB당 과금. 과소진 방지를 위해 실제 다운로드 바이트를
누적하고 일일 한도 초과 시 수집을 일시정지한다. (다음 날 자동 리셋)

- 일일 한도: 환경변수 EBOOK_DAILY_TRAFFIC_LIMIT_MB (기본 200MB/일)
- 상태 파일: /opt/ai_data/flaresolverr/ebook_watcher/traffic_state.json
  {"date": "2026-09-10", "bytes": 12345678, "chapters": 45}
- 날짜가 바뀌면 누적 바이트 자동 리셋 → loop가 자정 후 재개
"""

import json
import logging
import math
import os
import time
from typing import Optional
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

STATE_FILE = Path('/opt/ai_data/flaresolverr/ebook_watcher/traffic_state.json')
API_STATE_FILE = Path('/opt/ai_data/flaresolverr/ebook_watcher/dataimpulse_api_state.json')

DEFAULT_DAILY_LIMIT_MB = 200

# 기본 보정 계수 (API 과금 / TG 로컬 측정)
# [WHY] 2026-09-25 확정: 로컬 TG 과소 측정 → API/TG > 1 (실측 1.96, EWMA 1.8051).
# 과금은 wire 바이트(요청+응답, 압축)인데 TG는 응답 바디만 계상한다.
# 상태 유실 시에는 안전측(과대) 기본값 — 과소 추정은 한도 초과(과금)로 이어진다.
DEFAULT_CALIBRATION_FACTOR = 2.0
MIN_CALIBRATION_FACTOR = 1.0
MAX_CALIBRATION_FACTOR = 3.0

# EWMA 보정 계수 설정
CALIBRATION_ALPHA = 0.3           # EWMA 가중치 (0.2~0.4, 최근 3~4샘플 반영)
CALIBRATION_CHANGE_WARN_PCT = 20  # 급변 경고 임계치 (%)

# SPC (Statistical Process Control) 설정
SPC_UCL_MULTIPLIER = 1.20         # UCL = Ref × 1.20 (+20%)
SPC_LCL_MULTIPLIER = 0.80         # LCL = Ref × 0.80 (-20%)
SPC_RULE2_CONSECUTIVE = 5         # Rule 2: Ref 한쪽에 N연속 (편향 감지)
SPC_RULE2_DEADBAND_PCT = 5.0      # Rule 2 데드밴드: ±5% 이내면 무시 (정상 변동)
SPC_RULE3_WARNING_THRESHOLD = 4   # Rule 3: 경고 누적 임계치 (비상중지)

# 버킷 소비 급증 안전망 — 웜 기준선(회차당 KB) 대비
# [WHY] 회차별 값은 부정확하지만(콜드/캐시/사이트 변동) 버킷 누적은 안정적이다.
BUCKET_ANOMALY_DEV_PCT = 20.0            # 상대 하한: 기준선 대비 +20%
BUCKET_ANOMALY_MIN_KB = 5.0              # 절대 하한: +5KB/화 (AND; 소량 버킷 %노이즈 차단)
BUCKET_ANOMALY_UCL_K = 3.0               # NIST EWMA UCL 계수 (CL + k·s·√(λ/(2−λ)))
BUCKET_ANOMALY_ALERT_CONSECUTIVE = 3     # 3연속 = 경보(alert)
BUCKET_ANOMALY_CONSECUTIVE = 5           # 5연속 = 중지(stop)
BUCKET_ANOMALY_SEVERE_PCT = 50.0         # 심각 편차(%)
BUCKET_ANOMALY_SEVERE_CONSECUTIVE = 2    # 심각 편차 2연속 = 조기 중지
BUCKET_ANOMALY_MIN_SAMPLES = 3           # 기준선 EWMA 최소 표본(판정 시작)
BUCKET_ANOMALY_ALPHA = 0.2               # 기준선 EWMA 가중치

# 예측(forecast) 경보 — 산업 표준(예산 예측 초과 경보) 정합
FORECAST_MIN_ELAPSED_SEC = 3600          # 최소 경과(1h) 이전 예측은 폭주하므로 생략


def get_daily_limit_mb() -> int:
    try:
        return int(os.getenv('EBOOK_DAILY_TRAFFIC_LIMIT_MB', str(DEFAULT_DAILY_LIMIT_MB)))
    except (TypeError, ValueError):
        return DEFAULT_DAILY_LIMIT_MB


def daily_limit_bytes() -> int:
    return get_daily_limit_mb() * 1024 * 1024


def _today() -> str:
    return datetime.now().strftime('%Y-%m-%d')


def _state_lock():
    """traffic_state.json 배타 락 — 동시 collect 프로세스의 read-modify-write 경합 방지."""
    import fcntl
    lock_path = STATE_FILE.with_suffix('.lock')
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = open(lock_path, 'w')
    fcntl.flock(fd, fcntl.LOCK_EX)
    return fd


def _state_unlock(fd) -> None:
    import fcntl
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        fd.close()


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {"date": _today(), "bytes": 0, "chapters": 0, "last_exceeded_at": None}


def save_state(state: dict) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE.with_suffix(f'.tmp.{os.getpid()}')
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(tmp, STATE_FILE)
    except Exception as e:
        logger.warning(f"traffic state 저장 실패: {e}")


def reset_if_new_day() -> None:
    """날짜가 바뀌었으면 일일 누적 리셋.

    [WHY] 보정계수는 '전일 총량' 기준으로 1일 1회 갱신한다(단구간 노이즈 차단).
    이를 위해 리셋 직전 전일 totals 를 prev_day 로 보존한다.
    """
    lock = _state_lock()
    try:
        state = load_state()
        if state.get('date') != _today():
            prev = {
                "date": state.get('date'),
                "bytes": int(state.get('bytes', 0)),
                "chapters": int(state.get('chapters', 0)),
            }
            state = {
                "date": _today(),
                "bytes": 0,
                "chapters": 0,
                "last_exceeded_at": None,
                "check_count": 0,
                "prev_day": prev,
                # 보정계수/SPC 등은 날짜 무관하게 유지
                "calibration_factor_ewma": state.get('calibration_factor_ewma'),
                "calibration_factor_raw": state.get('calibration_factor_raw'),
                "calibration_spc": state.get('calibration_spc'),
                "calibration_last_day": state.get('calibration_last_day'),
            }
            save_state(state)
            logger.info(f"traffic guard: 새 일자({_today()}) 리셋 (prev_day {prev['date']} {prev['bytes']/1024/1024:.1f}MB 보존)")
    finally:
        _state_unlock(lock)


def get_prev_day() -> Optional[dict]:
    """전일 totals 반환 {date, bytes, chapters} (없으면 None)."""
    try:
        return load_state().get('prev_day')
    except Exception:
        return None


def current_bytes() -> int:
    return int(load_state().get('bytes', 0))


def add_bytes(n: int, chapter: bool = False) -> dict:
    """다운로드 바이트 누적. chapter=True면 회차 수도 증가."""
    lock = _state_lock()
    try:
        state = load_state()
        state['bytes'] = int(state.get('bytes', 0)) + max(0, int(n))
        if chapter:
            state['chapters'] = int(state.get('chapters', 0)) + 1
        save_state(state)
        return state
    finally:
        _state_unlock(lock)


def remaining_bytes() -> int:
    return max(0, daily_limit_bytes() - current_bytes())


def is_exceeded() -> bool:
    return current_bytes() >= daily_limit_bytes()


def seconds_until_next_day() -> int:
    """다음 자정(로컬)까지 남은 초. 최소 1초."""
    now = datetime.now()
    tomorrow = datetime(now.year, now.month, now.day) + timedelta(days=1)
    return max(1, int((tomorrow - now).total_seconds()))


def summary() -> dict:
    """현재 상태 요약 (로깅/상태 파일용)."""
    limit = daily_limit_bytes()
    used = current_bytes()
    return {
        "daily_limit_mb": get_daily_limit_mb(),
        "used_mb": round(used / (1024 * 1024), 2),
        "remaining_mb": round(max(0, limit - used) / (1024 * 1024), 2),
        "exceeded": used >= limit,
        "chapters": int(load_state().get('chapters', 0)),
    }


def get_check_count() -> int:
    """DataImpulse 체크 카운터 조회 (재시작 시 유지)."""
    return int(load_state().get('check_count', 0))


def increment_check_count() -> int:
    """DataImpulse 체크 카운터 증가 및 저장. 10 도달 시 0으로 리셋 후 0 반환."""
    lock = _state_lock()
    try:
        state = load_state()
        count = int(state.get('check_count', 0)) + 1
        if count >= 10:
            count = 0
        state['check_count'] = count
        save_state(state)
        return count
    finally:
        _state_unlock(lock)


def get_calibration_factor() -> float:
    """현재 EWMA 보정 계수 반환 (traffic_state.json에서 로드)."""
    try:
        state = load_state()
        ewma = state.get('calibration_factor_ewma')
        if ewma is not None:
            return float(ewma)
    except Exception:
        pass
    return DEFAULT_CALIBRATION_FACTOR


def _update_calibration_factor_ewma(latest_factor: float) -> float:
    """EWMA 보정 계수 갱신 + SPC 경고 (중심선 = 이동 EWMA).

    [WHY] 보정계수는 일 단위로 정당하게 이동하므로 '고정 기준선'은 가짜 이상을
    만든다. 중심선을 EWMA로 두어, 한 샘플(raw)이 현재 EWMA의 ±20%를 벗어나거나
    ±5% 데드밴드 밖에서 5연속 같은 방향이면 경고한다.
    자동중지(emergency)는 기본 비활성(경고만). 필요 시 EBOOK_CALIBRATION_AUTOSTOP=1.
    """
    autostop = os.getenv('EBOOK_CALIBRATION_AUTOSTOP', '0').lower() in ('1', 'true', 'yes')

    lock = _state_lock()
    try:
        state = load_state()
        prev_ewma = state.get('calibration_factor_ewma')

        latest_clamped = max(MIN_CALIBRATION_FACTOR, min(MAX_CALIBRATION_FACTOR, latest_factor))
        if prev_ewma is None:
            new_ewma = latest_clamped
        else:
            new_ewma = CALIBRATION_ALPHA * latest_clamped + (1 - CALIBRATION_ALPHA) * prev_ewma
        new_ewma = max(MIN_CALIBRATION_FACTOR, min(MAX_CALIBRATION_FACTOR, new_ewma))

        # 중심선 = 이동 EWMA (매 갱신마다 추종 → 정당한 이동은 이상 아님)
        cl = new_ewma
        ucl = cl * SPC_UCL_MULTIPLIER
        lcl = cl * SPC_LCL_MULTIPLIER

        spc = state.get('calibration_spc', {})
        beyond_ucl = spc.get('beyond_ucl', 0)
        beyond_lcl = spc.get('beyond_lcl', 0)
        same_side_ref = spc.get('same_side_ref', 0)
        warning_count = spc.get('warning_count', 0)

        # Rule 1: raw 가 중심선 ±20% 밖
        rule1 = False
        if latest_clamped > ucl:
            rule1 = True; beyond_ucl += 1; beyond_lcl = 0
            logger.warning(f"⚠️ SPC Rule 1: UCL 초과 | raw={latest_clamped:.4f} CL={cl:.4f} (+{((latest_clamped/cl)-1)*100:.1f}%)")
        elif latest_clamped < lcl:
            rule1 = True; beyond_lcl += 1; beyond_ucl = 0
            logger.warning(f"⚠️ SPC Rule 1: LCL 미만 | raw={latest_clamped:.4f} CL={cl:.4f} ({((latest_clamped/cl)-1)*100:.1f}%)")
        else:
            beyond_ucl = 0; beyond_lcl = 0

        # Rule 2: 데드밴드(±5%) 밖에서 같은 방향 연속
        pct = ((latest_clamped / cl) - 1) * 100
        if pct > SPC_RULE2_DEADBAND_PCT:
            same_side_ref = max(0, same_side_ref) + 1
        elif pct < -SPC_RULE2_DEADBAND_PCT:
            same_side_ref = min(0, same_side_ref) - 1
        else:
            same_side_ref = 0
        rule2 = abs(same_side_ref) >= SPC_RULE2_CONSECUTIVE
        if rule2:
            logger.warning(f"⚠️ SPC Rule 2: CL 편향 {abs(same_side_ref)}연속 | raw={latest_clamped:.4f} CL={cl:.4f} ({pct:+.1f}%)")

        # Rule 3: 경고 누적
        warning_count = min(5, warning_count + 1) if (rule1 or rule2) else max(0, warning_count - 1)
        if warning_count >= SPC_RULE3_WARNING_THRESHOLD:
            if autostop:
                state['calibration_emergency_stop'] = True
                logger.critical(f"🚨 SPC Rule 3: 경고 누적 {warning_count} — 자동중지 플래그 설정(autostop=on)")
            else:
                logger.warning(f"⚠️ SPC Rule 3: 경고 누적 {warning_count} — 경고만(autostop=off)")

        spc.update({
            'beyond_ucl': beyond_ucl, 'beyond_lcl': beyond_lcl,
            'same_side_ref': same_side_ref, 'warning_count': warning_count,
            'ref_baseline': cl, 'last_ucl': ucl, 'last_lcl': lcl,
        })
        state.pop('calibration_spc_ref_baseline', None)  # 구 고정 기준선 제거
        state['calibration_factor_ewma'] = round(new_ewma, 4)
        state['calibration_factor_raw'] = round(latest_clamped, 4)
        state['calibration_updated'] = time.time()
        state['calibration_spc'] = spc
        save_state(state)

        logger.info(f"SPC 갱신: CL={cl:.4f} UCL={ucl:.4f} LCL={lcl:.4f} | raw={latest_clamped:.4f} EWMA={new_ewma:.4f} | 경고={warning_count}")
        return new_ewma

    finally:
        _state_unlock(lock)


def is_calibration_emergency() -> bool:
    """보정 계수 비상 중지 플래그 확인.
    
    5회 연속 20% 이상 급변 감지 시 True 반환.
    파이프라인에서 호출하여 비상 중지 결정에 사용.
    """
    try:
        state = load_state()
        return bool(state.get('calibration_emergency_stop', False))
    except Exception:
        return False


def clear_calibration_emergency() -> None:
    """비상 중지 플래그 해제 (사용자 개입 후 수동 호출)."""
    lock = _state_lock()
    try:
        state = load_state()
        state['calibration_emergency_stop'] = False
        state['calibration_consecutive_spikes'] = 0
        save_state(state)
        logger.info("보정 계수 비상 중지 플래그 해제됨")
    finally:
        _state_unlock(lock)


def update_bucket_anomaly(kb_per_chapter: float, event_id: Optional[str] = None) -> dict:
    """완료된 웜 버킷의 회차당 KB를 진화 기준선(EWMA)과 비교해 소비 급증을 감시.

    판정(표준 정합):
    - 상대 하한 +BUCKET_ANOMALY_DEV_PCT% **그리고** 절대 하한 +BUCKET_ANOMALY_MIN_KB
      **그리고** σ 기반 UCL(CL + k·s·√(λ/(2−λ)), NIST) 초과 → 이상.
    - 경보(alert) = ALERT_CONSECUTIVE 연속, 중지(stop) = CONSECUTIVE 연속 또는
      심각 편차(≥ SEVERE_PCT)가 SEVERE_CONSECUTIVE 연속(조기 중지).
    - 기준선은 정상 샘플만 반영 → 급증이 기준선을 끌어올리지 않는다(20% 중복 누적 방지).
    - event_id 중복 평가 금지(5분 주기 streak 중복 방지).
    """
    lock = _state_lock()
    try:
        state = load_state()
        if event_id and state.get('bucket_last_event_id') == event_id:
            return {"skipped": True, "event_id": event_id}

        baseline = state.get('bucket_kb_ewma')
        var = state.get('bucket_kb_var_ewma')
        samples = int(state.get('bucket_samples', 0))
        streak = int(state.get('bucket_anomaly_streak', 0))
        value = max(0.0, float(kb_per_chapter))

        result = {
            "value": round(value, 2),
            "baseline": None,
            "dev_pct": None,
            "abs_kb": None,
            "sigma": None,
            "streak": streak,
            "alert": False,
            "stop": False,
        }

        if samples < BUCKET_ANOMALY_MIN_SAMPLES:
            base = float(baseline) if baseline is not None else value
            var = (
                (value - base) ** 2
                if var is None
                else BUCKET_ANOMALY_ALPHA * (value - base) ** 2
                + (1 - BUCKET_ANOMALY_ALPHA) * float(var)
            )
            baseline = (
                value
                if baseline is None
                else BUCKET_ANOMALY_ALPHA * value
                + (1 - BUCKET_ANOMALY_ALPHA) * base
            )
            samples += 1
        else:
            base = float(baseline)
            dev = ((value / base) - 1) * 100 if base > 0 else 0.0
            abs_kb = value - base
            sigma = math.sqrt(max(var, 0.0)) if var is not None else None
            s_eff = (
                sigma * math.sqrt(BUCKET_ANOMALY_ALPHA / (2 - BUCKET_ANOMALY_ALPHA))
                if sigma is not None
                else None
            )
            rel_floor = base * (1 + BUCKET_ANOMALY_DEV_PCT / 100)
            ucl = base + BUCKET_ANOMALY_UCL_K * s_eff if s_eff is not None else rel_floor
            threshold = max(rel_floor, ucl)
            is_anomaly = value > threshold and abs_kb >= BUCKET_ANOMALY_MIN_KB
            result.update(
                {
                    "baseline": round(base, 2),
                    "dev_pct": round(dev, 1),
                    "abs_kb": round(abs_kb, 2),
                    "sigma": round(sigma, 3) if sigma is not None else None,
                }
            )
            if is_anomaly:
                streak += 1
                logger.warning(
                    f"⚠️ 버킷 소비 급증 {streak}/{BUCKET_ANOMALY_CONSECUTIVE}: "
                    f"{value:.1f}KB/화 (기준선 {base:.1f}, {dev:+.1f}%, +{abs_kb:.1f}KB)"
                )
            else:
                streak = 0
                var = (
                    BUCKET_ANOMALY_ALPHA * (value - base) ** 2
                    + (1 - BUCKET_ANOMALY_ALPHA) * float(var)
                    if var is not None
                    else (value - base) ** 2
                )
                baseline = (
                    BUCKET_ANOMALY_ALPHA * value + (1 - BUCKET_ANOMALY_ALPHA) * base
                )
            severe = dev >= BUCKET_ANOMALY_SEVERE_PCT
            if streak >= BUCKET_ANOMALY_ALERT_CONSECUTIVE:
                result["alert"] = True
            if streak >= BUCKET_ANOMALY_CONSECUTIVE or (
                severe and streak >= BUCKET_ANOMALY_SEVERE_CONSECUTIVE
            ):
                state['bucket_anomaly_stop'] = True
                result["stop"] = True
                logger.critical(
                    f"🚨 버킷 소비 급증 {streak}연속(편차 {dev:+.1f}%) — 파이프라인 중지 플래그 설정"
                )

        state['bucket_kb_ewma'] = round(float(baseline), 4)
        if var is not None:
            state['bucket_kb_var_ewma'] = round(float(var), 6)
        state['bucket_samples'] = samples
        state['bucket_anomaly_streak'] = streak
        state['bucket_anomaly_updated'] = time.time()
        if event_id:
            state['bucket_last_event_id'] = event_id
        save_state(state)
        result["streak"] = streak
        return result
    finally:
        _state_unlock(lock)


def is_bucket_anomaly_stop() -> bool:
    """버킷 소비 급증으로 인한 파이프라인 중지 플래그 확인."""
    try:
        return bool(load_state().get('bucket_anomaly_stop', False))
    except Exception:
        return False


def clear_bucket_anomaly() -> None:
    """버킷 급증 중지 플래그/연속 카운트 해제 (사용자 개입 후 수동 호출)."""
    lock = _state_lock()
    try:
        state = load_state()
        state['bucket_anomaly_stop'] = False
        state['bucket_anomaly_streak'] = 0
        save_state(state)
        logger.info("버킷 급증 중지 플래그 해제됨")
    finally:
        _state_unlock(lock)


def current_bytes_calibrated() -> int:
    """보정 적용된 현재 바이트 (TG×보정계수, API 불가 시 폴백 근사치)."""
    raw = current_bytes()
    factor = get_calibration_factor()
    return int(raw * factor)


# API 일일 실측값 신선도 한계 (초). monitor가 매 화 갱신하므로 15분이면 충분히 신선.
API_FRESH_SEC = 900


def api_daily_used_mb() -> Optional[float]:
    """DataImpulse API의 '오늘' 실측 사용량(MB). 신선하지 않으면 None.

    [WHY] DataImpulse 과금의 SSOT는 API 실측값이다. TG×보정계수는 근사치이므로
    API 값이 신선하면 한도 판정에 API를 우선 사용한다. (일 경계: 서버 TZ=UTC,
    API group_date=UTC → 정합)
    """
    try:
        if not API_STATE_FILE.exists():
            return None
        data = json.loads(API_STATE_FILE.read_text(encoding='utf-8'))
        last = data.get('last_api_data') or {}
        ts = float(data.get('last_check') or 0)
        mb = last.get('total_mb')
        if mb is None or (time.time() - ts) > API_FRESH_SEC:
            return None
        # [WHY] API 오늘값은 비단조·청크(~1.5MB) 갱신 → 일중 최대값(단조 봉투)으로
        # 하향 튐을 막는다. 같은 날짜의 max만 사용(날짜 경계 오적용 방지).
        max_mb = data.get('api_today_max_mb')
        if data.get('api_today_date') == last.get('date') and max_mb is not None:
            return float(max(float(mb), float(max_mb)))
        return float(mb)
    except Exception:
        return None


def effective_used_bytes() -> tuple[int, str]:
    """한도 판정용 유효 사용량 (바이트, 출처).

    우선순위: API 오늘 실측 → TG×보정계수(폴백).
    """
    api_mb = api_daily_used_mb()
    if api_mb is not None:
        return int(api_mb * 1024 * 1024), "api"
    return current_bytes_calibrated(), "tg_calibrated"


def guard_used_bytes() -> tuple[int, str]:
    """한도 차단용 보수적 사용량 = max(API 실측, TG×보정).

    [WHY] API는 보고 지연·청크로 순간적으로 실제보다 낮을 수 있다. 차단(안전)은
    두 추정치의 최대값을 써서 과소 추정으로 인한 한도 초과를 방지한다.
    """
    api_mb = api_daily_used_mb()
    tg_cal = current_bytes_calibrated()
    if api_mb is None:
        return tg_cal, "tg_calibrated"
    api_bytes = int(api_mb * 1024 * 1024)
    if api_bytes >= tg_cal:
        return api_bytes, "api"
    return tg_cal, "tg_calibrated"


QUOTA_WARN_PCT = 0.80
QUOTA_HARD_PCT = 0.95


def forecast_used_mb(at: Optional[float] = None) -> Optional[float]:
    """현재 속도로 하루를 채울 때의 예상 사용량(MB). 1h 미만 경과 시 None.

    [WHY] 산업 표준(Azure/GCP)은 실제값뿐 아니라 **예측 초과**를 경보한다.
    """
    used, _ = guard_used_bytes()
    dt = datetime.fromtimestamp(at) if at is not None else datetime.now()
    midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    elapsed = (dt - midnight).total_seconds()
    if elapsed < FORECAST_MIN_ELAPSED_SEC:
        return None
    return used / (elapsed / 86400) / (1024 * 1024)


def quota_level() -> str:
    """예산 단계 — 보수적 사용량과 예측의 최악값 기준 ok/warn(80%)/critical(95%)."""
    used, _ = guard_used_bytes()
    limit = daily_limit_bytes()
    if limit <= 0:
        return "ok"
    worst = used / limit
    forecast_mb = forecast_used_mb()
    if forecast_mb is not None:
        worst = max(worst, forecast_mb * 1024 * 1024 / limit)
    if worst >= QUOTA_HARD_PCT:
        return "critical"
    if worst >= QUOTA_WARN_PCT:
        return "warn"
    return "ok"


def remaining_bytes_calibrated() -> int:
    """잔여 바이트 (한도 차단용 보수적 사용량 기준)."""
    used, _ = guard_used_bytes()
    return max(0, daily_limit_bytes() - used)


def is_exceeded_calibrated() -> bool:
    """일일 한도 초과 여부 — 보수적(API와 TG×보정 중 큰 값) 기준."""
    used, _ = guard_used_bytes()
    return used >= daily_limit_bytes()


def summary_calibrated() -> dict:
    """상태 요약 — API 실측 우선, TG 원시/보정 병기."""
    limit = daily_limit_bytes()
    used_raw = current_bytes()
    used_tg_cal = current_bytes_calibrated()
    api_mb = api_daily_used_mb()
    used_effective, source = effective_used_bytes()
    used_guard, guard_source = guard_used_bytes()
    factor = get_calibration_factor()
    return {
        "daily_limit_mb": get_daily_limit_mb(),
        "used_mb": round(used_effective / (1024 * 1024), 2),
        "used_mb_source": source,  # "api" | "tg_calibrated"
        "used_mb_guard": round(used_guard / (1024 * 1024), 2),
        "used_mb_guard_source": guard_source,
        "quota_level": quota_level(),
        "forecast_mb": (
            round(forecast_used_mb(), 2) if forecast_used_mb() is not None else None
        ),
        "used_mb_api": round(api_mb, 2) if api_mb is not None else None,
        "used_mb_tg_calibrated": round(used_tg_cal / (1024 * 1024), 2),
        "used_mb_raw": round(used_raw / (1024 * 1024), 2),
        "remaining_mb": round(max(0, limit - used_guard) / (1024 * 1024), 2),
        "exceeded": used_guard >= limit,
        "chapters": int(load_state().get('chapters', 0)),
        "calibration_factor": round(factor, 3),
    }