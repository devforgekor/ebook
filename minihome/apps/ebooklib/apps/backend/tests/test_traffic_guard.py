#!/usr/bin/env python3
# Status: experimental
# Path: apps/backend/tests/test_traffic_guard.py
"""일일 트래픽 가드 + DataImpulse 비교 로직 테스트 (실제 상태파일 미접촉)."""

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from lib import dataimpulse_monitor as monitor
from lib import traffic_guard as tg


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(tg, "STATE_FILE", tmp_path / "traffic_state.json")
    return tg.STATE_FILE


class TestDailyLimit:
    def test_should_use_env_limit_when_set(self, monkeypatch):
        monkeypatch.setenv("EBOOK_DAILY_TRAFFIC_LIMIT_MB", "500")
        assert tg.get_daily_limit_mb() == 500
        assert tg.daily_limit_bytes() == 500 * 1024 * 1024

    def test_should_fallback_to_default_when_env_invalid(self, monkeypatch):
        monkeypatch.setenv("EBOOK_DAILY_TRAFFIC_LIMIT_MB", "not-a-number")
        assert tg.get_daily_limit_mb() == tg.DEFAULT_DAILY_LIMIT_MB


class TestAccumulate:
    def test_should_accumulate_bytes_and_chapters(self, state):
        tg.add_bytes(1000, chapter=True)
        s = tg.add_bytes(500)
        assert s["bytes"] == 1500 and s["chapters"] == 1
        assert tg.current_bytes() == 1500

    def test_should_ignore_negative_bytes(self, state):
        tg.add_bytes(100)
        assert tg.add_bytes(-50)["bytes"] == 100

    def test_should_report_exceeded_at_exact_limit(self, state, monkeypatch):
        monkeypatch.setenv("EBOOK_DAILY_TRAFFIC_LIMIT_MB", "1")
        tg.add_bytes(1024 * 1024)
        assert tg.is_exceeded() is True
        assert tg.remaining_bytes() == 0

    def test_should_report_below_limit(self, state, monkeypatch):
        monkeypatch.setenv("EBOOK_DAILY_TRAFFIC_LIMIT_MB", "1")
        tg.add_bytes(1024)
        assert tg.is_exceeded() is False
        assert tg.remaining_bytes() == 1024 * 1024 - 1024

    def test_summary_shape(self, state, monkeypatch):
        monkeypatch.setenv("EBOOK_DAILY_TRAFFIC_LIMIT_MB", "1")
        tg.add_bytes(512 * 1024, chapter=True)
        s = tg.summary()
        assert s["daily_limit_mb"] == 1
        assert s["used_mb"] == 0.5
        assert s["exceeded"] is False
        assert s["chapters"] == 1


class TestNewDayReset:
    def test_should_reset_and_preserve_prev_day(self, state):
        tg.save_state(
            {
                "date": "2000-01-01",
                "bytes": 5 * 1024 * 1024,
                "chapters": 7,
                "calibration_factor_ewma": 0.85,
                "check_count": 3,
            }
        )
        tg.reset_if_new_day()
        s = tg.load_state()
        assert s["date"] == tg._today()
        assert s["bytes"] == 0 and s["chapters"] == 0
        assert s["prev_day"]["date"] == "2000-01-01"
        assert s["prev_day"]["bytes"] == 5 * 1024 * 1024
        assert s["calibration_factor_ewma"] == 0.85

    def test_should_not_reset_same_day(self, state):
        tg.add_bytes(123)
        tg.reset_if_new_day()
        assert tg.current_bytes() == 123

    def test_seconds_until_next_day_at_least_one(self):
        assert tg.seconds_until_next_day() >= 1


