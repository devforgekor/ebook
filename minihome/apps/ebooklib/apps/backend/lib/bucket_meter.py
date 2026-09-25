#!/usr/bin/env python3
# Status: experimental
# Path: ebooklib/apps/backend/lib/bucket_meter.py
"""버킷 단위 API/TG 트래픽 측정 — 수집 로그와 DataImpulse API 누적값 결합.

수집 로그의 회차별 TG 바이트와 API 일별 누적 MB를 시간축으로 결합해
버킷(기본 30화) 단위 `r = ΔAPI / ΔTG` 를 계산한다.

- API는 UTC 일 단위 누적이므로 일자 경계를 넘는 버킷은 계산하지 않는다.
- API 스냅샷이 경계(시작/종료)를 못 넘으면 확정 전이므로 quality=late.
- 원시 스냅샷은 append-only `api_points.jsonl`에 보존(멱등 event_id, raw 15일),
  `dataimpulse_api_state.json.comparisons`는 재계산 가능한 파생이다.
- 네트워크/DB 없음. 파일은 원시 아카이브에만 append한다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from bisect import bisect_left, bisect_right
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median, stdev

BUCKET_SIZES = (20, 30, 50)
DEFAULT_BUCKET_SIZE = 30

# [WHY] Prometheus raw 기본 15d + Influx 'raw는 짧게/요약은 길게' 패턴 (plan §14.2)
API_RAW_RETENTION_DAYS = 15

WATCHER_DIR = Path("/opt/ai_data/flaresolverr/ebook_watcher")
DEFAULT_LOG_PATH = WATCHER_DIR / "collect_toki31.log"
DEFAULT_API_STATE_PATH = WATCHER_DIR / "dataimpulse_api_state.json"
DEFAULT_API_POINTS_PATH = WATCHER_DIR / "api_points.jsonl"
DEFAULT_OUT_PATH = WATCHER_DIR / "bucket_facts.jsonl"

_MB = 1024 * 1024
_KB = 1024

_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+")
_ATTEMPT_RE = re.compile(r"\[(\d+)/(\d+)\] wr_id=(\d+).*?source=(\S+) 시도 (\d+)/(\d+)")
_TRAFFIC_RE = re.compile(r"📊 트래픽: ([\d.]+)(KB|MB) \[([^\]]+)\]")
_SAVED_RE = re.compile(r"✓ wr_id=(\d+) 저장 완료")

QUALITY_OK = "ok"
QUALITY_LATE = "late"
QUALITY_PARTIAL = "partial"


@dataclass
class ChapterEvent:
    """수집 로그에서 추출한 회차 단위 TG 트래픽 이벤트."""

    idx: int
    wr_id: str
    source: str
    started_at: float
    ended_at: float
    bytes: int
    warm: bool
    attempts: int
    saved: bool


@dataclass(frozen=True)
class ApiPoint:
    """DataImpulse API 일별 누적 사용량 스냅샷."""

    ts: float
    date: str
    mb: float


def _parse_ts(line: str) -> float | None:
    m = _TS_RE.match(line)
    if not m:
        return None
    # 로거는 UTC로 기록한다(서버 TZ=UTC). naive → UTC로 해석.
    dt = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return dt.timestamp()


def parse_log_lines(lines: Iterable[str]) -> list[ChapterEvent]:
    """로그 라인들에서 회차별 TG 트래픽 이벤트를 추출한다.

    같은 wr_id에 트래픽 라인이 여러 번 나오면(재시도) 바이트를 합산한다.
    """
    chapters: list[ChapterEvent] = []
    cur: ChapterEvent | None = None

    for line in lines:
        ts = _parse_ts(line)
        if ts is None:
            continue

        attempt = _ATTEMPT_RE.search(line)
        if attempt:
            idx = int(attempt.group(1))
            wr_id = attempt.group(3)
            attempt_no = int(attempt.group(5))
            if cur is not None and cur.wr_id == wr_id and cur.idx == idx:
                # 같은 회차 재시도 → 하나의 이벤트로 병합(트래픽 합산/시도 횟수 갱신)
                cur.attempts = max(cur.attempts, attempt_no)
                cur.started_at = min(cur.started_at, ts)
                cur.ended_at = max(cur.ended_at, ts)
                continue
            if cur is not None:
                chapters.append(cur)
            cur = ChapterEvent(
                idx=idx,
                wr_id=wr_id,
                source=attempt.group(4),
                started_at=ts,
                ended_at=ts,
                bytes=0,
                warm=True,
                attempts=attempt_no,
                saved=False,
            )
            continue

        if cur is None:
            continue

        traffic = _TRAFFIC_RE.search(line)
        if traffic:
            value = float(traffic.group(1))
            unit_bytes = _MB if traffic.group(2) == "MB" else _KB
            cur.bytes += round(value * unit_bytes)
            cur.warm = traffic.group(3) != "콜드"
            cur.ended_at = ts
            continue

        saved = _SAVED_RE.search(line)
        if saved and saved.group(1) == cur.wr_id:
            cur.saved = True
            cur.ended_at = ts

    if cur is not None:
        chapters.append(cur)

    # [WHY] 런(일자) 첫 회차는 콜드(전체 JS/문서 로드) — warm 기준선에서 제외한다.
    # 콜드는 웜 경로를 활성화(warmup)하는 용도이므로 baseline/σ를 오염시키면 안 된다.
    seen_days: set[str] = set()
    for chapter in chapters:
        day = _utc_date(chapter.started_at)
        if day not in seen_days:
            seen_days.add(day)
            chapter.warm = False
    return chapters


def load_chapters(log_path: str | Path) -> list[ChapterEvent]:
    """수집 로그 파일을 읽어 회차별 TG 이벤트 목록을 반환한다."""
    return parse_log_lines(Path(log_path).read_text(encoding="utf-8").splitlines())


def api_snapshot_fact(point: ApiPoint) -> dict:
    """원시 API 스냅샷 → append-only JSONL 레코드(멱등 event_id)."""
    return {
        "event_id": f"api:{point.date}:{point.ts:.3f}",
        "date": point.date,
        "ts": point.ts,
        "mb": point.mb,
    }


def append_api_snapshots(path: str | Path, points: Sequence[ApiPoint]) -> dict:
    """원시 스냅샷 append — 같은 event_id 재기록은 건너뛴다(멱등)."""
    return append_facts(path, [api_snapshot_fact(point) for point in points])


def _load_archive_points(path: Path) -> list[ApiPoint]:
    if not path.exists():
        return []
    points: list[ApiPoint] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            points.append(
                ApiPoint(
                    ts=float(row["ts"]), date=str(row["date"]), mb=float(row["mb"])
                )
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
    return points


def prune_api_snapshots(
    path: str | Path,
    *,
    keep_days: int = API_RAW_RETENTION_DAYS,
    now: float | None = None,
) -> dict:
    """raw TTL 정리 — 만료 스냅샷만 제거한다.

    파싱 불가 라인은 보존한다(원시 감사 추적의 데이터 손실 금지).
    """
    target = Path(path)
    if not target.exists():
        return {"removed": 0, "kept": 0}

    cutoff = (time.time() if now is None else now) - keep_days * 86400
    kept: list[str] = []
    removed = 0
    for line in target.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            ts = float(json.loads(stripped)["ts"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            kept.append(stripped)
            continue
        if ts < cutoff:
            removed += 1
        else:
            kept.append(stripped)

    if removed:
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
        os.replace(tmp, target)
    return {"removed": removed, "kept": len(kept)}


def load_api_points(
    state_path: str | Path, archive_path: str | Path | None = None
) -> list[ApiPoint]:
    """원시 아카이브 + 상태 파일 comparisons(파생)를 병합해 시간순 스냅샷 반환.

    같은 ts는 원시(아카이브)를 우선한다.
    """
    data = json.loads(Path(state_path).read_text(encoding="utf-8"))
    points: list[ApiPoint] = []
    for row in data.get("comparisons", []) or []:
        try:
            points.append(
                ApiPoint(
                    ts=float(row["timestamp"]),
                    date=str(row["date"]),
                    mb=float(row["api_mb"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue

    if archive_path:
        points = _load_archive_points(Path(archive_path)) + points

    points.sort(key=lambda p: p.ts)
    deduped: list[ApiPoint] = []
    for point in points:
        if deduped and deduped[-1].ts == point.ts:
            continue
        deduped.append(point)
    return deduped


def _utc_date(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def _iso_z(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _value_at(
    points: Sequence[ApiPoint],
    timestamps: Sequence[float],
    ts: float,
    expected_date: str,
) -> float | None:
    """API 누적값을 ts 시점에 대해 보간한다.

    범위 밖이거나 일자 경계를 가로지르는 구간이면 None(확정 불가).
    """
    if not points or ts < timestamps[0] or ts > timestamps[-1]:
        return None

    i = bisect_left(timestamps, ts)
    if i < len(points) and timestamps[i] == ts:
        point = points[i]
        return point.mb if point.date == expected_date else None

    before, after = points[i - 1], points[i]
    if before.date != expected_date or after.date != expected_date:
        return None
    if before.date != after.date or after.ts == before.ts:
        return None

    ratio = (ts - before.ts) / (after.ts - before.ts)
    return before.mb + (after.mb - before.mb) * ratio


def _bucket_fact(
    group: Sequence[ChapterEvent],
    size: int,
    points: Sequence[ApiPoint],
    timestamps: Sequence[float],
    source: str,
    config_hash: str | None = None,
) -> dict:
    issues: list[str] = []
    from_ts = group[0].started_at
    to_ts = max(chapter.ended_at for chapter in group)
    from_date = _utc_date(from_ts)
    to_date = _utc_date(to_ts)

    tg_bytes = sum(chapter.bytes for chapter in group)
    tg_mb = tg_bytes / _MB
    ok_count = sum(1 for ch in group if ch.saved and ch.warm)
    cold_count = sum(1 for ch in group if ch.saved and not ch.warm)
    fail_count = sum(1 for ch in group if not ch.saved)

    # 버킷 종료 시점까지 도착한 마지막 API 스냅샷(정확도/지연 판단 근거)
    settle_ts: float | None = None
    if timestamps:
        pos = bisect_right(timestamps, to_ts) - 1
        if pos >= 0:
            settle_ts = timestamps[pos]

    api_start: float | None = None
    api_end: float | None = None
    api_delta: float | None = None
    ratio: float | None = None

    if len(group) < size:
        issues.append("incomplete_bucket")

    if from_date != to_date:
        issues.append("utc_day_boundary")
    else:
        api_start = _value_at(points, timestamps, from_ts, from_date)
        api_end = _value_at(points, timestamps, to_ts, to_date)
        if api_start is None:
            issues.append("api_coverage_before_missing")
        if api_end is None:
            issues.append("api_coverage_after_missing")
        if api_start is not None and api_end is not None:
            api_delta = round(api_end - api_start, 4)
            if api_delta <= 0:
                issues.append("api_delta_not_settled")
            elif tg_mb > 0:
                ratio = round(api_delta / tg_mb, 4)

    structural = {"incomplete_bucket", "utc_day_boundary"}
    if any(issue in structural for issue in issues):
        quality = QUALITY_PARTIAL
    elif issues:
        quality = QUALITY_LATE
    else:
        quality = QUALITY_OK

    # [from, to) 반개구간 — event_id는 소스+시각+크기로 결정적이다(멱등 재기록 방지).
    return {
        "event_id": f"{source}:{_iso_z(from_ts)}:{size}",
        "source": source,
        "size": size,
        "start_idx": group[0].idx,
        "end_idx": group[-1].idx,
        "from_ts": from_ts,
        "to_ts": to_ts,
        "settle_ts": settle_ts,
        "tg_bytes_delta": tg_bytes,
        "api_mb_start": round(api_start, 4) if api_start is not None else None,
        "api_mb_end": round(api_end, 4) if api_end is not None else None,
        "api_mb_delta": api_delta,
        "r": ratio,
        "billed_api_mb": api_delta,
        "consumed_chapters": len(group),
        "cold_count": cold_count,
        "ok_count": ok_count,
        "fail_count": fail_count,
        "quality": quality,
        "note": ";".join(issues),
        "state": "active",
        "correction_of": None,
        "config_hash": config_hash,
        "experiment_id": None,
        "tags": {"source": source},
    }


def build_buckets(
    chapters: Sequence[ChapterEvent],
    api_points: Sequence[ApiPoint],
    size: int = DEFAULT_BUCKET_SIZE,
    *,
    source: str | None = None,
    config_hash: str | None = None,
) -> list[dict]:
    """회차를 size 크기 버킷으로 묶어 버킷 팩트 목록을 만든다."""
    if size < 1:
        raise ValueError("bucket size must be >= 1")

    ordered = sorted(chapters, key=lambda ch: ch.started_at)
    timestamps = [point.ts for point in api_points]
    resolved_source = source or _infer_source(ordered)

    facts: list[dict] = []
    for start in range(0, len(ordered), size):
        group = ordered[start : start + size]
        facts.append(
            _bucket_fact(
                group, size, api_points, timestamps, resolved_source, config_hash
            )
        )
    return facts


def _infer_source(chapters: Sequence[ChapterEvent]) -> str:
    counts: dict[str, int] = {}
    for chapter in chapters:
        counts[chapter.source] = counts.get(chapter.source, 0) + 1
    return max(counts, key=lambda name: counts[name]) if counts else "unknown"


def bucket_ratio(fact: dict) -> float | None:
    """버킷 팩트의 API/TG 비율(미확정이면 None)."""
    return fact.get("r")


def facts_by_config(facts: Sequence[dict], config_hash: str) -> list[dict]:
    """특정 config_hash로 태깅된 팩트만."""
    return [f for f in facts if f.get("config_hash") == config_hash]


def _metric_median(facts: Sequence[dict], metric: str) -> float | None:
    vals: list[float] = []
    for f in facts:
        chapters = f.get("consumed_chapters") or 0
        if (
            metric == "api_kb_per_chapter"
            and f.get("quality") == QUALITY_OK
            and f.get("api_mb_delta")
            and chapters
        ):
            vals.append(f["api_mb_delta"] * _KB / chapters)
        elif metric == "tg_kb_per_chapter" and chapters and f["tg_bytes_delta"] > 0:
            vals.append(f["tg_bytes_delta"] / _KB / chapters)
        elif metric == "r" and f.get("r"):
            vals.append(f["r"])
    return round(median(vals), 4) if vals else None


def _group_stats(facts: Sequence[dict]) -> dict:
    ok = [f for f in facts if f.get("quality") == QUALITY_OK and f.get("consumed_chapters")]
    return {
        "n": len(facts),
        "n_ok": len(ok),
        "api_kb_per_chapter_median": _metric_median(facts, "api_kb_per_chapter"),
        "tg_kb_per_chapter_median": _metric_median(facts, "tg_kb_per_chapter"),
        "r_median": _metric_median(facts, "r"),
        "fail_count": sum(int(f.get("fail_count", 0) or 0) for f in facts),
    }


def compare_configs(
    facts: Sequence[dict],
    baseline_hash: str,
    treatment_hash: str,
    metric: str = "api_kb_per_chapter",
) -> dict:
    """baseline/treatment 두 config의 OEC 비교 — 절감률/판정(계획 §6).

    감소율 = (baseline - treatment)/baseline × 100. ≥10% 다음 단계, ≥5% 채택, <5% 롤백.
    """
    base = _group_stats(facts_by_config(facts, baseline_hash))
    treat = _group_stats(facts_by_config(facts, treatment_hash))
    b, t = base.get(f"{metric}_median"), treat.get(f"{metric}_median")
    delta = round((t - b) / b * 100, 1) if (b and t and b > 0) else None
    if delta is None:
        verdict = "insufficient"
    elif -delta >= 10:
        verdict = "adopt_next"
    elif -delta >= 5:
        verdict = "adopt"
    else:
        verdict = "rollback"
    return {
        "metric": metric,
        "baseline": base,
        "treatment": treat,
        "delta_pct": delta,
        "reduction_pct": round(-delta, 1) if delta is not None else None,
        "verdict": verdict,
    }


def aa_report(
    facts: Sequence[dict], config_hash: str | None = None, metric: str = "tg_kb_per_chapter"
) -> dict:
    """동일 config 팩트를 전/후반으로 나눠 A/A 변동성 확인(작을수록 양호)."""
    series = list(facts if config_hash is None else facts_by_config(facts, config_hash))
    series = [f for f in series if f.get("consumed_chapters")]
    series.sort(key=lambda f: f.get("from_ts") or 0)
    if len(series) < 4:
        return {"n": len(series), "delta_pct": None, "ok": False, "note": "need >= 4 buckets"}
    mid = len(series) // 2
    first, second = _group_stats(series[:mid]), _group_stats(series[mid:])
    m1, m2 = first.get(f"{metric}_median"), second.get(f"{metric}_median")
    delta = round((m2 - m1) / m1 * 100, 1) if (m1 and m2) else None
    return {
        "n": len(series),
        "metric": metric,
        "first_half": first,
        "second_half": second,
        "delta_pct": delta,
        "ok": delta is not None and abs(delta) < 5.0,
    }


def daily_reconcile(
    facts: Sequence[dict], history: Sequence[dict], day: str
) -> dict:
    """일별 **확정 API(청구)** 총량과 버킷 롤업을 정산(계획 §8 P6, FOCUS reconcile).

    - `api_billed_mb`: 해당 일 `traffic_history.total_traffic`(지연 반영된 확정값)
    - `rollup_api_mb`: 버킷 `api_mb_delta` 합(수집 구간 귀속)
    - `gap_mb`: 청구 - 롤업 = 수집 외/미귀속(콜드·모니터·경계 넘김 등)
    - 같은 일자로 귀속: 팩트 `to_ts`(UTC) 기준, 경계 넘김은 partial로 계수
    """
    day_facts = [f for f in facts if _utc_date(f.get("to_ts") or 0) == day]
    api_billed = 0.0
    for entry in history or []:
        if str(entry.get("group_date", "")).startswith(day):
            api_billed = float(entry.get("total_traffic", 0) or 0) / _MB
            break
    rollup = sum(float(f.get("api_mb_delta") or 0) for f in day_facts)
    tg_mb = sum(int(f.get("tg_bytes_delta") or 0) for f in day_facts) / _MB
    return {
        "day": day,
        "api_billed_mb": round(api_billed, 3),
        "rollup_api_mb": round(rollup, 3),
        "tg_mb": round(tg_mb, 3),
        "r_day": round(api_billed / tg_mb, 4) if (tg_mb > 0 and api_billed > 0) else None,
        "gap_mb": round(api_billed - rollup, 3),
        "gap_pct": round((api_billed - rollup) / api_billed * 100, 1) if api_billed > 0 else None,
        "n_facts": len(day_facts),
        "ok_count": sum(1 for f in day_facts if f.get("quality") == QUALITY_OK),
        "late_count": sum(1 for f in day_facts if f.get("quality") == QUALITY_LATE),
        "partial_count": sum(1 for f in day_facts if f.get("quality") == QUALITY_PARTIAL),
        "api_settled": api_billed > 0,
    }


def load_facts(path: str | Path = DEFAULT_OUT_PATH) -> list[dict]:
    """append-only fact JSONL 로드(손상 라인은 건너뜀)."""
    target = Path(path)
    if not target.exists():
        return []
    facts: list[dict] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            facts.append(row)
    return facts


def report(facts: Sequence[dict]) -> dict:
    """버킷 팩트 목록 요약 — 품질 분포와 대표 지표."""
    ok_facts = [f for f in facts if f["quality"] == QUALITY_OK and f["r"] is not None]
    ratios = [f["r"] for f in ok_facts]
    tg_kb_per_chapter = [
        f["tg_bytes_delta"] / _KB / f["consumed_chapters"]
        for f in facts
        if f["consumed_chapters"]
    ]
    api_kb_per_chapter = [
        f["api_mb_delta"] * 1024 / f["consumed_chapters"]
        for f in ok_facts
        if f["consumed_chapters"]
    ]

    return {
        "n_buckets": len(facts),
        "bucket_sizes": sorted({f["size"] for f in facts}),
        "quality_counts": {
            QUALITY_OK: sum(1 for f in facts if f["quality"] == QUALITY_OK),
            QUALITY_LATE: sum(1 for f in facts if f["quality"] == QUALITY_LATE),
            QUALITY_PARTIAL: sum(1 for f in facts if f["quality"] == QUALITY_PARTIAL),
        },
        "r_median": round(median(ratios), 4) if ratios else None,
        "r_mean": round(mean(ratios), 4) if ratios else None,
        "r_min": round(min(ratios), 4) if ratios else None,
        "r_max": round(max(ratios), 4) if ratios else None,
        "tg_kb_per_chapter_mean": round(mean(tg_kb_per_chapter), 2)
        if tg_kb_per_chapter
        else None,
        "api_kb_per_chapter_mean": (
            round(mean(api_kb_per_chapter), 2) if api_kb_per_chapter else None
        ),
        "tg_mb_total": round(sum(f["tg_bytes_delta"] for f in facts) / _MB, 3),
        "api_mb_total": round(
            sum(f["api_mb_delta"] for f in facts if f["api_mb_delta"]), 3
        ),
        "chapters_total": sum(f["consumed_chapters"] for f in facts),
    }


def bucket_baseline_stats(
    log_path: str | Path = DEFAULT_LOG_PATH,
    size: int = DEFAULT_BUCKET_SIZE,
) -> dict | None:
    """과거 완결·웜 버킷만으로 회차당 KB 기준선(중앙값)과 σ를 산출.

    - API가 필요 없다(r 불필요) → 수집 로그만으로 초기 시딩 가능.
    - 콜드가 포함된 버킷/미완결/미저장 버킷은 제외한다.
    - 표본 2개 미만이면 None.
    """
    chapters = load_chapters(log_path)
    vals: list[float] = []
    for start in range(0, len(chapters), size):
        group = chapters[start : start + size]
        if len(group) < size or not all(c.warm and c.saved and c.bytes > 0 for c in group):
            continue
        vals.append(sum(c.bytes for c in group) / _KB / size)
    if len(vals) < 2:
        return None
    return {
        "n": len(vals),
        "kb_per_chapter_median": round(median(vals), 2),
        "kb_per_chapter_stdev": round(stdev(vals), 3),
    }


def completed_warm_facts(facts: Sequence[dict]) -> list[dict]:
    """완결(size 충족)·웜(콜드 없음)·quality ok 버킷만 골라낸다.

    [WHY] 콜드(첫 로드)와 미완결 버킷은 회차당 소비가 정상 범위를 벗어나므로
    기준선/안전망 판정에서 제외한다.
    """
    return [
        f
        for f in facts
        if f["quality"] == QUALITY_OK
        and f["consumed_chapters"] == f["size"]
        and f.get("cold_count", 0) == 0
    ]


def tg_warm_facts(facts: Sequence[dict]) -> list[dict]:
    """TG만으로 본 완결·웜 버킷(quality/r 무관) — 소비 안전망/기준선용.

    [WHY] 소비 급증 안전망은 TG KB/화만 쓰므로 API settle(quality=ok)을 기다리지
    않는다. r(보정)만 API settle이 필요하다.
    """
    return [
        f
        for f in facts
        if f["consumed_chapters"] == f["size"]
        and f.get("cold_count", 0) == 0
        and f["tg_bytes_delta"] > 0
    ]


def compute_config_hash(flags: Mapping[str, object]) -> str:
    """절감 레버 설정 조합의 식별자(실험 A/B 태깅용)."""
    payload = ";".join(f"{k}={flags[k]}" for k in sorted(flags))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def record_bucket_facts(
    log_path: str | Path = DEFAULT_LOG_PATH,
    state_path: str | Path = DEFAULT_API_STATE_PATH,
    archive_path: str | Path = DEFAULT_API_POINTS_PATH,
    out_path: str | Path | None = DEFAULT_OUT_PATH,
    size: int = DEFAULT_BUCKET_SIZE,
    config_hash: str | None = None,
) -> list[dict]:
    """버킷 팩트를 계산해 append-only `bucket_facts.jsonl`에 영속(멱등).

    반환값(팩트 목록)을 그대로 재사용하면 로그/상태 재파싱을 줄일 수 있다.
    """
    chapters = load_chapters(log_path)
    points = load_api_points(state_path, archive_path)
    facts = build_buckets(chapters, points, size, config_hash=config_hash)
    if out_path:
        append_facts(out_path, facts)
    return facts


def latest_tg_warm_fact(facts: Sequence[dict]) -> dict | None:
    """최근 완결·웜 버킷(TG 기준) — 없으면 None."""
    done = tg_warm_facts(facts)
    return done[-1] if done else None


def bucket_ratio_median_from_facts(facts: Sequence[dict], k: int = 5) -> float | None:
    """완결·웜 + settle(quality ok) 버킷 r의 최근 K개 중앙값 — 없으면 None."""
    done = completed_warm_facts(facts)
    ratios = [f["r"] for f in done[-k:] if f.get("r")]
    return round(median(ratios), 4) if ratios else None


def tg_baseline_stats_from_facts(
    facts: Sequence[dict], size: int = DEFAULT_BUCKET_SIZE
) -> dict | None:
    """버킷 팩트(TG)로 회차당 KB 기준선(중앙값)·σ 산출(표본 2개 미만이면 None)."""
    vals = [
        f["tg_bytes_delta"] / _KB / f["consumed_chapters"]
        for f in tg_warm_facts(facts)
        if f["consumed_chapters"]
    ]
    if len(vals) < 2:
        return None
    return {
        "n": len(vals),
        "kb_per_chapter_median": round(median(vals), 2),
        "kb_per_chapter_stdev": round(stdev(vals), 3),
    }


def kb_per_chapter(fact: dict) -> float:
    """버킷 팩트의 회차당 TG KB."""
    chapters = fact.get("consumed_chapters") or 0
    return fact["tg_bytes_delta"] / _KB / chapters if chapters else 0.0


def latest_completed_warm_bucket(
    log_path: str | Path = DEFAULT_LOG_PATH,
    state_path: str | Path = DEFAULT_API_STATE_PATH,
    archive_path: str | Path = DEFAULT_API_POINTS_PATH,
    size: int = DEFAULT_BUCKET_SIZE,
) -> dict | None:
    """가장 최근의 완결·웜 버킷 팩트 (없으면 None)."""
    chapters = load_chapters(log_path)
    points = load_api_points(state_path, archive_path)
    done = completed_warm_facts(build_buckets(chapters, points, size))
    return done[-1] if done else None


def bucket_ratio_median(
    log_path: str | Path = DEFAULT_LOG_PATH,
    state_path: str | Path = DEFAULT_API_STATE_PATH,
    archive_path: str | Path = DEFAULT_API_POINTS_PATH,
    size: int = DEFAULT_BUCKET_SIZE,
    k: int = 5,
) -> float | None:
    """최근 K개 완결·웜 버킷의 r 중앙값 (표본 없으면 None).

    [WHY] 단구간 r은 출렁이므로 버킷 누적 중앙값을 보정계수 EWMA 입력으로 쓴다.
    """
    chapters = load_chapters(log_path)
    points = load_api_points(state_path, archive_path)
    done = completed_warm_facts(build_buckets(chapters, points, size))
    ratios = [f["r"] for f in done[-k:] if f.get("r")]
    return round(median(ratios), 4) if ratios else None


def append_facts(path: str | Path, facts: Sequence[dict]) -> dict:
    """버킷 팩트를 JSONL에 append — event_id 중복은 건너뛴다(멱등)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    seen: set[str] = set()
    if target.exists():
        for line in target.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event_id = json.loads(line).get("event_id")
            except json.JSONDecodeError:
                continue
            if event_id:
                seen.add(event_id)

    appended = 0
    with target.open("a", encoding="utf-8") as handle:
        for fact in facts:
            event_id = fact.get("event_id")
            if not isinstance(event_id, str) or event_id in seen:
                continue
            seen.add(event_id)
            handle.write(json.dumps(fact, ensure_ascii=False) + "\n")
            appended += 1

    return {"appended": appended, "skipped": len(facts) - appended}


