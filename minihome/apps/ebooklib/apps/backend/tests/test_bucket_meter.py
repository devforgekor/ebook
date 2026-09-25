#!/usr/bin/env python3
# Status: experimental
# Path: apps/backend/tests/test_bucket_meter.py
"""버킷 측정(bucket_meter) — 파싱/버킷화/확정 품질/멱등 저장 테스트."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from lib.bucket_meter import (
    ApiPoint,
    ChapterEvent,
    append_api_snapshots,
    append_facts,
    build_buckets,
    load_api_points,
    load_chapters,
    parse_log_lines,
    prune_api_snapshots,
    report,
)

DAY = "2026-09-23"
ONE_MB = 1024 * 1024


def _ts(text: str) -> float:
    return (
        datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        .replace(tzinfo=timezone.utc)
        .timestamp()
    )


def _chapter(idx: int, started: str, **kwargs) -> ChapterEvent:
    size_bytes = kwargs.pop("size_bytes", ONE_MB)
    source = kwargs.pop("source", "toki31")
    saved = kwargs.pop("saved", True)
    warm = kwargs.pop("warm", True)
    wr_id = kwargs.pop("wr_id", str(9000000 - idx))
    assert not kwargs
    start = _ts(started)
    return ChapterEvent(
        idx=idx,
        wr_id=wr_id,
        source=source,
        started_at=start,
        ended_at=start + 2,
        bytes=size_bytes,
        warm=warm,
        attempts=1,
        saved=saved,
    )


def _point(ts: str, mb: float, date: str = DAY) -> ApiPoint:
    return ApiPoint(ts=_ts(ts), date=date, mb=mb)


def test_should_split_chapters_evenly_when_size_divides_count():
    chapters = [_chapter(i, f"{DAY} 00:{i:02d}:00") for i in range(4)]

    facts = build_buckets(chapters, [], size=2)

    assert [f["start_idx"] for f in facts] == [0, 2]
    assert [f["end_idx"] for f in facts] == [1, 3]
    assert all(f["consumed_chapters"] == 2 for f in facts)


def test_should_mark_partial_when_bucket_smaller_than_size():
    chapters = [_chapter(i, f"{DAY} 00:{i:02d}:00") for i in range(3)]

    facts = build_buckets(chapters, [], size=2)

    assert facts[0]["quality"] == "late"  # 크기는 충족, API 미커버
    assert "api_coverage_before_missing" in facts[0]["note"]
    assert facts[1]["quality"] == "partial"
    assert "incomplete_bucket" in facts[1]["note"]


def test_should_compute_ratio_when_api_covers_bucket_interpolated():
    chapters = [_chapter(1, f"{DAY} 00:00:10")]
    points = [_point(f"{DAY} 00:00:00", 0.0), _point(f"{DAY} 00:00:40", 8.0)]

    (fact,) = build_buckets(chapters, points, size=1)

    assert fact["quality"] == "ok"
    assert fact["note"] == ""
    assert fact["api_mb_start"] == pytest.approx(2.0, abs=1e-3)  # 10/40 구간 보간
    assert fact["api_mb_end"] == pytest.approx(2.4, abs=1e-3)  # 12/40 구간 보간
    assert fact["r"] == pytest.approx(0.4, abs=1e-3)
    assert fact["tg_bytes_delta"] == ONE_MB
    assert fact["settle_ts"] == _ts(f"{DAY} 00:00:00")


def test_should_mark_late_when_api_snapshot_starts_after_bucket_start():
    chapters = [_chapter(1, f"{DAY} 00:00:10")]
    points = [_point(f"{DAY} 00:00:11", 3.0), _point(f"{DAY} 00:00:30", 5.0)]

    (fact,) = build_buckets(chapters, points, size=1)

    assert fact["quality"] == "late"
    assert "api_coverage_before_missing" in fact["note"]
    assert "api_coverage_after_missing" not in fact["note"]
    assert fact["api_mb_start"] is None
    assert fact["api_mb_end"] is not None
    assert fact["r"] is None


def test_should_mark_late_when_api_snapshot_ends_before_bucket_end():
    chapters = [_chapter(1, f"{DAY} 00:00:10")]
    points = [_point(f"{DAY} 00:00:00", 1.0), _point(f"{DAY} 00:00:11", 3.0)]

    (fact,) = build_buckets(chapters, points, size=1)

    assert fact["quality"] == "late"
    assert "api_coverage_after_missing" in fact["note"]
    assert fact["api_mb_start"] is not None
    assert fact["api_mb_end"] is None
    assert fact["r"] is None


def test_should_mark_late_when_api_delta_not_settled():
    chapters = [_chapter(1, f"{DAY} 00:00:10")]
    points = [
        _point(f"{DAY} 00:00:00", 5.0),
        _point(f"{DAY} 00:00:11", 5.0),
        _point(f"{DAY} 00:00:30", 5.0),
    ]

    (fact,) = build_buckets(chapters, points, size=1)

    assert fact["quality"] == "late"
    assert "api_delta_not_settled" in fact["note"]
    assert fact["api_mb_delta"] == 0
    assert fact["r"] is None


def test_should_mark_partial_when_bucket_crosses_utc_day_boundary():
    chapters = [
        _chapter(1, "2026-09-23 23:59:50"),
        _chapter(2, "2026-09-24 00:00:10"),
    ]

    facts = build_buckets(chapters, [], size=2)

    (fact,) = facts
    assert fact["quality"] == "partial"
    assert "utc_day_boundary" in fact["note"]
    assert fact["api_mb_start"] is None
    assert fact["api_mb_end"] is None
    assert fact["r"] is None


def test_should_prefer_partial_over_late_when_bucket_incomplete_and_api_missing():
    chapters = [_chapter(1, f"{DAY} 00:00:10")]

    (fact,) = build_buckets(chapters, [], size=2)

    assert fact["quality"] == "partial"
    assert "incomplete_bucket" in fact["note"]
    assert "api_coverage_before_missing" in fact["note"]


def test_should_parse_chapter_events_when_log_has_attempt_traffic_save_lines(tmp_path):
    log = tmp_path / "collect.log"
    log.write_text(
        """2026-09-23 00:03:49,900 [INFO] [1/226] wr_id=5862270 (작품 | 뉴토끼) source=toki31 시도 1/3
