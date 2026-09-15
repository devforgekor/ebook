import json
from datetime import datetime
from azure.data.tables import TableClient, UpdateMode
from shared.utils.api_utils import get_env


AUDIT_TABLE = "AuditLog"   # 테이블 기반 감사 로그
# archive_utils 는 archive/{gen}/audit.jsonl 를 별도로 생성함.


# ✅ 1) TableClient 로딩
def _get_audit_table():
    conn = get_env("AzureWebJobsStorage")
    return TableClient.from_connection_string(conn, table_name=AUDIT_TABLE)


# ✅ 2) audit 항목 생성용 공통 구조
def _build_audit_item(action: str, detail: dict):
    now = datetime.utcnow().isoformat()

    # RowKey = timestamp 기반 유일 문자열
    rk = now.replace(":", "_").replace(".", "_")

    return {
        "PartitionKey": "audit",
        "RowKey": rk,
        "timestamp": now,
        "action": action,
        "detail": json.dumps(detail, ensure_ascii=False)
    }


# ✅ 3) 감사 로그 기록
def write_audit_log(action: str, detail: dict):
    """
    action: "roster_update", "schedule_update", "archive_complete", ...
    detail: JSON 저장 가능한 dict
    """
    table = _get_audit_table()
    item = _build_audit_item(action, detail)
    table.upsert_entity(item, mode=UpdateMode.REPLACE)

    print(f"[Audit] {action}: {detail}")
    return True


# ✅ 4) 관리자 Elevation 로그 기록
def write_elevation_log(admin_id: str, permission: str):
    """
    추가 인증(Elevation) 이벤트 기록
    permission 예: "pdf", "settings"
    """
    return write_audit_log("admin_elevation", {
        "admin_id": admin_id,
        "permission": permission
    })


# ✅ 5) Roster 상태/비고 변경시 기록
def write_roster_change(person_id: str, before: dict, after: dict):
    """
    before, after = {"status": "...", "workstatus": "...", "remark": "..."}
    """
    return write_audit_log("roster_change", {
        "person_id": person_id,
        "before": before,
        "after": after
    })


# ✅ 6) ShadowIndex 재빌드 기록
def write_shadowindex_rebuild(total_rows: int):
    return write_audit_log("shadowindex_rebuild", {
        "rows": total_rows
    })


# ✅ 7) 아카이브 시작 기록
def write_archive_start(gen: int):
    return write_audit_log("archive_started", {
        "generation": gen
    })


# ✅ 8) 아카이브 완료 기록
def write_archive_complete(gen: int, webp_count: int, roster_count: int, integrity: bool):
    return write_audit_log("archive_complete", {
        "generation": gen,
        "webp_count": webp_count,
        "roster_count": roster_count,
        "integrity": integrity
    })


# ✅ 9) Unknown → Roster 승격 기록
def write_unknown_promoted(person_id: str, record_key: str):
    return write_audit_log("unknown_promoted", {
        "person_id": person_id,
        "record_key": record_key
    })


# ✅ 10) Schedule 변경 기록
def write_schedule_update(updated_fields: list, off_days: int):
    return write_audit_log("schedule_update", {
        "fields": updated_fields,
        "off_days": off_days
    })


# ✅ 11) PDF 처리 오류(processPdf) 기록
def write_processpdf_error(record_key: str, err: str):
    return write_audit_log("processpdf_error", {
        "record_key": record_key,
        "error": err
    })


# ✅ 12) Audit 조회 (관리자 API에서 사용)
def query_audit_log(conn: str, generation: str = None):
    """
    auditSearch API에서 호출됨.
    generation 필터는 stub로 구현 가능.
    """
    table = TableClient.from_connection_string(conn, table_name=AUDIT_TABLE)

    rows = list(table.query_entities("PartitionKey eq 'audit'"))

    result = []
    for r in rows:
        result.append({
            "timestamp": r["timestamp"],
            "action": r["action"],
            "detail": json.loads(r["detail"])
        })

    return sorted(result, key=lambda x: x["timestamp"], reverse=True)

