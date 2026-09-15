
import pandas as pd
import sqlite3
from pathlib import Path
from typing import Optional
from neisync.core.db_utils import table_exists

def export_schedule_report(db_path: Path, out_path: Optional[Path] = None) -> str:
    """일정 DB 전체를 DataFrame으로 읽어 엑셀로 저장 (DDL 미존재 시 안전하게 스킵)"""
    conn = sqlite3.connect(db_path)
    if not table_exists(conn, "schedule"):
        conn.close()
        return "[WARN] 'schedule' 테이블 없음 → schedule 리포트 스킵"
    df = pd.read_sql_query("SELECT * FROM schedule", conn)
    conn.close()
    if out_path is None:
        out_path = db_path.with_suffix('.xlsx')
    df.to_excel(out_path, index=False)
    return str(out_path)
