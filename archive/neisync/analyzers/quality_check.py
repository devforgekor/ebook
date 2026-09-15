from pathlib import Path
import sqlite3
from typing import Dict, Any

def check_meal_quality(db_path: Path) -> Dict[str, Any]:
    """급식 DB 품질 점검: 결측치, 중복, 이상치 등 간단 점검"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    result = {}
    try:
        # 결측치(학교코드, 날짜, 메뉴) 체크
        cur.execute("SELECT COUNT(*) FROM meal WHERE school_code IS NULL OR date IS NULL OR menu IS NULL OR menu = ''")
        missing = cur.fetchone()[0]
        # 중복(학교+날짜) 체크
        cur.execute("SELECT COUNT(*) FROM (SELECT school_code, date, COUNT(*) FROM meal GROUP BY school_code, date HAVING COUNT(*) > 1)")
        duplicates = cur.fetchone()[0]
        result = {
            "missing_records": missing,
            "duplicate_school_date": duplicates
        }
    except Exception as e:
        result = {"error": str(e)}
    finally:
        conn.close()
    return result
