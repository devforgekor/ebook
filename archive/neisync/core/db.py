import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

@contextmanager
def connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute('PRAGMA journal_mode=WAL;')
    conn.execute('PRAGMA busy_timeout=30000;')
    conn.execute('PRAGMA foreign_keys=ON;')
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