class TestDataImpulseCompare:
    def test_parse_proxy_key_should_split_userinfo(self):
        assert monitor._parse_proxy_key("user:pw@host:1234") == ("user", "pw")

    def test_parse_proxy_key_should_return_empty_without_at(self):
        assert monitor._parse_proxy_key("host:1234") == ("", "")

    def test_should_extract_today_entry(self):
        today = monitor._today_str()
        data = {
            "traffic_history": [
                {"group_date": "1999-01-01", "total_traffic": 999},
                {
                    "group_date": f"{today} 00:00:00",
                    "inbound_traffic": 2 * 1024 * 1024,
                    "outgoing_traffic": 1024 * 1024,
                    "total_traffic": 3 * 1024 * 1024,
                    "requests_count": 4,
                    "errors": 1,
                },
            ]
        }
        out = monitor.get_today_usage(data)
        assert out["total_mb"] == 3.0
        assert out["inbound_mb"] == 2.0
        assert out["outgoing_mb"] == 1.0
        assert out["requests"] == 4 and out["errors"] == 1

    def test_should_return_none_when_no_today_entry(self):
        assert monitor.get_today_usage({"traffic_history": []}) is None
        assert monitor.get_today_usage({}) is None

    def test_should_compute_diff_against_traffic_guard(self, monkeypatch):
        monkeypatch.setattr(
            monitor, "get_traffic_summary", lambda: {"used_mb": 80.0, "chapters": 10}
        )
        api_today = {
            "date": "2026-09-25",
            "total_mb": 100.0,
            "inbound_mb": 60.0,
            "outgoing_mb": 40.0,
            "requests": 5,
        }
        out = monitor.compare_with_traffic_guard(api_today)
        assert out["diff_mb"] == 20.0
        assert out["diff_pct"] == 20.0
        assert out["tg_chapters"] == 10


