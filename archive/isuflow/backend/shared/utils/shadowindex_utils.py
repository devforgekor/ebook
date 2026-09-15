from azure.data.tables import TableClient, UpdateMode
from shared.utils.api_utils import get_env
from shared.utils.id_utils import build_operational_filename
from datetime import datetime
import json


SHADOW_TABLE = "ShadowIndex"


# ✅ 1) 공통 TableClient 생성
def _get_shadow_table():
    conn = get_env("AzureWebJobsStorage")
    return TableClient.from_connection_string(conn, table_name=SHADOW_TABLE)


# ✅ 2) person_id로 전체 행 조회 (checkList에서 사용)
def query_shadowindex_by_person(person_id: str):
    table = _get_shadow_table()
    return list(table.query_entities(f"PartitionKey eq '{person_id}'"))


# ✅ 3) record_key로 단일 행 조회
def get_shadow_row(record_key: str):
    table = _get_shadow_table()
    rows = list(table.query_entities(f"RowKey eq '{record_key}'"))
    return rows[0] if rows else None


# ✅ 4) record_key → WebP blob path 생성
def get_blob_path_from_record(record_key: str) -> str:
    row = get_shadow_row(record_key)
    if not row:
        return None
    year = row["year"]
    person_id = row["person_id"]
    return build_operational_filename(year, person_id, record_key, "webp")


# ✅ 5) record_key → PDF blob path 생성
def get_pdf_blob_path(record_key: str) -> str:
    row = get_shadow_row(record_key)
    if not row:
        return None
    year = row["year"]
    person_id = row["person_id"]
    return build_operational_filename(year, person_id, record_key, "pdf")


# ✅ 6) ShadowIndex 최신 1건 유지 정책
def remove_old_shadowindex_rows(person_id: str):
    """
    processPdf에서 새로운 record_key 생성 시,
    해당 person_id의 기존 record_key 행을 모두 삭제.
    (항상 최신 1건 유지)
    """
    table = _get_shadow_table()
    rows = query_shadowindex_by_person(person_id)

    for r in rows:
        table.delete_entity(r["PartitionKey"], r["RowKey"])


# ✅ 7) ShadowIndex 새 row 입력
def insert_shadowindex_row(item: dict):
    """
    item 예:
    {
        "PartitionKey": person_id,
        "RowKey": record_key,
        "year": "2026",
        "title_key": "...",
        "hours": "...",
        "org_key": "...",
        "person_id": person_id,
        "blob_path": "...",
        "cert_number": record_key
    }
    """
    table = _get_shadow_table()
    table.upsert_entity(item)


# ✅ 8) 관리자 페이지용: 전체 submissions 조회
def list_all_submissions(conn=None):
    if not conn:
        conn = get_env("AzureWebJobsStorage")

    table = TableClient.from_connection_string(conn, table_name=SHADOW_TABLE)
    rows = list(table.list_entities())
    return rows


# ✅ 9) 전체 재빌드 (admin → rebuildShadowIndex)
def rebuild_shadowindex_full(conn: str):
    """
    실제 운영 정책:
    - Blob Tags ↔ ShadowIndex diff 기반 다시 생성
    - 여기서는 stub로 전체 조회 후 개수 반환
    """
    table = TableClient.from_connection_string(conn, table_name=SHADOW_TABLE)
    rows = list(table.list_entities())
    return len(rows)


# ✅ 10) Blob Tags ↔ ShadowIndex 동기화 (midnight_fix)
def sync_tags_and_shadowindex(conn: str):
    """
    월 1회 실행되는 diff 검사와 동일한 구조.
    실제 구현:
      - Blob Tags 목록 읽기
      - ShadowIndex 목록 읽기
      - mismatch 존재 시 재생성
    여기서는 stub 형태로 구조만 제공.
    """

    shadow = TableClient.from_connection_string(conn, table_name=SHADOW_TABLE)
    shadow_rows = list(shadow.list_entities())

    print(f"[ShadowIndex Sync] 현재 ShadowIndex 개수 = {len(shadow_rows)}")
    return True