2026-09-23 00:03:49,908 [INFO] toki31 KR 인증 주입 프록시 기동: 127.0.0.1:42005
2026-09-23 00:04:04,167 [INFO]   📊 트래픽: 769.0KB [웜] (누적 0.8MB/200MB) JS캐시=19 hit=0 wasm=0
2026-09-23 00:04:04,169 [INFO]   ✓ wr_id=5862270 저장 완료 (7173 chars)
2026-09-23 00:04:34,171 [INFO] [2/226] wr_id=5862269 (작품 | 뉴토끼) source=toki31 시도 1/3
2026-09-23 00:04:36,494 [INFO]   📊 트래픽: 204.5KB [웜] (누적 0.9MB/200MB) JS캐시=19 hit=19 wasm=0
2026-09-23 00:04:36,505 [INFO]   ✓ wr_id=5862269 저장 완료 (12111 chars)
2026-09-23 00:04:36,505 [INFO]   23초 대기 (fetch 2.3s × 10, range 5~30s, source=toki31)...
""",
        encoding="utf-8",
    )

    chapters = load_chapters(log)

    assert [ch.idx for ch in chapters] == [1, 2]
    assert chapters[0].bytes == 769 * 1024
    assert chapters[1].bytes == 209408
    assert all(ch.saved and ch.source == "toki31" for ch in chapters)
    assert chapters[0].warm is False  # 런 첫 회차 = 콜드(태그 없어도 강제)
    assert chapters[1].warm is True
    assert chapters[0].started_at == _ts("2026-09-23 00:03:49")


def test_should_sum_bytes_when_same_chapter_retries():
    lines = [
        "2026-09-23 00:10:00,000 [INFO] [7/10] wr_id=5862260 (작품 | 뉴토끼) source=toki31 시도 1/3",
        "2026-09-23 00:10:03,000 [INFO]   📊 트래픽: 100.0KB [웜] (누적 1.0MB/200MB) JS캐시=19 hit=19 wasm=0",
        "2026-09-23 00:10:10,000 [INFO] [7/10] wr_id=5862260 (작품 | 뉴토끼) source=toki31 시도 2/3",
        "2026-09-23 00:10:13,000 [INFO]   📊 트래픽: 150.0KB [웜] (누적 1.2MB/200MB) JS캐시=19 hit=19 wasm=0",
        "2026-09-23 00:10:14,000 [INFO]   ✓ wr_id=5862260 저장 완료 (4000 chars)",
    ]

    chapters = parse_log_lines(lines)

    assert len(chapters) == 1
    assert chapters[0].bytes == 250 * 1024
    assert chapters[0].attempts == 2
    assert chapters[0].saved is True


def test_should_count_failed_chapter_when_no_save_line(tmp_path):
    log = tmp_path / "collect.log"
    log.write_text(
        """2026-09-23 00:10:00,000 [INFO] [1/2] wr_id=5862260 (작품 | 뉴토끼) source=toki31 시도 3/3
