from azure.data.tables import TableClient, UpdateMode
from datetime import datetime
import json

from shared.utils.api_utils import get_env
from shared.utils.generation_utils import get_current_generation
from shared.utils.audit_utils import write_audit_log


# ✅ Table 이름
ROSTER_TABLE = "Roster"
UNKNOWN_TABLE = "UnknownLog"
HISTORY_TABLE = "History"


# ✅ Roster Row 기본 스키마
def _default_roster_item(person_id, di, record_key, year):
    """
    di = {
        "name": "...",
        "yymmdd": "...",
        "org": "...",
        "position": "...",
        "title": "...",
        "hours": "...",
        ...
    }
    """
    return {
        "PartitionKey": str(get_current_generation()),
        "RowKey": person_id,
        "name": di["name"],
        "yymmdd": di["yymmdd"],
        "org": di.get("org", ""),
        "position": di.get("position", ""),
        "status": "completed",           # 신규 제출 → completed
        "workstatus": "working",         # 신규 제출 → working
        "record_keys": json.dumps([record_key]),
        "generation": str(get_current_generation()),
        "remark": "",
        "last_updated": datetime.utcnow().isoformat()
    }


# ✅ record_keys 최신 1건 유지
def _update_record_keys(entity, record_key):
    entity["record_keys"] = json.dumps([record_key])
    return entity


# ✅ 제출 이후 → Roster 업데이트 (가장 핵심 함수)
def update_roster_after_submission(person_id: str, di: dict, record_key: str, year: str):
    conn = get_env("AzureWebJobsStorage")
    roster = TableClient.from_connection_string(conn, table_name=ROSTER_TABLE)

    gen = str(get_current_generation())
    pk = gen
    rk = person_id

    try:
        # ✅ 기존 사용자 조회
        existing = roster.get_entity(pk, rk)

        # ✅ 상태 업데이트 → completed + latest record_key 유지
        existing["status"] = "completed"
        existing = _update_record_keys(existing, record_key)
        existing["last_updated"] = datetime.utcnow().isoformat()

        # org / position 변경사항 있을 경우 업데이트
        if di.get("org"):
            existing["org"] = di["org"]
        if di.get("position"):
            existing["position"] = di["position"]

        roster.update_entity(existing, mode=UpdateMode.REPLACE)

        write_audit_log("roster_update", {
            "person_id": person_id,
            "record_key": record_key,
            "update_type": "existing_completed"
        })

    except Exception:
        # ✅ 신규 사용자인 경우
        new_item = _default_roster_item(person_id, di, record_key, year)
        roster.upsert_entity(new_item)

        write_audit_log("roster_insert", {
            "person_id": person_id,
            "record_key": record_key,
            "update_type": "new_user_created"
        })


# ✅ UnknownLog → Roster 승격
def promote_unknown_to_roster(conn: str, record_key: str):
    unknown = TableClient.from_connection_string(conn, table_name=UNKNOWN_TABLE)
    roster = TableClient.from_connection_string(conn, table_name=ROSTER_TABLE)

    # UnknownLog에서 엔티티 조회
    rows = list(unknown.query_entities(f"RowKey eq '{record_key}'"))
    if not rows:
        return {"error": "not_found"}

    row = rows[0]
    person_id = row["person_id"]

    # ✅ Roster upsert
    roster.upsert_entity({
        "PartitionKey": row["PartitionKey"],
        "RowKey": person_id,
        "name": row.get("name", ""),
        "yymmdd": row.get("yymmdd", ""),
        "org": row.get("org", ""),
        "position": row.get("position", ""),
        "status": "incomplete",
        "workstatus": "working",
        "record_keys": json.dumps([]),
        "remark": "",
        "generation": row["PartitionKey"],
        "last_updated": datetime.utcnow().isoformat()
    })

    # ✅ UnknownLog 삭제
    unknown.delete_entity(row["PartitionKey"], record_key)

    write_audit_log("unknown_promoted", {
        "person_id": person_id,
        "record_key": record_key
    })

    return {"success": True, "person_id": person_id}


# ✅ UnknownLog 리스트 반환
def get_unknown_entries(conn: str):
    unknown = TableClient.from_connection_string(conn, table_name=UNKNOWN_TABLE)
    rows = list(unknown.list_entities())
    return rows


# ✅ 제출 기록(History) JSONL.append
def write_history(person_id: str, record_key: str, title: str, hours: str):
    """
    History 테이블 저장 구조:
    RowKey      = record_key
    PartitionKey = person_id
    """
    conn = get_env("AzureWebJobsStorage")
    table = TableClient.from_connection_string(conn, table_name=HISTORY_TABLE)

    item = {
        "PartitionKey": person_id,
        "RowKey": record_key,
        "submitted_at": datetime.utcnow().isoformat(),
        "title": title,
        "hours": hours
    }

    table.upsert_entity(item)

    write_audit_log("history_add", {
        "person_id": person_id,
        "record_key": record_key,
        "title": title
    })
    
    