def _print_summary(summary: dict, facts: Sequence[dict]) -> None:
    counts = summary["quality_counts"]
    print(
        f"buckets={summary['n_buckets']} sizes={summary['bucket_sizes']} "
        f"ok={counts[QUALITY_OK]} late={counts[QUALITY_LATE]} partial={counts[QUALITY_PARTIAL]}"
    )
    if summary["r_median"] is not None:
        print(
            f"r: median={summary['r_median']} mean={summary['r_mean']} "
            f"min={summary['r_min']} max={summary['r_max']}"
        )
    print(
        f"tg_kb/chapter={summary['tg_kb_per_chapter_mean']} "
        f"api_kb/chapter={summary['api_kb_per_chapter_mean']} "
        f"tg_mb={summary['tg_mb_total']} api_mb={summary['api_mb_total']} "
        f"chapters={summary['chapters_total']}"
    )
    for fact in facts:
        print(
            f"  [{fact['start_idx']}~{fact['end_idx']}] {fact['quality']:7s} "
            f"r={fact['r']} tg={fact['tg_bytes_delta'] / _KB:.1f}KB "
            f"api={fact['api_mb_delta']} note={fact['note'] or '-'}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bucket-based DataImpulse/TG traffic measurement (read-only)"
    )
    parser.add_argument("--log", default=str(DEFAULT_LOG_PATH), help="수집 로그 경로")
    parser.add_argument(
        "--state", default=str(DEFAULT_API_STATE_PATH), help="API 상태 JSON 경로"
    )
    parser.add_argument(
        "--size", type=int, default=DEFAULT_BUCKET_SIZE, help="버킷 크기(화)"
    )
    parser.add_argument("--source", default=None, help="source 태그 강제 지정")
    parser.add_argument(
        "--archive",
        default=str(DEFAULT_API_POINTS_PATH),
        help="원시 API 스냅샷 JSONL 경로",
    )
    parser.add_argument("--out", default=None, help="버킷 팩트 JSONL append 경로")
    parser.add_argument("--json", action="store_true", help="JSON 출력")
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("BASE_HASH", "TREAT_HASH"),
        help="config_hash 두 개 OEC 비교",
    )
    parser.add_argument("--aa", action="store_true", help="동일 config 전/후반 A/A 변동성")
    parser.add_argument("--reconcile", metavar="YYYY-MM-DD", help="일별 API↔버킷 정산")
    args = parser.parse_args(argv)

    if args.size < 1:
        parser.error("--size must be >= 1")
    if args.size not in BUCKET_SIZES:
        print(
            f"[warn] --size {args.size} 는 표준 크기 {BUCKET_SIZES} 외", file=sys.stderr
        )

    try:
        chapters = load_chapters(args.log)
        points = load_api_points(args.state, args.archive)
    except FileNotFoundError as exc:
        print(f"[error] 파일 없음: {exc.filename}", file=sys.stderr)
        return 2

    facts = build_buckets(chapters, points, args.size, source=args.source)
    if args.compare:
        print(
            json.dumps(
                compare_configs(facts, args.compare[0], args.compare[1]),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.aa:
        print(json.dumps(aa_report(facts), ensure_ascii=False, indent=2))
        return 0
    if args.reconcile:
        try:
            state = json.loads(Path(args.state).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
        history = [
            {"group_date": d, "total_traffic": mb * _MB}
            for d, mb in (state.get("api_history") or {}).items()
        ]
        print(
            json.dumps(
                daily_reconcile(facts, history, args.reconcile),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    summary = report(facts)
    if args.out:
        summary["append"] = append_facts(args.out, facts)

    if args.json:
        print(
            json.dumps(
                {"summary": summary, "buckets": facts}, ensure_ascii=False, indent=2
            )
        )
    else:
        _print_summary(summary, facts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