2026-09-23 00:11:00,000 [INFO] [2/2] wr_id=5862259 (작품 | 뉴토끼) source=toki31 시도 1/3
2026-09-23 00:11:03,000 [INFO]   📊 트래픽: 200.0KB [콜드] (누적 1.0MB/200MB) JS캐시=19 hit=0 wasm=0
2026-09-23 00:11:04,000 [INFO]   ✓ wr_id=5862259 저장 완료 (4000 chars)
""",
        encoding="utf-8",
    )

    chapters = load_chapters(log)
    assert len(chapters) == 2
    assert chapters[0].saved is False and chapters[0].warm is False
    assert chapters[1].warm is False

    facts = build_buckets(chapters, [], size=2)
    (fact,) = facts
    assert fact["fail_count"] == 1
    assert fact["cold_count"] == 1
    assert fact["ok_count"] == 0


def test_should_append_only_new_facts_when_event_ids_already_recorded(tmp_path):
    target = tmp_path / "bucket_facts.jsonl"
    first = [{"event_id": "toki31:2026-09-23T00:00:10Z:1", "r": 1.5}]
    append_facts(target, first)

    result = append_facts(
        target, first + [{"event_id": "toki31:2026-09-23T01:00:10Z:1", "r": 1.6}]
    )

    assert result == {"appended": 1, "skipped": 1}
    lines = [
        json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()
    ]
    assert [row["event_id"] for row in lines] == [
        "toki31:2026-09-23T00:00:10Z:1",
        "toki31:2026-09-23T01:00:10Z:1",
    ]


def test_should_report_quality_counts_when_some_buckets_late():
    chapters = [
        _chapter(1, f"{DAY} 00:00:10"),
        _chapter(2, f"{DAY} 00:10:10"),
        _chapter(3, f"{DAY} 00:30:10"),
        _chapter(4, f"{DAY} 00:40:10"),
    ]
    points = [
        _point(f"{DAY} 00:00:00", 0.0),
        _point(f"{DAY} 00:00:11", 1.0),
        _point(f"{DAY} 00:00:30", 2.0),
        _point(f"{DAY} 00:10:00", 3.0),
        _point(f"{DAY} 00:10:11", 4.0),
        _point(f"{DAY} 00:11:00", 5.0),
    ]

    summary = report(build_buckets(chapters, points, size=1))

    assert summary["n_buckets"] == 4
    assert summary["quality_counts"] == {"ok": 2, "late": 2, "partial": 0}
    assert summary["r_median"] is not None
    assert summary["tg_kb_per_chapter_mean"] == 1024.0
    assert summary["chapters_total"] == 4


def test_should_derive_deterministic_event_id_when_bucket_built():
    chapters = [_chapter(1, f"{DAY} 00:00:10")]

    (fact,) = build_buckets(chapters, [], size=1, source="toki31")

    assert fact["event_id"] == f"toki31:{DAY}T00:00:10Z:1"
    assert fact["state"] == "active" and fact["correction_of"] is None


def test_should_return_no_buckets_when_log_has_no_chapters():
    assert build_buckets([], [], size=30) == []


def test_should_reject_non_positive_bucket_size():
    with pytest.raises(ValueError):
        build_buckets([], [], size=0)


def test_should_load_api_points_sorted_when_comparisons_unsorted(tmp_path):
    state = tmp_path / "dataimpulse_api_state.json"
    state.write_text(
        json.dumps(
            {
                "last_check": 1790207934.87,
                "comparisons": [
                    {"timestamp": 1790178468.24, "date": DAY, "api_mb": 82.18},
                    {"timestamp": 1790178167.66, "date": DAY, "api_mb": 81.90},
                    {"timestamp": "bad", "date": DAY, "api_mb": 1.0},
                    {"date": DAY, "api_mb": 1.0},
                ],
            }
        ),
        encoding="utf-8",
    )

    points = load_api_points(state)

    assert [p.mb for p in points] == [81.90, 82.18]
    assert points[0].ts < points[1].ts


def test_should_append_api_snapshot_once_when_event_id_already_recorded(tmp_path):
    archive = tmp_path / "api_points.jsonl"
    point = ApiPoint(ts=_ts(f"{DAY} 01:00:00"), date=DAY, mb=10.0)

    first = append_api_snapshots(archive, [point])
    second = append_api_snapshots(archive, [point])

    assert first == {"appended": 1, "skipped": 0}
    assert second == {"appended": 0, "skipped": 1}
    assert len(archive.read_text(encoding="utf-8").splitlines()) == 1


def test_should_prefer_raw_archive_when_state_and_archive_share_timestamp(tmp_path):
    state = tmp_path / "state.json"
    archive = tmp_path / "api_points.jsonl"
    state.write_text(
        json.dumps(
            {
                "comparisons": [
                    {"timestamp": _ts(f"{DAY} 00:00:20"), "date": DAY, "api_mb": 4.0},
                    {"timestamp": _ts(f"{DAY} 00:00:05"), "date": DAY, "api_mb": 1.0},
                ]
            }
        ),
        encoding="utf-8",
    )
    append_api_snapshots(
        archive, [ApiPoint(ts=_ts(f"{DAY} 00:00:05"), date=DAY, mb=99.0)]
    )

    points = load_api_points(state, archive)

    assert [p.mb for p in points] == [99.0, 4.0]


def test_should_compute_bucket_ratio_when_only_archive_provides_coverage(tmp_path):
    state = tmp_path / "state.json"
    archive = tmp_path / "api_points.jsonl"
    state.write_text(json.dumps({"comparisons": []}), encoding="utf-8")
    append_api_snapshots(
        archive,
        [
            ApiPoint(ts=_ts(f"{DAY} 00:00:00"), date=DAY, mb=0.0),
            ApiPoint(ts=_ts(f"{DAY} 00:00:40"), date=DAY, mb=8.0),
        ],
    )
    chapters = [_chapter(1, f"{DAY} 00:00:10")]

    (fact,) = build_buckets(chapters, load_api_points(state, archive), size=1)

    assert fact["quality"] == "ok"
    assert fact["r"] == pytest.approx(0.4, abs=1e-3)


def test_should_prune_expired_snapshots_when_retention_exceeded(tmp_path):
    archive = tmp_path / "api_points.jsonl"
    now = _ts("2026-10-10 00:00:00")
    append_api_snapshots(
        archive,
        [
            ApiPoint(ts=now - 20 * 86400, date="2026-09-20", mb=1.0),
            ApiPoint(ts=now - 86400, date="2026-10-09", mb=2.0),
        ],
    )
    with archive.open("a", encoding="utf-8") as handle:
        handle.write("not-json\n")

    result = prune_api_snapshots(archive, keep_days=15, now=now)

    assert result == {"removed": 1, "kept": 2}
    lines = archive.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and "not-json" in lines


def test_should_keep_snapshots_when_within_retention(tmp_path):
    archive = tmp_path / "api_points.jsonl"
    now = _ts("2026-10-10 00:00:00")
    append_api_snapshots(archive, [ApiPoint(ts=now - 86400, date="2026-10-09", mb=2.0)])

    assert prune_api_snapshots(archive, keep_days=15, now=now) == {
        "removed": 0,
        "kept": 1,
    }


def test_should_record_raw_snapshot_when_pipeline_polls_api(tmp_path, monkeypatch):
    from lib import dataimpulse_monitor as monitor

    archive = tmp_path / "api_points.jsonl"
    state = tmp_path / "state.json"
    today = monitor._today_str()
    monkeypatch.setattr(monitor, "DEFAULT_API_POINTS_PATH", archive)
    monkeypatch.setattr(monitor, "STATE_FILE", state)
    monkeypatch.setattr(
        monitor,
        "fetch_stats_with_history",
        lambda: {
            "traffic_history": [
                {
                    "group_date": f"{today}T00:00:00Z",
                    "inbound_traffic": 1048576,
                    "outgoing_traffic": 0,
                    "total_traffic": 1048576,
                    "requests_count": 5,
                    "errors": 0,
                }
            ]
        },
    )
    monkeypatch.setattr(
        monitor, "get_traffic_summary", lambda: {"used_mb": 1.0, "chapters": 2}
    )
    monkeypatch.setattr(monitor, "_maybe_calibrate_daily", lambda _api_data: None)

    result = monitor.check_dataimpulse_sync()

    assert result["success"] is True
    rows = [
        json.loads(line) for line in archive.read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 1
    assert rows[0]["date"] == today
    assert rows[0]["mb"] == 1.0
    assert rows[0]["event_id"].startswith(f"api:{today}:")


def test_completed_warm_facts_should_filter_cold_late_and_partial():
    from lib.bucket_meter import completed_warm_facts, kb_per_chapter

    facts = [
        {"quality": "ok", "consumed_chapters": 30, "size": 30, "cold_count": 0, "tg_bytes_delta": 30 * 1024},
        {"quality": "ok", "consumed_chapters": 30, "size": 30, "cold_count": 1, "tg_bytes_delta": 1},
        {"quality": "late", "consumed_chapters": 30, "size": 30, "cold_count": 0, "tg_bytes_delta": 1},
        {"quality": "ok", "consumed_chapters": 10, "size": 30, "cold_count": 0, "tg_bytes_delta": 1},
    ]
    out = completed_warm_facts(facts)
    assert len(out) == 1
    assert kb_per_chapter(out[0]) == 1.0
    assert kb_per_chapter({"consumed_chapters": 0, "tg_bytes_delta": 5}) == 0.0


def test_parse_log_lines_should_mark_first_chapter_of_each_day_cold():
    from lib.bucket_meter import parse_log_lines

    def lines(day, wr):
        return [
            f"{day} 10:00:00,000 [INFO] [1/1] wr_id={wr} source=toki31 시도 1/3",
            f"{day} 10:00:05,000 [INFO]   📊 트래픽: 190.0KB [웜]",
            f"{day} 10:00:06,000 [INFO] ✓ wr_id={wr} 저장 완료",
        ]

    log = lines("2026-09-23", "111") + lines("2026-09-23", "222") + lines("2026-09-24", "333")
    chapters = parse_log_lines(log)
    assert len(chapters) == 3
    assert chapters[0].warm is False
    assert chapters[1].warm is True
    assert chapters[2].warm is False


def test_bucket_baseline_stats_should_use_warm_buckets_only(tmp_path):
    from lib.bucket_meter import bucket_baseline_stats

    log = tmp_path / "collect.log"
    lines = []

    def add(wr, kb):
        lines.append(f"2026-09-23 01:00:00,000 [INFO] [1/1] wr_id={wr} source=toki31 시도 1/3")
        lines.append(f"2026-09-23 01:00:05,000 [INFO]   📊 트래픽: {kb}.0KB [웜] (누적 1MB/200MB)")
        lines.append(f"2026-09-23 01:00:06,000 [INFO]   ✓ wr_id={wr} 저장 완료")

    for wr, kb in [(1, 800), (2, 200), (3, 202), (4, 198), (5, 202), (6, 202)]:
        add(wr, kb)
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")

    stats = bucket_baseline_stats(log, size=2)
    assert stats is not None
    assert stats["n"] == 2  # 첫 버킷은 콜드 포함으로 제외
    assert stats["kb_per_chapter_median"] == 201.0
    assert stats["kb_per_chapter_stdev"] > 0


def test_compute_config_hash_should_be_deterministic_and_sensitive():
    from lib.bucket_meter import compute_config_hash

    a = compute_config_hash({"x": "1", "y": "0"})
    assert a == compute_config_hash({"y": "0", "x": "1"})
    assert a != compute_config_hash({"x": "1", "y": "1"})


def test_record_bucket_facts_should_persist_idempotently_with_config_hash(tmp_path):
    from lib.bucket_meter import (
        latest_tg_warm_fact,
        record_bucket_facts,
        tg_warm_facts,
    )

    log = tmp_path / "collect.log"
    lines = []

    def add(wr, kb):
        lines.append(f"2026-09-23 01:00:00,000 [INFO] [1/1] wr_id={wr} source=toki31 시도 1/3")
        lines.append(f"2026-09-23 01:00:05,000 [INFO]   📊 트래픽: {kb}.0KB [웜] (누적 1MB/200MB)")
        lines.append(f"2026-09-23 01:00:06,000 [INFO]   ✓ wr_id={wr} 저장 완료")

    for wr, kb in [(1, 800), (2, 200), (3, 220)]:
        add(wr, kb)
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")

    state = tmp_path / "api_state.json"
    state.write_text('{"comparisons": []}', encoding="utf-8")
    out = tmp_path / "bucket_facts.jsonl"

    facts = record_bucket_facts(
        log, state, tmp_path / "none.jsonl", out, size=1, config_hash="abc123"
    )
    assert len(facts) == 3
    assert facts[0]["config_hash"] == "abc123"
    assert len(tg_warm_facts(facts)) == 2  # 첫 회차(콜드) 제외
    assert latest_tg_warm_fact(facts)["tg_bytes_delta"] == 220 * 1024

    first_lines = out.read_text(encoding="utf-8").splitlines()
    record_bucket_facts(
        log, state, tmp_path / "none.jsonl", out, size=1, config_hash="abc123"
    )
    assert len(out.read_text(encoding="utf-8").splitlines()) == len(first_lines)


def test_load_facts_should_skip_corrupt_lines(tmp_path):
    from lib.bucket_meter import load_facts

    p = tmp_path / "facts.jsonl"
    p.write_text('{"event_id":"a","size":30}\nnot-json\n\n{"event_id":"b","size":30}\n', encoding="utf-8")
    facts = load_facts(p)
    assert [f["event_id"] for f in facts] == ["a", "b"]
    assert load_facts(tmp_path / "missing.jsonl") == []
