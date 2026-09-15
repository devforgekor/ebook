from typing import AsyncIterator, Dict, Any
from pathlib import Path
from neisync.core.collector import BaseCollector
from neisync.core.db import connect
from neisync.core.config import settings
from neisync.core.db_schema import ensure_schema

class TimetableCollector(BaseCollector):
    async def run(self):
        ensure_schema(str(self.db_path))
        await super().run()
    async def fetch(self) -> AsyncIterator[Dict[str, Any]]:
        url = 'https://open.neis.go.kr/hub/hisTimetable'
        region = self.params.get('region', 'B10')
        ay = self.params.get('ay')
        semester = self.params.get('semester', 1)
        params = {
            'KEY': settings.neis_api_key,
            'Type': 'json',
            'pIndex': 1,
            'pSize': 100,
            'ATPT_OFCDC_SC_CODE': region,
            'SEM': semester,
        }
        if ay:
            params['AY'] = ay
        resp = await self.http_client.request('GET', url, params=params)
        data = resp.json()
        svc = data.get('hisTimetable') or []
        rows = []
        if len(svc) > 1 and isinstance(svc[1], dict):
            rows = svc[1].get('row', [])
        for row in rows:
            yield row
    
    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'school_code': raw.get('SD_SCHUL_CODE'),
            'date': raw.get('ALL_TI_YMD'),
            'grade': raw.get('GRADE'),
            'class_nm': raw.get('CLASS_NM'),
            'period': raw.get('PERIO'),
            'subject': raw.get('ITRT_CNTNT'),
        }
    
    def upsert(self, item: Dict[str, Any]) -> None:
        with connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS timetable (
                    school_code TEXT,
                    date TEXT,
                    grade TEXT,
                    class_nm TEXT,
                    period TEXT,
                    subject TEXT,
                    PRIMARY KEY (school_code, date, grade, class_nm, period)
                )
            ''')
            conn.execute('''
                INSERT OR REPLACE INTO timetable (school_code, date, grade, class_nm, period, subject)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (item['school_code'], item['date'], item['grade'], item['class_nm'], item['period'], item['subject']))
