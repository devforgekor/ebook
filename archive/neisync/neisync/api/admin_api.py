from fastapi import FastAPI, Query
from pathlib import Path
import sqlite3
import os

app = FastAPI(title="NEISync Admin API")

DB_PATH = os.environ.get("DB_PATH", "data/neisync.db")
LOG_PATH = "neisync/logs/engine.meal.log"

@app.get("/status")
def status():
    db_exists = Path(DB_PATH).exists()
    size = Path(DB_PATH).stat().st_size if db_exists else 0
    return {
        "db_path": DB_PATH,
        "db_exists": db_exists,
        "db_size": size,
        "log_path": LOG_PATH,
    }

@app.get("/logs")
def logs(lines: int = Query(20, ge=1, le=200)):
    if not Path(LOG_PATH).exists():
        return {"log": "로그 파일 없음"}
    with open(LOG_PATH, encoding="utf-8") as f:
        log_lines = f.readlines()[-lines:]
    return {"log": "".join(log_lines)}

@app.get("/meals")
def meals(school_id: int = Query(None), date: str = Query(None), limit: int = Query(20, le=100)):
    if not Path(DB_PATH).exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    q = "SELECT * FROM meal WHERE 1=1"
    params = []
    if school_id:
        q += " AND school_id=?"
        params.append(school_id)
    if date:
        q += " AND meal_date=?"
        params.append(date)
    q += " LIMIT ?"
    params.append(limit)
    rows = conn.execute(q, params).fetchall()
    cols = [d[0] for d in conn.execute("PRAGMA table_info(meal)")]
    conn.close()
    return [dict(zip(cols, r)) for r in rows]

# 실행: uvicorn neisync.api.admin_api:app --reload
