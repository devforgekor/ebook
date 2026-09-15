from pathlib import Path
import sqlite3
from typing import Dict, Any

def check_timetable_quality(db_path: Path) -> Dict[str, Any]:
    """시간표 DB 품질 점검: 결측치, 중복 등"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    result = {}
    try:
        cur.execute("SELECT COUNT(*) FROM timetable WHERE school_code IS NULL OR date IS NULL OR subject IS NULL OR subject = ''")
        missing = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM (SELECT school_code, date, grade, class_nm, period, COUNT(*) FROM timetable GROUP BY school_code, date, grade, class_nm, period HAVING COUNT(*) > 1)")
        duplicates = cur.fetchone()[0]
        result = {
            "missing_records": missing,
            "duplicate_school_date_class_period": duplicates
        }
    except Exception as e:
        result = {"error": str(e)}
    finally:
        conn.close()
    return result