def _write_api_state(path, total_mb, max_mb=None, date=None, age_sec=0):
    import json
    import time

    date = date or tg._today()
    path.write_text(
        json.dumps(
            {
                "last_check": time.time() - age_sec,
                "last_api_data": {"date": date, "total_mb": total_mb},
                "api_today_date": date,
                "api_today_max_mb": max_mb if max_mb is not None else total_mb,
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def api_state(tmp_path, monkeypatch):
    p = tmp_path / "dataimpulse_api_state.json"
    monkeypatch.setattr(tg, "API_STATE_FILE", p)
    return p


class TestGapSafety:
    def test_calibration_defaults_should_not_underestimate(self):
        # 방향 확정: API > TG → 계수는 1.0 이상, 기본값은 안전측(과대)
        assert tg.MIN_CALIBRATION_FACTOR >= 1.0
        assert tg.DEFAULT_CALIBRATION_FACTOR >= 1.0

    def test_api_daily_should_use_monotonic_max(self, api_state):
        _write_api_state(api_state, total_mb=0.4, max_mb=0.6)
        assert tg.api_daily_used_mb() == 0.6

    def test_api_daily_should_return_none_when_stale(self, api_state):
        _write_api_state(api_state, total_mb=0.4, age_sec=tg.API_FRESH_SEC + 1)
        assert tg.api_daily_used_mb() is None

    def test_guard_should_take_max_of_api_and_tg(self, state, api_state, monkeypatch):
        monkeypatch.setenv("EBOOK_DAILY_TRAFFIC_LIMIT_MB", "10")
        tg.save_state(
            {
                "date": tg._today(),
                "bytes": 512 * 1024,
                "chapters": 1,
                "calibration_factor_ewma": 2.0,
            }
        )
        _write_api_state(api_state, total_mb=0.6)
        used, src = tg.guard_used_bytes()
        assert src == "tg_calibrated"  # 1.0MB(TG cal) > 0.6MB(API)
        assert used == 1024 * 1024

    def test_guard_should_prefer_api_when_larger(self, state, api_state, monkeypatch):
        monkeypatch.setenv("EBOOK_DAILY_TRAFFIC_LIMIT_MB", "10")
        tg.save_state(
            {
                "date": tg._today(),
                "bytes": 100 * 1024,
                "chapters": 1,
                "calibration_factor_ewma": 1.0,
            }
        )
        _write_api_state(api_state, total_mb=5.0)
        used, src = tg.guard_used_bytes()
        assert src == "api"
        assert used == 5 * 1024 * 1024

    def test_quota_level_thresholds(self, state, monkeypatch):
        monkeypatch.setenv("EBOOK_DAILY_TRAFFIC_LIMIT_MB", "1")
        monkeypatch.setattr(tg, "API_STATE_FILE", state.parent / "none.json")
        monkeypatch.setattr(tg, "forecast_used_mb", lambda at=None: None)
        tg.save_state(
            {
                "date": tg._today(),
                "bytes": int(0.85 * 1024 * 1024),
                "chapters": 1,
                "calibration_factor_ewma": 1.0,
            }
        )
        assert tg.quota_level() == "warn"
        tg.save_state(
            {
                "date": tg._today(),
                "bytes": int(0.96 * 1024 * 1024),
                "chapters": 1,
                "calibration_factor_ewma": 1.0,
            }
        )
        assert tg.quota_level() == "critical"


class TestBucketAnomaly:
    def test_should_build_baseline_without_stop(self, state):
        for _ in range(tg.BUCKET_ANOMALY_MIN_SAMPLES):
            assert tg.update_bucket_anomaly(100.0)["stop"] is False
        assert tg.is_bucket_anomaly_stop() is False

    def test_should_stop_after_consecutive_spikes(self, state):
        for _ in range(tg.BUCKET_ANOMALY_MIN_SAMPLES):
            tg.update_bucket_anomaly(100.0)
        last = None
        for _ in range(tg.BUCKET_ANOMALY_CONSECUTIVE):
            last = tg.update_bucket_anomaly(200.0)  # +100%
        assert last["stop"] is True
        assert tg.is_bucket_anomaly_stop() is True

    def test_should_reset_streak_on_normal_value(self, state):
        for _ in range(tg.BUCKET_ANOMALY_MIN_SAMPLES):
            tg.update_bucket_anomaly(100.0)
        tg.update_bucket_anomaly(130.0)
        tg.update_bucket_anomaly(130.0)
        tg.update_bucket_anomaly(100.0)  # 정상 → streak 0
        assert tg.update_bucket_anomaly(130.0)["streak"] == 1
        assert tg.is_bucket_anomaly_stop() is False

    def test_should_ignore_small_absolute_increase(self, state):
        # +30%지만 절대 증가가 MIN_KB 미만이면 이상 아님(소량 버킷 %노이즈 차단)
        for _ in range(tg.BUCKET_ANOMALY_MIN_SAMPLES):
            tg.update_bucket_anomaly(1.0)
        r = tg.update_bucket_anomaly(1.3)
        assert r["dev_pct"] == 30.0
        assert r["streak"] == 0

    def test_should_alert_before_stop(self, state):
        for _ in range(tg.BUCKET_ANOMALY_MIN_SAMPLES):
            tg.update_bucket_anomaly(100.0)
        r = None
        for _ in range(tg.BUCKET_ANOMALY_ALERT_CONSECUTIVE):
            r = tg.update_bucket_anomaly(130.0)
        assert r["alert"] is True
        assert r["stop"] is False
        assert tg.is_bucket_anomaly_stop() is False

    def test_should_stop_early_on_severe_deviation(self, state):
        for _ in range(tg.BUCKET_ANOMALY_MIN_SAMPLES):
            tg.update_bucket_anomaly(100.0)
        for _ in range(tg.BUCKET_ANOMALY_SEVERE_CONSECUTIVE):
            r = tg.update_bucket_anomaly(160.0)  # +60%
        assert r["stop"] is True


class TestForecast:
    def test_should_extrapolate_daily_usage(self, state, api_state, monkeypatch):
        from datetime import datetime, timezone

        monkeypatch.setenv("EBOOK_DAILY_TRAFFIC_LIMIT_MB", "100")
        tg.save_state(
            {
                "date": tg._today(),
                "bytes": 10 * 1024 * 1024,
                "chapters": 1,
                "calibration_factor_ewma": 1.0,
            }
        )
        noon = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
        assert tg.forecast_used_mb(at=noon.timestamp()) == 20.0

    def test_should_return_none_before_min_elapsed(self, state, api_state, monkeypatch):
        from datetime import datetime, timezone

        monkeypatch.setenv("EBOOK_DAILY_TRAFFIC_LIMIT_MB", "100")
        early = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
        assert tg.forecast_used_mb(at=early.timestamp()) is None

    def test_clear_should_release_stop(self, state):
        for _ in range(tg.BUCKET_ANOMALY_MIN_SAMPLES):
            tg.update_bucket_anomaly(100.0)
        for _ in range(tg.BUCKET_ANOMALY_CONSECUTIVE):
            tg.update_bucket_anomaly(150.0)  # +50%
        assert tg.is_bucket_anomaly_stop() is True
        tg.clear_bucket_anomaly()
        assert tg.is_bucket_anomaly_stop() is False

    def test_baseline_should_not_be_inflated_by_anomalies(self, state):
        # 기준선은 참조 — 급증 샘플은 기준선을 끌어올리지 않아 20%가 중복 누적되지 않는다.
        for _ in range(tg.BUCKET_ANOMALY_MIN_SAMPLES):
            tg.update_bucket_anomaly(100.0)
        tg.update_bucket_anomaly(200.0)
        tg.update_bucket_anomaly(200.0)
        assert tg.load_state()["bucket_kb_ewma"] == 100.0

    def test_baseline_should_track_normal_drift(self, state):
        # 정상 범위 변화는 기준선이 계속 따라간다(고정 기준선 아님).
        for _ in range(tg.BUCKET_ANOMALY_MIN_SAMPLES):
            tg.update_bucket_anomaly(100.0)
        tg.update_bucket_anomaly(110.0)  # +10% (정상) → 기준선 이동
        assert tg.load_state()["bucket_kb_ewma"] > 100.0

    def test_should_skip_duplicate_event_id(self, state):
        # 같은 버킷(event_id)은 한 번만 평가 — 5분 주기 호출에서 중복 누적 방지
        for _ in range(tg.BUCKET_ANOMALY_MIN_SAMPLES):
            tg.update_bucket_anomaly(100.0)
        first = tg.update_bucket_anomaly(200.0, event_id="b1")
        again = tg.update_bucket_anomaly(200.0, event_id="b1")
        assert first["streak"] == 1
        assert again.get("skipped") is True
        assert tg.load_state()["bucket_anomaly_streak"] == 1


class TestColdBuckets:
    def test_cold_should_not_affect_baseline_or_streak(self, state):
        for _ in range(tg.BUCKET_ANOMALY_MIN_SAMPLES):
            tg.update_bucket_anomaly(100.0)
        base_before = tg.load_state()["bucket_kb_ewma"]
        r = tg.update_bucket_anomaly(200.0, cold=True)  # +100% < 5x 완화
        assert r["cold_exceeded"] is False
        assert r["streak"] == 0
        assert tg.load_state()["bucket_kb_ewma"] == base_before
        assert tg.is_bucket_anomaly_stop() is False

    def test_cold_should_flag_above_relaxed_threshold(self, state):
        for _ in range(tg.BUCKET_ANOMALY_MIN_SAMPLES):
            tg.update_bucket_anomaly(100.0)
        r = tg.update_bucket_anomaly(700.0, cold=True)  # +600% > 600(=100*1.2*5)
        assert r["cold_exceeded"] is True
        assert r["streak"] == 0
        assert tg.is_bucket_anomaly_stop() is False


class TestSeed:
    def test_seed_should_initialize_baseline_once(self, state):
        assert tg.seed_bucket_baseline(187.8, 0.9) is True
        s = tg.load_state()
        assert s["bucket_kb_ewma"] == 187.8
        assert s["bucket_samples"] >= tg.BUCKET_ANOMALY_MIN_SAMPLES
        assert tg.seed_bucket_baseline(999.0, 1.0) is False  # 멱등
        assert tg.load_state()["bucket_kb_ewma"] == 187.8

    def test_seeded_baseline_should_judge_immediately(self, state):
        tg.seed_bucket_baseline(187.8, 0.9)
        r = tg.update_bucket_anomaly(225.4)  # +20.1%
        assert r["dev_pct"] is not None
        assert r["streak"] == 1


class TestChapterCap:
    def test_should_use_env_chapter_cap(self, monkeypatch):
        monkeypatch.setenv("EBOOK_DAILY_CHAPTER_CAP", "50")
        assert tg.get_daily_chapter_cap() == 50

    def test_should_fallback_to_default_chapter_cap(self, monkeypatch):
        monkeypatch.setenv("EBOOK_DAILY_CHAPTER_CAP", "not-a-number")
        assert tg.get_daily_chapter_cap() == tg.DEFAULT_DAILY_CHAPTER_CAP

    def test_should_block_on_chapter_cap(self, state, monkeypatch):
        monkeypatch.setenv("EBOOK_DAILY_CHAPTER_CAP", "2")
        tg.add_bytes(1, chapter=True)
        tg.add_bytes(1, chapter=True)
        assert tg.chapters_today() == 2
        assert tg.is_chapter_exceeded() is True
        assert tg.should_stop_daily() is True

    def test_should_not_block_below_chapter_cap(self, state, monkeypatch):
        monkeypatch.setenv("EBOOK_DAILY_CHAPTER_CAP", "5")
        tg.add_bytes(1, chapter=True)
        assert tg.is_chapter_exceeded() is False

    def test_forecast_chapters_should_extrapolate(self, state, monkeypatch):
        from datetime import datetime, timezone

        tg.save_state(
            {"date": tg._today(), "bytes": 0, "chapters": 100, "calibration_factor_ewma": 1.0}
        )
        noon = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
        assert tg.forecast_chapters(at=noon.timestamp()) == 200

    def test_quota_level_should_consider_chapters(self, state, monkeypatch):
        monkeypatch.setenv("EBOOK_DAILY_TRAFFIC_LIMIT_MB", "100")
        monkeypatch.setenv("EBOOK_DAILY_CHAPTER_CAP", "100")
        monkeypatch.setattr(tg, "API_STATE_FILE", state.parent / "none.json")
        monkeypatch.setattr(tg, "forecast_used_mb", lambda at=None: None)
        monkeypatch.setattr(tg, "forecast_chapters", lambda at=None: None)
        tg.save_state(
            {"date": tg._today(), "bytes": 0, "chapters": 85, "calibration_factor_ewma": 1.0}
        )
        assert tg.quota_level() == "warn"
        tg.save_state(
            {"date": tg._today(), "bytes": 0, "chapters": 96, "calibration_factor_ewma": 1.0}
        )
        assert tg.quota_level() == "critical"


class TestUsageHeaders:
    def test_should_extract_only_usage_related_headers(self):
        from lib.dataimpulse_monitor import _extract_usage_headers

        headers = {
            "X-Proxy-Usage": "12MB",
            "X-Usage-Limit": "500",
            "Authorization": "Basic c2VjcmV0",
            "Set-Cookie": "sid=1",
            "Content-Type": "application/json",
        }
        out = _extract_usage_headers(headers)
        assert out == {"X-Proxy-Usage": "12MB", "X-Usage-Limit": "500"}

    def test_should_return_empty_when_no_usage_headers(self):
        from lib.dataimpulse_monitor import _extract_usage_headers

        assert _extract_usage_headers({"Content-Type": "application/json"}) == {}
        assert _extract_usage_headers(None) == {}


class TestBurnRate:
    def _seed(self, state, samples, used_mb, monkeypatch, limit_mb=100):
        monkeypatch.setenv("EBOOK_DAILY_TRAFFIC_LIMIT_MB", str(limit_mb))
        tg.save_state({"date": tg._today(), "bytes": int(used_mb * 1024 * 1024), "chapters": 0, "usage_samples": samples})

    def test_record_sample_should_throttle(self, state, monkeypatch):
        monkeypatch.setattr(tg, "guard_used_bytes", lambda: (0, "tg_calibrated"))
        assert tg.record_usage_sample(now=1000.0) is True
        assert tg.record_usage_sample(now=1000.0 + tg.USAGE_SAMPLE_MIN_INTERVAL_SEC - 1) is False
        assert tg.record_usage_sample(now=1000.0 + tg.USAGE_SAMPLE_MIN_INTERVAL_SEC + 1) is True

    def test_burn_should_be_critical_on_sustained_spike(self, state, monkeypatch):
        now = 10_000_000.0
        limit = 100
        used = 10.0  # 10% of daily
        tg.save_state({"date": tg._today(), "bytes": 0, "chapters": 0,
                       "usage_samples": [[now - 3600, 0], [now - 300, int(limit * 0.05 * 1024 * 1024)]]})
        monkeypatch.setenv("EBOOK_DAILY_TRAFFIC_LIMIT_MB", str(limit))
        monkeypatch.setattr(tg, "guard_used_bytes", lambda: (int(used * 1024 * 1024), "tg_calibrated"))
        out = tg.burn_rates(now=now)
        assert out["level"] == "critical"
        assert out["rate_1h"] == 2.4

    def test_burn_should_be_warn_on_slow_burn(self, state, monkeypatch):
        now = 10_000_000.0
        limit = 100
        used = 25.0  # 25% of daily
        tg.save_state({"date": tg._today(), "bytes": 0, "chapters": 0,
                       "usage_samples": [
                           [now - 21600, 0],
                           [now - 3600, int(limit * 0.18 * 1024 * 1024)],
                           [now - 1800, int(limit * 0.225 * 1024 * 1024)],
                           [now - 300, int(limit * 0.24 * 1024 * 1024)],
                       ]})
        monkeypatch.setenv("EBOOK_DAILY_TRAFFIC_LIMIT_MB", str(limit))
        monkeypatch.setattr(tg, "guard_used_bytes", lambda: (int(used * 1024 * 1024), "tg_calibrated"))
        out = tg.burn_rates(now=now)
        assert out["level"] == "warn"

    def test_burn_should_be_unknown_without_samples(self, state, monkeypatch):
        monkeypatch.setenv("EBOOK_DAILY_TRAFFIC_LIMIT_MB", "100")
        tg.save_state({"date": tg._today(), "bytes": 0, "chapters": 0})
        assert tg.burn_rates(now=10_000_000.0)["level"] == "unknown"


class TestOfficialFeed:
    SAMPLE = '''
    <div class="tgme_widget_message_text">서버 점검중입니다, 완료되면 공지드리겠습니다.</div>
    <div class="tgme_widget_message_text">
      <a href="http://newtoki1.org/">newtoki1.org</a>
      구버전만 롤백 서버로 복구되었으며,
      <a href="http://sbxh9.com/">sbxh9.com</a>
      <a href="http://toki31.com/">toki31.com</a>
      신버전 및 모든 서버 정상화까지 로그인은 제한되고 업로드가 중단됩니다.
      <a href="https://telegra.ph/x">telegra.ph</a>
    </div>
    '''

    def test_parse_should_extract_domains_and_maintenance(self):
        from lib.official_feed import parse_feed

        out = parse_feed(self.SAMPLE)
        assert "sbxh9.com" in out["domains"] and "toki31.com" in out["domains"]
        assert "newtoki1.org" in out["domains"]
        assert not any("telegra.ph" in d for d in out["domains"])
        assert out["maintenance"] is True
        assert out["n_messages"] == 2

    def test_parse_should_be_fail_open_when_unknown(self):
        from lib.official_feed import parse_feed

        out = parse_feed("<html>no messages</html>")
        assert out["domains"] == []
        assert out["maintenance"] is False

    def test_merge_candidates_should_add_only_family_domains(self, tmp_path, monkeypatch):
        import json

        import lib.sources as sources

        f = tmp_path / "sources.json"
        f.write_text(
            json.dumps(
                {"toki31": {"domains": ["newtoki31.com"], "base_url": "https://newtoki31.com"}}
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(sources, "_SOURCES_FILE", f)
        from lib.official_feed import merge_candidates

        added = merge_candidates(["sbxh9.com", "te.ml", "newtoki31.com"], "toki31")
        assert added == 1
        raw = json.loads(f.read_text(encoding="utf-8"))
        assert "sbxh9.com" in raw["toki31"]["domains"]
        assert raw["toki31"]["base_url"] == "https://newtoki31.com"


class TestOfficialMetadata:
    def test_should_detect_supported_platforms(self):
        from services.metadata_official import detect_platform

        assert detect_platform("https://series.naver.com/novel/detail.series?productNo=1") == "naver"
        assert detect_platform("https://novel.munpia.com/12345") == "munpia"
        assert detect_platform("https://www.joara.com/book/1") == "joara"
        assert detect_platform("https://unknown.example/x") is None

    def test_should_parse_naver_json_ld(self):
        from services.metadata_official import parse_platform

        html = '''
        <html><head><meta property="og:title" content="폴백제목">
        <script type="application/ld+json">
        {"@type":"Book","name":"절대회귀","author":{"name":"이블라인"},
         "description":"회귀물","image":"https://img/x.jpg"}
        </script>
        <span>작가</span><span>무시됨</span>
        <div>총 350화</div><div>연재중</div>
        </head></html>
        '''
        out = parse_platform("naver", html, "https://series.naver.com/x")
        assert out["title"] == "절대회귀"
        assert out["author"] == "이블라인"
        assert out["total_chapters"] == 350
        assert out["status"] == "연재중"
        assert out["source"] == "official:naver"

    def test_should_parse_munpia_labels_when_no_jsonld(self):
        from services.metadata_official import parse_platform

        html = '<meta property="og:title" content="작품A"><div>작가</div><div>홍길동</div><div>총 123화</div><div>완결</div>'
        out = parse_platform("munpia", html, "https://novel.munpia.com/1")
        assert out["title"] == "작품A"
        assert out["author"] == "홍길동"
        assert out["total_chapters"] == 123
        assert out["status"] == "완결"

    def test_fetch_should_return_none_for_unsupported(self):
        from services.metadata_official import fetch

        assert fetch("https://unsupported.example/x", fetcher=lambda u: "<html/>") is None

    def test_fetch_should_use_fetcher_for_supported(self):
        from services.metadata_official import fetch

        out = fetch(
            "https://novel.munpia.com/1",
            fetcher=lambda u: '<meta property="og:title" content="T"><div>작가</div><div>A</div>',
        )
        assert out and out["title"] == "T" and out["author"] == "A"


class TestOfficialMetaStorage:
    def test_update_meta_from_official_should_apply_total_and_status(self, tmp_path, monkeypatch):
        import json

        import lib.storage as storage
        import lib.paths as paths

        d = tmp_path / "절대회귀"
        d.mkdir()
        (d / "meta.json").write_text(
            json.dumps({"title": "절대회귀", "totalChapters": 187, "status": "연재중", "meta_source_url": "u"}),
            encoding="utf-8",
        )
        monkeypatch.setattr(storage, "find_novel_dir", lambda nid: d)
        monkeypatch.setattr(paths, "find_novel_dir", lambda nid: d)
        ok = storage.update_meta_from_official(
            "절대회귀",
            {"title": "절대회귀", "author": "이블라인", "total_chapters": 350, "status": "연재중",
             "source": "official:naver", "source_url": "u"},
        )
        assert ok is True
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        assert meta["author"] == "이블라인"
        assert meta["totalChapters"] == 350
        assert meta["metadata_source"] == "official"


class TestDiscoverCompletion:
    def _meta(self):
        return {"title": "T", "status": "연재중", "no_new_streak": 0}

    def test_discover_failure_should_not_count_toward_completion(self):
        import importlib.util
        import sys as _s

        # pipeline 모듈은 스크립트라 함수만 직접 로드
        _s.path.insert(0, "scripts")
        import pipeline as pl

        meta = self._meta()
        pl._update_novel_status_from_discover(meta, 0, "T", discovered_ok=False)
        assert meta["no_new_streak"] == 0
        assert meta["status"] == "연재중"

    def test_should_complete_after_threshold_zero_discovers(self):
        _s_pl = __import__("scripts.pipeline", fromlist=["x"]) if False else None
        import sys as _sys
        _sys.path.insert(0, "scripts")
        import pipeline as pl

        meta = self._meta()
        for _ in range(pl.NO_NEW_STREAK_COMPLETE):
            pl._update_novel_status_from_discover(meta, 0, "T", discovered_ok=True)
        assert meta["status"] == "완결"

    def test_official_ongoing_should_block_completion(self):
        import sys as _sys
        _sys.path.insert(0, "scripts")
        import pipeline as pl

        meta = {"title": "T", "status": "연재중", "no_new_streak": 0, "metadata_source": "official"}
        for _ in range(pl.NO_NEW_STREAK_COMPLETE + 2):
            pl._update_novel_status_from_discover(meta, 0, "T", discovered_ok=True)
        assert meta["status"] == "연재중"


class TestTextClean:
    def test_clean_title_should_strip_site_and_author_suffix(self):
        from lib.text_clean import clean_title

        assert clean_title("동생이 천재였다 - 시하 | 뉴토끼") == "동생이 천재였다"
        assert clean_title("[뉴토끼] 필드의 고인물") == "필드의 고인물"
        assert clean_title("절대회귀 - 215화") == "절대회귀"
        assert clean_title("하남자의 탑 공략법 | 북토끼") == "하남자의 탑 공략법"

    def test_clean_title_should_collapse_whitespace_and_zero_width(self):
        from lib.text_clean import clean_title

        assert clean_title("  화산 귀환\u200b  ") == "화산 귀환"
        assert clean_title("제목\n\t부제") == "제목 부제"

    def test_clean_author_should_strip_labels_and_normalize(self):
        from lib.text_clean import clean_author

        assert clean_author("작가: 정윤강") == "정윤강"
        assert clean_author("글쓴이 - 슬리버") == "슬리버"
        assert clean_author("홍길동(작가)") == "홍길동"
        assert clean_author("없음") == "미상"
        assert clean_author("") == ""
        assert clean_author("슬리버") == "슬리버"

    def test_normalize_meta_should_clean_both_fields(self):
        from lib.text_clean import normalize_meta

        out = normalize_meta({"title": "T - 작가 | 뉴토끼", "author": "작가: A"})
        assert out["title"] == "T"
        assert out["author"] == "A"
