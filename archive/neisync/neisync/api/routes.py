import asyncio
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse

from analyzers.export_meal_report import export_meal_report
from analyzers.export_schedule_report import export_schedule_report
from analyzers.export_timetable_report import export_timetable_report
from analyzers.meal_stats import analyze_meal_stats
from analyzers.quality_check import check_meal_quality
from analyzers.schedule_quality import check_schedule_quality
from analyzers.schedule_stats import analyze_schedule_stats
from analyzers.timetable_quality import check_timetable_quality
from analyzers.timetable_stats import analyze_timetable_stats
from neisync.collectors.meal import MealCollector
from neisync.collectors.neis_info import NeisInfoCollector
from neisync.collectors.schedule import ScheduleCollector
from neisync.collectors.timetable import TimetableCollector
from neisync.core.notify import send_alert

router = APIRouter()

# 추후 /collect, /status 등 엔드포인트 추가 예정

@router.post("/notify/test")
async def notify_test(request: Request):
    data = await request.json()
    message = data.get("message", "테스트 알림입니다.")
    level = data.get("level", "info")
    channel = data.get("channel", "telegram")
    await send_alert(message, level, channel)
    return JSONResponse({"result": "sent", "message": message, "level": level, "channel": channel})

@router.post("/collect/{collector}")
async def collect_run(collector: str, params: dict = None):
    params = params or {}
    shard = params.get("shard", "odd")
    db_path = Path(f"data/active/{collector}_{shard}.db")
    collector_map = {
        "meal": MealCollector,
        "schedule": ScheduleCollector,
        "timetable": TimetableCollector,
        "neis-info": NeisInfoCollector,
    }
    cls = collector_map.get(collector)
    if not cls:
        raise HTTPException(status_code=404, detail="Collector not found")
    try:
        result = await cls(collector, db_path, shard=shard, **params).run()
        return {"result": "ok", "collector": collector}
    except Exception as e:
        await send_alert(f"Collector {collector} failed: {e}", level="error")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status/{collector}")
async def collector_status(collector: str, shard: str = Query('odd')):
    db_path = Path(f"data/active/{collector}_{shard}.db")
    log_dir = Path("data/logs")
    log_files = sorted([str(f) for f in log_dir.glob(f"{collector}-{shard}-*.jsonl.gz")])
    # 최근 로그 파일에서 성공/실패 카운트 추출(간단 버전)
    success = 0
    failed = 0
    if log_files:
        import gzip
        import json
        try:
            with gzip.open(log_files[-1], 'rt', encoding='utf-8') as f:
                for line in f:
                    rec = json.loads(line)
                    if rec.get('event') == 'start':
                        continue
                    if rec.get('event') == 'fetch_failed':
                        failed += 1
                    else:
                        success += 1
        except Exception:
            pass
    return {
        "collector": collector,
        "shard": shard,
        "db_path": str(db_path),
        "log_files": log_files,
        "success": success,
        "failed": failed
    }

@router.get("/logs/{collector}")
async def collector_logs(collector: str, shard: str = Query('odd'), limit: int = Query(100)):
    log_dir = Path("data/logs")
    log_files = sorted([str(f) for f in log_dir.glob(f"{collector}-{shard}-*.jsonl.gz")])
    logs = []
    if log_files:
        import gzip
        import json
        try:
            with gzip.open(log_files[-1], 'rt', encoding='utf-8') as f:
                for i, line in enumerate(f):
                    if i >= limit:
                        break
                    logs.append(json.loads(line))
        except Exception:
            pass
    return {"collector": collector, "shard": shard, "log_file": log_files[-1] if log_files else None, "logs": logs}

@router.post("/collect-async/{collector}")
def collect_run_async(collector: str, background_tasks: BackgroundTasks, params: dict = None):
    params = params or {}
    shard = params.get("shard", "odd")
    db_path = Path(f"data/active/{collector}_{shard}.db")
    collector_map = {
        "meal": MealCollector,
        "schedule": ScheduleCollector,
        "timetable": TimetableCollector,
        "neis-info": NeisInfoCollector,
    }
    cls = collector_map.get(collector)
    if not cls:
        raise HTTPException(status_code=404, detail="Collector not found")
    async def run_collector():
        try:
            await cls(collector, db_path, shard=shard, **params).run()
        except Exception as e:
            await send_alert(f"Collector {collector} failed: {e}", level="error")
    background_tasks.add_task(asyncio.run, run_collector())
    return {"result": "accepted", "collector": collector}

@router.get("/analyze/meal")
async def analyze_meal(shard: str = Query('odd')):
    db_path = Path(f"data/active/meal_{shard}.db")
    stats = analyze_meal_stats(db_path)
    return stats

@router.get("/analyze/schedule")
async def analyze_schedule(shard: str = Query('odd')):
    db_path = Path(f"data/active/schedule_{shard}.db")
    stats = analyze_schedule_stats(db_path)
    return stats

@router.get("/analyze/timetable")
async def analyze_timetable(shard: str = Query('odd')):
    db_path = Path(f"data/active/timetable_{shard}.db")
    stats = analyze_timetable_stats(db_path)
    return stats

@router.get("/quality/meal")
async def quality_meal(shard: str = Query('odd')):
    db_path = Path(f"data/active/meal_{shard}.db")
    result = check_meal_quality(db_path)
    return result

@router.get("/quality/schedule")
async def quality_schedule(shard: str = Query('odd')):
    db_path = Path(f"data/active/schedule_{shard}.db")
    result = check_schedule_quality(db_path)
    return result

@router.get("/quality/timetable")
async def quality_timetable(shard: str = Query('odd')):
    db_path = Path(f"data/active/timetable_{shard}.db")
    result = check_timetable_quality(db_path)
    return result

@router.get("/export/meal")
async def export_meal(shard: str = Query('odd')):
    db_path = Path(f"data/active/meal_{shard}.db")
    out_path = db_path.with_suffix('.xlsx')
    export_meal_report(db_path, out_path)
    return FileResponse(out_path, filename=out_path.name)

@router.get("/export/schedule")
async def export_schedule(shard: str = Query('odd')):
    db_path = Path(f"data/active/schedule_{shard}.db")
    out_path = db_path.with_suffix('.xlsx')
    export_schedule_report(db_path, out_path)
    return FileResponse(out_path, filename=out_path.name)

@router.get("/export/timetable")
async def export_timetable(shard: str = Query('odd')):
    db_path = Path(f"data/active/timetable_{shard}.db")
    out_path = db_path.with_suffix('.xlsx')
    export_timetable_report(db_path, out_path)
    return FileResponse(out_path, filename=out_path.name)
