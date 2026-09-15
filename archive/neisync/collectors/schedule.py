from typing import AsyncIterator, Dict, Any
from pathlib import Path
from neisync.core.collector import BaseCollector
from neisync.core.db import connect
from neisync.core.config import settings
from neisync.core.db_schema import ensure_schema

class ScheduleCollector(BaseCollector):
    async def run(self):
        ensure_schema(str(self.db_path))
        await super().run()
    async def fetch(self) -> AsyncIterator[Dict[str, Any]]:
        url = 'https://open.neis.go.kr/hub/SchoolSchedule'
        region = self.params.get('region', 'B10')
        year = self.params.get('year')
        params = {
            'KEY': settings.neis_api_key,
            'Type': 'json',
            'pIndex': 1,
            'pSize': 100,
            'ATPT_OFCDC_SC_CODE': region,
        }
        if year:
            params['AY'] = year
        resp = await self.http_client.request('GET', url, params=params)
        data = resp.json()
        svc = data.get('SchoolSchedule') or []
        rows = []
        if len(svc) > 1 and isinstance(svc[1], dict):
            rows = svc[1].get('row', [])
        for row in rows:
            yield row
    
    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'school_code': raw.get('SD_SCHUL_CODE'),
            'date': raw.get('AA_YMD'),
            'event': raw.get('EVENT_NM'),
            'event_type': raw.get('EVENT_TYPE'),
        }
    
    def upsert(self, item: Dict[str, Any]) -> None:
        with connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS schedule (
                    school_code TEXT,
                    date TEXT,
                    event TEXT,
                    event_type TEXT,
                    PRIMARY KEY (school_code, date, event)
                )
            ''')
            conn.execute('''
                INSERT OR REPLACE INTO schedule (school_code, date, event, event_type)
                VALUES (?, ?, ?, ?)
            ''', (item['school_code'], item['date'], item['event'], item['event_type']))
