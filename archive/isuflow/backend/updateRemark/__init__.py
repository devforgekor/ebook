import azure.functions as func
import json
import traceback
from datetime import datetime
from azure.data.tables import TableClient, UpdateMode

from shared.utils.api_utils import (
    success,
    bad_request,
    server_error,
    get_env
)
from shared.utils.auth_utils import require_admin
from shared.utils.audit_utils import write_roster_change
from shared.utils.generation_utils import get_current_generation


ROSTER_TABLE = "Roster"


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        # ✅ 관리자 권한 검사
        admin = require_admin(req)

        body = req.get_json()

        person_id = body.get("person_id")
        new_remark = body.get("remark")

        if not person_id:
            return bad_request("person_id는 필수입니다.")
        if new_remark is None:
            return bad_request("remark는 빈 문자열이라도 반드시 포함해야 합니다.")

        conn = get_env("AzureWebJobsStorage")
        table = TableClient.from_connection_string(conn, table_name=ROSTER_TABLE)

        gen = str(get_current_generation())

        # ✅ 기존 Roster record 조회
        try:
            entity = table.get_entity(partition_key=gen, row_key=person_id)
        except Exception:
            return bad_request("해당 person_id를 찾을 수 없습니다.")

        before = {
            "status": entity.get("status"),
            "workstatus": entity.get("workstatus"),
            "remark": entity.get("remark", "")
        }

        # ✅ remark 변경
        entity["remark"] = new_remark
        entity["last_updated"] = datetime.utcnow().isoformat()

        # ✅ 저장
        table.update_entity(entity, mode=UpdateMode.REPLACE)

        after = {
            "status": entity["status"],
            "workstatus": entity["workstatus"],
            "remark": entity.get("remark", "")
        }

        # ✅ Audit 로그 기록
        write_roster_change(
            person_id=person_id,
            before=before,
            after=after
        )

        return success({
            "person_id": person_id,
            "before": before,
            "after": after
        })

    except ValueError as e:
        return bad_request(str(e))
    except Exception as e:
        print("🔥 updateRemark Error")
        print(traceback.format_exc())
        return server_error(e)
    
    