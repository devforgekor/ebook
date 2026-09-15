import azure.functions as func
import json
import traceback
from azure.data.tables import TableClient
from azure.storage.blob import ContainerClient, BlobClient
from datetime import datetime

from shared.utils.api_utils import (
    success,
    bad_request,
    server_error,
    get_env
)
from shared.utils.auth_utils import require_admin
from shared.utils.audit_utils import write_audit_log
from shared.utils.generation_utils import get_current_generation


ROSTER_TABLE = "Roster"
SHADOW_TABLE = "ShadowIndex"
OPTIMIZED_CONTAINER = "optimized-copies"


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        # ✅ 관리자 권한 확인 (super-admin만 허용)
        admin = require_admin(req)
        role = admin.get("role")
        if role != "super-admin":
            return bad_request("해당 기능은 super-admin만 사용할 수 있습니다.")

        body = req.get_json()
        person_id = body.get("person_id")

        if not person_id:
            return bad_request("person_id는 필수입니다.")

        conn = get_env("AzureWebJobsStorage")

        roster = TableClient.from_connection_string(conn, table_name=ROSTER_TABLE)
        shadow = TableClient.from_connection_string(conn, table_name=SHADOW_TABLE)
        optimized = ContainerClient.from_connection_string(conn, OPTIMIZED_CONTAINER)

        gen = str(get_current_generation())

        # -------------------------------------------------------
        # ✅ STEP1. Roster 조회
        # -------------------------------------------------------
        try:
            r = roster.get_entity(gen, person_id)
        except Exception:
            return bad_request("해당 person_id를 찾을 수 없습니다.")

        # record_keys (항상 최신 1개)
        record_keys = json.loads(r.get("record_keys", "[]"))

        # BEFORE 데이터 (audit 용)
        before = {
            "person_id": person_id,
            "record_keys": record_keys,
            "status": r.get("status"),
            "workstatus": r.get("workstatus"),
            "remark": r.get("remark", "")
        }

        # -------------------------------------------------------
        # ✅ STEP2. ShadowIndex 모든 row 삭제
        # -------------------------------------------------------
        shadow_rows = list(shadow.query_entities(f"PartitionKey eq '{person_id}'"))

        for row in shadow_rows:
            shadow.delete_entity(partition_key=row["PartitionKey"], row_key=row["RowKey"])

        # -------------------------------------------------------
        # ✅ STEP3. Blob 삭제 (PDF/WebP)
        # -------------------------------------------------------
        for record_key in record_keys:
            year = r.get("year") or str(datetime.now().year)
            webp_name = f"{year}_{person_id}_{record_key}.webp"
            pdf_name = f"{year}_{person_id}_{record_key}.pdf"

            try:
                blob = optimized.get_blob_client(webp_name)
                blob.delete_blob()
            except:
                pass

            try:
                blob = optimized.get_blob_client(pdf_name)
                blob.delete_blob()
            except:
                pass

        # -------------------------------------------------------
        # ✅ STEP4. Roster 삭제
        # -------------------------------------------------------
        roster.delete_entity(gen, person_id)

        # -------------------------------------------------------
        # ✅ STEP5. 감사 로그 기록
        # -------------------------------------------------------
        write_audit_log("delete_member", {
            "admin_id": admin.get("admin_id"),
            "person_id": person_id,
            "before": before
        })

        return success({
            "deleted_person_id": person_id,
            "shadowindex_rows_deleted": len(shadow_rows),
            "record_keys_removed": record_keys
        })

    except Exception as e:
        print("🔥 deleteMember Error")
        print(traceback.format_exc())
        return server_error(e)
    
    
    