import sqlite3

DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS meal (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        type TEXT NOT NULL,
        menu TEXT NOT NULL,
        source TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_meal_unique
    ON meal(date, type, menu);
    """,
    """
    CREATE TABLE IF NOT EXISTS schedule (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        title TEXT NOT NULL,
        location TEXT,
        source TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_schedule_date
    ON schedule(date);
    """,
    """
    CREATE TABLE IF NOT EXISTS timetable (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        period INTEGER NOT NULL,
        subject TEXT NOT NULL,
        teacher TEXT,
        room TEXT,
        source TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_timetable_date_period
    ON timetable(date, period);
    """
]

def ensure_schema(db_path: str) -> None:
    """
    DB 파일에 필요한 테이블이 없으면 자동 생성합니다.
    - 운영/테스트 환경 모두 지원
    - idempotent(여러 번 호출해도 안전)
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    # 급식 테이블 예시
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS meal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_code TEXT,
            date TEXT,
            menu TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()
