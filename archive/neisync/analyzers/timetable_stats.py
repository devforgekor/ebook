
from pathlib import Path
import sqlite3
from typing import Dict, Any
from neisync.core.db_utils import table_exists

def analyze_timetable_stats(db_path: Path) -> Dict[str, Any]:
    """시간표 DB에서 학교별/일자별 통계 분석 예시 (DDL 미존재 시 안전하게 스킵)"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    result = {}
    try:
        if not table_exists(conn, "timetable"):
            result = {"warn": "'timetable' 테이블 없음 → timetable 분석 스킵"}
        else:
            cur.execute("SELECT COUNT(*), COUNT(DISTINCT school_code), COUNT(DISTINCT date) FROM timetable")
            total, schools, dates = cur.fetchone()
            result = {
                "total_records": total,
                "unique_schools": schools,
                "unique_dates": dates
            }
    except Exception as e:
        result = {"error": str(e)}
    finally:
        conn.close()
    return result
