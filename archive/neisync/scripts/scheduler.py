import asyncio
import time
from datetime import datetime
from neisync.collectors.meal import MealCollector
from neisync.collectors.schedule import ScheduleCollector
from neisync.collectors.timetable import TimetableCollector
from pathlib import Path
from analyzers.meal_stats import analyze_meal_stats
from analyzers.schedule_stats import analyze_schedule_stats
from analyzers.timetable_stats import analyze_timetable_stats
from analyzers.quality_check import check_meal_quality
from analyzers.schedule_quality import check_schedule_quality
from analyzers.timetable_quality import check_timetable_quality
from analyzers.export_meal_report import export_meal_report
from analyzers.export_schedule_report import export_schedule_report
from analyzers.export_timetable_report import export_timetable_report
from neisync.core.notify import send_alert
from neisync.core.db_schema import ensure_schema

async def run_all_collectors():
    today = datetime.now().strftime('%Y%m%d')
    db_meal = Path(f'data/active/meal_odd.db')
    db_schedule = Path(f'data/active/schedule_odd.db')
    db_timetable = Path(f'data/active/timetable_odd.db')
    await MealCollector('meal', db_meal, shard='odd', date=today, region='B10').run()
    await ScheduleCollector('schedule', db_schedule, shard='odd', year=datetime.now().year, region='B10').run()
    await TimetableCollector('timetable', db_timetable, shard='odd', ay=datetime.now().year, semester=1, region='B10').run()

async def run_all_analysis():
    db_meal = Path('data/active/meal_odd.db')
    db_schedule = Path('data/active/schedule_odd.db')
    db_timetable = Path('data/active/timetable_odd.db')
    print('[분석] 급식 통계:', analyze_meal_stats(db_meal))
    print('[분석] 일정 통계:', analyze_schedule_stats(db_schedule))
    print('[분석] 시간표 통계:', analyze_timetable_stats(db_timetable))
    print('[품질] 급식:', check_meal_quality(db_meal))
    print('[품질] 일정:', check_schedule_quality(db_schedule))
    print('[품질] 시간표:', check_timetable_quality(db_timetable))
    print('[리포트] 급식:', export_meal_report(db_meal))
    print('[리포트] 일정:', export_schedule_report(db_schedule))
    print('[리포트] 시간표:', export_timetable_report(db_timetable))

async def notify_summary():
    db_meal = Path('data/active/meal_odd.db')
    db_schedule = Path('data/active/schedule_odd.db')
    db_timetable = Path('data/active/timetable_odd.db')
    meal_stats = analyze_meal_stats(db_meal)
    schedule_stats = analyze_schedule_stats(db_schedule)
    timetable_stats = analyze_timetable_stats(db_timetable)
    meal_quality = check_meal_quality(db_meal)
    schedule_quality = check_schedule_quality(db_schedule)
    timetable_quality = check_timetable_quality(db_timetable)
    msg = (
        f"[NEISync 자동 리포트]\n"
        f"급식: {meal_stats}\n품질: {meal_quality}\n"
        f"일정: {schedule_stats}\n품질: {schedule_quality}\n"
        f"시간표: {timetable_stats}\n품질: {timetable_quality}\n"
        f"엑셀 리포트가 생성되었습니다."
    )
    await send_alert(msg, level="info", channel="telegram")

if __name__ == '__main__':
    dbs = [
        Path('data/active/meal_odd.db'),
        Path('data/active/schedule_odd.db'),
        Path('data/active/timetable_odd.db'),
    ]
    for db in dbs:
        ensure_schema(str(db))
        print(f"[스키마] {db} ensured.")
    while True:
        print(f"[스케줄러] {datetime.now()} 수집 시작")
        asyncio.run(run_all_collectors())
        print(f"[스케줄러] {datetime.now()} 분석/품질/리포트 시작")
        asyncio.run(run_all_analysis())
        print(f"[스케줄러] {datetime.now()} 결과 알림 전송")
        asyncio.run(notify_summary())
        print(f"[스케줄러] {datetime.now()} 전체 완료. 24시간 대기...")
        time.sleep(60 * 60 * 24)
