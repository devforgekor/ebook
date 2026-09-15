import typer
from pathlib import Path
from neisync.collectors.meal import MealCollector
from neisync.core.config import settings

app = typer.Typer(help="NEISync 명령행 도구")

@app.command()
def meal(
    db_path: str = typer.Option(None, help="DB 파일 경로 (기본값: 설정값)"),
    debug: bool = typer.Option(False, help="디버그 모드")
):
    """
    급식 데이터 수집 실행
    """
    db = db_path or settings.DB_PATH
    collector = MealCollector(db_path=db, debug_mode=debug)
    import asyncio
    asyncio.run(collector.run())
    typer.echo(f"급식 데이터 수집 완료 (DB: {db})")

@app.command()
def show_paths():
    """
    DB/로그 경로 등 주요 경로 출력
    """
    typer.echo(f"DB 경로: {settings.DB_PATH}")
    typer.echo(f"로그 디렉터리: neisync/logs/")

if __name__ == "__main__":
    app()
