from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, Any, Optional
from pathlib import Path
from neisync.core.logging import get_logger, get_file_logger
from neisync.core.http import get_http_client
from neisync.core.config import settings
from neisync.core.notify import send_alert   # Phase 3에서 구현

class BaseCollector(ABC):
    def __init__(self, name: str, db_path: Path, shard: str = 'none', **params):
        self.name = name
        self.db_path = db_path
        self.shard = shard
        self.params = params
        self.logger = get_logger(f'collector.{name}', shard=shard, **params)
        self.file_log = get_file_logger(f'{name}-{shard}')
        self.http_client = None
    
    @abstractmethod
    async def fetch(self) -> AsyncIterator[Dict[str, Any]]:
        """API에서 데이터를 한 건씩 yield"""
        pass
    
    @abstractmethod
    def normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """API 응답을 DB에 저장할 형태로 변환"""
        pass
    
    @abstractmethod
    def upsert(self, item: Dict[str, Any]) -> None:
        """DB에 저장 (INSERT OR REPLACE)"""
        pass
    
    async def fetch_with_retry(self):
        try:
            async for item in self.fetch():
                yield item
        except Exception as e:
            self.logger.error('Fetch failed', exc_info=True)
            self.file_log.write({'event': 'fetch_failed', 'error': str(e)})
            await send_alert(f'{self.name} fetch failed: {e}', level='error')
            raise
    
    async def run(self):
        # DDL/파일 보장: fetch=0건이어도 DB 파일 생성
        from neisync.core.db_schema import ensure_schema
        ensure_schema(self.db_path)
        self.http_client = await get_http_client(self.name)
        success = 0
        failed = 0
        self.file_log.write({'event': 'start', 'shard': self.shard, 'params': self.params})
        async for raw in self.fetch_with_retry():
            try:
                item = self.normalize(raw)
                self.upsert(item)
                success += 1
            except Exception as e:
                self.logger.error('Item processing failed', exc_info=True)
                self.file_log.write({'event': 'item_failed', 'error': str(e)})
                failed += 1
        self.logger.info(f'Completed: success={success}, failed={failed}')
        self.file_log.write({'event': 'complete', 'success': success, 'failed': failed})
        if failed > 0:
            await send_alert(f'{self.name} completed with {failed} failures', level='warning')
        await self.http_client.close()
