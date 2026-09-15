from typing import AsyncIterator, Dict, Any
from pathlib import Path
from neisync.core.collector import BaseCollector
from neisync.core.db import connect
from neisync.core.config import settings

class NeisInfoCollector(BaseCollector):
    async def fetch(self) -> AsyncIterator[Dict[str, Any]]:
        url = 'https://open.neis.go.kr/hub/schoolInfo'
        region = self.params.get('region', 'B10')
        params = {
            'KEY': settings.neis_api_key,
            'Type': 'json',
            'pIndex': 1,
            'pSize': 100,
            'ATPT_OFCDC_SC_CODE': region,
        }
        resp = await self.http_client.request('GET', url, params=params)
        data = resp.json()
        svc = data.get('schoolInfo') or []
        rows = []
        if len(svc) > 1 and isinstance(svc[1], dict):
            rows = svc[1].get('row', [])
        for row in rows:
            yield row
    
    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'school_code': raw.get('SD_SCHUL_CODE'),
            'name': raw.get('SCHUL_NM'),
            'address': raw.get('ORG_RDNMA'),
            'type': raw.get('SCHUL_KND_SC_NM'),
            'region': raw.get('ATPT_OFCDC_SC_CODE'),
        }
    
    def upsert(self, item: Dict[str, Any]) -> None:
        with connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS schools (
                    school_code TEXT PRIMARY KEY,
                    name TEXT,
                    address TEXT,
                    type TEXT,
                    region TEXT
                )
            ''')
            conn.execute('''
                INSERT OR REPLACE INTO schools (school_code, name, address, type, region)
                VALUES (?, ?, ?, ?, ?)
            ''', (item['school_code'], item['name'], item['address'], item['type'], item['region']))
