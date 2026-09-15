import asyncio
import typer
from pathlib import Path
from typing import Optional

from .meal import MealCollector
from .schedule import ScheduleCollector
from .timetable import TimetableCollector
from .neis_info import NeisInfoCollector

app = typer.Typer()

@app.command()
def meal(
    shard: str = typer.Option('odd', help='샤드 (odd/even)'),
    date: Optional[str] = typer.Option(None, help='수집할 날짜 (YYYYMMDD)'),
    region: str = typer.Option('B10', help='교육청 코드'),
):
    db_path = Path(f'data/active/meal_{shard}.db')
    asyncio.run(MealCollector('meal', db_path, shard=shard, date=date, region=region).run())

@app.command()
def schedule(
    shard: str = typer.Option('odd', help='샤드 (odd/even)'),
    year: Optional[int] = typer.Option(None, help='학년도'),
    region: str = typer.Option('B10', help='교육청 코드'),
):
    db_path = Path(f'data/active/schedule_{shard}.db')
    asyncio.run(ScheduleCollector('schedule', db_path, shard=shard, year=year, region=region).run())

@app.command()
def timetable(
    shard: str = typer.Option('odd', help='샤드 (odd/even)'),
    ay: Optional[int] = typer.Option(None, help='학년도'),
    semester: int = typer.Option(1, help='학기'),
    region: str = typer.Option('B10', help='교육청 코드'),
):
    db_path = Path(f'data/active/timetable_{shard}.db')
    asyncio.run(TimetableCollector('timetable', db_path, shard=shard, ay=ay, semester=semester, region=region).run())

@app.command()
def neis_info(
    shard: str = typer.Option('odd', help='샤드 (odd/even)'),
    region: str = typer.Option('B10', help='교육청 코드'),
):
    db_path = Path(f'data/master/neis_info_{shard}.db')
    asyncio.run(NeisInfoCollector('neis_info', db_path, shard=shard, region=region).run())

if __name__ == '__main__':
    app()
