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
