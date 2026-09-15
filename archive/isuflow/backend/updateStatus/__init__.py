import azure.functions as func
import json
import traceback
from azure.data.tables import TableClient, UpdateMode
from datetime import datetime

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


# ✅ Smart Remark 규칙 (문서 5.6)
def smart_remark(before_status, before_work, after_status, after_work):
    """
    자동 Remark 삽입 규칙:
      working → retired     → [SYSTEM] 퇴직
      working → leave       → [SYSTEM] 휴직
      working → excluded    → [SYSTEM] 제외
      retired → working     → [SYSTEM] 재임용
      leave → working       → [SYSTEM] 복직
    """
    if before_work == "working" and after_work == "retired":
        return "[SYSTEM] 퇴직"
    if before_work == "working" and after_work == "leave":
        return "[SYSTEM] 휴직"
    if before_work == "working" and after_status == "excluded":
        return "[SYSTEM] 제외"
    if before_work == "retired" and after_work == "working":
        return "[SYSTEM] 재임용"
    if before_work == "leave" and after_work == "working":
        return "[SYSTEM] 복직"

    return None


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        # ✅ 관리자 권한 확인
        admin = require_admin(req)

        body = req.get_json()

        person_id = body.get("person_id")
        new_status = body.get("status")          # completed / incomplete / excluded
        new_work = body.get("workstatus")        # working / retired / leave
        remark = body.get("remark")              # optional

        if not person_id or not new_status or not new_work:
            return bad_request("person_id, status, workstatus는 필수입니다.")

        conn = get_env("AzureWebJobsStorage")
        table = TableClient.from_connection_string(conn, table_name=ROSTER_TABLE)

        gen = str(get_current_generation())

        # ✅ 기존 사용자 불러오기
        try:
            entity = table.get_entity(partition_key=gen, row_key=person_id)
        except Exception:
            return bad_request("해당 person_id를 찾을 수 없습니다.")

        before = {
            "status": entity.get("status"),
            "workstatus": entity.get("workstatus"),
            "remark": entity.get("remark", "")
        }

        # ✅ Smart Remark 생성 여부 판단
        sys_remark = smart_remark(
            before_status=before["status"],
            before_work=before["workstatus"],
            after_status=new_status,
            after_work=new_work
        )

        # ✅ 상태 변경
        entity["status"] = new_status
        entity["workstatus"] = new_work
        entity["last_updated"] = datetime.utcnow().isoformat()

        # ✅ remark 우선순위:
        # 1) 사용자가 remark 제공 → 그대로 사용 (Smart Remark 무시)
        # 2) 사용자 remark 없음 + Smart Remark 존재 → 자동 삽입
        # 3) 둘 다 없음 → 기존 remark 유지
        if remark:
            entity["remark"] = remark
        elif sys_remark:
            entity["remark"] = sys_remark

        # ✅ 저장
        table.update_entity(entity, mode=UpdateMode.REPLACE)

        after = {
            "status": entity["status"],
            "workstatus": entity["workstatus"],
            "remark": entity.get("remark", "")
        }

        # ✅ audit 기록
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
        print("🔥 updateStatus Error")
        print(traceback.format_exc())
        return server_error(e)
    
    