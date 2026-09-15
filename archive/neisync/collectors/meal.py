import re
from typing import AsyncIterator, Dict, Any
from pathlib import Path
from neisync.core.collector import BaseCollector
from neisync.core.db import connect
from neisync.core.config import settings
from neisync.core.db_schema import ensure_schema

def normalize_html_breaks(text: str) -> str:
    """HTML <br> 태그를 개행 문자로 변환"""
    return re.sub(r'(<br\s*/?>|&lt;br\s*/?&gt;)', '\n', text, flags=re.IGNORECASE)

class MealCollector(BaseCollector):
    async def run(self):
        # DDL/파일 보장: fetch=0건이어도 DB 파일 생성
        from neisync.core.db_schema import ensure_schema
        ensure_schema(self.db_path)
        print(f"[COLLECTOR] ensure_schema called for: {self.db_path}")
        print(f"[COLLECTOR] db_path.exists() after ensure_schema: {self.db_path.exists()}")
        await super().run()
    async def fetch(self) -> AsyncIterator[Dict[str, Any]]:
        url = 'https://open.neis.go.kr/hub/mealServiceDietInfo'
        region = self.params.get('region', 'B10')
        date = self.params.get('date')
        params = {
            'KEY': settings.neis_api_key,
            'Type': 'json',
            'pIndex': 1,
            'pSize': 100,
            'ATPT_OFCDC_SC_CODE': region,
        }
        if date:
            params['MLSV_YMD'] = date
        
        resp = await self.http_client.request('GET', url, params=params)
        data = resp.json()
        svc = data.get('mealServiceDietInfo') or []
        rows = []
        if len(svc) > 1 and isinstance(svc[1], dict):
            rows = svc[1].get('row', [])
        for row in rows:
            yield row
    
    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        menu = raw.get('DDISH_NM') or ''
        menu = normalize_html_breaks(menu)
        return {
            'school_code': raw.get('SD_SCHUL_CODE'),
            'date': raw.get('MLSV_YMD'),
            'type': (raw.get('MMEAL_SC_NM') or '').upper(),
            'menu': menu,
            'calories': raw.get('CAL_INFO'),
        }
    
    def upsert(self, item: Dict[str, Any]) -> None:
        # DDL 보장: 데이터가 0건이어도 DB 파일 생성
        from neisync.core.db_schema import ensure_schema
        ensure_schema(self.db_path)
        with connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS meal (
                    school_code TEXT,
                    date TEXT,
                    type TEXT,
                    menu TEXT,
                    calories TEXT,
                    PRIMARY KEY (school_code, date, type)
                )
            ''')
            conn.execute('''
                INSERT OR REPLACE INTO meal (school_code, date, type, menu, calories)
                VALUES (?, ?, ?, ?, ?)
            ''', (item['school_code'], item['date'], item['type'], item['menu'], item['calories']))
